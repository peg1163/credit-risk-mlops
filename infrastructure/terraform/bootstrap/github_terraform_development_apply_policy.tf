
locals {
  development_state_key          = "environments/dev/terraform.tfstate"
  development_bucket_arn_pattern = "arn:aws:s3:::${var.project_name}-development-data-*"
}

data "aws_iam_policy_document" "github_actions_terraform_apply_development_permissions" {
  statement {
    sid    = "CheckTerraformStateBucket"
    effect = "Allow"

    actions = [
      "s3:ListBucket",
    ]

    resources = [
      aws_s3_bucket.terraform_state.arn,
    ]
  }

  statement {
    sid    = "ReadWriteDevelopmentState"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]

    resources = [
      "${aws_s3_bucket.terraform_state.arn}/${local.development_state_key}",
    ]
  }

  statement {
    sid    = "ManageDevelopmentStateLock"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]

    resources = [
      "${aws_s3_bucket.terraform_state.arn}/${local.development_state_key}.tflock",
    ]
  }

  statement {
    sid    = "ManageDevelopmentDataBucket"
    effect = "Allow"

    actions = [
      "s3:CreateBucket",
      "s3:DeleteBucket",
      "s3:DeleteBucketPolicy",
      "s3:DeleteBucketTagging",
      "s3:DeleteBucketWebsite",
      "s3:DeleteLifecycleConfiguration",
      "s3:DeleteReplicationConfiguration",
      "s3:GetBucket*",
      "s3:GetEncryptionConfiguration",
      "s3:GetLifecycleConfiguration",
      "s3:GetObjectLockConfiguration",
      "s3:GetReplicationConfiguration",
      "s3:ListBucket",
      "s3:PutBucket*",
      "s3:PutEncryptionConfiguration",
      "s3:PutLifecycleConfiguration",
      "s3:PutObjectLockConfiguration",
      "s3:PutReplicationConfiguration",
    ]

    resources = [
      local.development_bucket_arn_pattern,
    ]
  }
}

resource "aws_iam_role_policy" "github_actions_terraform_apply_development" {
  name   = "${var.project_name}-terraform-apply-development"
  role   = aws_iam_role.github_actions_terraform_apply_development.id
  policy = data.aws_iam_policy_document.github_actions_terraform_apply_development_permissions.json
}
