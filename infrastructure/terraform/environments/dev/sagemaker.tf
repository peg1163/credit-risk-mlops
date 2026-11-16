# Serverless endpoint with capture inside the container (ADR-0008).

data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

data "aws_region" "current" {}

# The log group exists before the endpoint so its retention is finite from
# the first request, and it survives the endpoint so un-exported capture is
# not lost when the endpoint is deleted.
resource "aws_cloudwatch_log_group" "endpoint" {
  name              = local.capture_log_group
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "sagemaker_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["sagemaker.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sagemaker_execution" {
  name                 = "${local.name_prefix}-sagemaker-execution"
  description          = "Execution role of the serving endpoint: pulls its image, reads models/ and writes its own logs."
  assume_role_policy   = data.aws_iam_policy_document.sagemaker_assume_role.json
  max_session_duration = 3600
}

# ADR-0004: the endpoint reads models/ only and never writes to S3.
data "aws_iam_policy_document" "sagemaker_execution" {
  statement {
    sid       = "PullServingImage"
    actions   = ["ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    resources = [aws_ecr_repository.serving.arn]
  }

  statement {
    sid       = "EcrAuthorization"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid       = "ReadModelArtifacts"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data_lake.arn}/models/*"]
  }

  statement {
    sid       = "WriteEndpointLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
    resources = ["${aws_cloudwatch_log_group.endpoint.arn}:*"]
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

resource "aws_iam_role_policy" "sagemaker_execution" {
  name   = "${local.name_prefix}-sagemaker-execution"
  role   = aws_iam_role.sagemaker_execution.id
  policy = data.aws_iam_policy_document.sagemaker_execution.json
}

# A model fixes the image by digest and the model.tar.gz (ADR-0005). Changing
# either creates a new model and endpoint configuration; the endpoint switches
# to the new configuration, and reverting the variables is the rollback.
resource "aws_sagemaker_model" "serving" {
  count = local.endpoint_enabled ? 1 : 0

  name               = "${local.endpoint_name}-${local.deployment_id}"
  execution_role_arn = aws_iam_role.sagemaker_execution.arn

  primary_container {
    image          = "${aws_ecr_repository.serving.repository_url}@${var.serving_image_digest}"
    mode           = "SingleModel"
    model_data_url = "s3://${aws_s3_bucket.data_lake.id}/${var.model_artifact_key}"

    environment = {
      CAPTURE_ENABLED = "true"
    }
  }

  depends_on = [aws_iam_role_policy.sagemaker_execution]

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_sagemaker_endpoint_configuration" "serving" {
  count = local.endpoint_enabled ? 1 : 0

  name = "${local.endpoint_name}-${local.endpoint_config_id}"

  production_variants {
    variant_name = "AllTraffic"
    model_name   = aws_sagemaker_model.serving[0].name

    # Real-time on one instance when endpoint_instance_type is set; serverless otherwise.
    instance_type          = var.endpoint_instance_type
    initial_instance_count = var.endpoint_instance_type != null ? 1 : null

    dynamic "serverless_config" {
      for_each = var.endpoint_instance_type == null ? [1] : []

      content {
        memory_size_in_mb = var.serverless_memory_mb
        max_concurrency   = var.serverless_max_concurrency
      }
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_sagemaker_endpoint" "serving" {
  count = local.endpoint_enabled ? 1 : 0

  name                 = local.endpoint_name
  endpoint_config_name = aws_sagemaker_endpoint_configuration.serving[0].name

  depends_on = [aws_cloudwatch_log_group.endpoint]
}
