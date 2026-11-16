"""Build reproducible zip files for the monitoring Lambdas.

The same source always produces the same bytes, so the hash Terraform records
in a saved plan still matches when another runner applies it (ADR-0007).
"""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
FUNCTIONS = ("canary", "capture_export", "quality")
DEFAULT_OUTPUT = SOURCE.parents[1] / "infrastructure" / "terraform" / "environments" / "dev" / ".build"


def build(output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name in FUNCTIONS:
        target = output_dir / f"{name}.zip"
        info = zipfile.ZipInfo(f"{name}.py", date_time=(1980, 1, 1, 0, 0, 0))
        info.external_attr = 0o644 << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr(info, (SOURCE / f"{name}.py").read_bytes())
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    return hashes


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    for name, digest in build(args.output_dir).items():
        print(f"{name}.zip {digest}")
