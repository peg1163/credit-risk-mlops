variable "aws_region" {
  description = "Región AWS utilizada por el bootstrap."
  type        = string
  default     = "us-east-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]+$", var.aws_region))
    error_message = "aws_region debe tener un formato válido, por ejemplo us-east-1."
  }
}

variable "allowed_account_id" {
  description = "ID de la única cuenta AWS donde se permite ejecutar el bootstrap."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[0-9]{12}$", var.allowed_account_id))
    error_message = "allowed_account_id debe contener exactamente 12 dígitos."
  }
}

variable "project_name" {
  description = "Nombre utilizado para identificar los recursos del proyecto."
  type        = string
  default     = "credit-risk-mlops"
}

variable "environment" {
  description = "Entorno administrado por esta configuración."
  type        = string
  default     = "bootstrap"

  validation {
    condition     = contains(["bootstrap", "development", "staging", "production"], var.environment)
    error_message = "environment debe ser bootstrap, development, staging o production."
  }
}
