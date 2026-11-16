"""One inference contract for SageMaker endpoints and Batch Transform, with request capture."""

from __future__ import annotations

import json
import hashlib
import math
import os
import sys
import threading
import time
import uuid
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import joblib
import pandas as pd

from .dataset import FEATURES

MODEL_VERSION = "0.1.0"
META_FIELDS = {"account_id", "observation_date"}
CATEGORICAL_FIELDS = {"district_id", "statement_frequency"}
MAX_BODY_BYTES = 6 * 1024 * 1024
IMAGE_VERSION = os.environ.get("IMAGE_VERSION", "local")
CAPTURE_EVENT = "inference_capture"
CAPTURE_SCHEMA_VERSION = 1
CANARY_ATTRIBUTE = "synthetic=canary"


class InvalidRequest(ValueError):
    pass


def load_bundle(model_dir: Path) -> dict:
    path = model_dir / "champion.joblib"
    manifest_path = model_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != manifest["model_sha256"]:
            raise ValueError("Model checksum differs from package manifest")
        if manifest["model_version"] != MODEL_VERSION or manifest["features"] != FEATURES:
            raise ValueError("Model package manifest differs from the serving contract")
    bundle = joblib.load(path)
    if bundle["features"] != FEATURES:
        raise ValueError("Model feature contract differs from the source contract")
    return bundle


def validate_records(records: list[dict], features: list[str] = FEATURES) -> pd.DataFrame:
    if not records:
        raise InvalidRequest("At least one record is required")
    expected = META_FIELDS | set(features)
    cleaned = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise InvalidRequest(f"Record {index} must be a JSON object")
        missing = expected - record.keys()
        extra = record.keys() - expected
        if missing or extra:
            raise InvalidRequest(f"Record {index}: missing={sorted(missing)}, extra={sorted(extra)}")
        account_id = record["account_id"]
        if isinstance(account_id, bool) or not isinstance(account_id, int) or account_id < 0:
            raise InvalidRequest(f"Record {index}: account_id must be a nonnegative integer")
        try:
            observed = date.fromisoformat(record["observation_date"])
            if (observed.replace(day=28) + pd.offsets.MonthEnd()).date() != observed:
                raise ValueError("not month end")
        except (TypeError, ValueError):
            raise InvalidRequest(f"Record {index}: observation_date must be a month-end YYYY-MM-DD") from None
        row = {"account_id": account_id, "observation_date": observed.isoformat()}
        for feature in features:
            value = record[feature]
            if feature == "district_id":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise InvalidRequest(f"Record {index}: district_id must be an integer")
            elif feature == "statement_frequency":
                if not isinstance(value, str) or not value:
                    raise InvalidRequest(f"Record {index}: statement_frequency must be a nonempty string")
            elif value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise InvalidRequest(f"Record {index}: {feature} must be a finite number or null")
            row[feature] = value
        cleaned.append(row)
    return pd.DataFrame(cleaned, columns=["account_id", "observation_date", *features])


def predict_records(bundle: dict, records: list[dict]) -> list[dict]:
    frame = validate_records(records, bundle["features"])
    scores = bundle["model"].predict_proba(frame[bundle["features"]])[:, 1]
    return [
        {
            "account_id": int(row.account_id),
            "observation_date": row.observation_date,
            "score": float(score),
            "decision": int(score >= bundle["threshold"]),
            "model_version": MODEL_VERSION,
            "dataset_id": bundle["dataset_id"],
            "feature_pipeline_version": bundle["feature_pipeline_version"],
        }
        for row, score in zip(frame.itertuples(index=False), scores, strict=True)
    ]


def parse_body(body: bytes, content_type: str) -> tuple[list[dict], bool]:
    try:
        raw = body.decode("utf-8")
        if content_type == "application/json":
            value = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(value, dict):
                raise InvalidRequest("application/json requires one JSON object")
            return [value], False
        if content_type in {"application/jsonlines", "application/x-ndjson"}:
            lines = raw.splitlines()
            if not lines or any(not line.strip() for line in lines):
                raise InvalidRequest("JSON Lines requires nonempty lines")
            return [json.loads(line, parse_constant=lambda _: (_ for _ in ()).throw(ValueError())) for line in lines], True
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise InvalidRequest("Invalid JSON request body") from error
    raise InvalidRequest("Use application/json or application/jsonlines")


