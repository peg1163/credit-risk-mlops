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


REQUIRED = {"model", "features", "threshold", "dataset_id", "feature_pipeline_version"}


def model_manifest(bundle: dict, model_path: Path, model_version: str = "0.1.0") -> dict:
    if not REQUIRED.issubset(bundle):
        raise ValueError(f"Model bundle lacks {sorted(REQUIRED - bundle.keys())}")
    return {
        "model_version": model_version,
        "model_file": "champion.joblib",
        "model_sha256": sha256(model_path),
        "dataset_id": bundle["dataset_id"],
        "feature_pipeline_version": bundle["feature_pipeline_version"],
        "features": bundle["features"],
        "threshold": float(bundle["threshold"]),
    }


def write_model_dir(bundle: dict, directory: Path, model_version: str, extra: dict | None = None) -> dict:
    """Same layout as model.tar.gz; a SageMaker training job tars /opt/ml/model itself."""
    directory.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, directory / "champion.joblib")
    manifest = {**model_manifest(bundle, directory / "champion.joblib", model_version), **(extra or {})}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def package_model(model_path: Path, output_path: Path) -> dict:
    manifest = model_manifest(joblib.load(model_path), model_path)
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
