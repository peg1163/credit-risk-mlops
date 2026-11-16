# Training jobs and experiment tracking in SageMaker (ADR-0010).
#
# - The training image lives in its own repository with the ADR-0009 tags.
# - A training job reads datasets/, writes models/training-jobs/ and logs to
#   the MLflow App; it cannot touch the champion's models/version=*/ keys.
# - The MLflow App is serverless and has no hourly charge: only its artifacts
#   in s3://<bucket>/mlflow/ cost storage.

resource "aws_ecr_repository" "training" {
  name                 = "${local.name_prefix}-sagemaker-training"
  image_tag_mutability = "IMMUTABLE"

  encryption_configuration {
    encryption_type = "AES256"
  }

  image_scanning_configuration {
    scan_on_push = true
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_ecr_lifecycle_policy" "training" {
  repository = aws_ecr_repository.training.name
  policy     = local.ecr_lifecycle_policy
}

# SageMaker writes every training job to this fixed group; managing it here
# keeps its retention finite.
resource "aws_cloudwatch_log_group" "training_jobs" {
  name              = "/aws/sagemaker/TrainingJobs"
  retention_in_days = var.log_retention_days
}

# --- MLflow App ---------------------------------------------------------------

resource "aws_iam_role" "mlflow_app" {
  count = var.mlflow_app_enabled ? 1 : 0

  name                 = "${local.name_prefix}-mlflow-app"
  description          = "Service role of the SageMaker MLflow App: reads and writes its artifact store only."
  assume_role_policy   = data.aws_iam_policy_document.sagemaker_assume_role.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "mlflow_app" {
  statement {
    sid       = "ArtifactStoreObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.data_lake.arn}/${local.mlflow_artifact_prefix}/*"]
  }

  statement {
    sid       = "ArtifactStoreListing"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.data_lake.arn]
  }
}

resource "aws_iam_role_policy" "mlflow_app" {
  count = var.mlflow_app_enabled ? 1 : 0

  name   = "${local.name_prefix}-mlflow-app"
  role   = aws_iam_role.mlflow_app[0].id
  policy = data.aws_iam_policy_document.mlflow_app.json
}

resource "aws_sagemaker_mlflow_app" "this" {
  count = var.mlflow_app_enabled ? 1 : 0

  name               = local.name_prefix
  artifact_store_uri = "s3://${aws_s3_bucket.data_lake.id}/${local.mlflow_artifact_prefix}"
  role_arn           = aws_iam_role.mlflow_app[0].arn

  # Promotion goes through serving-release.auto.tfvars.json (ADR-0005), not
  # through the SageMaker Model Registry.
  model_registration_mode         = "AutoModelRegistrationDisabled"
  weekly_maintenance_window_start = "Sun:04:00"

  depends_on = [aws_iam_role_policy.mlflow_app]
}

# --- Training execution role ---------------------------------------------------

resource "aws_iam_role" "sagemaker_training" {
  name                 = "${local.name_prefix}-sagemaker-training"
  description          = "Execution role of training jobs: reads datasets/, writes models/training-jobs/ and logs to MLflow."
  assume_role_policy   = data.aws_iam_policy_document.sagemaker_assume_role.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "sagemaker_training" {
  statement {
    sid       = "PullTrainingImage"
    actions   = ["ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    resources = [aws_ecr_repository.training.arn]
  }

  statement {
    sid       = "EcrAuthorization"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid       = "ReadDatasets"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data_lake.arn}/${local.training_dataset_prefix}/*"]
  }

  statement {
    sid       = "ListTrainingPrefixes"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data_lake.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${local.training_dataset_prefix}/*", "${local.training_output_prefix}/*", "${local.mlflow_artifact_prefix}/*"]
    }
  }

  statement {
    sid       = "WriteTrainingOutput"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.data_lake.arn}/${local.training_output_prefix}/*"]
  }

  # The MLflow client uploads artifacts to the store directly.
  statement {
    sid       = "MlflowArtifacts"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.data_lake.arn}/${local.mlflow_artifact_prefix}/*"]
  }

  dynamic "statement" {
    for_each = var.mlflow_app_enabled ? [1] : []

    content {
      sid       = "MlflowTracking"
      actions   = ["sagemaker:CallMlflowAppApi"]
      resources = [aws_sagemaker_mlflow_app.this[0].arn]
    }
  }

  statement {
    sid       = "WriteTrainingLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
    resources = ["${aws_cloudwatch_log_group.training_jobs.arn}:*"]
  }

  statement {
    sid       = "PublishSageMakerMetrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]

    condition {
      test     = "StringLike"
      variable = "cloudwatch:namespace"
      values   = ["/aws/sagemaker/*"]
    }
  }
}

resource "aws_iam_role_policy" "sagemaker_training" {
  name   = "${local.name_prefix}-sagemaker-training"
  role   = aws_iam_role.sagemaker_training.id
  policy = data.aws_iam_policy_document.sagemaker_training.json
}
