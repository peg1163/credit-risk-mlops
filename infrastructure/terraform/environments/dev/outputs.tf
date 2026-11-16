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

output "training_repository_url" {
  description = "URL del repositorio ECR de la imagen de entrenamiento (ADR-0010)."
  value       = aws_ecr_repository.training.repository_url
}

output "sagemaker_training_role_arn" {
  description = "ARN del rol de ejecución de los training jobs."
  value       = aws_iam_role.sagemaker_training.arn
}

output "training_dataset_uri" {
  description = "Prefijo S3 donde se sube modeling_dataset.parquet para los training jobs."
  value       = "s3://${aws_s3_bucket.data_lake.id}/${local.training_dataset_prefix}/modeling/"
}

output "mlflow_app_arn" {
  description = "ARN de la MLflow App; usarlo como MLFLOW_TRACKING_URI. null si mlflow_app_enabled es false."
  value       = var.mlflow_app_enabled ? aws_sagemaker_mlflow_app.this[0].arn : null
}
