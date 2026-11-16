# Permissions for the serving endpoint and its monitoring in development
# (ADR-0006, ADR-0008, ADR-0009). Every mutable resource is scoped to names
# that start with the development prefix.

data "aws_caller_identity" "current" {}

locals {
  development_prefix = "${var.project_name}-development"
  account_id         = data.aws_caller_identity.current.account_id
  region             = var.aws_region
  serving_repository = "${local.development_prefix}-sagemaker-inference"
}

# Read access for plan and for the refresh that precedes every apply. These
# Describe/Get/List actions mostly lack resource-level permissions.
data "aws_iam_policy_document" "development_serving_read" {
  statement {
    sid    = "ReadServingAndMonitoring"
    effect = "Allow"

    actions = [
      "cloudwatch:DescribeAlarms",
      "cloudwatch:GetDashboard",
      "cloudwatch:ListTagsForResource",
      "ecr:DescribeRepositories",
      "ecr:GetLifecyclePolicy",
      "ecr:GetRepositoryPolicy",
      "ecr:ListTagsForResource",
      "events:DescribeRule",
      "events:ListTagsForResource",
      "events:ListTargetsByRule",
      "lambda:GetFunction",
      "lambda:GetFunctionCodeSigningConfig",
      "lambda:GetPolicy",
      "lambda:ListTags",
      "lambda:ListVersionsByFunction",
      "logs:DescribeLogGroups",
      "logs:DescribeMetricFilters",
      "logs:ListTagsForResource",
      "logs:ListTagsLogGroup",
      "sagemaker:DescribeEndpoint",
      "sagemaker:DescribeEndpointConfig",
      "sagemaker:DescribeModel",
      "sagemaker:ListTags",
      "scheduler:GetSchedule",
      "scheduler:ListTagsForResource",
      "sns:GetSubscriptionAttributes",
      "sns:GetTopicAttributes",
      "sns:ListSubscriptionsByTopic",
      "sns:ListTagsForResource",
    ]

    resources = ["*"]
  }

  statement {
    sid    = "ReadDevelopmentRoles"
    effect = "Allow"

    actions = [
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:ListRolePolicies",
      "iam:ListRoleTags",
    ]

    resources = ["arn:aws:iam::${local.account_id}:role/${local.development_prefix}-*"]
  }
}

resource "aws_iam_policy" "development_serving_read" {
  name        = "${var.project_name}-development-serving-read"
  description = "Read the development serving endpoint and its monitoring."
  policy      = data.aws_iam_policy_document.development_serving_read.json
}

resource "aws_iam_role_policy_attachment" "plan_development_serving_read" {
  role       = aws_iam_role.github_actions_terraform_plan.name
  policy_arn = aws_iam_policy.development_serving_read.arn
}

resource "aws_iam_role_policy_attachment" "apply_development_serving_read" {
  role       = aws_iam_role.github_actions_terraform_apply_development.name
  policy_arn = aws_iam_policy.development_serving_read.arn
}

