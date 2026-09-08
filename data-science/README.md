# Data Science implementation

## Data decision

Freddie Mac was evaluated first on 2026-09-08. The official full and per-vintage datasets require registration and sign-in to Clarity. The public Release 47 format sample was downloaded and inspected: 1,000 origination rows and 1,011 performance rows for 12 loans, with zero intersecting loan identifiers. It cannot support model development. Legacy sample URLs returned HTTP 403. The official guide, layout, headers and sample remain under `data/source_docs` and `data/downloads` locally; raw downloads are ignored by Git because redistribution terms apply.

The executed fallback is the real anonymized PKDD'99 Czech Financial Dataset, downloaded from the public mirror `https://github.com/jlacko/berka-dataset`. It has 1,056,320 transactions for 4,500 accounts and 682 loans. For loan accounts the prepared subset has 191,556 transactions across 72 months (1993-01 through 1998-12). Source checksums are in `data/raw_archive/dataset_manifest.json`.

PKDD'99 does not expose DPD. The target is therefore not 90+ DPD: it is the first observed negative transaction balance during the six calendar months strictly after an observation date. Only pre-event snapshots are eligible. This signal matches all 76 B/D problem-loan accounts in the source, but remains a proxy for severe financial distress.

## Reproduce

From this directory, after creating a Python 3.11 environment and installing `requirements.txt`:

```bash
export PYTHONPATH=src
python download_data.py
python prepare_data.py --source data/downloads/berka-dataset
python build_snapshots.py
python train.py
python evaluate.py
pytest -q
```

`prepare_data.py` refuses to overwrite an existing archive. Rebuilding it requires an explicit manual removal because the archive is immutable by contract.

## Historical replay

```bash
python replay.py --status
python replay.py --next
python replay.py --release-month 1998-02
python replay.py --reset
```

Each release copies exactly one immutable Parquet partition to `data/incoming`, verifies SHA-256, persists state, blocks duplicates and writes `data/manifests/batch-YYYY-MM.json`. It also releases static loan/account reference tables on the first batch. Production features use only incoming data:

```bash
python build_features.py --source incoming
python predict.py --input data/features/production-1998-01.parquet --output data/predictions/example.parquet
```

## Layout and retention

- `data/raw_archive`: immutable complete history; replay controller only.
- `data/incoming`: released history visible to production simulation.
- `data/features`, `labels`, `predictions`, `manifests`: derived zones.
- `artifacts/champion.joblib`: executable model bundle.
- `artifacts/mlruns`: executed local MLflow experiment.

Raw data and executable models are ignored by Git. In a public repository, publish code, documentation, configs, metrics, schemas and checksums; obtain data through `download_data.py`.

