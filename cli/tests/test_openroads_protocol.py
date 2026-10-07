"""The OpenRoads bridge's MCP protocol, against its development host (the real server, without OpenRoads).

Runs when BIMAI_OPENROADS_DEVHOST names the host command (Windows CI compiles it with the .NET Framework's
csc.exe, exactly as bimai does on a user's PC; locally e.g. "dotnet path/to/devnet.dll").
"""
from __future__ import annotations

import base64
import http.client
import json
import os
import shlex
import subprocess

import pytest

from bimai import bridges

COMMAND = os.environ.get("BIMAI_OPENROADS_DEVHOST")
pytestmark = pytest.mark.skipif(not COMMAND, reason="set BIMAI_OPENROADS_DEVHOST to run the OpenRoads bridge host")
MODERN = "2026-07-28"


@pytest.fixture(scope="module")
def port():
    args = shlex.split(COMMAND, posix=os.name != "nt") + ["0"]
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace")
    line = proc.stdout.readline()
    assert line.startswith("listening "), (line, proc.stderr.read() if proc.poll() is not None else "")
    yield int(line.split()[1])
    proc.kill()
    proc.wait(timeout=10)


def post(port, body, headers=None, host=None, path="/mcp", method="POST"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    data = body if isinstance(body, (bytes, str)) else json.dumps(body)
    hdrs = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", **(headers or {})}
    conn.putrequest(method, path, skip_host=True)
    conn.putheader("Host", host or f"127.0.0.1:{port}")
    for k, v in hdrs.items():
        conn.putheader(k, v)
    raw = data.encode() if isinstance(data, str) else data
    conn.putheader("Content-Length", str(len(raw)))
    conn.endheaders(raw)
    response = conn.getresponse()
    text = response.read().decode("utf-8")
    conn.close()
    return response.status, (json.loads(text) if text else None)


def modern(port, method, params=None, name=None, headers=None, id=1):
    params = dict(params or {})
    params["_meta"] = {"io.modelcontextprotocol/protocolVersion": MODERN}
    hdrs = {"MCP-Protocol-Version": MODERN, "Mcp-Method": method, **({"Mcp-Name": name} if name else {}), **(headers or {})}
    return post(port, {"jsonrpc": "2.0", "id": id, "method": method, "params": params}, hdrs)


def test_discover_and_bimai_probe(port):
    status, body = modern(port, "server/discover")
    assert status == 200 and body["id"] == 1
    result = body["result"]
    assert MODERN in result["supportedVersions"] and result["resultType"] == "complete"
    assert result["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "bimai-openroads"
    assert bridges.probe(port)["name"] == "bimai-openroads"          # what `bimai connect` checks


def test_legacy_initialize(port):
    status, body = post(port, {"jsonrpc": "2.0", "id": "a", "method": "initialize",
                               "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}}})
    assert status == 200 and body["id"] == "a"
    assert body["result"]["protocolVersion"] == "2025-06-18"
    assert body["result"]["serverInfo"]["title"] == "bimai OpenRoads bridge"
    status, _ = post(port, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert status == 202


def test_tools_are_read_only_and_sorted(port):
    _, body = modern(port, "tools/list")
    tools = body["result"]["tools"]
    names = [t["name"] for t in tools]
    assert names == sorted(names) and len(names) == 9
    assert {"get_drawing_info", "list_alignments", "get_alignment", "locate_on_alignment", "list_profiles", "get_profile",
            "list_corridors", "list_terrains", "get_terrain_elevation"} == set(names)
    assert all(t["annotations"]["readOnlyHint"] and not t["annotations"]["destructiveHint"] for t in tools)
    assert next(t for t in tools if t["name"] == "get_alignment")["inputSchema"]["required"] == ["alignment"]


def test_tool_outside_openroads_explains(port):
    _, body = modern(port, "tools/call", {"name": "list_alignments", "arguments": {}}, name="list_alignments")
    result = body["result"]
    assert result["isError"] is True and "only works inside OpenRoads Designer" in result["content"][0]["text"]


def test_header_rules(port):
    status, body = post(port, {"jsonrpc": "2.0", "id": 2, "method": "tools/list",
                               "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": MODERN}}},
                         {"MCP-Protocol-Version": MODERN, "Mcp-Method": "tools/call"})
    assert status == 400 and body["error"]["code"] == -32020
    status, body = modern(port, "tools/call", {"name": "list_terrains"}, name="list_alignments")
    assert status == 400 and body["error"]["code"] == -32020
    encoded = "=?base64?" + base64.b64encode("list_terrains".encode()).decode() + "?="
    status, body = modern(port, "tools/call", {"name": "list_terrains"}, name=encoded)
    assert status == 200 and body["result"]["isError"] is True


def test_unsupported_version(port):
    status, body = post(port, {"jsonrpc": "2.0", "id": 3, "method": "tools/list",
                               "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2099-01-01"}}},
                         {"MCP-Protocol-Version": "2099-01-01", "Mcp-Method": "tools/list"})
    assert status == 400 and body["error"]["code"] == -32022 and MODERN in body["error"]["data"]["supported"]


def test_bad_requests(port):
    assert post(port, "{not json")[1]["error"]["code"] == -32700
    assert post(port, [{"jsonrpc": "2.0", "id": 1, "method": "ping"}])[1]["error"]["code"] == -32600
    _, body = modern(port, "tools/call", {"name": "nope"}, name="nope")
    assert body["error"]["code"] == -32602 and "Available:" in body["error"]["message"]
    status, body = modern(port, "no/such")
    assert status == 404 and body["error"]["code"] == -32601
    _, body = modern(port, "ping", id=12345678901)
    assert body["id"] == 12345678901


def test_local_only(port):
    status, body = post(port, {"jsonrpc": "2.0", "id": 1, "method": "ping"}, host="evil.example:80")
    assert status == 403 and "Host" in body["error"]["message"]
    status, _ = post(port, {"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"Origin": "http://evil.example"})
    assert status == 403
    assert post(port, "", path="/other")[0] == 404
    assert post(port, "", method="GET")[0] == 405


def test_unicode_round_trip(port):
    _, body = modern(port, "ping", id="tunnel-Ø-✓")
    assert body["id"] == "tunnel-Ø-✓"
