"""A small MCP server over stdio (newline-delimited JSON-RPC), for bimai's own servers such as the SCIA bridge.

Both protocol eras, like bimai's HTTP bridges: modern clients (2026-07-28) put the protocol version in each
request's _meta and may call server/discover; legacy clients (2025-03-26 to 2025-11-25) start with initialize.
Tools are read-only. A tool raises ToolError for a refusal the person should read; anything else is reported
as an unexpected error without crashing the server.
"""
from __future__ import annotations

import json
import sys
import traceback
from dataclasses import dataclass
from typing import Callable, TextIO

MODERN = ["2026-07-28"]
LEGACY = ["2025-11-25", "2025-06-18", "2025-03-26"]
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_SERVER = "io.modelcontextprotocol/serverInfo"
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL = -32700, -32600, -32601, -32602, -32603
UNSUPPORTED_VERSION = -32022


class ToolError(Exception):
    """A refusal with a message for the person (bad arguments, no project open, …)."""


@dataclass
class Tool:
    name: str
    title: str
    description: str
    input_schema: dict
    handler: Callable[[dict], dict]

    def as_json(self) -> dict:
        return {"name": self.name, "title": self.title, "description": self.description,
                "inputSchema": self.input_schema,
                "annotations": {"title": self.title, "readOnlyHint": True, "destructiveHint": False,
                                "idempotentHint": True, "openWorldHint": False}}


def schema(properties: dict[str, tuple[str, str]], required: tuple[str, ...] = (), enums: dict | None = None) -> dict:
    """An object schema from {name: (type, description)}."""
    props = {}
    for name, (kind, description) in properties.items():
        props[name] = {"type": kind, "description": description}
        if enums and name in enums:
            props[name]["enum"] = enums[name]
    out = {"type": "object", "properties": props, "additionalProperties": False}
    if required:
        out["required"] = list(required)
    return out


class Server:
    def __init__(self, name: str, title: str, version: str, instructions: str, tools: list[Tool], log: Callable = None):
        self.info = {"name": name, "title": title, "version": version}
        self.instructions = instructions
        self.tools = {t.name: t for t in sorted(tools, key=lambda t: t.name)}
        self.log = log or (lambda message: None)

    def handle(self, message) -> dict | None:
        """One JSON-RPC message in, the response out (None for notifications)."""
        if isinstance(message, list):
            return self._error(None, INVALID_REQUEST, "Batch requests are not supported")
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return self._error(None, INVALID_REQUEST, "Invalid request: expected a JSON-RPC 2.0 object")
        method = message.get("method")
        if "id" not in message:
            return None                                  # a notification (or a client's response): nothing to say
        rid = message["id"]
        if not isinstance(method, str):
            return self._error(rid, INVALID_REQUEST, "Invalid request: 'method' is required")
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        version = ((params.get("_meta") or {}) if isinstance(params.get("_meta"), dict) else {}).get(META_VERSION)
        if version is not None and version not in MODERN + LEGACY:
            return self._error(rid, UNSUPPORTED_VERSION, "Unsupported protocol version",
                               {"supported": MODERN + LEGACY, "requested": version})
        try:
            if method == "initialize":
                requested = params.get("protocolVersion")
                result = {"protocolVersion": requested if requested in LEGACY else LEGACY[0],
                          "capabilities": {"tools": {"listChanged": False}}, "serverInfo": self.info,
                          "instructions": self.instructions}
            elif method == "server/discover":
                result = {"supportedVersions": MODERN + LEGACY, "capabilities": {"tools": {"listChanged": False}},
                          "instructions": self.instructions, "ttlMs": 3_600_000, "cacheScope": "private"}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": [t.as_json() for t in self.tools.values()], "ttlMs": 3_600_000, "cacheScope": "private"}
            elif method == "tools/call":
                name = params.get("name")
                tool = self.tools.get(name)
                if tool is None:
                    return self._error(rid, INVALID_PARAMS, f"Unknown tool: {name}. Available: {', '.join(self.tools)}")
                arguments = params.get("arguments") or {}
                if not isinstance(arguments, dict):
                    return self._error(rid, INVALID_PARAMS, "'arguments' must be an object")
                result = self._call(tool, arguments)
            else:
                return self._error(rid, METHOD_NOT_FOUND, f"Method not found: {method}")
        except Exception as exc:                          # never let one request take the server down
            self.log(f"{method} failed: {exc}\n{traceback.format_exc()}")
            return self._error(rid, INTERNAL, "Internal error")
        result["resultType"] = "complete"
        result.setdefault("_meta", {})[META_SERVER] = self.info
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    def _call(self, tool: Tool, arguments: dict) -> dict:
        try:
            structured = tool.handler(arguments)
        except ToolError as exc:
            self.log(f"tool {tool.name} refused: {exc}")
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        except Exception as exc:
            self.log(f"tool {tool.name} failed: {exc}\n{traceback.format_exc()}")
            return {"content": [{"type": "text", "text": f"The bridge hit an unexpected error ({type(exc).__name__}: {exc})."}],
                    "isError": True}
        return {"content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False)}],
                "structuredContent": structured, "isError": False}

    @staticmethod
    def _error(rid, code: int, message: str, data=None) -> dict:
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": rid, "error": error}

    def serve(self, stdin: TextIO = None, stdout: TextIO = None) -> None:
        """Reads one JSON message per line until the client closes stdin."""
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        for line in stdin:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except ValueError:
                response = self._error(None, PARSE_ERROR, "Parse error: not valid JSON")
            else:
                response = self.handle(message)
            if response is not None:
                stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                stdout.flush()
