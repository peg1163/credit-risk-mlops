# One row per monitoring layer of ADR-0006.
locals {
  endpoint_dims = ["EndpointName", local.endpoint_name, "VariantName", "AllTraffic"]
  custom_dims   = ["EndpointName", local.endpoint_name]
  region        = data.aws_region.current.region

  dashboard_rows = [
    {
      title = "1. Disponibilidad"
      widgets = [
        { title = "Canary OK (1 = responde)", stat = "Minimum", period = 600, metrics = [concat([local.metric_namespace, "CanaryOK"], local.custom_dims)] },
        { title = "Errores 4XX / 5XX", stat = "Sum", period = 300, metrics = [concat(["AWS/SageMaker", "Invocation4XXErrors"], local.endpoint_dims), concat(["AWS/SageMaker", "Invocation5XXErrors"], local.endpoint_dims)] },
        { title = "Latencia p90 (microsegundos)", stat = "p90", period = 300, metrics = [concat(["AWS/SageMaker", "ModelLatency"], local.endpoint_dims), concat(["AWS/SageMaker", "OverheadLatency"], local.endpoint_dims)] },
      ]
    },
    {
      title = "2. Captura y tráfico"
      widgets = [
        { title = "Invocaciones (incluye canary)", stat = "Sum", period = 3600, metrics = [concat(["AWS/SageMaker", "Invocations"], local.endpoint_dims)] },
        { title = "Solicitudes reales registradas", stat = "Sum", period = 3600, metrics = [[local.metric_namespace, "RealRequestsLogged"]] },
        { title = "Brecha de captura diaria", stat = "Maximum", period = 86400, metrics = [concat([local.metric_namespace, "CaptureGap"], local.custom_dims), concat([local.metric_namespace, "CapturedRequests"], local.custom_dims)] },
      ]
    },
    {
      title = "3. Calidad del modelo"
      widgets = [
        { title = "PSI máximo y PSI del score", stat = "Maximum", period = 86400, metrics = [concat([local.metric_namespace, "PsiMax"], local.custom_dims), concat([local.metric_namespace, "ScorePsi"], local.custom_dims)] },
        { title = "Score promedio y tasa de decisión", stat = "Average", period = 86400, metrics = [concat([local.metric_namespace, "ScoreMean"], local.custom_dims), concat([local.metric_namespace, "DecisionRate"], local.custom_dims)] },
        { title = "Nulos (pp sobre train) y rechazos", stat = "Maximum", period = 86400, metrics = [concat([local.metric_namespace, "NullRateDeltaMaxPp"], local.custom_dims), concat([local.metric_namespace, "RejectionRate"], local.custom_dims)] },
      ]
    },
  ]

  dashboard_widgets = flatten([
    for row_index, row in local.dashboard_rows : concat(
      [{
        type   = "text"
        x      = 0
        y      = row_index * 7
        width  = 24
        height = 1
        properties = {
          markdown = "## ${row.title}"
        }
      }],
      [for widget_index, widget in row.widgets : {
        type   = "metric"
        x      = widget_index * 8
        y      = row_index * 7 + 1
        width  = 8
        height = 6
        properties = {
          title   = widget.title
          region  = local.region
          view    = "timeSeries"
          stat    = widget.stat
          period  = widget.period
          metrics = widget.metrics
        }
      }]
    )
  ])
}

resource "aws_cloudwatch_dashboard" "endpoint" {
  count = local.endpoint_enabled ? 1 : 0

  dashboard_name = "${local.name_prefix}-endpoint"
  dashboard_body = jsonencode({ widgets = local.dashboard_widgets })
}
