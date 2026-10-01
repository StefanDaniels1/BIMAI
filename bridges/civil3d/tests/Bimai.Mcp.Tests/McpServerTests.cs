using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Bimai.Mcp;
using Xunit;

namespace Bimai.Mcp.Tests;

public sealed class ServerFixture : IDisposable
{
    public McpServer Server { get; }
    public int Port => Server.Port;
    public HttpClient Http { get; } = new() { Timeout = TimeSpan.FromSeconds(10) };

    public ServerFixture()
    {
        var tools = new ToolRegistry()
            .Add(new ToolDefinition
            {
                Name = "echo", Title = "Echo", Description = "Returns its text.",
                InputSchema = Schema(("text", "string")),
                Handler = (args, _) => Task.FromResult(new JsonObject { ["text"] = args.RequiredString("text") }),
            })
            .Add(new ToolDefinition
            {
                Name = "busy", Title = "Busy", Description = "Always refuses.",
                InputSchema = Schema(),
                Handler = (_, _) => throw new ToolException("Civil 3D is busy: a command is running."),
            })
            .Add(new ToolDefinition
            {
                Name = "crash", Title = "Crash", Description = "Throws.",
                InputSchema = Schema(),
                Handler = (_, _) => throw new InvalidOperationException("boom"),
            })
            .Add(new ToolDefinition
            {
                Name = "ünïcode-tool", Title = "Unicode", Description = "Name needs Base64 in headers.",
                InputSchema = Schema(),
                Handler = (_, _) => Task.FromResult(new JsonObject { ["ok"] = true }),
            });
        Server = new McpServer(new McpServerInfo { Name = "test", Title = "Test", Version = "1.2.3", Instructions = "Use it." },
                               tools, NullLog.Instance, maxBodyBytes: 64 * 1024);
        Server.Start(0);
    }

    public static JsonObject Schema(params (string name, string type)[] props)
    {
        var p = new JsonObject();
        foreach (var (name, type) in props) p[name] = new JsonObject { ["type"] = type };
        return new JsonObject { ["type"] = "object", ["properties"] = p };
    }

    public void Dispose()
    {
        Server.Dispose();
        Http.Dispose();
    }
}

public sealed class McpServerTests : IClassFixture<ServerFixture>
{
    private readonly ServerFixture _f;
    public McpServerTests(ServerFixture f) { _f = f; }

    private string Url => $"http://127.0.0.1:{_f.Port}/mcp";

    private async Task<(HttpStatusCode status, JsonObject? body, HttpResponseMessage raw)> Post(
        string json, IDictionary<string, string>? headers = null, string? url = null)
    {
        using var req = new HttpRequestMessage(HttpMethod.Post, url ?? Url)
        {
            Content = new StringContent(json, Encoding.UTF8, "application/json"),
        };
        req.Headers.Add("Accept", "application/json, text/event-stream");
        if (headers is not null) foreach (var (k, v) in headers) req.Headers.TryAddWithoutValidation(k, v);
        var resp = await _f.Http.SendAsync(req);
        var text = await resp.Content.ReadAsStringAsync();
        return (resp.StatusCode, text.Length == 0 ? null : JsonNode.Parse(text) as JsonObject, resp);
    }

    private static string Request(string method, JsonObject? @params = null, object id = null!) =>
        new JsonObject { ["jsonrpc"] = "2.0", ["id"] = JsonValue.Create(id ?? 1), ["method"] = method, ["params"] = @params }.ToJsonString();

    private static JsonObject ModernParams(JsonObject? extra = null, string version = McpServer.LatestModern)
    {
        var p = extra ?? new JsonObject();
        p["_meta"] = new JsonObject
        {
            ["io.modelcontextprotocol/protocolVersion"] = version,
            ["io.modelcontextprotocol/clientInfo"] = new JsonObject { ["name"] = "test", ["version"] = "1" },
            ["io.modelcontextprotocol/clientCapabilities"] = new JsonObject(),
        };
        return p;
    }

    private static Dictionary<string, string> ModernHeaders(string method, string? name = null, string version = McpServer.LatestModern)
    {
        var h = new Dictionary<string, string> { ["MCP-Protocol-Version"] = version, ["Mcp-Method"] = method };
        if (name is not null) h["Mcp-Name"] = name;
        return h;
    }

    // -------------------------------------------------------------- legacy era

