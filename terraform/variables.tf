"""
Terraform Variables
"""

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "production"
  
  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Environment must be one of: development, staging, production."
  }
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "gcp_project_id" {
  description = "GCP project ID"
  type        = string
  sensitive   = true
}

variable "gcp_region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "azure_subscription_id" {
  description = "Azure subscription ID"
  type        = string
  sensitive   = true
}

variable "azure_tenant_id" {
  description = "Azure tenant ID"
  type        = string
  sensitive   = true
}

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
  default     = "trading-cluster"
}

variable "cluster_version" {
  description = "Kubernetes version"
  type        = string
  default     = "1.28"
}

variable "node_groups" {
  description = "EKS node groups configuration"
  type = map(object({
    instance_types = list(string)
    desired_size   = number
    min_size       = number
    max_size       = number
    disk_size      = number
    labels         = map(string)
    taints         = list(object({
      key    = string
      value  = string
      effect = string
    }))
  }))
  default = {
    general = {
      instance_types = ["m5.xlarge"]
      desired_size   = 3
      min_size       = 3
      max_size       = 10
      disk_size      = 100
      labels = {
        node-type = "general"
      }
      taints = []
    }
    cpu-intensive = {
      instance_types = ["c5.2xlarge"]
      desired_size   = 2
      min_size       = 2
      max_size       = 8
      disk_size      = 100
      labels = {
        node-type = "cpu-intensive"
      }
      taints = []
    }
    memory-intensive = {
      instance_types = ["r5.2xlarge"]
      desired_size   = 2
      min_size       = 2
      max_size       = 8
      disk_size      = 100
      labels = {
        node-type = "memory-intensive"
      }
      taints = []
    }
    gpu = {
      instance_types = ["g4dn.xlarge"]
      desired_size   = 1
      min_size       = 1
      max_size       = 4
      disk_size      = 200
      labels = {
        node-type = "gpu"
        nvidia.com/gpu = "present"
      }
      taints = [{
        key    = "nvidia.com/gpu"
        value  = "present"
        effect = "NO_SCHEDULE"
      }]
    }
  }
}

variable "database_config" {
  description = "Database configurations"
  type = object({
    postgres = object({
      instance_class = string
      allocated_storage = number
      max_allocated_storage = number
      multi_az = bool
      backup_retention_period = number
    })
    redis = object({
      node_type = string
      num_cache_nodes = number
      automatic_failover_enabled = bool
    })
    mongodb = object({
      instance_class = string
      cluster_size = number
      disk_size_gb = number
    })
  })
  default = {
    postgres = {
      instance_class           = "db.r5.xlarge"
      allocated_storage        = 500
      max_allocated_storage    = 1000
      multi_az                 = true
      backup_retention_period  = 30
    }
    redis = {
      node_type                 = "cache.r5.large"
      num_cache_nodes           = 3
      automatic_failover_enabled = true
    }
    mongodb = {
      instance_class = "M30"
      cluster_size   = 3
      disk_size_gb   = 500
    }
  }
}

variable "vpc_config" {
  description = "VPC configuration"
  type = object({
    cidr_block = string
    enable_nat_gateway = bool
    single_nat_gateway = bool
    enable_vpn_gateway = bool
    enable_dns_hostnames = bool
    enable_dns_support = bool
  })
  default = {
    cidr_block           = "10.0.0.0/16"
    enable_nat_gateway   = true
    single_nat_gateway   = false
    enable_vpn_gateway   = false
    enable_dns_hostnames = true
    enable_dns_support   = true
  }
}

variable "domain_name" {
  description = "Domain name for the application"
  type        = string
  default     = "tradingecosystem.com"
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID"
  type        = string
  sensitive   = true
}

variable "ssl_certificate_arn" {
  description = "ACM SSL certificate ARN"
  type        = string
  sensitive   = true
  default     = ""
}

variable "monitoring_config" {
  description = "Monitoring configuration"
  type = object({
    prometheus_retention_days = number
    grafana_admin_password = string
    alertmanager_slack_webhook = string
    pagerduty_service_key = string
  })
  sensitive = true
  default = {
    prometheus_retention_days = 30
    grafana_admin_password    = "changeme"
    alertmanager_slack_webhook = ""
    pagerduty_service_key     = ""
  }
}

variable "backup_config" {
  description = "Backup configuration"
  type = object({
    retention_days = number
    backup_window = string
    maintenance_window = string
    s3_bucket_name = string
  })
  default = {
    retention_days     = 30
    backup_window      = "02:00-03:00"
    maintenance_window = "sun:04:00-sun:05:00"
    s3_bucket_name     = "trading-backups"
  }
}

variable "allowed_cidr_blocks" {
  description = "CIDR blocks allowed to access the cluster"
  type        = list(string)
  default     = ["0.0.0.0/0"] # Change in production
}

variable "enable_dr" {
  description = "Enable disaster recovery"
  type        = bool
  default     = true
}

variable "dr_region" {
  description = "Disaster recovery region"
  type        = string
  default     = "us-west-2"
}