output "state_bucket_name" {
  description = "Nombre del bucket S3 utilizado para state remoto."
  value       = aws_s3_bucket.terraform_state.id
}

output "state_bucket_region" {
  description = "Región del bucket de state."
  value       = aws_s3_bucket.terraform_state.region
}

output "state_bucket_versioning" {
  description = "Estado del versionado del bucket."
  value       = aws_s3_bucket_versioning.terraform_state.versioning_configuration[0].status
}
