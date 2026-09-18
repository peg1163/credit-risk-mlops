data "aws_iam_policy_document" "github_actions_terraform_plan_permissions" {
  statement {
    sid    = "ReadTerraformState"
    effect = "Allow"

    actions = [
      "s3:GetObject",
    ]

    resources = [
      "${aws_s3_bucket.terraform_state.arn}/bootstrap/terraform.tfstate",
    ]
  }

  statement {
    sid    = "CheckAndListStateBucket"
    effect = "Allow"

    actions = [
      "s3:ListBucket",
    ]

    resources = [
      aws_s3_bucket.terraform_state.arn,
    ]
  }

  statement {
    sid    = "ManageTerraformStateLock"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]

    resources = [
      "${aws_s3_bucket.terraform_state.arn}/bootstrap/terraform.tfstate.tflock",
    ]
  }

  statement {
    sid    = "ReadStateBucketConfiguration"
    effect = "Allow"

    actions = [
      "s3:Get*",
    ]

    resources = [
      aws_s3_bucket.terraform_state.arn,
    ]
  }

  statement {
    sid    = "ReadManagedIAMResources"
    effect = "Allow"

    actions = [
      "iam:GetOpenIDConnectProvider",
      "iam:ListOpenIDConnectProviderTags",
    ]

    resources = [
      aws_iam_openid_connect_provider.github_actions.arn,
    ]
  }

  statement {
    sid    = "ReadManagedIAMRoles"
    effect = "Allow"

    actions = [
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListRolePolicies",
      "iam:ListRoleTags",
    ]

    resources = [
      aws_iam_role.github_actions_identity_check.arn,
      aws_iam_role.github_actions_terraform_plan.arn,
    ]
  }
}

resource "aws_iam_role_policy" "github_actions_terraform_plan" {
  name   = "${var.project_name}-terraform-plan"
  role   = aws_iam_role.github_actions_terraform_plan.id
  policy = data.aws_iam_policy_document.github_actions_terraform_plan_permissions.json
}
