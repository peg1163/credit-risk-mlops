# Endpoint observability (ADR-0006): canary, daily capture copy, daily quality
# job, alarms and two SNS topics. The Lambda zips are built by
# mlops/monitoring/build_lambdas.py before plan and apply.

locals {
  lambda_build_dir = "${path.module}/.build"

  monitoring_functions = local.endpoint_enabled ? {
    canary = {
      description = "Invokes the serving endpoint with a synthetic request and publishes CanaryOK."
      timeout     = 60
      memory      = 256
      environment = {
        ENDPOINT_NAME  = local.endpoint_name
        CANARY_PAYLOAD = jsonencode(jsondecode(file("${path.module}/../../../../mlops/monitoring/canary_payload.json")))
      }
    }
    capture_export = {
      description = "Copies one UTC day of endpoint capture from CloudWatch Logs to S3 and publishes CaptureGap."
      timeout     = 300
      memory      = 512
      environment = {
        ENDPOINT_NAME     = local.endpoint_name
        DATA_BUCKET       = aws_s3_bucket.data_lake.id
        CAPTURE_LOG_GROUP = aws_cloudwatch_log_group.endpoint.name
      }
    }
    quality = {
      description = "Computes data quality and PSI drift of the endpoint capture."
      timeout     = 300
      memory      = 512
      environment = {
        ENDPOINT_NAME     = local.endpoint_name
        DATA_BUCKET       = aws_s3_bucket.data_lake.id
        DRIFT_WINDOW_DAYS = tostring(var.drift_window_days)
      }
    }
  } : {}

  # The copy runs first; the quality job reads what the copy wrote.
  monitoring_schedules = {
    canary         = var.canary_schedule
    capture_export = "cron(15 0 * * ? *)"
    quality        = "cron(45 0 * * ? *)"
  }

  endpoint_arn = "arn:${data.aws_partition.current.partition}:sagemaker:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:endpoint/${local.endpoint_name}"
}

# --- Notification ----------------------------------------------------------

resource "aws_sns_topic" "alerts" {
  for_each = toset(["critical", "warning"])

  name = "${local.name_prefix}-alerts-${each.key}"
}

data "aws_iam_policy_document" "alerts_topic" {
  for_each = aws_sns_topic.alerts

  statement {
    sid       = "AllowAlarmsAndEvents"
    actions   = ["sns:Publish"]
    resources = [each.value.arn]

    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com", "events.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sns_topic_policy" "alerts" {
  for_each = aws_sns_topic.alerts

  arn    = each.value.arn
  policy = data.aws_iam_policy_document.alerts_topic[each.key].json
}

resource "aws_sns_topic_subscription" "alerts_email" {
  for_each = nonsensitive(try(length(var.alert_email), 0) > 0) ? aws_sns_topic.alerts : {}

  topic_arn = each.value.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# --- Monitoring Lambdas ----------------------------------------------------

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_cloudwatch_log_group" "monitoring" {
  for_each = local.monitoring_functions

  name              = "/aws/lambda/${local.name_prefix}-${replace(each.key, "_", "-")}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "monitoring" {
  for_each = local.monitoring_functions

  name                 = "${local.name_prefix}-${replace(each.key, "_", "-")}"
  description          = each.value.description
  assume_role_policy   = data.aws_iam_policy_document.lambda_assume_role.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "monitoring" {
  for_each = local.monitoring_functions

  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.monitoring[each.key].arn}:*"]
  }

  statement {
    sid       = "PublishEndpointMetrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = [local.metric_namespace]
    }
  }

  dynamic "statement" {
    for_each = each.key == "canary" ? [1] : []

    content {
      sid       = "InvokeServingEndpoint"
      actions   = ["sagemaker:InvokeEndpoint"]
      resources = [local.endpoint_arn]
    }
  }

  dynamic "statement" {
    for_each = each.key == "capture_export" ? [1] : []

    content {
      sid       = "ReadCaptureLogs"
      actions   = ["logs:FilterLogEvents"]
      resources = ["${aws_cloudwatch_log_group.endpoint.arn}:*"]
    }
  }

  dynamic "statement" {
    for_each = each.key == "capture_export" ? [1] : []

    content {
      sid       = "ReadInvocationCount"
      actions   = ["cloudwatch:GetMetricStatistics"]
      resources = ["*"]
    }
  }

  dynamic "statement" {
    for_each = each.key == "capture_export" ? [1] : []

    content {
      sid       = "WriteCapture"
      actions   = ["s3:PutObject"]
      resources = ["${aws_s3_bucket.data_lake.arn}/endpoint-capture/*"]
    }
  }

  dynamic "statement" {
    for_each = each.key == "quality" ? [1] : []

    content {
      sid       = "ReadCaptureAndReference"
      actions   = ["s3:GetObject"]
      resources = ["${aws_s3_bucket.data_lake.arn}/endpoint-capture/*", "${aws_s3_bucket.data_lake.arn}/monitoring/reference/*"]
    }
  }

  # Without ListBucket a missing day returns AccessDenied instead of NoSuchKey.
  dynamic "statement" {
    for_each = each.key == "quality" ? [1] : []

    content {
      sid       = "ListCapture"
      actions   = ["s3:ListBucket"]
      resources = [aws_s3_bucket.data_lake.arn]

      condition {
        test     = "StringLike"
        variable = "s3:prefix"
        values   = ["endpoint-capture/*"]
      }
    }
  }

  dynamic "statement" {
    for_each = each.key == "quality" ? [1] : []

    content {
      sid       = "WriteReports"
      actions   = ["s3:PutObject"]
      resources = ["${aws_s3_bucket.data_lake.arn}/monitoring/endpoint/*"]
    }
  }
}

