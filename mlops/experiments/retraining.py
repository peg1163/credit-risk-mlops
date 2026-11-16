"""Retraining and drift simulation over the historical cohorts.

Two questions, answered with the data the project already has:

1. Retraining: at each simulated date T the champion is compared with a
   challenger retrained on every label known at T (``label_maturity_date <= T``).
   Both score the next ``horizon_months`` of mature cohorts. A paired bootstrap
   gives the confidence interval of each difference, because a window holds
   only 30 to 40 defaults.
2. Drift: every observation month is compared with the champion's training
   profile using the same buckets and PSI as the daily quality Lambda
   (``mlops/monitoring/quality.py``). Drift needs no labels, so it covers the
   months whose labels have not matured.

Runs on a laptop or as a SageMaker training job (``mlops/sagemaker/train.py``)
and logs to MLflow: the local store by default, or the SageMaker MLflow App
when ``MLFLOW_TRACKING_URI`` holds its ARN. See ADR-0010.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from credit_risk.common import DATA, config, write_json
from credit_risk.dataset import FEATURES
from credit_risk.modeling import bundle, fit, ks, metrics, split, tracking_uri
from mlops.monitoring.build_reference_profile import profile_from
from mlops.monitoring.quality import day_quality, window_drift

EXPERIMENT = "credit-risk-retraining-simulation"
DEFAULT_RETRAIN_DATES = ("1997-01-31", "1997-07-31", "1998-01-31")
PSI_INVESTIGATE, PSI_MATERIAL = 0.10, 0.25  # docs/MONITORING_AND_RETRAINING.md
# Features that move with calendar time by construction: the portfolio ages,
# so their PSI against an older training split grows even without any change
# in the customers. They are reported, but kept out of the drift level.
STRUCTURAL_FEATURES = {"loan_age_months"}
PAIRED_METRICS = {
    "roc_auc": roc_auc_score,
    "pr_auc": average_precision_score,
    "brier": brier_score_loss,
    "ks": ks,
}


def month_end(value: str | pd.Timestamp, months: int = 0) -> pd.Timestamp:
    """End of the month of ``value``, shifted by ``months`` month ends."""
    end = pd.Timestamp(value) + pd.offsets.MonthEnd(0)
    return end + pd.offsets.MonthEnd(months) if months else end


def challenger_parts(df: pd.DataFrame, as_of: pd.Timestamp, validation_months: int) -> dict[str, pd.DataFrame]:
    """Rows whose label is known at ``as_of``; the last months pick the threshold."""
    known = df[df.label_maturity_date.le(as_of)]
    validation_start = month_end(known.observation_date.max(), -validation_months) + pd.Timedelta(days=1)
    return {
        "train": known[known.observation_date.lt(validation_start)],
        "validation": known[known.observation_date.ge(validation_start)],
        "all": known,
    }


def fit_challenger(df: pd.DataFrame, as_of: pd.Timestamp, validation_months: int, refit: bool, C: float, seed: int):
    """Threshold from the validation months; with ``refit`` the final model also learns from them."""
    parts = challenger_parts(df, as_of, validation_months)
    model, threshold = fit(parts, C, seed)
    if refit:
        model, _ = fit({"train": parts["all"], "validation": parts["validation"]}, C, seed)
    info = {
        "label_cutoff": str(parts["all"].observation_date.max().date()),
        "train_rows": len(parts["all"] if refit else parts["train"]),
        "train_events": int((parts["all"] if refit else parts["train"]).target.sum()),
        "validation_start": str(parts["validation"].observation_date.min().date()),
        "validation_events": int(parts["validation"].target.sum()),
        "threshold": threshold,
    }
    return model, threshold, info


def paired_bootstrap(y: np.ndarray, champion: np.ndarray, challenger: np.ndarray, samples: int, seed: int) -> dict:
    """Challenger minus champion on the same resampled rows."""
    rng = np.random.default_rng(seed)
    deltas = {name: [] for name in PAIRED_METRICS}
    for _ in range(samples):
        rows = rng.integers(0, len(y), len(y))
        if y[rows].min() == y[rows].max():
            continue
        for name, fn in PAIRED_METRICS.items():
            deltas[name].append(fn(y[rows], challenger[rows]) - fn(y[rows], champion[rows]))
    result = {}
    for name, values in deltas.items():
        values = np.asarray(values)
        result[name] = {
            "delta": float(PAIRED_METRICS[name](y, challenger) - PAIRED_METRICS[name](y, champion)),
            "ci95": [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))],
            "p_improves": float(np.mean(values < 0 if name == "brier" else values > 0)),
            "samples": len(values),
        }
    return result


def verdict(comparison: dict) -> str:
    low, high = comparison["roc_auc"]["ci95"]
    if low > 0:
        return "challenger_better"
    if high < 0:
        return "challenger_worse"
    return "no_significant_difference"


def retraining_backtest(df: pd.DataFrame, champion, champion_threshold: float, dates, horizon_months: int,
                        validation_months: int, refit: bool, C: float, seed: int, samples: int) -> dict:
    windows, pooled = [], []
    for value in dates:
        as_of = month_end(value)
        end = month_end(as_of, horizon_months)
        cohort = df[df.observation_date.gt(as_of) & df.observation_date.le(end) & df.is_mature]
        if cohort.empty or cohort.target.nunique() < 2:
            windows.append({"as_of": str(as_of.date()), "skipped": "no mature cohort with both classes"})
            continue
        challenger, threshold, info = fit_challenger(df, as_of, validation_months, refit, C, seed)
        y = cohort.target.to_numpy()
        p_champion = champion.predict_proba(cohort[FEATURES])[:, 1]
        p_challenger = challenger.predict_proba(cohort[FEATURES])[:, 1]
        comparison = paired_bootstrap(y, p_champion, p_challenger, samples, seed)
        windows.append({
            "as_of": str(as_of.date()),
            "evaluation": [str(cohort.observation_date.min().date()), str(cohort.observation_date.max().date())],
            "rows": len(cohort),
            "events": int(y.sum()),
            "challenger": info,
            "champion_metrics": metrics(y, p_champion, champion_threshold),
            "challenger_metrics": metrics(y, p_challenger, threshold),
            "paired": comparison,
            "verdict": verdict(comparison),
        })
        pooled.append(pd.DataFrame({"y": y, "champion": p_champion, "challenger": p_challenger}))
    policy = None
    if pooled:
        frame = pd.concat(pooled)
        comparison = paired_bootstrap(frame.y.to_numpy(), frame.champion.to_numpy(), frame.challenger.to_numpy(), samples, seed)
        policy = {"rows": len(frame), "events": int(frame.y.sum()), "paired": comparison, "verdict": verdict(comparison)}
    return {"windows": windows, "policy_retrain_every_window_vs_static": policy}


def capture_like(cohort: pd.DataFrame, scores: np.ndarray, threshold: float) -> list[dict]:
    """Rows shaped like the endpoint capture, so the Lambda's functions apply unchanged."""
    frame = cohort[FEATURES].astype(object).where(cohort[FEATURES].notna(), None)
    return [
        {"request_id": str(index), "status": "accepted", "input": record,
         "output": {"score": float(score), "decision": int(score >= threshold)}}
        for index, (record, score) in enumerate(zip(frame.to_dict("records"), scores))
    ]