data "aws_iam_policy_document" "development_serving_manage" {
  statement {
    sid    = "ManageServingRepository"
    effect = "Allow"

    actions = [
      "ecr:CreateRepository",
      "ecr:DeleteLifecyclePolicy",
      "ecr:DeleteRepository",
      "ecr:PutImageScanningConfiguration",
      "ecr:PutImageTagMutability",
      "ecr:PutLifecyclePolicy",
      "ecr:TagResource",
      "ecr:UntagResource",
    ]

    resources = ["arn:aws:ecr:${local.region}:${local.account_id}:repository/${local.development_prefix}-*"]
  }

  statement {
    sid    = "ManageServingEndpoint"
    effect = "Allow"

    actions = [
      "sagemaker:AddTags",
      "sagemaker:CreateEndpoint",
      "sagemaker:CreateEndpointConfig",
      "sagemaker:CreateModel",
      "sagemaker:DeleteEndpoint",
      "sagemaker:DeleteEndpointConfig",
      "sagemaker:DeleteModel",
      "sagemaker:DeleteTags",
      "sagemaker:UpdateEndpoint",
    ]

    resources = [
      "arn:aws:sagemaker:${local.region}:${local.account_id}:model/${local.development_prefix}-*",
      "arn:aws:sagemaker:${local.region}:${local.account_id}:endpoint-config/${local.development_prefix}-*",
      "arn:aws:sagemaker:${local.region}:${local.account_id}:endpoint/${local.development_prefix}-*",
    ]
  }

  statement {
    sid    = "ManageDevelopmentRoles"
    effect = "Allow"

    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:DeleteRolePolicy",
      "iam:PutRolePolicy",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:UpdateAssumeRolePolicy",
      "iam:UpdateRole",
      "iam:UpdateRoleDescription",
    ]

    resources = ["arn:aws:iam::${local.account_id}:role/${local.development_prefix}-*"]
  }

  statement {
    sid       = "PassDevelopmentRoles"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${local.account_id}:role/${local.development_prefix}-*"]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com", "sagemaker.amazonaws.com", "scheduler.amazonaws.com"]
    }
  }

  statement {
    sid    = "ManageMonitoringFunctions"
    effect = "Allow"

    actions = [
      "lambda:CreateFunction",
      "lambda:DeleteFunction",
      "lambda:TagResource",
      "lambda:UntagResource",
      "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration",
    ]

    resources = ["arn:aws:lambda:${local.region}:${local.account_id}:function:${local.development_prefix}-*"]
  }

  statement {
    sid    = "ManageLogGroups"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:DeleteLogGroup",
      "logs:DeleteMetricFilter",
      "logs:DeleteRetentionPolicy",
      "logs:PutMetricFilter",
      "logs:PutRetentionPolicy",
      "logs:TagLogGroup",
      "logs:TagResource",
      "logs:UntagLogGroup",
      "logs:UntagResource",
    ]

    resources = [
      "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/sagemaker/Endpoints/${local.development_prefix}-*",
      "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${local.development_prefix}-*",
    ]
  }

  statement {
    sid    = "ManageAlarmsAndDashboards"
    effect = "Allow"

    actions = [
      "cloudwatch:DeleteAlarms",
      "cloudwatch:DeleteDashboards",
      "cloudwatch:PutDashboard",
      "cloudwatch:PutMetricAlarm",
      "cloudwatch:TagResource",
      "cloudwatch:UntagResource",
    ]

    resources = [
      "arn:aws:cloudwatch:${local.region}:${local.account_id}:alarm:${local.development_prefix}-*",
      "arn:aws:cloudwatch::${local.account_id}:dashboard/${local.development_prefix}-*",
    ]
  }

  statement {
    sid    = "ManageAlertTopics"
    effect = "Allow"

    actions = [
      "sns:CreateTopic",
      "sns:DeleteTopic",
      "sns:SetTopicAttributes",
      "sns:Subscribe",
      "sns:TagResource",
      "sns:Unsubscribe",
      "sns:UntagResource",
    ]

    resources = ["arn:aws:sns:${local.region}:${local.account_id}:${local.development_prefix}-*"]
  }

  statement {
    sid    = "ManageSchedulesAndRules"
    effect = "Allow"

    actions = [
      "events:DeleteRule",
      "events:PutRule",
      "events:PutTargets",
      "events:RemoveTargets",
      "events:TagResource",
      "events:UntagResource",
      "scheduler:CreateSchedule",
      "scheduler:DeleteSchedule",
      "scheduler:TagResource",
      "scheduler:UntagResource",
      "scheduler:UpdateSchedule",
    ]

    resources = [
      "arn:aws:events:${local.region}:${local.account_id}:rule/${local.development_prefix}-*",
      "arn:aws:scheduler:${local.region}:${local.account_id}:schedule/default/${local.development_prefix}-*",
    ]
  }
}

resource "aws_iam_policy" "development_serving_manage" {
  name        = "${var.project_name}-development-serving-manage"
  description = "Create, change and delete the development serving endpoint and its monitoring."
  policy      = data.aws_iam_policy_document.development_serving_manage.json
}

resource "aws_iam_role_policy_attachment" "apply_development_serving_manage" {
  role       = aws_iam_role.github_actions_terraform_apply_development.name
  policy_arn = aws_iam_policy.development_serving_manage.arn
}

# Pushes release images of the serving image from main (ADR-0009). It can
# read the deployed endpoint to verify the rollback window before a push.
resource "aws_iam_role" "github_actions_ecr_push_development" {
  name                 = "${var.project_name}-github-actions-ecr-push-development"
  description          = "GitHub Actions OIDC role that pushes release serving images from main."
  assume_role_policy   = data.aws_iam_policy_document.github_actions_assume_role.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "github_actions_ecr_push_development" {
  statement {
    sid       = "EcrAuthorization"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "PushServingImage"
    effect = "Allow"

    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]

    resources = ["arn:aws:ecr:${local.region}:${local.account_id}:repository/${local.serving_repository}"]
  }

  statement {
    sid    = "ReadDeployedImage"
    effect = "Allow"

    actions = [
      "sagemaker:DescribeEndpoint",
      "sagemaker:DescribeEndpointConfig",
      "sagemaker:DescribeModel",
    ]

    resources = [
      "arn:aws:sagemaker:${local.region}:${local.account_id}:model/${local.development_prefix}-*",
      "arn:aws:sagemaker:${local.region}:${local.account_id}:endpoint-config/${local.development_prefix}-*",
      "arn:aws:sagemaker:${local.region}:${local.account_id}:endpoint/${local.development_prefix}-*",
    ]
  }
}

resource "aws_iam_role_policy" "github_actions_ecr_push_development" {
  name   = "${var.project_name}-ecr-push-development"
  role   = aws_iam_role.github_actions_ecr_push_development.id
  policy = data.aws_iam_policy_document.github_actions_ecr_push_development.json
}
