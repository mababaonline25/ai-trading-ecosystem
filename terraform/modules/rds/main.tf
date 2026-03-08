"""
RDS Module - PostgreSQL database
"""

resource "aws_db_subnet_group" "postgres" {
  name        = "${var.environment}-postgres-subnet-group"
  description = "Subnet group for PostgreSQL"
  subnet_ids  = var.subnet_ids
  
  tags = var.tags
}

resource "aws_security_group" "postgres" {
  name        = "${var.environment}-postgres-sg"
  description = "Security group for PostgreSQL"
  vpc_id      = var.vpc_id
  
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.eks_security_group_id]
  }
  
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = var.tags
}

resource "aws_db_parameter_group" "postgres" {
  name        = "${var.environment}-postgres-params"
  family      = "postgres15"
  description = "Parameter group for PostgreSQL"
  
  parameter {
    name  = "log_connections"
    value = "1"
  }
  
  parameter {
    name  = "log_disconnections"
    value = "1"
  }
  
  parameter {
    name  = "log_duration"
    value = "1"
  }
  
  parameter {
    name  = "log_lock_waits"
    value = "1"
  }
  
  parameter {
    name  = "log_statement"
    value = "ddl"
  }
  
  parameter {
    name  = "shared_preload_libraries"
    value = "pg_stat_statements"
  }
  
  parameter {
    name  = "pg_stat_statements.track"
    value = "all"
  }
  
  tags = var.tags
}

resource "aws_db_instance" "postgres_primary" {
  identifier = "${var.environment}-postgres-primary"
  
  engine         = "postgres"
  engine_version = "15.4"
  
  instance_class = var.instance_class
  
  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true
  
  db_name  = "trading_${var.environment}"
  username = var.username
  password = random_password.postgres.result
  
  db_subnet_group_name   = aws_db_subnet_group.postgres.name
  vpc_security_group_ids = [aws_security_group.postgres.id]
  
  backup_retention_period = var.backup_retention_period
  backup_window           = var.backup_window
  maintenance_window      = var.maintenance_window
  
  multi_az               = var.multi_az
  publicly_accessible    = false
  skip_final_snapshot    = false
  final_snapshot_identifier = "${var.environment}-postgres-final-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"
  
  performance_insights_enabled          = true
  performance_insights_retention_period = 7
  
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  
  auto_minor_version_upgrade = true
  deletion_protection        = var.environment == "production" ? true : false
  
  parameter_group_name = aws_db_parameter_group.postgres.name
  
  tags = var.tags
}

resource "aws_db_instance" "postgres_replica" {
  count = var.multi_az ? 1 : 0
  
  identifier = "${var.environment}-postgres-replica"
  
  replicate_source_db = aws_db_instance.postgres_primary.identifier
  
  instance_class = var.instance_class
  
  storage_encrypted = true
  
  vpc_security_group_ids = [aws_security_group.postgres.id]
  
  performance_insights_enabled          = true
  performance_insights_retention_period = 7
  
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  
  tags = var.tags
}

resource "random_password" "postgres" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "postgres" {
  name = "${var.environment}-postgres-credentials"
  
  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "postgres" {
  secret_id = aws_secretsmanager_secret.postgres.id
  
  secret_string = jsonencode({
    username = var.username
    password = random_password.postgres.result
    host     = aws_db_instance.postgres_primary.address
    port     = aws_db_instance.postgres_primary.port
    dbname   = "trading_${var.environment}"
  })
}

# CloudWatch Alarms
resource "aws_cloudwatch_metric_alarm" "postgres_cpu" {
  alarm_name          = "${var.environment}-postgres-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = "300"
  statistic           = "Average"
  threshold           = "80"
  alarm_description   = "This metric monitors postgres CPU utilization"
  alarm_actions       = var.sns_topic_arn != "" ? [var.sns_topic_arn] : []
  
  dimensions = {
    DBInstanceIdentifier = aws_db_instance.postgres_primary.identifier
  }
  
  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "postgres_storage" {
  alarm_name          = "${var.environment}-postgres-storage-low"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = "600"
  statistic           = "Average"
  threshold           = "5000000000" # 5GB
  alarm_description   = "This metric monitors postgres free storage space"
  alarm_actions       = var.sns_topic_arn != "" ? [var.sns_topic_arn] : []
  
  dimensions = {
    DBInstanceIdentifier = aws_db_instance.postgres_primary.identifier
  }
  
  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "postgres_connections" {
  alarm_name          = "${var.environment}-postgres-connections-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = "300"
  statistic           = "Average"
  threshold           = "500"
  alarm_description   = "This metric monitors postgres connections"
  alarm_actions       = var.sns_topic_arn != "" ? [var.sns_topic_arn] : []
  
  dimensions = {
    DBInstanceIdentifier = aws_db_instance.postgres_primary.identifier
  }
  
  tags = var.tags
}

# Outputs
output "postgres_endpoint" {
  value = aws_db_instance.postgres_primary.address
}

output "postgres_port" {
  value = aws_db_instance.postgres_primary.port
}

output "postgres_secret_arn" {
  value = aws_secretsmanager_secret.postgres.arn
}