def psi_noise_floor(spec: dict, rows: int, reference_rows: int) -> float:
    """Expected PSI between two samples of the same population: (buckets - 1) * (1/n + 1/N).

    A small month or a feature with many buckets (district_id) shows PSI near
    this value with no real change, so a PSI is only meaningful well above it.
    """
    return (len(spec["proportions"]) - 1) * (1 / rows + 1 / reference_rows)


def monthly_drift(df: pd.DataFrame, champion, threshold: float, profile: dict, since: str) -> list[dict]:
    months = []
    for month, cohort in df[df.observation_date.ge(pd.Timestamp(since))].groupby("observation_date"):
        lines = capture_like(cohort, champion.predict_proba(cohort[FEATURES])[:, 1], threshold)
        drift, quality = window_drift(lines, profile), day_quality(lines, profile)
        behavioural = {k: v for k, v in drift["psi"].items() if k != "score" and k not in STRUCTURAL_FEATURES}
        worst = max(behavioural, key=behavioural.get) if behavioural else None
        psi_max = behavioural[worst] if worst else None
        months.append({
            "month": str(month.date())[:7],
            "rows": len(cohort),
            "labels_mature": bool(cohort.is_mature.all()),
            "psi_max_all": drift["psi_max"],
            "psi_max_all_feature": drift["psi_max_feature"],
            "psi_max": psi_max,
            "psi_max_feature": worst,
            "psi_max_noise_floor": psi_noise_floor(profile["features"][worst], len(cohort), profile["rows"]) if worst else None,
            "score_psi": drift.get("score_psi"),
            "psi": drift["psi"],
            "score_mean": quality["score_mean"],
            "decision_rate": quality["decision_rate"],
            "null_rate_delta_max_pp": quality["null_rate_delta_max_pp"],
            "level": None if psi_max is None else "material" if psi_max >= PSI_MATERIAL else "investigate" if psi_max >= PSI_INVESTIGATE else "stable",
        })
    return months


