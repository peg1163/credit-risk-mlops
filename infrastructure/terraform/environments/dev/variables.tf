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

variable "serving_release_images_to_keep" {
  description = "Imágenes de release (tags v*) que conserva ECR; cubre el campeón y la ventana de rollback (ADR-0009)."
  type        = number
  default     = 10

  validation {
    condition     = var.serving_release_images_to_keep >= 3
    error_message = "Conservar al menos 3 imágenes de release para poder hacer rollback."
  }
}

variable "serving_image_digest" {
  description = "Digest sha256 de la imagen de serving en ECR. Mientras sea null no se crea el endpoint."
  type        = string
  default     = null

  validation {
    condition     = var.serving_image_digest == null || can(regex("^sha256:[0-9a-f]{64}$", var.serving_image_digest))
    error_message = "serving_image_digest debe tener el formato sha256:<64 hex>."
  }
}

variable "model_artifact_key" {
  description = "Clave S3 del model.tar.gz dentro del bucket de datos, bajo models/. Mientras sea null no se crea el endpoint."
  type        = string
  default     = null

  validation {
    condition     = var.model_artifact_key == null || can(regex("^models/.+\\.tar\\.gz$", var.model_artifact_key))
    error_message = "model_artifact_key debe estar bajo models/ y terminar en .tar.gz."
  }
}

variable "serverless_memory_mb" {
  description = "Memoria del endpoint serverless."
  type        = number
  default     = 2048

  validation {
    condition     = contains([1024, 2048, 3072, 4096, 5120, 6144], var.serverless_memory_mb)
    error_message = "serverless_memory_mb debe ser 1024, 2048, 3072, 4096, 5120 o 6144."
  }
}

variable "serverless_max_concurrency" {
  description = "Invocaciones simultáneas máximas del endpoint serverless."
  type        = number
  default     = 2

  validation {
    condition     = var.serverless_max_concurrency >= 1 && var.serverless_max_concurrency <= 200
    error_message = "serverless_max_concurrency debe estar entre 1 y 200."
  }
}

variable "log_retention_days" {
  description = "Retención de los logs del endpoint y de las Lambdas; la copia permanente de la captura vive en S3 (ADR-0004)."
  type        = number
  default     = 30
}

variable "canary_schedule" {
  description = "Frecuencia del canary del endpoint."
  type        = string
  default     = "rate(10 minutes)"
}

variable "drift_window_days" {
  description = "Días de la ventana móvil para el PSI diario (ADR-0006)."
  type        = number
  default     = 7
}

variable "model_latency_p90_threshold_ms" {
  description = "Umbral del p90 de ModelLatency en milisegundos; ajustar tras observar tráfico real."
  type        = number
  default     = 1000
}

variable "overhead_latency_p90_threshold_ms" {
  description = "Umbral del p90 de OverheadLatency (incluye arranques en frío) en milisegundos."
  type        = number
  default     = 10000
}

variable "min_daily_real_requests" {
  description = "Alarma de tráfico bajo: mínimo de solicitudes reales por día. null desactiva la alarma."
  type        = number
  default     = null
}

variable "alert_email" {
  description = "Correo suscrito a los dos tópicos SNS. No se versiona: secreto ALERT_EMAIL en GitHub o TF_VAR_alert_email en local. Vacío no crea suscripción."
  type        = string
  default     = null
  sensitive   = true
}
