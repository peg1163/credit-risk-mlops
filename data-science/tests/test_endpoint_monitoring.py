from __future__ import annotations

import io
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from credit_risk.common import ARTIFACTS, DATA
from credit_risk.sagemaker_serve import CAPTURE_EVENT, capture_lines, load_bundle, predict_records, validate_records
from mlops.monitoring import canary, capture_export, quality, retrospective
from mlops.monitoring.build_reference_profile import reference_profile

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = json.loads((ROOT / "mlops/monitoring/canary_payload.json").read_text())


@pytest.fixture(scope="module")
def profile():
    return reference_profile(DATA / "modeling_dataset.parquet", ARTIFACTS / "champion.joblib")


@pytest.fixture(scope="module")
def production_lines():
    frame = pd.read_parquet(DATA / "features" / "production-1998-01.parquet").head(60)
    bundle = load_bundle(ARTIFACTS)
    frame["observation_date"] = frame.observation_date.dt.strftime("%Y-%m-%d")
    records = json.loads(frame[["account_id", "observation_date", *bundle["features"]]].to_json(orient="records"))
    results = predict_records(bundle, records)
    lines = []
    for index, (record, result) in enumerate(zip(records, results)):
        lines += capture_lines(f"r{index}", False, "application/json", 200, [record], [result], None, 5.0)
    return lines


class FakeBody(io.BytesIO):
    pass


class FakeS3:
    class exceptions:
        class NoSuchKey(Exception):
            pass

    def __init__(self, objects=None):
        self.objects = dict(objects or {})

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise self.exceptions.NoSuchKey(Key)
        return {"Body": FakeBody(self.objects[Key])}

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.objects[Key] = Body


class FakeCloudWatch:
    def __init__(self, invocations=0.0):
        self.invocations = invocations
        self.published = []

    def put_metric_data(self, Namespace, MetricData):
        self.published += [(Namespace, item["MetricName"], item["Value"]) for item in MetricData]

    def get_metric_statistics(self, **kwargs):
        return {"Datapoints": [{"Sum": self.invocations}] if self.invocations else []}


class FakeLogs:
    class exceptions:
        class ResourceNotFoundException(Exception):
            pass

    def __init__(self, messages):
        self.messages = messages

    def get_paginator(self, name):
        messages = self.messages

        class Paginator:
            def paginate(self, **kwargs):
                return [{"events": [{"message": message} for message in messages]}]

        return Paginator()


def test_canary_payload_follows_the_serving_contract():
    assert len(validate_records([PAYLOAD])) == 1


def test_canary_publishes_failure_when_endpoint_errors(monkeypatch):
    monkeypatch.setenv("ENDPOINT_NAME", "endpoint")
    monkeypatch.setenv("CANARY_PAYLOAD", json.dumps(PAYLOAD))

    class Broken:
        def invoke_endpoint(self, **kwargs):
            assert kwargs["CustomAttributes"] == "synthetic=canary"
            raise RuntimeError("down")

    class Working:
        def invoke_endpoint(self, **kwargs):
            return {"Body": FakeBody(b'{"score": 0.2, "decision": 0}')}

    cloudwatch = FakeCloudWatch()
    assert not canary.handler({}, None, Broken(), cloudwatch)["ok"]
    assert canary.handler({}, None, Working(), cloudwatch)["ok"]
    assert [value for _, name, value in cloudwatch.published if name == "CanaryOK"] == [0.0, 1.0]