def cross_check(backtest: dict, drift: list[dict], horizon_months: int) -> list[dict]:
    """Did the drift seen before each retraining date predict that retraining would help?"""
    rows = []
    for window in backtest["windows"]:
        if "skipped" in window:
            continue
        as_of = month_end(window["as_of"])
        before = [m for m in drift if month_end(m["month"]) <= as_of and month_end(m["month"]) > month_end(as_of, -horizon_months)]
        worst = max(before, key=lambda m: m["psi_max"] or 0, default=None)
        rows.append({
            "as_of": window["as_of"],
            "psi_max_previous_months": worst["psi_max"] if worst else None,
            "psi_max_feature": worst["psi_max_feature"] if worst else None,
            "drift_flag": worst["level"] if worst else None,
            "retraining_verdict": window["verdict"],
        })
    return rows


def run(dataset: Path, dates=DEFAULT_RETRAIN_DATES, horizon_months: int = 6, validation_months: int = 12,
        refit: bool = True, C: float = 0.5, seed: int | None = None, samples: int = 1000) -> dict:
    seed = config()["random_seed"] if seed is None else seed
    df = pd.read_parquet(dataset)
    parts = split(df)
    champion, champion_threshold = fit(parts, C, seed)
    profile = profile_from(parts["train"], bundle(champion, champion_threshold))
    backtest = retraining_backtest(df, champion, champion_threshold, dates, horizon_months, validation_months, refit, C, seed, samples)
    drift = monthly_drift(df, champion, champion_threshold, profile, config()["splits"]["validation_start"])
    return {
        "dataset_id": config()["dataset_id"],
        "parameters": {"retrain_dates": list(dates), "horizon_months": horizon_months, "validation_months": validation_months,
                       "refit_on_validation": refit, "C": C, "seed": seed, "bootstrap_samples": samples},
        "champion": {"train_end": config()["splits"]["train_end"], "threshold": champion_threshold},
        "retraining": backtest,
        "drift": drift,
        "drift_vs_retraining": cross_check(backtest, drift, horizon_months),
    }


def summary(report: dict) -> str:
    lines = ["| Retrain date | Evaluated cohorts | Events | AUC champion | AUC challenger | Δ AUC (95% CI) | Δ Brier | Verdict |",
             "|---|---|---|---|---|---|---|---|"]
    for w in report["retraining"]["windows"]:
        if "skipped" in w:
            lines.append(f"| {w['as_of']} | — | — | — | — | — | — | {w['skipped']} |")
            continue
        auc = w["paired"]["roc_auc"]
        lines.append(f"| {w['as_of']} | {w['evaluation'][0][:7]}…{w['evaluation'][1][:7]} | {w['events']} | "
                     f"{w['champion_metrics']['roc_auc']:.3f} | {w['challenger_metrics']['roc_auc']:.3f} | "
                     f"{auc['delta']:+.3f} [{auc['ci95'][0]:+.3f}, {auc['ci95'][1]:+.3f}] | "
                     f"{w['paired']['brier']['delta']:+.4f} | {w['verdict']} |")
    policy = report["retraining"]["policy_retrain_every_window_vs_static"]
    if policy:
        auc = policy["paired"]["roc_auc"]
        lines.append(f"\nPolicy (all windows pooled, {policy['events']} events): Δ AUC {auc['delta']:+.3f} "
                     f"[{auc['ci95'][0]:+.3f}, {auc['ci95'][1]:+.3f}] → {policy['verdict']}")
    lines += ["", f"PSI max excludes {', '.join(sorted(STRUCTURAL_FEATURES))}; it is shown apart.", "",
              "| Month | Rows | Labels mature | PSI max | Feature | Noise floor | PSI loan_age_months | Score PSI | Level |", "|---|---|---|---|---|---|---|---|---|"]
    for m in report["drift"]:
        psi_max = "—" if m["psi_max"] is None else f"{m['psi_max']:.3f}"
        score = "—" if m["score_psi"] is None else f"{m['score_psi']:.3f}"
        age = m["psi"].get("loan_age_months")
        age = "—" if age is None else f"{age:.3f}"
        lines.append(f"| {m['month']} | {m['rows']} | {'yes' if m['labels_mature'] else 'no'} | {psi_max} | {m['psi_max_feature'] or '—'} | {m['psi_max_noise_floor'] or 0:.3f} | {age} | {score} | {m['level'] or '—'} |")
    return "\n".join(lines) + "\n"


