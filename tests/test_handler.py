import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

import handler  # noqa: E402


def call(message, **event):
    response = handler.handler({"requestContext": {"http": {"method": "POST"}}, "body": json.dumps(message), **event}, None)
    return response["statusCode"], json.loads(response["body"]) if response["body"] else None


def test_initialize_negotiates_the_protocol_version():
    status, body = call({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t"}}})
    assert status == 200 and body["result"]["protocolVersion"] == "2025-03-26"
    assert body["result"]["capabilities"] == {"tools": {"listChanged": False}}
    _, body = call({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}})
    assert body["result"]["protocolVersion"] == "2025-06-18"


def test_notifications_get_202_and_no_body():
    assert call({"jsonrpc": "2.0", "method": "notifications/initialized"}) == (202, None)


def test_tools_list():
    _, body = call({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    assert [t["name"] for t in body["result"]["tools"]] == ["check_eligibility", "coverage_period"]


def test_check_eligibility():
    _, body = call({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                    "params": {"name": "check_eligibility", "arguments": {"member_id": "M-20001", "service_date": "2024-01-01"}}})
    result = body["result"]
    assert result["isError"] is False and result["structuredContent"]["eligible"] is True
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]


def test_lapsed_and_unknown_members_are_not_eligible():
    assert handler.check_eligibility("M-20003", "2025-01-01")["eligible"] is False
    assert handler.check_eligibility("M-99999", "2025-01-01")["reason"] == "unknown member"


def test_bad_date_is_a_tool_error_not_a_protocol_error():
    _, body = call({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                    "params": {"name": "check_eligibility", "arguments": {"member_id": "M-20001", "service_date": "01-JAN-24"}}})
    assert body["result"]["isError"] is True and "YYYY-MM-DD" in body["result"]["content"][0]["text"]


def test_protocol_errors():
    _, body = call({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "nope"}})
    assert body["error"]["code"] == -32602
    _, body = call({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "coverage_period"}})
    assert "Missing arguments: member_id" in body["error"]["message"]
    _, body = call({"jsonrpc": "2.0", "id": 8, "method": "resources/list"})
    assert body["error"]["code"] == -32601
    _, body = call({"id": 9, "method": "ping"})
    assert body["error"]["code"] == -32600


def test_http_level_handling():
    get = handler.handler({"requestContext": {"http": {"method": "GET"}}}, None)
    assert get["statusCode"] == 405
    bad = handler.handler({"requestContext": {"http": {"method": "POST"}}, "body": "{not json"}, None)
    assert bad["statusCode"] == 400 and json.loads(bad["body"])["error"]["code"] == -32700
    import base64
    encoded = base64.b64encode(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode()).decode()
    status, body = call({}, body=encoded, isBase64Encoded=True)
    assert status == 200 and body["result"] == {}
