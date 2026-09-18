variable "aws_region" {
  description = "Región AWS del entorno de desarrollo."
  type        = string
  default     = "us-east-1"
}

variable "allowed_account_id" {
  description = "Única cuenta AWS autorizada para este entorno."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[0-9]{12}$", var.allowed_account_id))
    error_message = "allowed_account_id debe contener exactamente 12 dígitos."
  }
}

variable "project_name" {
  description = "Nombre del proyecto utilizado para identificar recursos."
  type        = string
  default     = "credit-risk-mlops"
}

variable "environment" {
  description = "Nombre del entorno."
  type        = string
  default     = "development"

  validation {
    condition     = var.environment == "development"
    error_message = "Este stack administra exclusivamente development."
  }
}
