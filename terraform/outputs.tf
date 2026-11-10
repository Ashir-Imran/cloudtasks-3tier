output "app_url" {
  description = "Open this in a browser (wait ~6-10 minutes after apply for the servers to boot)"
  value       = "http://${aws_lb.public.dns_name}"
}

output "rds_endpoint" {
  value = aws_db_instance.main.address
}

output "s3_bucket" {
  value = aws_s3_bucket.uploads.bucket
}

output "web_asg_name" {
  value = aws_autoscaling_group.web.name
}

output "app_asg_name" {
  value = aws_autoscaling_group.app.name
}

output "github_actions_role_arn" {
  description = "Put this in the GitHub secret AWS_ROLE_ARN (used by the deploy pipeline)"
  value       = aws_iam_role.github_deploy.arn
}
