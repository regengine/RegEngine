# RegEngine Terraform Variables

#########################
# Environment Variables
#########################

variable "environment" {
  description = "Environment name (demo, sandbox, production)"
  type        = string
  validation {
    condition     = contains(["demo", "sandbox", "production"], var.environment)
    error_message = "Environment must be demo, sandbox, or production."
  }
}

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

#########################
# Networking Variables
#########################

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "enable_nat_gateway" {
  description = "Enable NAT Gateway for private subnets"
  type        = bool
  default     = true
}

variable "single_nat_gateway" {
  description = "Use a single NAT Gateway (cost optimization for non-prod)"
  type        = bool
  default     = false
}

#########################
# Container Registry Variables
#########################

variable "ecr_registry" {
  description = "ECR registry URL (without repository name)"
  type        = string
}

variable "image_tag" {
  description = "Docker image tag for all services"
  type        = string
  default     = "latest"
}

#########################
# Database Variables
#########################

variable "neo4j_instance_type" {
  description = "EC2 instance type for Neo4j"
  type        = string
  default     = "m6g.large"
}

variable "neo4j_volume_size" {
  description = "EBS volume size for Neo4j (GB)"
  type        = number
  default     = 200
}

variable "neo4j_backup_retention_days" {
  description = "Number of days to retain Neo4j backups"
  type        = number
  default     = 7
}

#########################
# Event Streaming Variables
#########################

variable "redpanda_instance_type" {
  description = "EC2 instance type for Redpanda"
  type        = string
  default     = "m6g.large"
}

variable "redpanda_volume_size" {
  description = "EBS volume size for Redpanda (GB)"
  type        = number
  default     = 200
}

variable "redpanda_num_brokers" {
  description = "Number of Redpanda broker nodes"
  type        = number
  default     = 3
}

#########################
# Application Service Variables
#########################

variable "ingestion_cpu" {
  description = "CPU units for ingestion service (1024 = 1 vCPU)"
  type        = number
  default     = 512
}

variable "ingestion_memory" {
  description = "Memory for ingestion service (MB)"
  type        = number
  default     = 1024
}

variable "ingestion_desired_count" {
  description = "Desired number of ingestion service tasks"
  type        = number
  default     = 2
}

variable "nlp_cpu" {
  description = "CPU units for NLP service"
  type        = number
  default     = 1024
}

variable "nlp_memory" {
  description = "Memory for NLP service (MB)"
  type        = number
  default     = 2048
}

variable "nlp_desired_count" {
  description = "Desired number of NLP service tasks"
  type        = number
  default     = 2
}

variable "graph_cpu" {
  description = "CPU units for graph service"
  type        = number
  default     = 512
}

variable "graph_memory" {
  description = "Memory for graph service (MB)"
  type        = number
  default     = 1024
}

variable "graph_desired_count" {
  description = "Desired number of graph service tasks"
  type        = number
  default     = 2
}

variable "opportunity_cpu" {
  description = "CPU units for opportunity service"
  type        = number
  default     = 512
}

variable "opportunity_memory" {
  description = "Memory for opportunity service (MB)"
  type        = number
  default     = 1024
}

variable "opportunity_desired_count" {
  description = "Desired number of opportunity service tasks"
  type        = number
  default     = 2
}

variable "admin_cpu" {
  description = "CPU units for admin service"
  type        = number
  default     = 256
}

variable "admin_memory" {
  description = "Memory for admin service (MB)"
  type        = number
  default     = 512
}

variable "admin_desired_count" {
  description = "Desired number of admin service tasks"
  type        = number
  default     = 1
}

variable "compliance_cpu" {
  description = "CPU units for compliance service"
  type        = number
  default     = 512
}

variable "compliance_memory" {
  description = "Memory for compliance service (MB)"
  type        = number
  default     = 1024
}

variable "compliance_desired_count" {
  description = "Desired number of compliance service tasks"
  type        = number
  default     = 2
}

#########################
# Monitoring & Logging Variables
#########################

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "enable_cloudwatch_logs" {
  description = "Enable CloudWatch Logs"
  type        = bool
  default     = true
}

variable "enable_s3_log_archival" {
  description = "Enable S3 archival of logs"
  type        = bool
  default     = true
}

variable "enable_prometheus" {
  description = "Enable Prometheus metrics"
  type        = bool
  default     = true
}

variable "enable_grafana" {
  description = "Enable Grafana dashboards"
  type        = bool
  default     = true
}

#########################
# Security Variables
#########################

variable "enable_waf" {
  description = "Enable AWS WAF for API Gateway"
  type        = bool
  default     = false
}

variable "enable_shield" {
  description = "Enable AWS Shield Advanced (DDoS protection)"
  type        = bool
  default     = false
}

variable "kms_key_deletion_window" {
  description = "KMS key deletion window in days"
  type        = number
  default     = 30
}

variable "enable_secrets_rotation" {
  description = "Enable automatic secrets rotation"
  type        = bool
  default     = false
}

variable "secrets_rotation_days" {
  description = "Secrets rotation interval in days"
  type        = number
  default     = 90
}

#########################
# Cost Optimization Variables
#########################

variable "enable_autoscaling" {
  description = "Enable autoscaling for ECS services"
  type        = bool
  default     = true
}

variable "min_capacity" {
  description = "Minimum number of tasks for autoscaling"
  type        = number
  default     = 1
}

variable "max_capacity" {
  description = "Maximum number of tasks for autoscaling"
  type        = number
  default     = 10
}

variable "target_cpu_utilization" {
  description = "Target CPU utilization for autoscaling (%)"
  type        = number
  default     = 70
}

variable "use_spot_instances" {
  description = "Use EC2 Spot instances (for non-prod only)"
  type        = bool
  default     = false
}

#########################
# Tags
#########################

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default = {
    Project     = "RegEngine"
    ManagedBy   = "Terraform"
    CostCenter  = "Engineering"
  }
}

variable "additional_tags" {
  description = "Additional tags specific to this deployment"
  type        = map(string)
  default     = {}
}

#########################
# Feature Flags
#########################

variable "enable_design_partner_sandboxes" {
  description = "Enable design partner sandbox provisioning"
  type        = bool
  default     = false
}

variable "enable_public_api_gateway" {
  description = "Enable public API Gateway (vs. private VPC endpoint)"
  type        = bool
  default     = true
}

variable "enable_demo_data_loading" {
  description = "Automatically load demo data on deployment"
  type        = bool
  default     = false
}
