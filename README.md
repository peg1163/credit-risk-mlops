# Credit Risk MLOps

Portfolio project separating an executed Data Science handoff from an evolving MLOps platform. The scientific implementation is in [`data-science/`](data-science/), container operations are in [`mlops/`](mlops/), and the guided infrastructure work is in [`infrastructure/`](infrastructure/).

This is educational software. It must not be used for lending decisions.

## Current status

- Real anonymized PKDD'99 banking data downloaded and prepared.
- Monthly historical archive and deterministic replay implemented.
- Six-month severe-distress target, leakage-safe features, chronological splits.
- Logistic-regression champion trained; local MLflow experiment recorded.
- Containerized replay, feature generation and inference components.
- A local monthly pipeline that preserves warm-up and future-data isolation.
- End-to-end container integration tests in GitHub Actions.
- Local Terraform foundations implemented and validated in CI.
- AWS bootstrap in progress with cost guardrails configured before resources.
- Inference, evaluation and automated scientific tests executed successfully.

See [`DATA_SCIENCE_HANDOFF.md`](DATA_SCIENCE_HANDOFF.md) for the operational contract, [`docs/MLOPS_PROGRESS.md`](docs/MLOPS_PROGRESS.md) for the exact implementation checkpoint, and [`data-science/README.md`](data-science/README.md) for scientific commands.
