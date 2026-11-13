"""One inference contract for SageMaker real-time and Batch Transform."""

from __future__ import annotations

import json
import hashlib
import math
import os
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import joblib
import pandas as pd

from .dataset import FEATURES

MODEL_VERSION = "0.1.0"
META_FIELDS = {"account_id", "observation_date"}
CATEGORICAL_FIELDS = {"district_id", "statement_frequency"}
MAX_BODY_BYTES = 6 * 1024 * 1024


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


def handler_for(bundle: dict):
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
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size <= 0 or size > MAX_BODY_BYTES:
                    raise InvalidRequest("Request body must be between 1 byte and 6 MiB")
                content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                records, lines = parse_body(self.rfile.read(size), content_type)
                results = predict_records(bundle, records)
                payload = ("\n".join(json.dumps(item, allow_nan=False) for item in results) + "\n").encode() if lines else json.dumps(results[0], allow_nan=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/jsonlines" if lines else "application/json")
            except InvalidRequest as error:
                payload = json.dumps({"error": str(error)}).encode()
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
            except Exception:
                self.log_error("Inference failed")
                payload = b'{"error":"Inference failed"}'
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

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
