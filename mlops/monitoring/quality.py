"""Daily Lambda: data quality and drift of the endpoint capture.

Reads the capture copied by ``capture_export`` and a reference profile built
from the training split, writes a JSON report to ``monitoring/`` and publishes
low-cardinality metrics to CloudWatch. Canary requests are excluded.

The module has no dependencies outside the Lambda runtime, so the same
functions also build the reference profile. See ADR-0006.
"""

from __future__ import annotations

import json
import math
import os
from bisect import bisect_left
from datetime import date, datetime, timedelta, timezone

NAMESPACE = "CreditRisk/Endpoint"
PROFILE_KEY = "monitoring/reference/profile.json"
NULL_BUCKET = "__null__"
OTHER_BUCKET = "__other__"
PSI_EPSILON = 1e-4
MIN_DRIFT_RECORDS = 30


def capture_key(day: date) -> str:
    return f"endpoint-capture/date={day.isoformat()}/capture.jsonl"


def report_key(day: date) -> str:
    return f"monitoring/endpoint/daily/date={day.isoformat()}/report.json"


def is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def numeric_bucket(value, edges: list[float]) -> str:
    if is_missing(value):
        return NULL_BUCKET
    return str(bisect_left(edges, float(value)))


def categorical_bucket(value, categories: list[str]) -> str:
    if is_missing(value):
        return NULL_BUCKET
    return str(value) if str(value) in categories else OTHER_BUCKET


def bucket_of(value, spec: dict) -> str:
    if spec["type"] == "numeric":
        return numeric_bucket(value, spec["edges"])
    return categorical_bucket(value, list(spec["categories"]))


def proportions(values: list, spec: dict) -> dict[str, float]:
    counts: dict[str, int] = {}
    for value in values:
        bucket = bucket_of(value, spec)
        counts[bucket] = counts.get(bucket, 0) + 1
    total = len(values)
    return {bucket: count / total for bucket, count in counts.items()} if total else {}


def psi(expected: dict[str, float], actual: dict[str, float]) -> float:
    total = 0.0
    for bucket in set(expected) | set(actual):
        e = max(expected.get(bucket, 0.0), PSI_EPSILON)
        a = max(actual.get(bucket, 0.0), PSI_EPSILON)
        total += (a - e) * math.log(a / e)
    return total


def quantile_edges(values: list[float], bins: int = 10) -> list[float]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return []
    edges = []
    for step in range(1, bins):
        position = step * (len(ordered) - 1) / bins
        low, high = math.floor(position), math.ceil(position)
        edge = ordered[low] + (ordered[high] - ordered[low]) * (position - low)
        if not edges or edge > edges[-1]:
            edges.append(edge)
    return edges


def build_profile(columns: dict[str, list], categorical: set[str], source: str, min_share: float = 0.01) -> dict:
    """Reference distribution per column, using the same buckets as the daily job."""
    features = {}
    for name, values in columns.items():
        present = [value for value in values if not is_missing(value)]
        if name in categorical:
            counts: dict[str, int] = {}
            for value in present:
                counts[str(value)] = counts.get(str(value), 0) + 1
            categories = sorted(key for key, count in counts.items() if count / max(len(values), 1) >= min_share)
            spec = {"type": "categorical", "categories": categories}
        else:
            spec = {"type": "numeric", "edges": quantile_edges(present)}
        spec["null_rate"] = 1 - len(present) / len(values) if values else 0.0
        spec["proportions"] = proportions(values, spec)
        features[name] = spec
    rows = len(next(iter(columns.values()))) if columns else 0
    return {"profile_version": 1, "source": source, "rows": rows, "features": features}


def real_lines(lines: list[dict]) -> list[dict]:
    return [line for line in lines if not line.get("synthetic")]


def day_quality(lines: list[dict], profile: dict) -> dict:
    lines = real_lines(lines)
    requests = {line["request_id"] for line in lines}
    rejected = {line["request_id"] for line in lines if line["status"] != "accepted"}
    accepted = [line for line in lines if line["status"] == "accepted"]
    report = {
        "real_requests": len(requests),
        "accepted_records": len(accepted),
        "rejected_requests": len(rejected),
        "rejection_rate": len(rejected) / len(requests) if requests else None,
        "score_mean": None,
        "decision_rate": None,
        "null_rate": {},
        "null_rate_delta_max_pp": None,
    }
    if not accepted:
        return report
    report["score_mean"] = sum(line["output"]["score"] for line in accepted) / len(accepted)
    report["decision_rate"] = sum(line["output"]["decision"] for line in accepted) / len(accepted)
    deltas = []
    for name, spec in profile["features"].items():
        if name == "score":
            continue
        rate = sum(is_missing(line["input"].get(name)) for line in accepted) / len(accepted)
        report["null_rate"][name] = rate
        deltas.append((rate - spec["null_rate"]) * 100)
    report["null_rate_delta_max_pp"] = max(deltas) if deltas else None
    return report


