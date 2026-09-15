output "generated_file_path" {
  description = "Ruta del archivo administrado por Terraform."
  value       = local_file.learning.filename
}

output "generated_content_sha256" {
  description = "Hash SHA-256 del contenido generado."
  value       = local_file.learning.content_sha256
}
