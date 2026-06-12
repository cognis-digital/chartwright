"""chartwright MCP server — stdio JSON-RPC 2.0. Standard library only.

    {"command": "python", "args": ["-m", "chartwright", "mcp"]}
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional

from chartwright import TOOL_NAME, TOOL_VERSION
from chartwright.core import (
    ChartError,
    diff_values,
    lint_chart,
    load_chart,
    load_values,
    render_chart,
)

PROTOCOL_VERSION = "2024-11-05"

_TOOLS = [
    {
        "name": "template",
        "description": "Render a Helm chart's templates against its values "
                       "(plus optional overrides). Returns rendered manifests.",
        "inputSchema": {
            "type": "object",
            "properties": {"chart": {"type": "string"},
                           "release": {"type": "string"},
                           "values": {"type": "string"}},
            "required": ["chart"], "additionalProperties": False,
        },
    },
    {
        "name": "lint",
        "description": "Lint a chart's structure and template blocks; reports "
                       "findings and a pass/fail.",
        "inputSchema": {
            "type": "object",
            "properties": {"chart": {"type": "string"}},
            "required": ["chart"], "additionalProperties": False,
        },
    },
    {
        "name": "diff",
        "description": "Diff two values files; returns added/removed/changed keys.",
        "inputSchema": {
            "type": "object",
            "properties": {"left": {"type": "string"}, "right": {"type": "string"}},
            "required": ["left", "right"], "additionalProperties": False,
        },
    },
]


def _result(req_id, result): return {"jsonrpc": "2.0", "id": req_id, "result": result}
def _error(req_id, code, msg): return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": msg}}


def _call_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if name == "template":
        chart = args.get("chart")
        if not isinstance(chart, str) or not chart:
            raise ValueError("`chart` (string) is required")
        overrides = load_values(args["values"]) if args.get("values") else None
        rendered = render_chart(load_chart(chart),
                                release=args.get("release") or "release",
                                overrides=overrides)
        return {"content": [{"type": "text", "text": json.dumps(rendered, indent=2)}],
                "isError": False}
    if name == "lint":
        chart = args.get("chart")
        if not isinstance(chart, str) or not chart:
            raise ValueError("`chart` (string) is required")
        res = lint_chart(load_chart(chart))
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}],
                "isError": not res["ok"]}
    if name == "diff":
        left, right = args.get("left"), args.get("right")
        if not isinstance(left, str) or not isinstance(right, str):
            raise ValueError("`left` and `right` (strings) are required")
        d = diff_values(load_values(left), load_values(right))
        return {"content": [{"type": "text", "text": json.dumps(d, indent=2)}],
                "isError": False}
    raise ValueError(f"unknown tool: {name}")


def handle_request(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = req.get("method")
    req_id = req.get("id")
    params = req.get("params") or {}
    is_notification = "id" not in req

    if method == "initialize":
        res = _result(req_id, {"protocolVersion": PROTOCOL_VERSION,
                               "capabilities": {"tools": {"listChanged": False}},
                               "serverInfo": {"name": TOOL_NAME, "version": TOOL_VERSION}})
        return None if is_notification else res
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return None if is_notification else _result(req_id, {})
    if method == "tools/list":
        return _result(req_id, {"tools": _TOOLS})
    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            return _result(req_id, _call_tool(name, args))
        except (ValueError, OSError, ChartError) as exc:
            return _error(req_id, -32602, str(exc))
        except Exception as exc:  # pragma: no cover
            return _error(req_id, -32603, f"internal error: {exc}")
    if is_notification:
        return None
    return _error(req_id, -32601, f"method not found: {method}")


def run_mcp_server(stdin=None, stdout=None) -> None:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(json.dumps(_error(None, -32700, "parse error")) + "\n")
            stdout.flush()
            continue
        response = handle_request(req)
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()


if __name__ == "__main__":
    run_mcp_server()
