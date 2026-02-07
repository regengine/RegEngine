# RegEngine Terraform Infrastructure
# High-level Terraform spec for RegEngine infrastructure
# This provides the foundational AWS infrastructure for all environments

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "regengine-terraform-state"
    key            = "infra/global/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "regengine-terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region
}

########################
# VPC & Networking
########################

module "vpc" {
  source = "./modules/vpc"

  name       = "regengine-${var.environment}"
  cidr_block = "10.0.0.0/16"
  azs        = ["us-east-1a", "us-east-1b"]
}

########################
# ECS Cluster for Services
########################

module "ecs" {
  source = "./modules/ecs"

  cluster_name = "regengine-${var.environment}"
  vpc_id       = module.vpc.vpc_id
  subnets      = module.vpc.private_subnets
}

########################
# Neo4j Graph Backend
########################

module "neo4j" {
  source = "./modules/neo4j"

  environment   = var.environment
  vpc_id        = module.vpc.vpc_id
  subnets       = module.vpc.private_subnets
  instance_type = "m6g.large"
  volume_size   = 200
}

########################
# Redpanda / Kafka Equivalent
########################

module "redpanda" {
  source = "./modules/redpanda"

  environment   = var.environment
  vpc_id        = module.vpc.vpc_id
  subnets       = module.vpc.private_subnets
  instance_type = "m6g.large"
  volume_size   = 200
}

########################
# Application Services – Ingestion, NLP, Graph API, Opportunity API
########################

module "regengine_services" {
  source = "./modules/regengine_services"

  cluster_arn = module.ecs.cluster_arn
  vpc_id      = module.vpc.vpc_id
  subnets     = module.vpc.private_subnets

  services = {
    ingestion = {
      image          = "${var.ecr_registry}/ingestion:${var.image_tag}"
      cpu            = 512
      memory         = 1024
      desired_count  = 2
      container_port = 8000
    }
    nlp = {
      image          = "${var.ecr_registry}/nlp:${var.image_tag}"
      cpu            = 1024
      memory         = 2048
      desired_count  = 2
      container_port = 8100
    }
    graph = {
      image          = "${var.ecr_registry}/graph:${var.image_tag}"
      cpu            = 512
      memory         = 1024
      desired_count  = 2
      container_port = 8200
    }
    opportunity = {
      image          = "${var.ecr_registry}/opportunity:${var.image_tag}"
      cpu            = 512
      memory         = 1024
      desired_count  = 2
      container_port = 8300
    }
    admin = {
      image          = "${var.ecr_registry}/admin:${var.image_tag}"
      cpu            = 256
      memory         = 512
      desired_count  = 1
      container_port = 8400
    }
    compliance = {
      image          = "${var.ecr_registry}/compliance:${var.image_tag}"
      cpu            = 512
      memory         = 1024
      desired_count  = 2
      container_port = 8500
    }
  }
}

########################
# Security & Observability
########################

module "logging" {
  source = "./modules/logging"

  environment        = var.environment
  log_retention_days = 30
  create_cloudwatch  = true
  create_s3_archival = true
  s3_bucket_name     = "regengine-logs-${var.environment}"
}

module "iam" {
  source = "./modules/iam"

  environment      = var.environment
  ecs_task_roles   = module.regengine_services.task_roles
  allow_s3_buckets = ["regengine-docs-${var.environment}", module.logging.s3_bucket_name]
  allow_kms_keys   = ["alias/regengine-${var.environment}"]
}

########################
# Variables
########################

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (demo, sandbox, production)"
  type        = string
}

variable "image_tag" {
  description = "Docker image tag for all services"
  type        = string
  default     = "latest"
}

variable "ecr_registry" {
  description = "ECR registry URL"
  type        = string
}

########################
# Outputs
########################

output "neo4j_endpoint" {
  description = "Neo4j connection endpoint"
  value       = module.neo4j.endpoint
  sensitive   = true
}

output "public_api_url" {
  description = "Public API gateway URL"
  value       = module.regengine_services.api_gateway_url
}

output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = module.ecs.cluster_name
}
