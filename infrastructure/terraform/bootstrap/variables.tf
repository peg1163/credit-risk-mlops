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

variable "github_repository" {
  description = "Repositorio autorizado para asumir el rol OIDC, con formato owner/repository."
  type        = string
  default     = "peg1163/credit-risk-mlops"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository debe tener el formato owner/repository."
  }
}

variable "github_branch" {
  description = "Única rama autorizada para asumir el rol OIDC inicial."
  type        = string
  default     = "main"

  validation {
    condition     = can(regex("^[A-Za-z0-9._/-]+$", var.github_branch))
    error_message = "github_branch contiene caracteres no válidos."
  }
}

variable "github_owner_id" {
  description = "ID inmutable del propietario del repositorio en GitHub."
  type        = string
  default     = "92898224"

  validation {
    condition     = can(regex("^[0-9]+$", var.github_owner_id))
    error_message = "github_owner_id debe contener únicamente dígitos."
  }
}

variable "github_repository_id" {
  description = "ID inmutable del repositorio en GitHub."
  type        = string
  default     = "1360977016"

  validation {
    condition     = can(regex("^[0-9]+$", var.github_repository_id))
    error_message = "github_repository_id debe contener únicamente dígitos."
  }
}
