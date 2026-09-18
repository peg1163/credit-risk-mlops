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
