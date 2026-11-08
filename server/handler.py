"""Claims MCP tool: an MCP server other teams' agents call to check claims-related facts.

Runs on AWS Lambda behind a function URL with AWS_IAM auth, so only roles that were granted
access can call it (see terraform/access). It speaks MCP's Streamable HTTP transport in its
stateless form: each POST carries one JSON-RPC message and gets one JSON reply.
"""

import base64
import json
from datetime import date

SERVER_INFO = {"name": "claims-mcp", "version": "1.4.0"}
SUPPORTED_VERSIONS = ("2025-06-18", "2025-03-26")

# Coverage periods by member. A real system reads the eligibility database; the point of this
# tool in the demo is who may call it, not what it knows.
COVERAGE = {
    "M-20001": ("2023-01-01", "2026-12-31"),
    "M-20002": ("2024-01-01", "2026-12-31"),
    "M-20003": ("2022-07-01", "2024-06-30"),
    "M-20004": ("2024-03-01", "2027-02-28"),
}

TOOLS = [
    {
        "name": "check_eligibility",
        "title": "Check member eligibility",
        "description": "Whether a member had active coverage on a date of service.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "member_id": {"type": "string", "description": "e.g. M-20001"},
                "service_date": {"type": "string", "description": "ISO date, YYYY-MM-DD"},
            },
            "required": ["member_id", "service_date"],
        },
    },
    {
        "name": "coverage_period",
        "title": "Member coverage period",
        "description": "A member's coverage start and end dates.",
        "inputSchema": {
            "type": "object",
            "properties": {"member_id": {"type": "string"}},
            "required": ["member_id"],
        },
    },
]


class ToolError(Exception):
    """Reported to the caller as a tool result with isError, per the MCP spec."""


def check_eligibility(member_id: str, service_date: str) -> dict:
    try:
        when = date.fromisoformat(service_date)
    except ValueError as e:
        raise ToolError(f"service_date must be YYYY-MM-DD, got {service_date!r}") from e
    period = COVERAGE.get(member_id)
    if period is None:
        return {"member_id": member_id, "eligible": False, "reason": "unknown member"}
    start, end = (date.fromisoformat(d) for d in period)
    eligible = start <= when <= end
    return {"member_id": member_id, "service_date": service_date, "eligible": eligible,
            "reason": "active coverage" if eligible else f"not covered on {service_date}"}


def coverage_period(member_id: str) -> dict:
    period = COVERAGE.get(member_id)
    if period is None:
        raise ToolError(f"unknown member {member_id!r}")
    return {"member_id": member_id, "start": period[0], "end": period[1]}


IMPLEMENTATIONS = {"check_eligibility": check_eligibility, "coverage_period": coverage_period}


def handle_message(message) -> dict | None:
    """One JSON-RPC message in, one response out (None for notifications)."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or "method" not in message:
        return _error(None, -32600, "Invalid Request")
    msg_id, method, params = message.get("id"), message["method"], message.get("params") or {}
    if msg_id is None:
        return None  # a notification, e.g. notifications/initialized

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
        return _result(msg_id, {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
                                "serverInfo": SERVER_INFO})
    if method == "ping":
        return _result(msg_id, {})
    if method == "tools/list":
        return _result(msg_id, {"tools": TOOLS})
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        tool = IMPLEMENTATIONS.get(name)
        if tool is None:
            return _error(msg_id, -32602, f"Unknown tool: {name}")
        missing = [p for p in next(t for t in TOOLS if t["name"] == name)["inputSchema"]["required"] if p not in args]
        if missing:
            return _error(msg_id, -32602, f"Missing arguments: {', '.join(missing)}")
        try:
            output = tool(**{k: str(v) for k, v in args.items() if k in ("member_id", "service_date")})
        except ToolError as e:
            return _result(msg_id, {"content": [{"type": "text", "text": str(e)}], "isError": True})
        return _result(msg_id, {"content": [{"type": "text", "text": json.dumps(output)}],
                                "structuredContent": output, "isError": False})
    return _error(msg_id, -32601, f"Method not found: {method}")


def handler(event, context):
    """AWS Lambda function URL entry point."""
    method = event.get("requestContext", {}).get("http", {}).get("method", "POST")
    if method != "POST":
        return {"statusCode": 405, "headers": {"Allow": "POST"}, "body": ""}  # no server-sent stream
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        return _http(400, _error(None, -32700, "Parse error"))
    response = handle_message(message)
    if response is None:
        return {"statusCode": 202, "body": ""}
    return _http(200, response)


def _result(msg_id, result):
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id, code, message):
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _http(status, payload):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": json.dumps(payload)}
