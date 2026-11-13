# WIP (en aprendizaje): repositorio ECR para la imagen de inferencia SageMaker.
# Comentado hasta corregir:
#   - image_tag_mutability / filtros de exclusion vacios
#   - repository debe referenciar el nombre del repositorio, no registry_id
#   - permisos ECR en los roles de GitHub Actions (bootstrap)
/*
resource "aws_ecr_repository" "data_lake" {
  name                 = "${var.project_name}-${var.environment}-image-inference"
  image_tag_mutability = "IMMUTABLE_WITH_EXCLUSION"
  image_scanning_configuration {
    scan_on_push = true
  }
  image_tag_mutability_exclusion_filter {
    filter  = " "
    filter_type =  ""
  }
  image_tag_mutability_exclusion_filter {
    filter = ""
    filter_type = ""
  }
}
resource "aws_ecr_lifecycle_policy" "data_lake" {
  repository = aws_ecr_repository.data_lake.registry_id
  policy     = jsonencode(
{
  "rules": [
    {
      "rulePriority": 1,
      "description": "Expire images older than 14 days",
      "selection": {
        "tagStatus": "untagged",
        "countType": "sinceImagePushed",
        "countUnit": "days",
        "countNumber": 14
      },
      "action": {
        "type": "expire"
      }
    }
  ]
}
  )
}
*/
