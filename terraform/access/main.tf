# Grants ClaimsAdjudicationService's role, and only that role, permission to call the Claims
# MCP tool. Owned by the MCP team because it's their resource; MaC runs it only after the
# requester's manager and then the MCP team approve. Undo (terraform destroy) revokes it.
terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
  backend "s3" {}
}

variable "mac_env" {
  type = string
}

variable "mac_run_id" {
  type    = string
  default = "manual"
}

provider "aws" {
  default_tags {
    tags = {
      "mac:migration"     = "claims-adjudication-onprem-to-aws"
      "mac:env"           = var.mac_env
      "mac:deployment-id" = var.mac_run_id
      "managed-by"        = "MaC"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  prefix          = "mac-claims-${var.mac_env}"
  mcp_function    = "${local.prefix}-mcp"
  service_role_id = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${local.prefix}-service"
}

# Function URLs with AWS_IAM auth check both permissions.
resource "aws_lambda_permission" "invoke_url" {
  statement_id           = "allow-claims-service-url"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = local.mcp_function
  principal              = local.service_role_id
  function_url_auth_type = "AWS_IAM"
}

resource "aws_lambda_permission" "invoke" {
  statement_id  = "allow-claims-service-invoke"
  action        = "lambda:InvokeFunction"
  function_name = local.mcp_function
  principal     = local.service_role_id
}

output "granted_to" {
  value = local.service_role_id
}
