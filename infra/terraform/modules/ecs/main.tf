# ECS Cluster and Service Definitions for RegEngine
# This module provisions ECS Fargate services for all RegEngine microservices

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for ECS tasks"
  type        = list(string)
}

variable "alb_target_group_arns" {
  description = "Map of service names to ALB target group ARNs"
  type        = map(string)
}

variable "secret_arns" {
  description = "Map of secret ARNs for service configuration"
  type        = map(string)
}

# ECS Cluster
resource "aws_ecs_cluster" "regengine" {
  name = "regengine-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# ECS Task Execution Role
resource "aws_iam_role" "ecs_task_execution" {
  name = "regengine-ecs-task-execution-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Additional policy for Secrets Manager access
resource "aws_iam_role_policy" "ecs_secrets_access" {
  name = "secrets-access"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ]
      Resource = "arn:aws:secretsmanager:*:*:secret:regengine/*"
    }]
  })
}

# ECS Task Role (for application permissions)
resource "aws_iam_role" "ecs_task" {
  name = "regengine-ecs-task-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })
}

# Policy for S3 access
resource "aws_iam_role_policy" "ecs_s3_access" {
  name = "s3-access"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ]
      Resource = [
        "arn:aws:s3:::regengine-*",
        "arn:aws:s3:::regengine-*/*"
      ]
    }]
  })
}

# Security Group for ECS Tasks
resource "aws_security_group" "ecs_tasks" {
  name        = "regengine-ecs-tasks-${var.environment}"
  description = "Security group for RegEngine ECS tasks"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 8000
    to_port         = 8500
    protocol        = "tcp"
    security_groups = []  # Add ALB security group
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "regengine-ecs-tasks-${var.environment}"
    Environment = var.environment
  }
}

# Service definitions
locals {
  services = {
    admin = {
      port          = 8400
      cpu           = 512
      memory        = 1024
      desired_count = 2
    }
    ingestion = {
      port          = 8000
      cpu           = 1024
      memory        = 2048
      desired_count = 3
    }
    nlp = {
      port          = 8100
      cpu           = 2048
      memory        = 4096
      desired_count = 4
    }
    graph = {
      port          = 8200
      cpu           = 1024
      memory        = 2048
      desired_count = 3
    }
    opportunity = {
      port          = 8300
      cpu           = 512
      memory        = 1024
      desired_count = 2
    }
    compliance = {
      port          = 8500
      cpu           = 512
      memory        = 1024
      desired_count = 2
    }
  }
}

# Task Definitions
resource "aws_ecs_task_definition" "services" {
  for_each = local.services

  family                   = "regengine-${each.key}-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name  = each.key
    image = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.name}.amazonaws.com/regengine-${each.key}:latest"

    portMappings = [{
      containerPort = each.value.port
      protocol      = "tcp"
    }]

    environment = [
      { name = "ENVIRONMENT", value = var.environment },
      { name = "LOG_LEVEL", value = "INFO" }
    ]

    secrets = [
      {
        name      = "NEO4J_PASSWORD"
        valueFrom = var.secret_arns["neo4j-password"]
      },
      {
        name      = "ADMIN_MASTER_KEY"
        valueFrom = var.secret_arns["admin-master-key"]
      }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/regengine/${var.environment}/${each.key}"
        "awslogs-region"        = data.aws_region.current.name
        "awslogs-stream-prefix" = each.key
      }
    }

    healthCheck = {
      command = ["CMD-SHELL", "curl -f http://localhost:${each.value.port}/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])

  tags = {
    Environment = var.environment
    Service     = each.key
  }
}

# ECS Services
resource "aws_ecs_service" "services" {
  for_each = local.services

  name            = "regengine-${each.key}-${var.environment}"
  cluster         = aws_ecs_cluster.regengine.id
  task_definition = aws_ecs_task_definition.services[each.key].arn
  desired_count   = each.value.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.alb_target_group_arns[each.key]
    container_name   = each.key
    container_port   = each.value.port
  }

  deployment_configuration {
    maximum_percent         = 200
    minimum_healthy_percent = 100
  }

  depends_on = [aws_iam_role_policy.ecs_s3_access]

  tags = {
    Environment = var.environment
    Service     = each.key
  }
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Outputs
output "cluster_id" {
  description = "ECS cluster ID"
  value       = aws_ecs_cluster.regengine.id
}

output "service_names" {
  description = "Map of service names"
  value       = { for k, v in aws_ecs_service.services : k => v.name }
}
