# Application Load Balancer for RegEngine
# Routes traffic to ECS services with TLS termination

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for ALB"
  type        = list(string)
}

variable "certificate_arn" {
  description = "ACM certificate ARN for HTTPS"
  type        = string
  default     = ""
}

# Security Group for ALB
resource "aws_security_group" "alb" {
  name        = "regengine-alb-${var.environment}"
  description = "Security group for RegEngine ALB"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS from internet"
  }

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTP from internet (redirect to HTTPS)"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "regengine-alb-${var.environment}"
    Environment = var.environment
  }
}

# Application Load Balancer
resource "aws_lb" "regengine" {
  name               = "regengine-alb-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids

  enable_deletion_protection = var.environment == "production" ? true : false
  enable_http2              = true
  enable_cross_zone_load_balancing = true

  tags = {
    Name        = "regengine-alb-${var.environment}"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# Target Groups for each service
locals {
  services = {
    admin = {
      port = 8400
      path = "/health"
    }
    ingestion = {
      port = 8000
      path = "/health"
    }
    nlp = {
      port = 8100
      path = "/health"
    }
    graph = {
      port = 8200
      path = "/health"
    }
    opportunity = {
      port = 8300
      path = "/health"
    }
    compliance = {
      port = 8500
      path = "/health"
    }
  }
}

resource "aws_lb_target_group" "services" {
  for_each = local.services

  name        = "regengine-${each.key}-${substr(var.environment, 0, 4)}"
  port        = each.value.port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    path                = each.value.path
    protocol            = "HTTP"
    matcher             = "200"
  }

  deregistration_delay = 30

  tags = {
    Name        = "regengine-${each.key}-${var.environment}"
    Environment = var.environment
    Service     = each.key
  }
}

# HTTPS Listener (default)
resource "aws_lb_listener" "https" {
  count = var.certificate_arn != "" ? 1 : 0

  load_balancer_arn = aws_lb.regengine.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"
  certificate_arn   = var.certificate_arn

  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "application/json"
      message_body = jsonencode({
        error = "Not Found"
        message = "No valid route found. Use /admin, /ingest, /nlp, /graph, /opportunities, or /compliance endpoints."
      })
      status_code = "404"
    }
  }
}

# HTTP Listener (redirect to HTTPS)
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.regengine.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = var.certificate_arn != "" ? "redirect" : "fixed-response"

    dynamic "redirect" {
      for_each = var.certificate_arn != "" ? [1] : []
      content {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }

    dynamic "fixed_response" {
      for_each = var.certificate_arn == "" ? [1] : []
      content {
        content_type = "application/json"
        message_body = jsonencode({ error = "Not Found" })
        status_code  = "404"
      }
    }
  }
}

# Listener Rules for path-based routing
resource "aws_lb_listener_rule" "admin" {
  count = var.certificate_arn != "" ? 1 : 0

  listener_arn = aws_lb_listener.https[0].arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.services["admin"].arn
  }

  condition {
    path_pattern {
      values = ["/admin/*", "/overlay/*", "/keys/*"]
    }
  }
}

resource "aws_lb_listener_rule" "ingestion" {
  count = var.certificate_arn != "" ? 1 : 0

  listener_arn = aws_lb_listener.https[0].arn
  priority     = 200

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.services["ingestion"].arn
  }

  condition {
    path_pattern {
      values = ["/ingest/*"]
    }
  }
}

resource "aws_lb_listener_rule" "opportunities" {
  count = var.certificate_arn != "" ? 1 : 0

  listener_arn = aws_lb_listener.https[0].arn
  priority     = 300

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.services["opportunity"].arn
  }

  condition {
    path_pattern {
      values = ["/opportunities/*"]
    }
  }
}

resource "aws_lb_listener_rule" "compliance" {
  count = var.certificate_arn != "" ? 1 : 0

  listener_arn = aws_lb_listener.https[0].arn
  priority     = 400

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.services["compliance"].arn
  }

  condition {
    path_pattern {
      values = ["/compliance/*"]
    }
  }
}

# Outputs
output "alb_arn" {
  description = "ARN of the load balancer"
  value       = aws_lb.regengine.arn
}

output "alb_dns_name" {
  description = "DNS name of the load balancer"
  value       = aws_lb.regengine.dns_name
}

output "alb_zone_id" {
  description = "Zone ID of the load balancer"
  value       = aws_lb.regengine.zone_id
}

output "target_group_arns" {
  description = "Map of service names to target group ARNs"
  value       = { for k, v in aws_lb_target_group.services : k => v.arn }
}

output "alb_security_group_id" {
  description = "Security group ID of the ALB"
  value       = aws_security_group.alb.id
}