    [Theory]
    [InlineData("2025-06-18", "2025-06-18")]
    [InlineData("2025-03-26", "2025-03-26")]
    [InlineData("2025-11-25", "2025-11-25")]
    [InlineData("2024-11-05", "2025-11-25")]   // unknown: we answer with our latest legacy version
    public async Task Initialize_negotiates_a_legacy_version(string requested, string expected)
    {
        var (status, body, _) = await Post(Request("initialize", new JsonObject
        {
            ["protocolVersion"] = requested, ["capabilities"] = new JsonObject(),
            ["clientInfo"] = new JsonObject { ["name"] = "c", ["version"] = "1" },
        }));
        Assert.Equal(HttpStatusCode.OK, status);
        var result = body!["result"]!.AsObject();
        Assert.Equal(expected, result["protocolVersion"]!.GetValue<string>());
        Assert.Equal("test", result["serverInfo"]!["name"]!.GetValue<string>());
        Assert.Equal("1.2.3", result["serverInfo"]!["version"]!.GetValue<string>());
        Assert.NotNull(result["capabilities"]!["tools"]);
        Assert.Equal("Use it.", result["instructions"]!.GetValue<string>());
    }

    [Fact]
    public async Task Notification_gets_202_without_body()
    {
        var (status, body, _) = await Post("""{"jsonrpc":"2.0","method":"notifications/initialized"}""");
        Assert.Equal(HttpStatusCode.Accepted, status);
        Assert.Null(body);
    }

    [Fact]
    public async Task Ping_works_for_legacy_clients()
    {
        var (status, body, _) = await Post(Request("ping"), new Dictionary<string, string> { ["MCP-Protocol-Version"] = "2025-06-18" });
        Assert.Equal(HttpStatusCode.OK, status);
        Assert.Equal("complete", body!["result"]!["resultType"]!.GetValue<string>());
    }

    [Fact]
    public async Task Tools_list_is_sorted_read_only_and_cacheable()
    {
        var (_, body, _) = await Post(Request("tools/list"));
        var result = body!["result"]!.AsObject();
        var names = result["tools"]!.AsArray().Select(t => t!["name"]!.GetValue<string>()).ToList();
        Assert.Equal(names.OrderBy(n => n, StringComparer.Ordinal), names);
        foreach (var tool in result["tools"]!.AsArray())
        {
            Assert.True(tool!["annotations"]!["readOnlyHint"]!.GetValue<bool>());
            Assert.False(tool["annotations"]!["destructiveHint"]!.GetValue<bool>());
            Assert.Equal("object", tool["inputSchema"]!["type"]!.GetValue<string>());
        }
        Assert.Equal(3_600_000, result["ttlMs"]!.GetValue<int>());
        Assert.Equal("private", result["cacheScope"]!.GetValue<string>());
        Assert.Equal("complete", result["resultType"]!.GetValue<string>());
        Assert.Equal("test", result["_meta"]!["io.modelcontextprotocol/serverInfo"]!["name"]!.GetValue<string>());
    }

    [Fact]
    public async Task Tool_call_returns_text_and_structured_content()
    {
        var (status, body, _) = await Post(Request("tools/call", new JsonObject
        {
            ["name"] = "echo", ["arguments"] = new JsonObject { ["text"] = "Knooppunt Oost" },
        }, id: "abc"));
        Assert.Equal(HttpStatusCode.OK, status);
        Assert.Equal("abc", body!["id"]!.GetValue<string>());
        var result = body["result"]!.AsObject();
        Assert.False(result["isError"]!.GetValue<bool>());
        Assert.Equal("Knooppunt Oost", result["structuredContent"]!["text"]!.GetValue<string>());
        var text = JsonNode.Parse(result["content"]![0]!["text"]!.GetValue<string>())!;
        Assert.Equal("Knooppunt Oost", text["text"]!.GetValue<string>());
    }

    [Fact]
    public async Task Tool_refusal_is_a_tool_error_with_the_message()
    {
        var (_, body, _) = await Post(Request("tools/call", new JsonObject { ["name"] = "busy" }));
        var result = body!["result"]!.AsObject();
        Assert.True(result["isError"]!.GetValue<bool>());
        Assert.Contains("busy", result["content"]![0]!["text"]!.GetValue<string>());
    }

    [Fact]
    public async Task Unexpected_exception_is_a_tool_error_not_a_crash()
    {
        var (status, body, _) = await Post(Request("tools/call", new JsonObject { ["name"] = "crash" }));
        Assert.Equal(HttpStatusCode.OK, status);
        Assert.True(body!["result"]!["isError"]!.GetValue<bool>());
        Assert.Contains("boom", body["result"]!["content"]![0]!["text"]!.GetValue<string>());
        // The server keeps working.
        var (status2, _, _) = await Post(Request("ping"));
        Assert.Equal(HttpStatusCode.OK, status2);
    }

