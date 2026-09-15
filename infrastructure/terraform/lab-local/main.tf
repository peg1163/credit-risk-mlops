resource "local_file" "learning" {
  filename             = "${path.module}/terraform-generated.txt"
  content              = "Project ${var.project_name} infrastructure managed by Terraform.\n"
  file_permission      = "0644"
  directory_permission = "0755"
}
