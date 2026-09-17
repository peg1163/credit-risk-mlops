# MLOps implementation progress

Last reviewed: 2026-09-16

This document is the restart point for continuing the project from another
computer or a new working session. It contains no AWS account identifiers,
credentials, private URLs, email addresses, or Terraform state.

## Current phase

The executed Data Science handoff is complete. The local MLOps path is also
operational: replay, feature generation, and inference run in separate Docker
images and are connected by a deterministic monthly pipeline.

The project is starting its AWS/Terraform bootstrap. No application
infrastructure has been deployed to AWS yet.

## Completed work

- Real PKDD'99/Berka data prepared into a monthly immutable archive.
- Leakage-safe temporal snapshots, six-month labels, chronological splits.
- Logistic-regression champion trained and evaluated with local MLflow.
- Containerized inference, historical replay, and feature generation.
- `run-monthly-pipeline.sh` connects replay, features, and inference.
- Synthetic end-to-end CI fixture validates the complete monthly pipeline.
- GitHub Actions validates Python, shell, Docker, and Terraform.
- Local Terraform laboratory covers init, plan, apply, state, drift, outputs,
  variables, saved plans, and destroy.
- AWS CLI v2 installed locally and browser-based temporary login tested.
- AWS Budgets configured for near-zero spend and a USD 5 monthly ceiling,
  without automated budget actions.
- Initial read-only inventory found no EC2, EBS, Elastic IP, NAT Gateway, load
  balancer, RDS, EKS, ECR, S3, Lambda, or DynamoDB resources.

## Current security decision

Local AWS access currently uses `aws login`, which issues temporary browser
credentials. No access keys are used or stored in the repository.

Root access was accepted temporarily by the project owner for the bootstrap,
despite the documented recommendation to use an IAM identity or assumed role.
Every AWS plan must be reviewed before apply. Migrating daily work away from
root remains an explicit security task.

Never commit `.aws/`, credentials, account IDs, ARNs, sign-in URLs, email
addresses, MFA material, Terraform state, or downloaded console output.

## Files intentionally absent from Git

- Licensed/raw and replayed datasets under `data-science/data/`.
- Trained model and local MLflow artifacts under `data-science/artifacts/`.
- Docker images and container runtime data.
- Local `.tfvars`, `.terraform/`, plans, and `*.tfstate*` files.
- AWS CLI configuration, login cache, and credentials.

See `.gitignore`, `.dockerignore`, `DATA_SCIENCE_HANDOFF.md`, and the
component READMEs for the reproducible inputs and commands.

## Restore on another computer

1. Clone the repository and check out `main`.
2. Install Python 3.11, Docker, Terraform, and AWS CLI v2.
3. Create the Python environment from the versioned requirements.
4. Reproduce the licensed dataset and champion artifact using the Data Science
   instructions, or transfer them through an approved private channel.
5. Build the inference, replay, and features images from `mlops/docker/`.
6. Run the local unit and container integration tests.
7. Authenticate again with `aws login`; temporary sessions are never copied
   between computers.
8. Run Terraform `init`, `fmt -check`, and `validate`. Do not copy local state.

## Current AWS guardrails

- Region selected for the initial lab: `us-east-1`.
- Near-zero-spend alert triggers above USD 0.01 actual monthly cost.
- Monthly USD 5 budget includes actual and forecast notifications.
- Budget actions are disabled; alerts do not stop resources automatically.
- Expensive baseline components are prohibited for the initial lab: NAT
  Gateway, EKS, RDS, always-on EC2, and load balancers.

## Next implementation step

Create `infrastructure/terraform/bootstrap/` for a private and versioned S3
Terraform state bucket. Before apply:

1. verify current S3 pricing from AWS primary sources;
2. validate provider and variable constraints;
3. run a read-only Terraform plan;
4. review encryption, public-access blocking, versioning, deletion protection,
   tags, expected cost, and destroy/recovery behavior;
5. obtain explicit approval before creating the bucket.

After bootstrap, migrate environment state to S3 and add GitHub Actions OIDC.
Do not create permanent AWS access keys for GitHub.

## Definition of done for the next phase

- Remote state bucket exists with secure defaults and minimal expected cost.
- Backend migration is documented and tested.
- State locking behavior is validated.
- GitHub Actions authenticates through OIDC, not stored AWS keys.
- `terraform plan` runs for development without automatic production apply.
- Cleanup and state-recovery procedures are documented.
