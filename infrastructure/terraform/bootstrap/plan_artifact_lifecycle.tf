resource "aws_s3_bucket_lifecycle_configuration" "terraform_plan_artifacts" {
  bucket = aws_s3_bucket.terraform_state.id

  depends_on = [
    aws_s3_bucket_versioning.terraform_state,
  ]

  rule {
    id     = "expire-temporary-terraform-plans"
    status = "Enabled"

    filter {
      prefix = "plans/"
    }

    expiration {
      days = 2
    }

    noncurrent_version_expiration {
      noncurrent_days = 2
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}