resource "aws_iam_role_policy" "monitoring" {
  for_each = local.monitoring_functions

  name   = aws_iam_role.monitoring[each.key].name
  role   = aws_iam_role.monitoring[each.key].id
  policy = data.aws_iam_policy_document.monitoring[each.key].json
}

resource "aws_lambda_function" "monitoring" {
  for_each = local.monitoring_functions

  function_name    = "${local.name_prefix}-${replace(each.key, "_", "-")}"
  description      = each.value.description
  role             = aws_iam_role.monitoring[each.key].arn
  runtime          = "python3.13"
  handler          = "${each.key}.handler"
  filename         = "${local.lambda_build_dir}/${each.key}.zip"
  source_code_hash = filebase64sha256("${local.lambda_build_dir}/${each.key}.zip")
  timeout          = each.value.timeout
  memory_size      = each.value.memory

  environment {
    variables = each.value.environment
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.monitoring[each.key].name
  }

  depends_on = [aws_iam_role_policy.monitoring]
}

# --- Schedules -------------------------------------------------------------

data "aws_iam_policy_document" "scheduler_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  count = local.endpoint_enabled ? 1 : 0

  name                 = "${local.name_prefix}-monitoring-scheduler"
  description          = "EventBridge Scheduler role that invokes the monitoring Lambdas."
  assume_role_policy   = data.aws_iam_policy_document.scheduler_assume_role.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "scheduler" {
  count = local.endpoint_enabled ? 1 : 0

  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [for function in aws_lambda_function.monitoring : function.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  count = local.endpoint_enabled ? 1 : 0

  name   = "${local.name_prefix}-monitoring-scheduler"
  role   = aws_iam_role.scheduler[0].id
  policy = data.aws_iam_policy_document.scheduler[0].json
}

resource "aws_scheduler_schedule" "monitoring" {
  for_each = local.monitoring_functions

  name                         = "${local.name_prefix}-${replace(each.key, "_", "-")}"
  schedule_expression          = local.monitoring_schedules[each.key]
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.monitoring[each.key].arn
    role_arn = aws_iam_role.scheduler[0].arn
    input    = jsonencode({})

    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }
  }
}

