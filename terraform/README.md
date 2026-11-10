# Terraform - CloudTasks on AWS (ap-south-1)

```
Internet -> public ALB -> Web ASG (Nginx, private subnets)
                              -> internal ALB -> App ASG (Flask, private subnets)
                                                    -> RDS PostgreSQL (isolated subnets, Multi-AZ)
                                                    -> S3 (via gateway endpoint)
```

| Subnet tier | CIDR | Internet route |
|---|---|---|
| public (ALB, NAT) x2 | 10.0.1.0/24, 10.0.2.0/24 | Internet Gateway |
| web x2 | 10.0.11.0/24, 10.0.12.0/24 | via NAT (outbound only) |
| app x2 | 10.0.21.0/24, 10.0.22.0/24 | via NAT (outbound only) |
| db x2 | 10.0.31.0/24, 10.0.32.0/24 | none |

## Use
```bash
terraform init
terraform plan            # free: shows what will be created
terraform apply           # costs money from here (about $4-6 per day)
terraform output app_url
terraform destroy         # stops all charges
```
Servers need ~6-10 minutes after `apply` to boot, pull images and pass health checks.

Cheaper: `terraform apply -var="db_multi_az=false" -var="asg_min=1"`.
