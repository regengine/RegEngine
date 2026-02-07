# Terraform module for AWS Secrets Manager automatic rotation
# This configures Lambda-based rotation for RegEngine secrets

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID for Lambda function"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for Lambda function"
  type        = list(string)
}

# IAM role for Lambda rotation function
resource "aws_iam_role" "rotation_lambda" {
  name = "regengine-secret-rotation-lambda-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })

  tags = {
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# IAM policy for Lambda rotation function
resource "aws_iam_role_policy" "rotation_lambda" {
  name = "regengine-secret-rotation-policy"
  role = aws_iam_role.rotation_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:DescribeSecret",
          "secretsmanager:GetSecretValue",
          "secretsmanager:PutSecretValue",
          "secretsmanager:UpdateSecretVersionStage"
        ]
        Resource = "arn:aws:secretsmanager:*:*:secret:regengine/*"
      },
      {
        Effect = "Allow"
        Action = [
          "rds:DescribeDBInstances",
          "rds:ModifyDBInstance"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface"
        ]
        Resource = "*"
      }
    ]
  })
}

# Security group for Lambda function
resource "aws_security_group" "rotation_lambda" {
  name        = "regengine-rotation-lambda-${var.environment}"
  description = "Security group for secret rotation Lambda"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "regengine-rotation-lambda-${var.environment}"
    Environment = var.environment
  }
}

# Lambda function for secret rotation
resource "aws_lambda_function" "rotation" {
  filename      = "${path.module}/../lambda/secret_rotation/deployment.zip"
  function_name = "regengine-secret-rotation-${var.environment}"
  role          = aws_iam_role.rotation_lambda.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.11"
  timeout       = 300
  memory_size   = 512

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.rotation_lambda.id]
  }

  environment {
    variables = {
      ENVIRONMENT = var.environment
    }
  }

  tags = {
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# Lambda permission for Secrets Manager
resource "aws_lambda_permission" "secrets_manager" {
  statement_id  = "AllowExecutionFromSecretsManager"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.rotation.function_name
  principal     = "secretsmanager.amazonaws.com"
}

# Output Lambda ARN for rotation configuration
output "rotation_lambda_arn" {
  description = "ARN of the secret rotation Lambda function"
  value       = aws_lambda_function.rotation.arn
}

output "rotation_lambda_name" {
  description = "Name of the secret rotation Lambda function"
  value       = aws_lambda_function.rotation.function_name
}
