from __future__ import annotations

import io
import json
import tarfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import joblib
import pandas as pd
import pytest

from credit_risk.common import ARTIFACTS, DATA
from credit_risk.predict import predict
from credit_risk.sagemaker_serve import CAPTURE_EVENT, CaptureWriter, handler_for, load_bundle
from mlops.sagemaker.package_model import package_model
from mlops.sagemaker.prepare_batch import prepare_batch


@pytest.fixture
def sample(tmp_path: Path):
    source = DATA / "features" / "production-1998-01.parquet"
    frame = pd.read_parquet(source).head(3)
    parquet = tmp_path / "features.parquet"
    frame.to_parquet(parquet, index=False)
    jsonl = tmp_path / "applications.jsonl"
    manifest = prepare_batch(parquet, jsonl, ARTIFACTS / "champion.joblib", "1998-01")
    records = [json.loads(line) for line in jsonl.read_text().splitlines()]
    assert json.loads((tmp_path / manifest["endpoint_example_file"]).read_text()) == records[0]
    return parquet, jsonl, manifest, records


def test_package_and_batch_match_existing_predictions(tmp_path: Path, sample):
    parquet, jsonl, manifest, records = sample
    archive = tmp_path / "model.tar.gz"
    package_model(ARTIFACTS / "champion.joblib", archive)
    with tarfile.open(archive, "r:gz") as packaged:
        assert packaged.getnames() == ["champion.joblib", "manifest.json"]
        assert json.load(packaged.extractfile("manifest.json"))["features"] == joblib.load(ARTIFACTS / "champion.joblib")["features"]
        packaged.extractall(tmp_path / "extracted", filter="data")
    assert load_bundle(tmp_path / "extracted")["features"] == load_bundle(ARTIFACTS)["features"]
    assert manifest["rows"] == len(records) == 3
    assert manifest["period"] == "1998-01"
    original = tmp_path / "original.parquet"
    predict(parquet, original)
    expected = pd.read_parquet(original)
    bundle = load_bundle(ARTIFACTS)
    from credit_risk.sagemaker_serve import predict_records

    actual = predict_records(bundle, records)
    assert [row["account_id"] for row in actual] == expected.account_id.tolist()
    assert [row["score"] for row in actual] == pytest.approx(expected.score.tolist())
    assert [row["decision"] for row in actual] == expected.decision.tolist()


def test_http_endpoint_and_batch_use_same_contract(sample):
    _, jsonl, _, records = sample
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(load_bundle(ARTIFACTS)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/ping") as response:
            assert response.status == 200
        endpoint = Request(base + "/invocations", data=json.dumps(records[0]).encode(), headers={"Content-Type": "application/json"})
        with urlopen(endpoint) as response:
            one = json.load(response)
        batch = Request(base + "/invocations", data=jsonl.read_bytes(), headers={"Content-Type": "application/jsonlines"})
        with urlopen(batch) as response:
            many = [json.loads(line) for line in response.read().splitlines()]
        assert one == many[0]
        assert len(many) == 3
        invalid = dict(records[0])
        invalid.pop("loan_amount")
        bad = Request(base + "/invocations", data=json.dumps(invalid).encode(), headers={"Content-Type": "application/json"})
        with pytest.raises(HTTPError) as error:
            urlopen(bad)
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_batch_rejects_wrong_period(tmp_path: Path, sample):
    parquet, _, _, _ = sample
    with pytest.raises(ValueError, match="outside the requested period"):
        prepare_batch(parquet, tmp_path / "wrong.jsonl", ARTIFACTS / "champion.joblib", "1998-02")


def test_endpoint_captures_every_request(sample):
    _, jsonl, _, records = sample
    stream = io.StringIO()
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(load_bundle(ARTIFACTS), CaptureWriter(stream, enabled=True)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        real = Request(base + "/invocations", data=json.dumps(records[0]).encode(), headers={"Content-Type": "application/json"})
        with urlopen(real) as response:
            one = json.load(response)
            assert response.headers["X-Amzn-SageMaker-Custom-Attributes"].startswith("request_id=")
        canary = Request(
            base + "/invocations",
            data=json.dumps(records[1]).encode(),
            headers={"Content-Type": "application/json", "X-Amzn-SageMaker-Custom-Attributes": "synthetic=canary"},
        )
        urlopen(canary).close()
        batch = Request(base + "/invocations", data=jsonl.read_bytes(), headers={"Content-Type": "application/jsonlines"})
        urlopen(batch).close()
        bad = Request(base + "/invocations", data=b'{"account_id": 1}', headers={"Content-Type": "application/json"})
        with pytest.raises(HTTPError):
            urlopen(bad)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(lines) == 1 + 1 + 3 + 1
    assert {line["event"] for line in lines} == {CAPTURE_EVENT}
    first, synthetic, *batch_lines, rejected = lines
    assert first["input"] == records[0] and first["output"] == one and not first["synthetic"]
    assert synthetic["synthetic"] and synthetic["status"] == "accepted"
    assert [line["record_index"] for line in batch_lines] == [0, 1, 2]
    assert len({line["request_id"] for line in batch_lines}) == 1
    assert rejected["status"] == "rejected" and rejected["http_status"] == 400
    assert rejected["input"] is None and "missing" in rejected["error"]


def test_capture_can_be_disabled():
    stream = io.StringIO()
    CaptureWriter(stream, enabled=False).write([{"event": CAPTURE_EVENT}])
    assert stream.getvalue() == ""
