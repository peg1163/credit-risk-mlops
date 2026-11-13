"""Create the model.tar.gz consumed by SageMaker hosting and Batch Transform."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
from pathlib import Path

import joblib


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_model(model_path: Path, output_path: Path) -> dict:
    bundle = joblib.load(model_path)
    required = {"model", "features", "threshold", "dataset_id", "feature_pipeline_version"}
    if not required.issubset(bundle):
        raise ValueError(f"Model bundle lacks {sorted(required - bundle.keys())}")
    manifest = {
        "model_version": "0.1.0",
        "model_file": "champion.joblib",
        "model_sha256": sha256(model_path),
        "dataset_id": bundle["dataset_id"],
        "feature_pipeline_version": bundle["feature_pipeline_version"],
        "features": bundle["features"],
        "threshold": float(bundle["threshold"]),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(manifest, indent=2) + "\n").encode()
    with tarfile.open(output_path, "w:gz") as archive:
        archive.add(model_path, arcname="champion.joblib")
        info = tarfile.TarInfo("manifest.json")
        info.size = len(encoded)
        archive.addfile(info, io.BytesIO(encoded))
    manifest["archive_sha256"] = sha256(output_path)
    manifest["archive_path"] = str(output_path)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=Path("data-science/artifacts/champion.joblib"))
    parser.add_argument("--output", type=Path, default=Path("dist/sagemaker/model.tar.gz"))
    args = parser.parse_args()
    print(json.dumps(package_model(args.model, args.output), indent=2))
