# The Claims MCP tool on AWS Lambda, behind a function URL that only accepts AWS-signed
# requests from roles that were granted access (see ../access).
terraform {
  required_version = ">= 1.10"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.7" }
  }
  backend "s3" {} # MaC supplies bucket, key and locking per environment and step
}

variable "mac_env" {
  description = "rehearsal or production; every name includes it so the two never collide"
  type        = string
}

variable "mac_run_id" {
  description = "The MaC deployment ID that last changed these resources"
  type        = string
  default     = "manual"
}

provider "aws" {
  default_tags {
    tags = {
      "mac:migration"     = "claims-adjudication-onprem-to-aws"
      "mac:env"           = var.mac_env
      "mac:deployment-id" = var.mac_run_id
      "managed-by"        = "MaC"
      "owner-team"        = "claims-mcp-team"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  prefix = "mac-claims-${var.mac_env}"
  # The role comes from claims-service-iac (terraform/iam). Built from its name, not looked up,
  # so Build can plan this before the role exists.
  role_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${local.prefix}-mcp"
}

data "archive_file" "code" {
  type        = "zip"
  source_dir  = "${path.module}/../../server"
  output_path = "${path.module}/.build/server.zip"
  excludes    = ["__pycache__"]
}

resource "aws_lambda_function" "mcp" {
  function_name    = "${local.prefix}-mcp"
  description      = "Claims MCP tool (check_eligibility, coverage_period)"
  role             = local.role_arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.code.output_path
  source_code_hash = data.archive_file.code.output_base64sha256
  timeout          = 10
  memory_size      = 256
}

resource "aws_lambda_function_url" "mcp" {
  function_name      = aws_lambda_function.mcp.function_name
  authorization_type = "AWS_IAM"
}

output "function_name" {
  value = aws_lambda_function.mcp.function_name
}

output "url" {
  value = aws_lambda_function_url.mcp.function_url
}
