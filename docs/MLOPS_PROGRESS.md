# MLOps implementation progress

Last reviewed locally: 2026-11-12

This document is the restart point for continuing the project from another
computer or a new working session. It intentionally excludes credentials, AWS
account identifiers, role ARNs, bucket names, email addresses and Terraform
state.

## Current phase

The Data Science handoff and local monthly pipeline are complete. The bootstrap
AWS foundation was deployed in an earlier session. The repository now also has
a **local SageMaker inference package** for the existing loan-account model:
one container contract for Batch Transform and a temporary endpoint, a model
archive, JSON Lines input and a deployment guide. See
[`SAGEMAKER_HANDOFF.md`](SAGEMAKER_HANDOFF.md).

The development Terraform workflow is merged into `main`. The current AWS
state, the development apply result and any AWS spending require verification
with the owner's correct session before further cloud work. No SageMaker
resources were created during the local packaging work.

## Completed work

- Real PKDD'99/Berka data prepared into a monthly immutable archive.
- Leakage-safe temporal snapshots, six-month labels and chronological splits.
- Logistic-regression champion trained and evaluated with local MLflow.
- Containerized replay, feature generation and inference.
- Deterministic local monthly pipeline with a synthetic end-to-end CI fixture.
- GitHub Actions validation for Python, shell, Docker and Terraform.
- Terraform stacks separated into local laboratory, bootstrap and development.
- Private, encrypted and versioned S3 backend with native lockfile support.
- GitHub OIDC provider and separate identity-check, plan and development-apply
  roles; no permanent AWS access keys are stored in GitHub.
- OIDC identity workflow and bootstrap Terraform plan verified successfully.
- Development GitHub Environment created with a `main` branch restriction and
  a manual approval rule while the repository was public.
- AWS Budgets alerts configured for near-zero spend and a USD 5 monthly ceiling.
- Development data bucket configuration defined with versioning, SSE-S3,
  public-access blocking, TLS-only access, ownership enforcement and lifecycle
  cost controls.
- Approved development plan/apply workflow merged into `main`.
- Local SageMaker serving container, model archive generator, monthly JSON Lines
  input generator, manifest and endpoint example implemented.
- SageMaker container built and exercised locally with the real model; all 11
  Python tests passed on 2026-11-12.

## Work in progress

The SageMaker packaging files and documentation are local working-tree changes;
they have not been committed or pushed. Generated model and batch artifacts
remain under ignored `dist/sagemaker/`.

Next cloud checkpoint, owned by the user:

1. Sign in to the intended AWS and GitHub accounts and verify account ID,
   credit eligibility, budgets, remote Terraform state and development stack.
2. Produce a fresh development plan if needed; do not reuse an expired saved
   plan. Reconcile any failed workflow before an apply.
3. Follow the SageMaker handoff to push the image to ECR, upload the model and
   input to S3, then test Batch Transform before creating an endpoint.
4. Add monitoring jobs and MLflow after batch and endpoint parity is verified.

## AWS and security guardrails

- Local AWS access uses browser-issued temporary sessions through `aws login`.
- The current local profile is never copied between computers.
- The initial region is `us-east-1`.
- Every AWS plan is reviewed before apply; destructive changes require explicit
  approval.
- State, saved plans and local variable files are never committed.
- The initial platform excludes NAT Gateway, EKS, RDS, load balancers and
  permanently running EC2 instances.
- Root-backed local access remains accepted temporarily by the owner for the
  bootstrap, but migration to a dedicated IAM Identity Center identity remains
  a security task.
- The repository was verified as public on 2026-09-19, so its configured
  Environment protection is available. If it is later changed to private,
  confirm that the current GitHub plan still enforces required reviewers and
  environment restrictions before enabling the apply workflow.

## Continue from another computer

GitHub Environments and GitHub Codespaces solve different problems:

- a GitHub Environment protects a deployment job with branch rules,
  approvals, variables and secrets;
- a GitHub Codespace is a remote development machine where the repository can
  be edited and its local checks can run.

Recommended portable workflow:

1. Use a Codespace or clone the repository on another trusted computer.
2. Check out the intended Git branch and install the versioned toolchain.
3. Recreate ignored local files from their committed `.example` templates.
4. Authenticate to AWS again using a short-lived login when local AWS access is
   required; never copy login caches or credentials.
5. Keep licensed datasets and trained artifacts outside Git. Reproduce them
   from the handoff instructions or transfer them through an approved private
   channel.
6. Use GitHub Actions OIDC for CI/CD deployment; a developer workstation or
   Codespace should not receive the GitHub deployment role credentials.

A future `.devcontainer/devcontainer.json` can pin Python, Terraform, AWS CLI
and development extensions so a Codespace and a local Dev Container start with
the same toolchain. Docker-heavy integration tests may still be more practical
on a local workstation or GitHub-hosted Actions runner.

## Files intentionally absent from Git

- Licensed/raw and replayed datasets under `data-science/data/`.
- Trained model and local MLflow artifacts under `data-science/artifacts/`.
- Docker images and container runtime data.
- Local `.tfvars`, `.tfbackend`, `.terraform/`, plans and `*.tfstate*` files.
- AWS CLI configuration, login cache and credentials.
- Generated SageMaker model archive, JSON Lines files and example request under
  `dist/sagemaker/`.

## Definition of done for the next AWS phase

- Development state and account identity have been verified with the owner's
  intended session; any new Terraform apply uses a newly reviewed plan.
- The ECR image digest and S3 model version are recorded.
- Batch Transform produces the same scores and row count as local inference.
- A temporary endpoint produces the same score for the example account and is
  removed after the test.
- Inputs, outputs and manifests are stored by period and batch ID.
- Monitoring distinguishes immediate data checks from performance checks that
  need six-month-mature labels.
