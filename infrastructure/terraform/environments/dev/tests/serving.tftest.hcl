# Runs the stack against a mocked AWS provider: no credentials, no cost.
# Run mlops/monitoring/build_lambdas.py first so the Lambda zips exist.

mock_provider "aws" {
  mock_data "aws_region" {
    defaults = {
      region = "us-east-1"
    }
  }

  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
    }
  }

  mock_data "aws_partition" {
    defaults = {
      partition = "aws"
    }
  }

  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::123456789012:role/mock"
    }
  }

  mock_resource "aws_sns_topic" {
    defaults = {
      arn = "arn:aws:sns:us-east-1:123456789012:mock"
    }
  }

  mock_resource "aws_lambda_function" {
    defaults = {
      arn = "arn:aws:lambda:us-east-1:123456789012:function:mock"
    }
  }

  mock_resource "aws_cloudwatch_log_group" {
    defaults = {
      arn = "arn:aws:logs:us-east-1:123456789012:log-group:mock"
    }
  }

  mock_resource "aws_ecr_repository" {
    defaults = {
      arn            = "arn:aws:ecr:us-east-1:123456789012:repository/mock"
      repository_url = "123456789012.dkr.ecr.us-east-1.amazonaws.com/mock"
    }
  }

  mock_resource "aws_s3_bucket" {
    defaults = {
      arn = "arn:aws:s3:::mock"
    }
  }

  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{}"
    }
  }
}

variables {
  allowed_account_id = "123456789012"
}

run "without_image_only_registry_and_topics" {
  command = plan

  # Overrides serving-release.auto.tfvars.json, which holds the deployed release.
  variables {
    serving_image_digest = null
    model_artifact_key   = null
  }

  assert {
    condition     = length(aws_sagemaker_endpoint.serving) == 0 && length(aws_lambda_function.monitoring) == 0
    error_message = "The endpoint and its monitoring must wait for an image digest and a model key."
  }

  assert {
    condition     = aws_ecr_repository.serving.image_tag_mutability == "IMMUTABLE" && aws_ecr_repository.serving.encryption_configuration[0].encryption_type == "AES256"
    error_message = "ECR must use immutable tags and explicit AES256 (ADR-0004, ADR-0009)."
  }

  assert {
    condition     = [for rule in jsondecode(aws_ecr_lifecycle_policy.serving.policy).rules : rule.selection.tagStatus == "tagged" ? rule.selection.tagPatternList[0] : rule.selection.tagStatus] == ["untagged", "dev-*", "v*"]
    error_message = "Lifecycle rules must be untagged, dev-* and v*, in that priority (ADR-0009)."
  }

  assert {
    condition     = jsondecode(aws_ecr_lifecycle_policy.serving.policy).rules[2].selection.countNumber == 10
    error_message = "Releases keep the 10 most recent images (ADR-0009)."
  }

  assert {
    condition     = length(aws_sns_topic.alerts) == 2
    error_message = "Critical and warning topics always exist."
  }
}

run "with_image_and_model_creates_serverless_endpoint" {
  # apply against the mock provider; nothing reaches AWS.
  command = apply

  variables {
    serving_image_digest   = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    model_artifact_key     = "models/version=0.1.0/model.tar.gz"
    endpoint_instance_type = null
  }

  assert {
    condition     = endswith(aws_sagemaker_model.serving[0].primary_container[0].image, "@sha256:0000000000000000000000000000000000000000000000000000000000000000")
    error_message = "The SageMaker Model must reference the image by digest (ADR-0005)."
  }

  assert {
    condition     = aws_sagemaker_endpoint_configuration.serving[0].production_variants[0].serverless_config[0].memory_size_in_mb == 2048
    error_message = "The endpoint must be serverless (ADR-0008)."
  }

  assert {
    condition     = aws_sagemaker_endpoint.serving[0].name == "credit-risk-mlops-development-serving" && aws_cloudwatch_log_group.endpoint.name == "/aws/sagemaker/Endpoints/credit-risk-mlops-development-serving"
    error_message = "The pre-created log group must match the endpoint name."
  }

  assert {
    condition     = toset(keys(aws_lambda_function.monitoring)) == toset(["canary", "capture_export", "quality"])
    error_message = "Canary, capture copy and quality job must exist with the endpoint."
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.canary[0].treat_missing_data == "breaching" && aws_cloudwatch_metric_alarm.capture_gap[0].treat_missing_data == "breaching"
    error_message = "Missing canary or capture-gap data must count as failure (ADR-0006)."
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.latency["model"].threshold == 1000000
    error_message = "Latency thresholds must be converted to microseconds."
  }

  assert {
    condition     = length(aws_cloudwatch_metric_alarm.low_traffic) == 0
    error_message = "The low-traffic alarm stays off until a threshold is chosen."
  }
}

run "with_instance_type_creates_realtime_endpoint" {
  command = apply

  variables {
    serving_image_digest   = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    model_artifact_key     = "models/version=0.1.0/model.tar.gz"
    endpoint_instance_type = "ml.t2.medium"
  }

  assert {
    condition     = aws_sagemaker_endpoint_configuration.serving[0].production_variants[0].instance_type == "ml.t2.medium" && length(aws_sagemaker_endpoint_configuration.serving[0].production_variants[0].serverless_config) == 0
    error_message = "An instance type must produce a real-time variant without serverless_config."
  }
}
