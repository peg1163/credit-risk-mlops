variable "project_name" {
  description = "Nombre del proyecto utilizado en el contenido generado."
  type        = string
  default     = "credit-risk-mlops"

  validation {
    condition     = length(trimspace(var.project_name)) > 0
    error_message = "project_name no puede estar vacío."
  }
}
