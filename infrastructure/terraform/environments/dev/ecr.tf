
resource "aws_ecr_repository" "data_lake" {
  name                 = "${var.project_name}-${var.environment}-image-inference"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
  lifecycle {
  prevent_destroy = true
} 

}
resource "aws_ecr_lifecycle_policy" "data_lake" {
  repository = aws_ecr_repository.data_lake.name
  policy     = jsonencode({
    rules = [
  {
    rulePriority = 1
    selection = {
      tagStatus   = "tagged"
      countType   = "imageCountMoreThan"
      countNumber = 10
      
    }
    action = { type = "expire" }
  },
  # segunda regla
]
  })
  lifecycle {
  prevent_destroy = true
  }
}

