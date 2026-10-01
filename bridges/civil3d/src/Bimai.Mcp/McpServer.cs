using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace Bimai.Mcp;

public sealed class McpServerInfo
{
    public required string Name { get; init; }
    public required string Title { get; init; }
    public required string Version { get; init; }
    public string? Instructions { get; init; }
}

/// <summary>
/// A dual-era MCP server over Streamable HTTP (application/json responses only).
/// Modern clients (2026-07-28) send the protocol version in every request's _meta and the matching
/// MCP-Protocol-Version / Mcp-Method / Mcp-Name headers; they may call server/discover.
/// Legacy clients (2025-03-26 to 2025-11-25) start with initialize. No sessions are kept.
/// </summary>
public sealed class McpServer : IDisposable
{
    public const string Endpoint = "/mcp";
    public const string LatestModern = "2026-07-28";
    public const string LatestLegacy = "2025-11-25";
    public static readonly string[] ModernVersions = { "2026-07-28" };
    public static readonly string[] LegacyVersions = { "2025-11-25", "2025-06-18", "2025-03-26" };
    public static IEnumerable<string> SupportedVersions => ModernVersions.Concat(LegacyVersions);

    private const string MetaVersion = "io.modelcontextprotocol/protocolVersion";
    private const string MetaServerInfo = "io.modelcontextprotocol/serverInfo";

    // JSON-RPC and MCP error codes.
    public const int ParseError = -32700, InvalidRequest = -32600, MethodNotFound = -32601, InvalidParams = -32602,
                     InternalError = -32603, HeaderMismatch = -32020, UnsupportedProtocolVersion = -32022;

    private readonly McpServerInfo _info;
    private readonly ToolRegistry _tools;
    private readonly ILog _log;
    private readonly HttpServer _http;
    private static readonly JsonSerializerOptions Compact = new() { WriteIndented = false };

    public int Port => _http.Port;
    public bool IsRunning => _http.IsRunning;
    public string Url => $"http://127.0.0.1:{Port}{Endpoint}";
    public long ToolCalls => Interlocked.Read(ref _toolCalls);
    private long _toolCalls;

    public McpServer(McpServerInfo info, ToolRegistry tools, ILog log, int maxBodyBytes = 4 * 1024 * 1024)
    {
        _info = info;
        _tools = tools;
        _log = log;
        _http = new HttpServer(HandleAsync, log, maxBodyBytes);
    }

    public void Start(int port)
    {
        _http.Start(port);
        _log.Info($"MCP server listening on {Url}");
    }

    public void Stop() => _http.Stop();

    public void Dispose() => _http.Dispose();

    // ------------------------------------------------------------------ HTTP level

    public Task<HttpResponse> HandleAsync(HttpRequest request, CancellationToken ct)
    {
        if (!IsLocalRequest(request, out var why))
        {
            _log.Info($"refused request: {why}");
            return Task.FromResult(HttpResponse.Json(403, ErrorJson(null, InvalidRequest, "Forbidden: " + why)));
        }
        if (request.Path != Endpoint)
            return Task.FromResult(HttpResponse.Empty(404));
        if (request.Method != "POST")
            return Task.FromResult(HttpResponse.Empty(405, new Dictionary<string, string> { ["Allow"] = "POST" }));
        return HandlePostAsync(request, ct);
    }

    /// <summary>Loopback peer, a loopback Host header for our port, and no foreign Origin (DNS rebinding).</summary>
    private bool IsLocalRequest(HttpRequest request, out string why)
    {
        why = "";
        if (!System.Net.IPAddress.IsLoopback(request.RemoteAddress))
        {
            why = "not a local connection";
            return false;
        }
        var allowedHosts = new[] { $"127.0.0.1:{Port}", $"localhost:{Port}", $"[::1]:{Port}" };
        var host = request.Header("Host");
        if (host is null || !allowedHosts.Contains(host.Trim().ToLowerInvariant()))
        {
            why = $"unexpected Host header '{host}'";
            return false;
        }
        var origin = request.Header("Origin");
        if (origin is not null && !allowedHosts.Any(h => origin.Trim().ToLowerInvariant() == "http://" + h))
        {
            why = $"unexpected Origin '{origin}'";
            return false;
        }
        return true;
    }