# --- Layer 1: availability -------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "canary" {
  count = local.endpoint_enabled ? 1 : 0

  alarm_name          = "${local.name_prefix}-endpoint-canary-failed"
  alarm_description   = "The endpoint did not answer the canary in 2 of the last 3 periods. Missing data counts as failure."
  namespace           = local.metric_namespace
  metric_name         = "CanaryOK"
  dimensions          = { EndpointName = local.endpoint_name }
  statistic           = "Minimum"
  period              = 600
  evaluation_periods  = 3
  datapoints_to_alarm = 2
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alerts["critical"].arn]
  ok_actions          = [aws_sns_topic.alerts["critical"].arn]
}

resource "aws_cloudwatch_metric_alarm" "invocation_5xx" {
  count = local.endpoint_enabled ? 1 : 0

  alarm_name          = "${local.name_prefix}-endpoint-5xx"
  alarm_description   = "The model container answered with 5XX errors."
  namespace           = "AWS/SageMaker"
  metric_name         = "Invocation5XXErrors"
  dimensions          = { EndpointName = local.endpoint_name, VariantName = "AllTraffic" }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts["critical"].arn]
}

resource "aws_cloudwatch_metric_alarm" "invocation_4xx" {
  count = local.endpoint_enabled ? 1 : 0

  alarm_name          = "${local.name_prefix}-endpoint-4xx"
  alarm_description   = "Clients are sending requests the contract rejects. Initial threshold; tune after observing real traffic."
  namespace           = "AWS/SageMaker"
  metric_name         = "Invocation4XXErrors"
  dimensions          = { EndpointName = local.endpoint_name, VariantName = "AllTraffic" }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts["warning"].arn]
}

# SageMaker reports ModelLatency and OverheadLatency in microseconds.
resource "aws_cloudwatch_metric_alarm" "latency" {
  for_each = local.endpoint_enabled ? {
    model    = { metric = "ModelLatency", threshold_ms = var.model_latency_p90_threshold_ms }
    overhead = { metric = "OverheadLatency", threshold_ms = var.overhead_latency_p90_threshold_ms }
  } : {}

  alarm_name          = "${local.name_prefix}-endpoint-${each.key}-latency-p90"
  alarm_description   = "p90 of ${each.value.metric} above ${each.value.threshold_ms} ms. OverheadLatency includes cold starts."
  namespace           = "AWS/SageMaker"
  metric_name         = each.value.metric
  dimensions          = { EndpointName = local.endpoint_name, VariantName = "AllTraffic" }
  extended_statistic  = "p90"
  period              = 300
  evaluation_periods  = 3
  datapoints_to_alarm = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = each.value.threshold_ms * 1000
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts["warning"].arn]
}

resource "aws_cloudwatch_event_rule" "endpoint_failed" {
  count = local.endpoint_enabled ? 1 : 0

  name        = "${local.name_prefix}-endpoint-failed"
  description = "The serving endpoint changed to Failed."

  event_pattern = jsonencode({
    source        = ["aws.sagemaker"]
    "detail-type" = ["SageMaker Endpoint State Change"]
    detail = {
      EndpointName   = [local.endpoint_name]
      EndpointStatus = ["FAILED"]
    }
  })
}

resource "aws_cloudwatch_event_target" "endpoint_failed" {
  count = local.endpoint_enabled ? 1 : 0

  rule = aws_cloudwatch_event_rule.endpoint_failed[0].name
  arn  = aws_sns_topic.alerts["critical"].arn
}

resource "aws_cloudwatch_metric_alarm" "monitoring_job_errors" {
  for_each = local.monitoring_functions

  alarm_name          = "${local.name_prefix}-${replace(each.key, "_", "-")}-errors"
  alarm_description   = "The ${each.key} Lambda failed."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.monitoring[each.key].function_name }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts[each.key == "quality" ? "warning" : "critical"].arn]
}

# --- Layer 2: capture and traffic ------------------------------------------