    [Fact]
    public async Task Bad_argument_is_a_tool_error()
    {
        var (_, body, _) = await Post(Request("tools/call", new JsonObject { ["name"] = "echo", ["arguments"] = new JsonObject() }));
        Assert.True(body!["result"]!["isError"]!.GetValue<bool>());
        Assert.Contains("'text' is required", body["result"]!["content"]![0]!["text"]!.GetValue<string>());
    }

    [Fact]
    public async Task Unknown_tool_is_invalid_params_listing_the_tools()
    {
        var (_, body, _) = await Post(Request("tools/call", new JsonObject { ["name"] = "nope" }, id: 7));
        Assert.Equal(McpServer.InvalidParams, body!["error"]!["code"]!.GetValue<int>());
        Assert.Equal(7, body["id"]!.GetValue<int>());
        Assert.Contains("echo", body["error"]!["message"]!.GetValue<string>());
    }

    [Fact]
    public async Task Unknown_method_legacy_is_200_with_method_not_found()
    {
        var (status, body, _) = await Post(Request("resources/list"));
        Assert.Equal(HttpStatusCode.OK, status);
        Assert.Equal(McpServer.MethodNotFound, body!["error"]!["code"]!.GetValue<int>());
    }

    [Fact]
    public async Task Unsupported_legacy_header_version_is_400()
    {
        var (status, body, _) = await Post(Request("tools/list"), new Dictionary<string, string> { ["MCP-Protocol-Version"] = "1999-01-01" });
        Assert.Equal(HttpStatusCode.BadRequest, status);
        Assert.Equal(McpServer.UnsupportedProtocolVersion, body!["error"]!["code"]!.GetValue<int>());
    }

    // -------------------------------------------------------------- modern era (2026-07-28)

    [Fact]
    public async Task Discover_lists_versions_and_capabilities()
    {
        var (status, body, _) = await Post(Request("server/discover", ModernParams()), ModernHeaders("server/discover"));
        Assert.Equal(HttpStatusCode.OK, status);
        var result = body!["result"]!.AsObject();
        var versions = result["supportedVersions"]!.AsArray().Select(v => v!.GetValue<string>()).ToList();
        Assert.Contains("2026-07-28", versions);
        Assert.Contains("2025-06-18", versions);
        Assert.NotNull(result["capabilities"]!["tools"]);
        Assert.Equal("complete", result["resultType"]!.GetValue<string>());
        Assert.Equal("1.2.3", result["_meta"]!["io.modelcontextprotocol/serverInfo"]!["version"]!.GetValue<string>());
    }

    [Fact]
    public async Task Modern_tool_call_with_matching_headers_works()
    {
        var p = ModernParams(new JsonObject { ["name"] = "echo", ["arguments"] = new JsonObject { ["text"] = "hi" } });
        var (status, body, _) = await Post(Request("tools/call", p), ModernHeaders("tools/call", "echo"));
        Assert.Equal(HttpStatusCode.OK, status);
        Assert.Equal("hi", body!["result"]!["structuredContent"]!["text"]!.GetValue<string>());
    }

    [Fact]
    public async Task Modern_base64_tool_name_header_is_decoded()
    {
        var encoded = "=?base64?" + Convert.ToBase64String(Encoding.UTF8.GetBytes("ünïcode-tool")) + "?=";
        var (status, body, _) = await Post(Request("tools/call", ModernParams(new JsonObject { ["name"] = "ünïcode-tool" })),
                                           ModernHeaders("tools/call", encoded));
        Assert.Equal(HttpStatusCode.OK, status);
        Assert.True(body!["result"]!["structuredContent"]!["ok"]!.GetValue<bool>());
    }

    [Theory]
    [InlineData("name")]      // Mcp-Name differs from the body
    [InlineData("method")]    // Mcp-Method differs
    [InlineData("version")]   // MCP-Protocol-Version differs from _meta
    [InlineData("missing")]   // Mcp-Name missing
    public async Task Modern_header_mismatch_is_400_and_runs_nothing(string what)
    {
        var headers = ModernHeaders("tools/call", "echo");
        if (what == "name") headers["Mcp-Name"] = "busy";
        if (what == "method") headers["Mcp-Method"] = "tools/list";
        if (what == "version") headers["MCP-Protocol-Version"] = "2025-06-18";
        if (what == "missing") headers.Remove("Mcp-Name");
        var before = _f.Server.ToolCalls;
        var (status, body, _) = await Post(Request("tools/call", ModernParams(new JsonObject
        {
            ["name"] = "echo", ["arguments"] = new JsonObject { ["text"] = "x" },
        })), headers);
        Assert.Equal(HttpStatusCode.BadRequest, status);
        Assert.Equal(McpServer.HeaderMismatch, body!["error"]!["code"]!.GetValue<int>());
        Assert.Equal(before, _f.Server.ToolCalls);
    }