    private async Task<HttpResponse> HandlePostAsync(HttpRequest request, CancellationToken ct)
    {
        JsonNode? parsed;
        try
        {
            parsed = JsonNode.Parse(request.Body.Length == 0 ? "null" : Encoding.UTF8.GetString(request.Body));
        }
        catch (JsonException)
        {
            return HttpResponse.Json(400, ErrorJson(null, ParseError, "Parse error: the body is not valid JSON"));
        }
        if (parsed is JsonArray)
            return HttpResponse.Json(400, ErrorJson(null, InvalidRequest, "Batch requests are not supported"));
        if (parsed is not JsonObject message || message["jsonrpc"]?.GetValue<string>() != "2.0")
            return HttpResponse.Json(400, ErrorJson(null, InvalidRequest, "Invalid request: expected a JSON-RPC 2.0 object"));

        var hasId = message.TryGetPropertyValue("id", out var idNode);
        var method = message["method"] is JsonValue mv && mv.TryGetValue(out string? m) ? m : null;

        if (!hasId)
        {
            // A notification (or a client response, legacy): accepted, nothing to answer.
            return method is not null || message.ContainsKey("result") || message.ContainsKey("error")
                ? HttpResponse.Empty(202)
                : HttpResponse.Json(400, ErrorJson(null, InvalidRequest, "Invalid request"));
        }
        if (method is null)
            return HttpResponse.Json(400, ErrorJson(idNode, InvalidRequest, "Invalid request: 'method' is required"));

        var @params = message["params"] as JsonObject;
        var meta = @params?["_meta"] as JsonObject;
        string? modernVersion = meta?[MetaVersion] is JsonValue vv && vv.TryGetValue(out string? s) ? s : null;
        var headerVersion = request.Header("MCP-Protocol-Version")?.Trim();

        bool modern = modernVersion is not null;
        _log.Info($"{method} ({(modern ? "modern " + modernVersion : "legacy" + (headerVersion is null ? "" : " " + headerVersion))})");
        if (modern)
        {
            // 2026-07-28: headers mirror the body and must match it.
            if (headerVersion != modernVersion)
                return Mismatch(idNode, $"MCP-Protocol-Version header '{headerVersion}' does not match _meta protocol version '{modernVersion}'");
            if (request.Header("Mcp-Method")?.Trim() != method)
                return Mismatch(idNode, $"Mcp-Method header '{request.Header("Mcp-Method")}' does not match method '{method}'");
            if (method is "tools/call" or "prompts/get" or "resources/read")
            {
                var bodyName = (@params?["name"] ?? @params?["uri"]) is JsonValue nv && nv.TryGetValue(out string? n) ? n : null;
                var headerName = DecodeHeaderValue(request.Header("Mcp-Name"));
                if (headerName is null || headerName != bodyName)
                    return Mismatch(idNode, $"Mcp-Name header '{request.Header("Mcp-Name")}' does not match '{bodyName}'");
            }
            if (!SupportedVersions.Contains(modernVersion))
                return HttpResponse.Json(400, UnsupportedVersionJson(idNode, modernVersion!));
        }
        else if (headerVersion is not null && !SupportedVersions.Contains(headerVersion))
        {
            return HttpResponse.Json(400, UnsupportedVersionJson(idNode, headerVersion));
        }

        JsonObject result;
        try
        {
            switch (method)
            {
                case "initialize":
                    result = Initialize(@params);
                    break;
                case "server/discover":
                    result = Discover();
                    break;
                case "ping":
                    result = new JsonObject();
                    break;
                case "tools/list":
                    result = new JsonObject
                    {
                        ["tools"] = new JsonArray(_tools.All.Select(t => (JsonNode)t.ToJson()).ToArray()),
                        ["ttlMs"] = 3_600_000,
                        ["cacheScope"] = "private",
                    };
                    break;
                case "tools/call":
                    var call = await CallToolAsync(@params, ct).ConfigureAwait(false);
                    if (call.Error is { } err) return HttpResponse.Json(200, ErrorJson(idNode, err.Code, err.Message));
                    result = call.Result!;
                    break;
                default:
                    var notFound = ErrorJson(idNode, MethodNotFound, $"Method not found: {method}");
                    return HttpResponse.Json(modern ? 404 : 200, notFound);
            }
        }
        catch (Exception ex)
        {
            _log.Error($"{method} failed", ex);
            return HttpResponse.Json(200, ErrorJson(idNode, InternalError, "Internal error"));
        }

        result["resultType"] = "complete";
        var resultMeta = result["_meta"] as JsonObject ?? new JsonObject();
        resultMeta[MetaServerInfo] = ServerInfoJson();
        result["_meta"] = resultMeta;
        var response = new JsonObject { ["jsonrpc"] = "2.0", ["id"] = idNode?.DeepClone(), ["result"] = result };
        return HttpResponse.Json(200, response.ToJsonString(Compact));
    }

    // ------------------------------------------------------------------ methods