def log_to_mlflow(report: dict, output_dir: Path, run_name: str, tags: dict | None = None) -> str | None:
    try:
        import mlflow
    except ImportError:
        print("WARNING: MLflow unavailable; report written, run not registered")
        return None
    mlflow.set_tracking_uri(tracking_uri())
    mlflow.set_experiment(EXPERIMENT)
    with mlflow.start_run(run_name=run_name, tags=tags or {}) as parent:
        params = {k: (",".join(v) if isinstance(v, list) else v) for k, v in report["parameters"].items()}
        mlflow.log_params({**params, "dataset_id": report["dataset_id"], "champion_train_end": report["champion"]["train_end"]})
        for window in report["retraining"]["windows"]:
            if "skipped" in window:
                continue
            with mlflow.start_run(run_name=f"retrain-{window['as_of']}", nested=True):
                mlflow.log_params({"as_of": window["as_of"], **{f"challenger_{k}": v for k, v in window["challenger"].items()}})
                mlflow.set_tag("verdict", window["verdict"])
                for role in ("champion", "challenger"):
                    for key in ("roc_auc", "pr_auc", "brier", "ks", "recall", "precision"):
                        mlflow.log_metric(f"{role}_{key}", window[f"{role}_metrics"][key])
                for key, value in window["paired"].items():
                    mlflow.log_metrics({f"delta_{key}": value["delta"], f"delta_{key}_ci_low": value["ci95"][0],
                                        f"delta_{key}_ci_high": value["ci95"][1]})
        policy = report["retraining"]["policy_retrain_every_window_vs_static"]
        if policy:
            mlflow.log_metrics({"policy_delta_roc_auc": policy["paired"]["roc_auc"]["delta"],
                                "policy_delta_roc_auc_ci_low": policy["paired"]["roc_auc"]["ci95"][0],
                                "policy_delta_roc_auc_ci_high": policy["paired"]["roc_auc"]["ci95"][1]})
            mlflow.set_tag("policy_verdict", policy["verdict"])
        # One step per month, so the MLflow UI draws drift as a time series.
        for step, month in enumerate(report["drift"]):
            values = {"drift_psi_max": month["psi_max"], "drift_score_psi": month["score_psi"],
                      "drift_score_mean": month["score_mean"], "drift_decision_rate": month["decision_rate"],
                      **{f"psi_{name}": value for name, value in month["psi"].items()}}
            mlflow.log_metrics({k: v for k, v in values.items() if v is not None}, step=step)
        mlflow.log_artifacts(str(output_dir))
        return parent.info.run_id


def main(argv=None, tags: dict | None = None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", type=Path, default=DATA / "modeling_dataset.parquet")
    parser.add_argument("--output-dir", type=Path, default=Path("dist/experiments/retraining"))
    parser.add_argument("--retrain-dates", default=",".join(DEFAULT_RETRAIN_DATES))
    parser.add_argument("--horizon-months", type=int, default=6)
    parser.add_argument("--validation-months", type=int, default=12)
    parser.add_argument("--no-refit", action="store_true", help="keep the model fitted without the validation months")
    parser.add_argument("--C", type=float, default=0.5)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--run-name", default="retrain-every-6-months")
    parser.add_argument("--no-mlflow", action="store_true")
    args = parser.parse_args(argv)
    report = run(args.dataset, tuple(args.retrain_dates.split(",")), args.horizon_months, args.validation_months,
                 not args.no_refit, args.C, None, args.bootstrap_samples)
    write_json(args.output_dir / "report.json", report)
    (args.output_dir / "summary.md").write_text(summary(report))
    if not args.no_mlflow:
        report["mlflow_run_id"] = log_to_mlflow(report, args.output_dir, args.run_name, tags)
    print(summary(report))
    return report


if __name__ == "__main__":
    main()
