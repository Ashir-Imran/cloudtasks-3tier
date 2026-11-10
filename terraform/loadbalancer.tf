# ---------------------------------------------------------------- public ALB -> web tier
resource "aws_lb" "public" {
  name                       = "${var.project}-public-alb"
  load_balancer_type         = "application"
  internal                   = false
  security_groups            = [aws_security_group.alb_public.id]
  subnets                    = aws_subnet.public[*].id
  drop_invalid_header_fields = true
  tags                       = { Name = "${var.project}-public-alb" }
}

resource "aws_lb_target_group" "web" {
  name                 = "${var.project}-web-tg"
  port                 = 80
  protocol             = "HTTP"
  target_type          = "instance"
  vpc_id               = aws_vpc.main.id
  deregistration_delay = 30

  health_check {
    path                = "/healthz"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "public_http" {
  load_balancer_arn = aws_lb.public.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

# ---------------------------------------------------------------- internal ALB -> app tier
resource "aws_lb" "internal" {
  name                       = "${var.project}-internal-alb"
  load_balancer_type         = "application"
  internal                   = true
  security_groups            = [aws_security_group.alb_internal.id]
  subnets                    = aws_subnet.app[*].id
  drop_invalid_header_fields = true
  tags                       = { Name = "${var.project}-internal-alb" }
}

resource "aws_lb_target_group" "app" {
  name                 = "${var.project}-app-tg"
  port                 = 5000
  protocol             = "HTTP"
  target_type          = "instance"
  vpc_id               = aws_vpc.main.id
  deregistration_delay = 30

  health_check {
    path                = "/api/health"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "internal_http" {
  load_balancer_arn = aws_lb.internal.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}