def is_synthetic(custom_attributes: str) -> bool:
    parts = custom_attributes.replace(",", ";").split(";")
    return any(part.strip() == CANARY_ATTRIBUTE for part in parts)


def capture_lines(
    request_id: str,
    synthetic: bool,
    content_type: str,
    http_status: int,
    records: list[dict] | None,
    results: list[dict] | None,
    error: str | None,
    latency_ms: float,
) -> list[dict]:
    """One line per scored record, or one line for a request that was not scored."""
    common = {
        "event": CAPTURE_EVENT,
        "capture_schema_version": CAPTURE_SCHEMA_VERSION,
        "request_id": request_id,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "synthetic": synthetic,
        "content_type": content_type,
        "http_status": http_status,
        "image_version": IMAGE_VERSION,
        "model_version": MODEL_VERSION,
        "latency_ms": round(latency_ms, 3),
    }
    if results is not None and records is not None:
        return [
            {**common, "status": "accepted", "record_index": index, "record_count": len(results), "input": record, "output": result, "error": None}
            for index, (record, result) in enumerate(zip(records, results, strict=True))
        ]
    status = "rejected" if http_status == 400 else "error"
    return [{**common, "status": status, "record_index": None, "record_count": 0, "input": None, "output": None, "error": error}]


class CaptureWriter:
    """Writes capture lines to stdout; SageMaker ships stdout to CloudWatch Logs."""

    def __init__(self, stream=None, enabled: bool | None = None):
        self.stream = stream
        self.enabled = os.environ.get("CAPTURE_ENABLED", "true").lower() != "false" if enabled is None else enabled
        self.lock = threading.Lock()

    def write(self, lines: list[dict]) -> None:
        if not self.enabled:
            return
        text = "".join(json.dumps(line, allow_nan=False, separators=(",", ":")) + "\n" for line in lines)
        stream = self.stream or sys.stdout
        with self.lock:
            stream.write(text)
            stream.flush()


def handler_for(bundle: dict, capture: CaptureWriter | None = None):
    capture = capture or CaptureWriter()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/ping":
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path != "/invocations":
                self.send_error(404)
                return
            started = time.perf_counter()
            request_id = uuid.uuid4().hex
            synthetic = is_synthetic(self.headers.get("X-Amzn-SageMaker-Custom-Attributes", ""))
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            records = results = error = None
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size <= 0 or size > MAX_BODY_BYTES:
                    raise InvalidRequest("Request body must be between 1 byte and 6 MiB")
                records, lines = parse_body(self.rfile.read(size), content_type)
                results = predict_records(bundle, records)
                payload = ("\n".join(json.dumps(item, allow_nan=False) for item in results) + "\n").encode() if lines else json.dumps(results[0], allow_nan=False).encode()
                status = 200
                self.send_response(status)
                self.send_header("Content-Type", "application/jsonlines" if lines else "application/json")
            except InvalidRequest as invalid:
                results = None
                error = str(invalid)
                payload = json.dumps({"error": error}).encode()
                status = 400
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
            except Exception:
                self.log_error("Inference failed")
                results = None
                error = "Inference failed"
                payload = b'{"error":"Inference failed"}'
                status = 500
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
            self.send_header("X-Amzn-SageMaker-Custom-Attributes", f"request_id={request_id}")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            latency_ms = (time.perf_counter() - started) * 1000
            capture.write(capture_lines(request_id, synthetic, content_type, status, records, results, error, latency_ms))

    return Handler


def main() -> None:
    import sys

    if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[1] != "serve"):
        raise SystemExit("Usage: python -m credit_risk.sagemaker_serve [serve]")
    bundle = load_bundle(Path(os.environ.get("MODEL_DIR", "/opt/ml/model")))
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), handler_for(bundle))
    server.serve_forever()


if __name__ == "__main__":
    main()
