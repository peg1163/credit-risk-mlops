# Infrastructure workspace

Terraform is split by responsibility and state boundary:

- `terraform/lab-local`: local learning stack; it does not use AWS.
- `terraform/bootstrap`: remote state, GitHub OIDC and CI/CD IAM roles.
- `terraform/environments/dev`: application infrastructure for development.

The bootstrap is deployed first because environments depend on its backend and
OIDC roles. It is not a preproduction copy of an environment: it is the
administrative foundation used by all environments.

Local variable, backend, plan and state files are ignored. Start from the
committed `.example` files and never commit credentials, account identifiers,
bucket names or role ARNs.

Cost and destroy procedures must be reviewed before applying resources. A plan
that contains unexpected replacements or deletions must not be applied.
