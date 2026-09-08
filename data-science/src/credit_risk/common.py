from __future__ import annotations
import hashlib, json
from pathlib import Path
import pandas as pd
import yaml

DS = Path(__file__).resolve().parents[2]
ROOT = DS.parent
DATA = DS / "data"
ARTIFACTS = DS / "artifacts"
CONFIG = DS / "configs" / "project.yaml"

def config() -> dict:
    return yaml.safe_load(CONFIG.read_text())

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n")

def parse_berka_date(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.zfill(6)
    yy = text.str[:2].astype(int)
    years = (1900 + yy).astype(str)
    return pd.to_datetime(years + text.str[2:], format="%Y%m%d")

def month_end(series: pd.Series) -> pd.Series:
    return series.dt.to_period("M").dt.to_timestamp("M")