def test_capture_export_copies_day_and_reports_gap(monkeypatch, production_lines):
    monkeypatch.setenv("ENDPOINT_NAME", "endpoint")
    monkeypatch.setenv("DATA_BUCKET", "bucket")
    monkeypatch.setenv("CAPTURE_LOG_GROUP", "/aws/sagemaker/Endpoints/endpoint")
    canary_line = capture_lines("c1", True, "application/json", 200, None, None, "x", 1.0)[0] | {"status": "accepted"}
    messages = [json.dumps(line) for line in production_lines[:5]] + [json.dumps(canary_line), "GET /ping 200", json.dumps(production_lines[0])]
    s3, cloudwatch = FakeS3(), FakeCloudWatch(invocations=7)
    now = datetime(2026, 11, 16, 1, tzinfo=timezone.utc)
    result = capture_export.handler({}, None, FakeLogs(messages), cloudwatch, s3, now=now)
    assert result["date"] == "2026-11-15"
    assert result["captured_lines"] == 6 and result["real_requests"] == 5 and result["synthetic_requests"] == 1
    assert result["capture_gap"] == 1
    stored = s3.objects["endpoint-capture/date=2026-11-15/capture.jsonl"].decode().splitlines()
    assert len(stored) == 6 and all(json.loads(line)["event"] == CAPTURE_EVENT for line in stored)
    assert ("CreditRisk/Endpoint", "CaptureGap", 1.0) in cloudwatch.published


def test_psi_is_zero_for_same_distribution_and_large_for_shift():
    spec = {"type": "numeric", "edges": [1.0, 2.0, 3.0]}
    reference = quality.proportions([0.5, 1.5, 2.5, 3.5] * 25, spec)
    assert quality.psi(reference, reference) == pytest.approx(0.0)
    assert quality.psi(reference, quality.proportions([3.5] * 100, spec)) > 0.25


def test_quality_report_flags_drift_only_when_inputs_shift(monkeypatch, profile, production_lines):
    monkeypatch.setenv("ENDPOINT_NAME", "endpoint")
    monkeypatch.setenv("DATA_BUCKET", "bucket")
    monkeypatch.setenv("DRIFT_WINDOW_DAYS", "2")

    def run(lines):
        body = "".join(json.dumps(line) + "\n" for line in lines).encode()
        s3 = FakeS3({quality.PROFILE_KEY: json.dumps(profile).encode(), quality.capture_key(date(2026, 11, 15)): body})
        cloudwatch = FakeCloudWatch()
        quality.handler({"date": "2026-11-15"}, None, s3, cloudwatch)
        report = json.loads(s3.objects[quality.report_key(date(2026, 11, 15))])
        return report, {name: value for _, name, value in cloudwatch.published}

    report, metrics = run(production_lines)
    assert report["missing_capture_days"] == ["2026-11-14"]
    assert report["day"]["real_requests"] == 60 and report["day"]["rejection_rate"] == 0
    # The 1998-01 production features have balance_change_3m null in every row
    # (only three months of history), while training never has it null.
    assert report["day"]["null_rate"]["balance_change_3m"] == 1.0
    assert metrics["NullRateDeltaMaxPp"] == pytest.approx(100.0)
    assert report["window"]["psi_max_feature"] == "balance_change_3m"
    baseline_loan_psi = report["window"]["psi"]["loan_amount"]
    assert baseline_loan_psi < 0.25

    shifted = json.loads(json.dumps(production_lines))
    for line in shifted:
        line["input"]["loan_amount"] = 10_000_000
    report, _ = run(shifted)
    assert report["window"]["psi"]["loan_amount"] > 0.25

def test_quality_requires_capture_of_the_day(monkeypatch, profile):
    monkeypatch.setenv("ENDPOINT_NAME", "endpoint")
    monkeypatch.setenv("DATA_BUCKET", "bucket")
    s3 = FakeS3({quality.PROFILE_KEY: json.dumps(profile).encode()})
    with pytest.raises(RuntimeError, match="missing"):
        quality.handler({"date": "2026-11-15"}, None, s3, FakeCloudWatch())


def test_retrospective_joins_mature_labels(tmp_path, production_lines):
    capture_dir = tmp_path / "endpoint-capture" / "date=2026-11-15"
    capture_dir.mkdir(parents=True)
    (capture_dir / "capture.jsonl").write_text("".join(json.dumps(line) + "\n" for line in production_lines))
    labels = pd.read_parquet(DATA / "labels" / "labels.parquet")
    report = retrospective.evaluate(retrospective.load_capture(tmp_path / "endpoint-capture"), labels)
    assert report["captured_records"] == 60
    assert report["labeled_records"] <= 60
    assert set(report["thresholds"]) == {"roc_auc_min", "ks_min", "brier_max", "recall_min"}
