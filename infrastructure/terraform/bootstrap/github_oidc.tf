locals {
  github_repository_parts         = split("/", var.github_repository)
  github_oidc_subject             = "repo:${local.github_repository_parts[0]}@${var.github_owner_id}/${local.github_repository_parts[1]}@${var.github_repository_id}:ref:refs/heads/${var.github_branch}"
  github_development_oidc_subject = "repo:${local.github_repository_parts[0]}@${var.github_owner_id}/${local.github_repository_parts[1]}@${var.github_repository_id}:environment:development"
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  url = "https://token.actions.githubusercontent.com"

  client_id_list = [
    "sts.amazonaws.com",
  ]
}

data "aws_iam_policy_document" "github_actions_assume_role" {
  statement {
    sid     = "AllowGitHubActionsFromMain"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [local.github_oidc_subject]
    }
  }
}

resource "aws_iam_role" "github_actions_identity_check" {
  name                 = "${var.project_name}-github-actions-identity-check"
  description          = "GitHub Actions OIDC role for authentication checks without AWS service permissions."
  assume_role_policy   = data.aws_iam_policy_document.github_actions_assume_role.json
  max_session_duration = 3600
}

resource "aws_iam_role" "github_actions_terraform_plan" {
  name                 = "${var.project_name}-github-actions-terraform-plan"
  description          = "GitHub Actions OIDC role for read-only Terraform planning."
  assume_role_policy   = data.aws_iam_policy_document.github_actions_assume_role.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "github_actions_development_assume_role" {
  statement {
    sid     = "AllowGitHubActionsDevelopmentEnvironment"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [local.github_development_oidc_subject]
    }
  }
}

resource "aws_iam_role" "github_actions_terraform_apply_development" {
  name                 = "${var.project_name}-github-actions-apply-development"
  description          = "GitHub Actions OIDC role for approved Terraform applies in development."
  assume_role_policy   = data.aws_iam_policy_document.github_actions_development_assume_role.json
  max_session_duration = 3600
}
