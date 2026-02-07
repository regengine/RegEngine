# CloudWatch Log Groups for RegEngine services
# This module creates log groups for all microservices with appropriate retention policies

variable "environment" {
  description = "Deployment environment (production, staging, development)"
  type        = string
}

variable "retention_in_days" {
  description = "Log retention period in days"
  type        = number
  default     = 30
}

variable "services" {
  description = "List of service names to create log groups for"
  type        = list(string)
  default     = ["admin", "ingestion", "nlp", "graph", "opportunity", "compliance"]
}

# Create log groups for each service
resource "aws_cloudwatch_log_group" "service_logs" {
  for_each = toset(var.services)

  name              = "/regengine/${var.environment}/${each.value}"
  retention_in_days = var.retention_in_days

  tags = {
    Environment = var.environment
    Service     = each.value
    ManagedBy   = "terraform"
    Project     = "RegEngine"
  }
}

# Create metric filters for error tracking
resource "aws_cloudwatch_log_metric_filter" "error_count" {
  for_each = toset(var.services)

  name           = "${each.value}-error-count"
  log_group_name = aws_cloudwatch_log_group.service_logs[each.value].name
  pattern        = "[timestamp, request_id, level=ERROR*, ...]"

  metric_transformation {
    name      = "${each.value}_error_count"
    namespace = "RegEngine/${var.environment}"
    value     = "1"
    default_value = 0
  }
}

# Create metric filters for latency tracking
resource "aws_cloudwatch_log_metric_filter" "high_latency" {
  for_each = toset(var.services)

  name           = "${each.value}-high-latency"
  log_group_name = aws_cloudwatch_log_group.service_logs[each.value].name
  pattern        = "[timestamp, request_id, level, latency>500, ...]"

  metric_transformation {
    name      = "${each.value}_high_latency_count"
    namespace = "RegEngine/${var.environment}"
    value     = "1"
    default_value = 0
  }
}

# CloudWatch Dashboard for service health
resource "aws_cloudwatch_dashboard" "regengine_dashboard" {
  dashboard_name = "RegEngine-${var.environment}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric"
        properties = {
          metrics = [
            for service in var.services : [
              "RegEngine/${var.environment}",
              "${service}_error_count",
              { stat = "Sum", period = 300 }
            ]
          ]
          period = 300
          stat   = "Sum"
          region = "us-east-1"
          title  = "Error Count by Service"
        }
      },
      {
        type = "metric"
        properties = {
          metrics = [
            for service in var.services : [
              "RegEngine/${var.environment}",
              "${service}_high_latency_count",
              { stat = "Sum", period = 300 }
            ]
          ]
          period = 300
          stat   = "Sum"
          region = "us-east-1"
          title  = "High Latency Events"
        }
      }
    ]
  })
}

# Alarm for critical error rates
resource "aws_cloudwatch_metric_alarm" "high_error_rate" {
  for_each = toset(var.services)

  alarm_name          = "${var.environment}-${each.value}-high-error-rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "${each.value}_error_count"
  namespace           = "RegEngine/${var.environment}"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "Alert when ${each.value} error rate exceeds threshold"
  treat_missing_data  = "notBreaching"

  tags = {
    Environment = var.environment
    Service     = each.value
    Severity    = "critical"
  }
}

# Output log group names for reference
output "log_group_names" {
  description = "CloudWatch log group names by service"
  value       = { for k, v in aws_cloudwatch_log_group.service_logs : k => v.name }
}

output "log_group_arns" {
  description = "CloudWatch log group ARNs by service"
  value       = { for k, v in aws_cloudwatch_log_group.service_logs : k => v.arn }
}

output "dashboard_name" {
  description = "CloudWatch dashboard name"
  value       = aws_cloudwatch_dashboard.regengine_dashboard.dashboard_name
}