def window_drift(lines: list[dict], profile: dict, min_records: int = MIN_DRIFT_RECORDS) -> dict:
    accepted = [line for line in real_lines(lines) if line["status"] == "accepted"]
    report = {"records": len(accepted), "min_records": min_records, "psi": {}, "psi_max": None, "psi_max_feature": None}
    if len(accepted) < min_records:
        return report
    for name, spec in profile["features"].items():
        values = [line["output"]["score"] if name == "score" else line["input"].get(name) for line in accepted]
        report["psi"][name] = psi(spec["proportions"], proportions(values, spec))
    feature_psi = {name: value for name, value in report["psi"].items() if name != "score"}
    if feature_psi:
        worst = max(feature_psi, key=feature_psi.get)
        report["psi_max"], report["psi_max_feature"] = feature_psi[worst], worst
    report["score_psi"] = report["psi"].get("score")
    return report


def metric_data(report: dict, endpoint: str) -> list[dict]:
    dimensions = [{"Name": "EndpointName", "Value": endpoint}]
    day, drift = report["day"], report["window"]
    values = {
        "RealRequests": (day["real_requests"], "Count"),
        "RejectionRate": (day["rejection_rate"], "None"),
        "ScoreMean": (day["score_mean"], "None"),
        "DecisionRate": (day["decision_rate"], "None"),
        "NullRateDeltaMaxPp": (day["null_rate_delta_max_pp"], "None"),
        "PsiMax": (drift["psi_max"], "None"),
        "ScorePsi": (drift.get("score_psi"), "None"),
    }
    return [
        {"MetricName": name, "Dimensions": dimensions, "Value": float(value), "Unit": unit}
        for name, (value, unit) in values.items()
        if value is not None
    ]


def read_lines(s3, bucket: str, key: str) -> list[dict] | None:
    try:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode()
    except s3.exceptions.NoSuchKey:
        return None
    return [json.loads(line) for line in body.splitlines() if line.strip()]



def client(name: str):
    import boto3  # available in the Lambda runtime; tests pass fake clients

    return boto3.client(name)

def handler(event, context, s3=None, cloudwatch=None, now: datetime | None = None):
    endpoint = os.environ["ENDPOINT_NAME"]
    bucket = os.environ["DATA_BUCKET"]
    window_days = int(os.environ.get("DRIFT_WINDOW_DAYS", "7"))
    s3 = s3 or client("s3")
    cloudwatch = cloudwatch or client("cloudwatch")

    now = now or datetime.now(timezone.utc)
    day = date.fromisoformat(event["date"]) if event and event.get("date") else (now - timedelta(days=1)).date()
    profile = json.loads(s3.get_object(Bucket=bucket, Key=PROFILE_KEY)["Body"].read())

    window, missing_days = [], []
    for offset in range(window_days):
        current = day - timedelta(days=offset)
        lines = read_lines(s3, bucket, capture_key(current))
        if lines is None:
            missing_days.append(current.isoformat())
            continue
        window.extend(lines)
        if offset == 0:
            today_lines = lines
    if day.isoformat() in missing_days:
        raise RuntimeError(f"Capture for {day} is missing; run capture_export first")

    report = {
        "date": day.isoformat(),
        "endpoint": endpoint,
        "window_days": window_days,
        "missing_capture_days": missing_days,
        "profile_source": profile.get("source"),
        "day": day_quality(today_lines, profile),
        "window": window_drift(window, profile),
    }
    s3.put_object(
        Bucket=bucket,
        Key=report_key(day),
        Body=(json.dumps(report, indent=2, sort_keys=True) + "\n").encode(),
        ContentType="application/json",
        ServerSideEncryption="AES256",
    )
    data = metric_data(report, endpoint)
    if data:
        cloudwatch.put_metric_data(Namespace=NAMESPACE, MetricData=data)
    summary = {"date": report["date"], "metrics": {item["MetricName"]: item["Value"] for item in data}}
    print(json.dumps(summary))
    return summary
