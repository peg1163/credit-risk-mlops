output "data_bucket_name" {
  description = "Nombre del bucket S3 de datos del entorno development."
  value       = aws_s3_bucket.data_lake.id
}

output "data_bucket_arn" {
  description = "ARN del bucket S3 de datos del entorno development."
  value       = aws_s3_bucket.data_lake.arn
}

output "data_bucket_versioning" {
  description = "Estado del versionado del bucket de datos."
  value       = aws_s3_bucket_versioning.data_lake.versioning_configuration[0].status
}

output "serving_repository_url" {
  description = "URL del repositorio ECR de la imagen de serving; el image URI es <url>@<digest>."
  value       = aws_ecr_repository.serving.repository_url
}

output "serving_repository_name" {
  description = "Nombre del repositorio ECR de la imagen de serving."
  value       = aws_ecr_repository.serving.name
}

output "endpoint_name" {
  description = "Nombre del endpoint serverless; null hasta definir imagen y modelo."
  value       = local.endpoint_enabled ? aws_sagemaker_endpoint.serving[0].name : null
}

output "endpoint_config_name" {
  description = "Configuración vigente del endpoint; registrarla en el manifiesto de promoción (ADR-0005)."
  value       = local.endpoint_enabled ? aws_sagemaker_endpoint_configuration.serving[0].name : null
}

output "sagemaker_execution_role_arn" {
  description = "ARN del rol de ejecución del endpoint."
  value       = aws_iam_role.sagemaker_execution.arn
}

output "endpoint_capture_log_group" {
  description = "Grupo de logs donde el contenedor escribe la captura."
  value       = aws_cloudwatch_log_group.endpoint.name
}

output "alert_topic_arns" {
  description = "Tópicos SNS crítico y de aviso."
  value       = { for key, topic in aws_sns_topic.alerts : key => topic.arn }
}