    [Fact]
    public async Task Modern_unsupported_version_lists_supported_versions()
    {
        var (status, body, _) = await Post(Request("tools/list", ModernParams(version: "2099-01-01")),
                                           ModernHeaders("tools/list", version: "2099-01-01"));
        Assert.Equal(HttpStatusCode.BadRequest, status);
        var error = body!["error"]!.AsObject();
        Assert.Equal(McpServer.UnsupportedProtocolVersion, error["code"]!.GetValue<int>());
        Assert.Equal("2099-01-01", error["data"]!["requested"]!.GetValue<string>());
        Assert.Contains("2026-07-28", error["data"]!["supported"]!.AsArray().Select(v => v!.GetValue<string>()));
    }

    [Fact]
    public async Task Modern_unknown_method_is_404_with_method_not_found()
    {
        var (status, body, _) = await Post(Request("prompts/list", ModernParams()), ModernHeaders("prompts/list"));
        Assert.Equal(HttpStatusCode.NotFound, status);
        Assert.Equal(McpServer.MethodNotFound, body!["error"]!["code"]!.GetValue<int>());
    }

    // -------------------------------------------------------------- HTTP and security

    [Fact]
    public async Task Foreign_origin_is_403()
    {
        var before = _f.Server.ToolCalls;
        var (status, _, _) = await Post(Request("tools/call", new JsonObject { ["name"] = "echo", ["arguments"] = new JsonObject { ["text"] = "x" } }),
                                        new Dictionary<string, string> { ["Origin"] = "https://evil.example" });
        Assert.Equal(HttpStatusCode.Forbidden, status);
        Assert.Equal(before, _f.Server.ToolCalls);
    }

    [Fact]
    public async Task Local_origin_is_allowed()
    {
        var (status, _, _) = await Post(Request("ping"), new Dictionary<string, string> { ["Origin"] = $"http://localhost:{_f.Port}" });
        Assert.Equal(HttpStatusCode.OK, status);
    }

    [Theory]
    [InlineData("evil.example:{0}")]
    [InlineData("127.0.0.1:1")]
    [InlineData("127.0.0.1")]
    public async Task Foreign_host_header_is_403(string hostTemplate)
    {
        var raw = await Raw($"POST /mcp HTTP/1.1\r\nHost: {string.Format(hostTemplate, _f.Port)}\r\nContent-Type: application/json\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{{}}");
        Assert.StartsWith("HTTP/1.1 403", raw);
    }

    [Fact]
    public async Task Get_and_delete_are_405()
    {
        var get = await _f.Http.GetAsync(Url);
        Assert.Equal(HttpStatusCode.MethodNotAllowed, get.StatusCode);
        Assert.Contains("POST", get.Content.Headers.Allow);
        var del = await _f.Http.DeleteAsync(Url);
        Assert.Equal(HttpStatusCode.MethodNotAllowed, del.StatusCode);
    }

    [Fact]
    public async Task Other_paths_are_404()
    {
        var (status, _, _) = await Post(Request("ping"), url: $"http://127.0.0.1:{_f.Port}/other");
        Assert.Equal(HttpStatusCode.NotFound, status);
    }

    [Fact]
    public async Task Invalid_json_is_400_parse_error()
    {
        var (status, body, _) = await Post("{ nope");
        Assert.Equal(HttpStatusCode.BadRequest, status);
        Assert.Equal(McpServer.ParseError, body!["error"]!["code"]!.GetValue<int>());
    }

    [Fact]
    public async Task Batches_are_rejected()
    {
        var (status, body, _) = await Post("[" + Request("ping") + "]");
        Assert.Equal(HttpStatusCode.BadRequest, status);
        Assert.Equal(McpServer.InvalidRequest, body!["error"]!["code"]!.GetValue<int>());
    }

    [Fact]
    public async Task Too_large_body_is_413()
    {
        var big = Request("tools/call", new JsonObject { ["name"] = "echo", ["arguments"] = new JsonObject { ["text"] = new string('x', 70_000) } });
        var (status, _, _) = await Post(big);
        Assert.Equal((HttpStatusCode)413, status);
    }

