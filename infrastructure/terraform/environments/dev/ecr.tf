# Serving image of the SageMaker endpoint (ADR-0008). Tags follow ADR-0009:
# releases are v<semver>-<sha7>, test builds are dev-<sha7>.
resource "aws_ecr_repository" "serving" {
  name                 = "${local.name_prefix}-sagemaker-inference"
  image_tag_mutability = "IMMUTABLE"

  # The encryption type cannot change after creation (ADR-0004).
  encryption_configuration {
    encryption_type = "AES256"
  }

  image_scanning_configuration {
    scan_on_push = true
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_ecr_lifecycle_policy" "serving" {
  repository = aws_ecr_repository.serving.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Untagged layers left by later pushes"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Test builds pushed by people"
        selection = {
          tagStatus      = "tagged"
          tagPatternList = ["dev-*"]
          countType      = "sinceImagePushed"
          countUnit      = "days"
          countNumber    = 7
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 3
        description  = "Releases: champion and rollback window"
        selection = {
          tagStatus      = "tagged"
          tagPatternList = ["v*"]
          countType      = "imageCountMoreThan"
          countNumber    = var.serving_release_images_to_keep
        }
        action = { type = "expire" }
      },
    ]
  })
}
