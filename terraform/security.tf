# One security group per tier. Each tier only accepts traffic from the tier in front of it.
#   internet -> alb_public -> web -> alb_internal -> app -> db

resource "aws_security_group" "alb_public" {
  name        = "${var.project}-alb-public-sg"
  description = "Public ALB: HTTP from the internet"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${var.project}-alb-public-sg" }
}

resource "aws_security_group" "web" {
  name        = "${var.project}-web-sg"
  description = "Web tier: only from the public ALB"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${var.project}-web-sg" }
}

resource "aws_security_group" "alb_internal" {
  name        = "${var.project}-alb-internal-sg"
  description = "Internal ALB: only from the web tier"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${var.project}-alb-internal-sg" }
}

resource "aws_security_group" "app" {
  name        = "${var.project}-app-sg"
  description = "App tier: only from the internal ALB"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${var.project}-app-sg" }
}

resource "aws_security_group" "db" {
  name        = "${var.project}-db-sg"
  description = "Database: only from the app tier"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${var.project}-db-sg" }
}

# ---- public ALB
resource "aws_vpc_security_group_ingress_rule" "alb_public_http" {
  security_group_id = aws_security_group.alb_public.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
  description       = "HTTP from the internet"
}

resource "aws_vpc_security_group_egress_rule" "alb_public_to_web" {
  security_group_id            = aws_security_group.alb_public.id
  referenced_security_group_id = aws_security_group.web.id
  from_port                    = 80
  to_port                      = 80
  ip_protocol                  = "tcp"
  description                  = "To web tier"
}

# ---- web tier
resource "aws_vpc_security_group_ingress_rule" "web_from_alb" {
  security_group_id            = aws_security_group.web.id
  referenced_security_group_id = aws_security_group.alb_public.id
  from_port                    = 80
  to_port                      = 80
  ip_protocol                  = "tcp"
  description                  = "From public ALB"
}

resource "aws_vpc_security_group_egress_rule" "web_to_internal_alb" {
  security_group_id            = aws_security_group.web.id
  referenced_security_group_id = aws_security_group.alb_internal.id
  from_port                    = 80
  to_port                      = 80
  ip_protocol                  = "tcp"
  description                  = "To internal ALB (app tier)"
}

resource "aws_vpc_security_group_egress_rule" "web_https_out" {
  security_group_id = aws_security_group.web.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "HTTPS out via NAT (image pull, packages, CloudWatch, SSM)"
}

# ---- internal ALB
resource "aws_vpc_security_group_ingress_rule" "alb_internal_from_web" {
  security_group_id            = aws_security_group.alb_internal.id
  referenced_security_group_id = aws_security_group.web.id
  from_port                    = 80
  to_port                      = 80
  ip_protocol                  = "tcp"
  description                  = "From web tier"
}

resource "aws_vpc_security_group_egress_rule" "alb_internal_to_app" {
  security_group_id            = aws_security_group.alb_internal.id
  referenced_security_group_id = aws_security_group.app.id
  from_port                    = 5000
  to_port                      = 5000
  ip_protocol                  = "tcp"
  description                  = "To app tier"
}

# ---- app tier
resource "aws_vpc_security_group_ingress_rule" "app_from_alb" {
  security_group_id            = aws_security_group.app.id
  referenced_security_group_id = aws_security_group.alb_internal.id
  from_port                    = 5000
  to_port                      = 5000
  ip_protocol                  = "tcp"
  description                  = "From internal ALB"
}

resource "aws_vpc_security_group_egress_rule" "app_to_db" {
  security_group_id            = aws_security_group.app.id
  referenced_security_group_id = aws_security_group.db.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "PostgreSQL to the database tier"
}

resource "aws_vpc_security_group_egress_rule" "app_https_out" {
  security_group_id = aws_security_group.app.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "HTTPS out (image pull, Secrets Manager, S3, CloudWatch, SSM)"
}

# ---- database tier (no egress rules at all)
resource "aws_vpc_security_group_ingress_rule" "db_from_app" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.app.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "PostgreSQL from the app tier only"
}
