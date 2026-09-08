# Credit Risk MLOps

Portfolio project separating an executed Data Science handoff from the future MLOps platform. The scientific implementation is in [`data-science/`](data-science/); `mlops/` and `infrastructure/` are intentionally left for the MLOps Engineer.

This is educational software. It must not be used for lending decisions.

## Current status

- Real anonymized PKDD'99 banking data downloaded and prepared.
- Monthly historical archive and deterministic replay implemented.
- Six-month severe-distress target, leakage-safe features, chronological splits.
- Logistic-regression champion trained; local MLflow experiment recorded.
- Inference, evaluation and seven automated tests executed successfully.

See [`DATA_SCIENCE_HANDOFF.md`](DATA_SCIENCE_HANDOFF.md) for the operational contract and [`data-science/README.md`](data-science/README.md) for commands.

