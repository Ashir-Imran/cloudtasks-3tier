variable "region" {
  description = "AWS region"
  type        = string
  default     = "ap-south-1"
}

variable "project" {
  description = "Name prefix for all resources"
  type        = string
  default     = "cloudtasks"
}

variable "vpc_cidr" {
  description = "CIDR block of the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "github_repo" {
  description = "GitHub repository (owner/name, exact case) - used for the image names and the CI/CD role"
  type        = string
  default     = "Ashir-Imran/cloudtasks-3tier"
}

variable "image_tag" {
  description = "Docker image tag the servers pull from GHCR"
  type        = string
  default     = "latest"
}

variable "instance_type" {
  description = "EC2 instance type for the web and app tiers"
  type        = string
  default     = "t3.micro"
}

variable "asg_min" {
  description = "Minimum (and starting) number of instances per tier. 2 = one per Availability Zone"
  type        = number
  default     = 2
  validation {
    condition     = var.asg_min >= 1
    error_message = "asg_min must be at least 1."
  }
}

variable "asg_max" {
  description = "Maximum number of instances per tier"
  type        = number
  default     = 4
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_multi_az" {
  description = "RDS Multi-AZ (automatic failover). Doubles the database cost; set false to save credits"
  type        = bool
  default     = true
}

variable "db_name" {
  type    = string
  default = "tasksdb"
}

variable "db_username" {
  type    = string
  default = "appuser"
}