    [Fact]
    public async Task Chunked_body_is_supported()
    {
        var json = Request("tools/call", new JsonObject { ["name"] = "echo", ["arguments"] = new JsonObject { ["text"] = "chunked" } });
        var bytes = Encoding.UTF8.GetBytes(json);
        var half = bytes.Length / 2;
        string Chunk(byte[] b, int from, int len) => $"{len:x}\r\n{Encoding.UTF8.GetString(b, from, len)}\r\n";
        var raw = await Raw($"POST /mcp HTTP/1.1\r\nHost: 127.0.0.1:{_f.Port}\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n" +
                            Chunk(bytes, 0, half) + Chunk(bytes, half, bytes.Length - half) + "0\r\n\r\n");
        Assert.StartsWith("HTTP/1.1 200", raw);
        Assert.Contains("\"chunked\"", raw);
    }

    [Fact]
    public async Task Expect_continue_is_answered()
    {
        var json = Request("ping");
        var raw = await Raw($"POST /mcp HTTP/1.1\r\nHost: 127.0.0.1:{_f.Port}\r\nContent-Length: {Encoding.UTF8.GetByteCount(json)}\r\nExpect: 100-continue\r\nConnection: close\r\n\r\n{json}");
        Assert.StartsWith("HTTP/1.1 100 Continue", raw);
        Assert.Contains("HTTP/1.1 200", raw);
    }

    [Fact]
    public async Task Keep_alive_serves_several_requests_on_one_connection()
    {
        using var client = new TcpClient();
        await client.ConnectAsync(IPAddress.Loopback, _f.Port);
        var stream = client.GetStream();
        var reader = new StreamReader(stream, Encoding.UTF8);
        for (int i = 0; i < 3; i++)
        {
            var json = Request("ping", id: i);
            var req = $"POST /mcp HTTP/1.1\r\nHost: 127.0.0.1:{_f.Port}\r\nContent-Type: application/json\r\nContent-Length: {Encoding.UTF8.GetByteCount(json)}\r\n\r\n{json}";
            var bytes = Encoding.UTF8.GetBytes(req);
            await stream.WriteAsync(bytes);
            var status = await reader.ReadLineAsync();
            Assert.Equal("HTTP/1.1 200 OK", status);
            int length = 0;
            string? line;
            while (!string.IsNullOrEmpty(line = await reader.ReadLineAsync()))
                if (line.StartsWith("Content-Length:", StringComparison.OrdinalIgnoreCase)) length = int.Parse(line[15..].Trim());
            var body = new char[length];
            int read = 0;
            while (read < length) read += await reader.ReadAsync(body, read, length - read);
            Assert.Equal(i, JsonNode.Parse(new string(body))!["id"]!.GetValue<int>());
        }
    }

    [Fact]
    public async Task Ipv6_loopback_is_served_when_available()
    {
        if (!Socket.OSSupportsIPv6) return;
        using var http = new HttpClient();
        using var req = new HttpRequestMessage(HttpMethod.Post, $"http://[::1]:{_f.Port}/mcp") { Content = new StringContent(Request("ping"), Encoding.UTF8, "application/json") };
        try
        {
            var resp = await http.SendAsync(req);
            Assert.Equal(HttpStatusCode.OK, resp.StatusCode);
        }
        catch (HttpRequestException)
        {
            // IPv6 loopback unavailable on this machine: the server logs it and serves IPv4 only.
        }
    }

    [Fact]
    public async Task Concurrent_calls_all_succeed()
    {
        var calls = Enumerable.Range(0, 25).Select(i => Post(Request("tools/call", new JsonObject
        {
            ["name"] = "echo", ["arguments"] = new JsonObject { ["text"] = $"t{i}" },
        }, id: i)));
        var results = await Task.WhenAll(calls);
        for (int i = 0; i < results.Length; i++)
            Assert.Equal($"t{i}", results[i].body!["result"]!["structuredContent"]!["text"]!.GetValue<string>());
    }

    [Fact]
    public async Task Session_id_header_is_ignored_and_never_minted()
    {
        var (status, _, raw) = await Post(Request("ping"), new Dictionary<string, string> { ["Mcp-Session-Id"] = "abc" });
        Assert.Equal(HttpStatusCode.OK, status);
        Assert.False(raw.Headers.Contains("Mcp-Session-Id"));
    }

    private async Task<string> Raw(string request)
    {
        using var client = new TcpClient();
        await client.ConnectAsync(IPAddress.Loopback, _f.Port);
        var stream = client.GetStream();
        await stream.WriteAsync(Encoding.UTF8.GetBytes(request));
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        var buffer = new MemoryStream();
        var chunk = new byte[8192];
        try
        {
            int n;
            while ((n = await stream.ReadAsync(chunk, cts.Token)) > 0) buffer.Write(chunk, 0, n);
        }
        catch (OperationCanceledException) { }
        catch (IOException) { }
        return Encoding.UTF8.GetString(buffer.ToArray());
    }
}
