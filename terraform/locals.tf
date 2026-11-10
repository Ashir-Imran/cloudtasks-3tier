data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs          = slice(data.aws_availability_zones.available.names, 0, 2)
  ghcr_owner   = lower(split("/", var.github_repo)[0])
  app_image    = "ghcr.io/${local.ghcr_owner}/cloudtasks-app:${var.image_tag}"
  web_image    = "ghcr.io/${local.ghcr_owner}/cloudtasks-web:${var.image_tag}"
  vpc_resolver = cidrhost(var.vpc_cidr, 2) # Amazon DNS server (VPC base + 2)
}
