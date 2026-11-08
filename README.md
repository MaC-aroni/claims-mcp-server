# claims-mcp-server

The **Claims MCP tool**, owned by the claims-mcp-team: an MCP server that other teams' agents
and services call. It offers `check_eligibility` and `coverage_period`, and speaks MCP's
Streamable HTTP transport in its stateless form (one JSON-RPC message per POST).

It runs on AWS Lambda behind a function URL with **AWS_IAM auth**: only roles this team has
granted access can call it.

| Path | Used by MaC step | What it does |
|---|---|---|
| `terraform/server` | `deploy_mcp_server` | The Lambda function and its function URL |
| `terraform/access` | `grant_mcp_access` | Lets ClaimsAdjudicationService's role call it. MaC runs this only after the requester's manager, then this team, approve. Undo revokes it |
| `server/handler.py` | | The MCP server |

## Naming contract (shared by all four repos)

MaC passes `MAC_ENV` (`rehearsal` or `production`) to every step, and every resource name
includes it, so a rehearsal never touches production:

| Resource | Name |
|---|---|
| Claims table (DynamoDB) | `mac-claims-<env>-claims` |
| Service role / Lambda | `mac-claims-<env>-service` |
| MCP tool role / Lambda | `mac-claims-<env>-mcp` |

Every AWS resource is tagged `mac:env`, `mac:migration` and `mac:deployment-id` (the MaC run
that last changed it), so you can see in the AWS console which deployment made what.

## How it runs

MaC checks this repo's `main` out at the exact commit Build locked and runs it; see
[MaC's runner docs](https://github.com/MaC-aroni/deployed-on-a-prayer/blob/main/docs/runner.md).
Build only runs code whose CI passed and that reached `main` through an approved pull request,
so **every change here goes through a reviewed PR**.

Local checks: `pip install -r requirements-dev.txt && python -m pytest`
