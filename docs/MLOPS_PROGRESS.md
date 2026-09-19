# MLOps implementation progress

Last reviewed: 2026-09-19

This document is the restart point for continuing the project from another
computer or a new working session. It intentionally excludes credentials, AWS
account identifiers, role ARNs, bucket names, email addresses and Terraform
state.

## Current phase

The Data Science handoff and local containerized monthly pipeline are complete.
The AWS foundation is deployed and its Terraform state is stored remotely. The
current work adds an approved deployment path for the development stack.

The development data stack is defined and produces a reviewed seven-resource
create plan, but it has not yet been applied. No managed runtime, scheduler or
online inference service has been deployed.

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

## Work in progress

Branch: `feat/terraform-development-deploy`

Unapplied bootstrap changes:

- allow the plan role to upload saved plans only under
  `plans/development/*` in the private state bucket;
- allow the approved development-apply role to read and delete only those
  saved plans;
- expire temporary plans and their noncurrent versions after two days.

Terraform formatting and validation pass. The next gate is reviewing a saved
bootstrap plan. Expected summary: one lifecycle resource added, two IAM inline
policies changed, and zero resources destroyed. Do not apply if the result
differs.

After that bootstrap update, create the development deployment workflow:

1. the plan job authenticates with the read-only plan role;
2. it creates a saved binary plan and stores it privately in S3;
3. the apply job targets the protected `development` GitHub Environment;
4. after manual approval it assumes the development-apply role;
5. it downloads, verifies and applies the same saved plan;
6. it removes the temporary plan after completion.

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
- Because the repository is now private, confirm that the current GitHub plan
  enforces the required reviewer and environment restrictions before enabling
  the apply workflow. Do not treat a visible Environment as proof that its
  protection rules are active.

## Continue from another computer

GitHub Environments and GitHub Codespaces solve different problems:

- a GitHub Environment protects a deployment job with branch rules,
  approvals, variables and secrets;
- a GitHub Codespace is a remote development machine where the repository can
  be edited and its local checks can run.

Recommended portable workflow:

1. Use a Codespace or clone the repository on another trusted computer.
2. Check out the active feature branch and install the versioned toolchain.
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

## Definition of done for the current phase

- Bootstrap permission changes produce no destructive actions and are applied.
- The private-repository GitHub Environment protection behavior is verified.
- Development `plan` and approved `apply` use different OIDC roles.
- Apply consumes the exact saved plan rather than regenerating it.
- The development S3 foundation is deployed from GitHub Actions.
- A subsequent development plan reports no changes.
- Recovery and cleanup behavior is documented and tested.
