locals {
  name_prefix   = "${var.project_name}-${var.environment}"
  endpoint_name = "${local.name_prefix}-serving"

  # The endpoint exists only after an image is in ECR and a model is in S3.
  endpoint_enabled = var.serving_image_digest != null && var.model_artifact_key != null

  # Short identifier of the image and model pair; a new pair means a new
  # SageMaker Model and EndpointConfig (ADR-0005).
  deployment_id = local.endpoint_enabled ? substr(sha1("${var.serving_image_digest}|${var.model_artifact_key}"), 0, 10) : null

  capture_log_group = "/aws/sagemaker/Endpoints/${local.endpoint_name}"
  metric_namespace  = "CreditRisk/Endpoint"
}