    private JsonObject Initialize(JsonObject? @params)
    {
        var requested = @params?["protocolVersion"] is JsonValue v && v.TryGetValue(out string? s) ? s : null;
        var negotiated = requested is not null && LegacyVersions.Contains(requested) ? requested : LatestLegacy;
        var result = new JsonObject
        {
            ["protocolVersion"] = negotiated,
            ["capabilities"] = Capabilities(),
            ["serverInfo"] = ServerInfoJson(),
        };
        if (_info.Instructions is not null) result["instructions"] = _info.Instructions;
        return result;
    }

    private JsonObject Discover()
    {
        var result = new JsonObject
        {
            ["supportedVersions"] = new JsonArray(SupportedVersions.Select(v => (JsonNode)v).ToArray()),
            ["capabilities"] = Capabilities(),
            ["ttlMs"] = 3_600_000,
            ["cacheScope"] = "private",
        };
        if (_info.Instructions is not null) result["instructions"] = _info.Instructions;
        return result;
    }

    private static JsonObject Capabilities() => new() { ["tools"] = new JsonObject { ["listChanged"] = false } };

    private JsonObject ServerInfoJson() => new() { ["name"] = _info.Name, ["title"] = _info.Title, ["version"] = _info.Version };

    private sealed record RpcError(int Code, string Message);
    private sealed record CallOutcome(JsonObject? Result, RpcError? Error);

    private async Task<CallOutcome> CallToolAsync(JsonObject? @params, CancellationToken ct)
    {
        var name = @params?["name"] is JsonValue nv && nv.TryGetValue(out string? n) ? n : null;
        if (name is null) return new(null, new(InvalidParams, "tools/call needs 'name'"));
        var tool = _tools.Find(name);
        if (tool is null)
            return new(null, new(InvalidParams, $"Unknown tool: {name}. Available: {string.Join(", ", _tools.All.Select(t => t.Name))}"));
        if (@params?["arguments"] is not null and not JsonObject)
            return new(null, new(InvalidParams, "'arguments' must be an object"));

        Interlocked.Increment(ref _toolCalls);
        var watch = Stopwatch.StartNew();
        try
        {
            var structured = await tool.Handler(new Args(@params?["arguments"] as JsonObject), ct).ConfigureAwait(false);
            _log.Info($"tool {name} ok in {watch.ElapsedMilliseconds} ms");
            return new(new JsonObject
            {
                ["content"] = new JsonArray(new JsonObject { ["type"] = "text", ["text"] = structured.ToJsonString(Compact) }),
                ["structuredContent"] = structured,
                ["isError"] = false,
            }, null);
        }
        catch (ToolException ex)
        {
            _log.Info($"tool {name} refused in {watch.ElapsedMilliseconds} ms: {ex.Message}");
            return new(ToolError(ex.Message), null);
        }
        catch (Exception ex)
        {
            _log.Error($"tool {name} failed after {watch.ElapsedMilliseconds} ms", ex);
            return new(ToolError($"The bimai Civil 3D bridge hit an unexpected error ({ex.GetType().Name}: {ex.Message}). " +
                              "Details are in the bridge log; try again or run BIMAIBRIDGE in Civil 3D."), null);
        }
    }

    private static JsonObject ToolError(string message) => new()
    {
        ["content"] = new JsonArray(new JsonObject { ["type"] = "text", ["text"] = message }),
        ["isError"] = true,
    };

    // ------------------------------------------------------------------ helpers

    private static HttpResponse Mismatch(JsonNode? id, string message) =>
        HttpResponse.Json(400, ErrorJson(id, HeaderMismatch, "Header mismatch: " + message));

    private static string UnsupportedVersionJson(JsonNode? id, string requested) =>
        ErrorJson(id, UnsupportedProtocolVersion, "Unsupported protocol version", new JsonObject
        {
            ["supported"] = new JsonArray(SupportedVersions.Select(v => (JsonNode)v).ToArray()),
            ["requested"] = requested,
        });

    public static string ErrorJson(JsonNode? id, int code, string message, JsonNode? data = null)
    {
        var error = new JsonObject { ["code"] = code, ["message"] = message };
        if (data is not null) error["data"] = data;
        return new JsonObject { ["jsonrpc"] = "2.0", ["id"] = id?.DeepClone(), ["error"] = error }.ToJsonString(Compact);
    }

    /// <summary>Decodes the 2026-07-28 Base64 sentinel form "=?base64?…?=" used for non-ASCII header values.</summary>
    public static string? DecodeHeaderValue(string? value)
    {
        if (value is null) return null;
        value = value.Trim();
        if (value.StartsWith("=?base64?", StringComparison.Ordinal) && value.EndsWith("?=", StringComparison.Ordinal) && value.Length >= 11)
        {
            try { return Encoding.UTF8.GetString(Convert.FromBase64String(value[9..^2])); }
            catch (FormatException) { return null; }
        }
        return value;
    }
}