# Counts real requests as they arrive: one line per request carries
# record_index 0 (scored) or null (rejected or failed).
resource "aws_cloudwatch_log_metric_filter" "real_requests" {
  name           = "${local.name_prefix}-real-requests"
  log_group_name = aws_cloudwatch_log_group.endpoint.name
  pattern        = "{ $.event = \"inference_capture\" && $.synthetic IS FALSE && ($.record_index = 0 || $.record_index IS NULL) }"

  metric_transformation {
    name          = "RealRequestsLogged"
    namespace     = local.metric_namespace
    value         = "1"
    unit          = "Count"
    default_value = 0
  }
}

resource "aws_cloudwatch_metric_alarm" "capture_gap" {
  count = local.endpoint_enabled ? 1 : 0

  alarm_name          = "${local.name_prefix}-endpoint-capture-gap"
  alarm_description   = "Invocations minus captured requests for the previous day is above zero, or the copy did not run."
  namespace           = local.metric_namespace
  metric_name         = "CaptureGap"
  dimensions          = { EndpointName = local.endpoint_name }
  statistic           = "Maximum"
  period              = 86400
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alerts["critical"].arn]
}

resource "aws_cloudwatch_metric_alarm" "low_traffic" {
  count = local.endpoint_enabled && var.min_daily_real_requests != null ? 1 : 0

  alarm_name          = "${local.name_prefix}-endpoint-low-traffic"
  alarm_description   = "Fewer than ${coalesce(var.min_daily_real_requests, 0)} real requests in a day."
  namespace           = local.metric_namespace
  metric_name         = "RealRequestsLogged"
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  comparison_operator = "LessThanThreshold"
  threshold           = coalesce(var.min_daily_real_requests, 0)
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alerts["warning"].arn]
}

# --- Layer 3: model quality ------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "quality" {
  for_each = local.endpoint_enabled ? {
    psi-investigate = { metric = "PsiMax", threshold = 0.10, description = "Maximum feature PSI over the rolling window is at least 0.10: investigate." }
    psi-material    = { metric = "PsiMax", threshold = 0.25, description = "Maximum feature PSI over the rolling window is at least 0.25: material drift." }
    score-psi       = { metric = "ScorePsi", threshold = 0.10, description = "Score distribution PSI over the rolling window is at least 0.10." }
    null-rate       = { metric = "NullRateDeltaMaxPp", threshold = 5, description = "A feature null rate is at least 5 percentage points above training." }
    rejection-rate  = { metric = "RejectionRate", threshold = 0.05, description = "At least 5% of real requests were rejected yesterday." }
  } : {}

  alarm_name          = "${local.name_prefix}-endpoint-${each.key}"
  alarm_description   = each.value.description
  namespace           = local.metric_namespace
  metric_name         = each.value.metric
  dimensions          = { EndpointName = local.endpoint_name }
  statistic           = "Maximum"
  period              = 86400
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = each.value.threshold
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts["warning"].arn]
}

# Anomaly detection needs about two weeks of history before it is useful.
resource "aws_cloudwatch_metric_alarm" "score_anomaly" {
  for_each = local.endpoint_enabled ? toset(["ScoreMean", "DecisionRate"]) : toset([])

  alarm_name          = "${local.name_prefix}-endpoint-${lower(each.key)}-anomaly"
  alarm_description   = "${each.key} of real requests left its expected band."
  comparison_operator = "LessThanLowerOrGreaterThanUpperThreshold"
  evaluation_periods  = 1
  threshold_metric_id = "band"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts["warning"].arn]

  metric_query {
    id          = "value"
    return_data = true

    metric {
      namespace   = local.metric_namespace
      metric_name = each.key
      dimensions  = { EndpointName = local.endpoint_name }
      stat        = "Average"
      period      = 86400
    }
  }

  metric_query {
    id          = "band"
    expression  = "ANOMALY_DETECTION_BAND(value, 2)"
    label       = "${each.key} expected band"
    return_data = true
  }
}
