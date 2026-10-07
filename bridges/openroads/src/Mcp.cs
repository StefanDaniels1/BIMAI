using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Net;
using System.Text;

namespace Bimai.OpenRoads
{
    public sealed class McpServerInfo
    {
        public string Name;
        public string Title;
        public string Version;
        public string Instructions;
    }

    /// <summary>
    /// A dual-era MCP server over Streamable HTTP (application/json responses only), the same behaviour as
    /// the bimai Civil 3D bridge. Modern clients (2026-07-28) send the protocol version in every request's
    /// _meta and the matching MCP-Protocol-Version / Mcp-Method / Mcp-Name headers; they may call
    /// server/discover. Legacy clients (2025-03-26 to 2025-11-25) start with initialize. No sessions.
    /// </summary>
    public sealed class McpServer
    {
        public const string Endpoint = "/mcp";
        public const string LatestLegacy = "2025-11-25";
        public static readonly string[] ModernVersions = { "2026-07-28" };
        public static readonly string[] LegacyVersions = { "2025-11-25", "2025-06-18", "2025-03-26" };

        private const string MetaVersion = "io.modelcontextprotocol/protocolVersion";
        private const string MetaServerInfo = "io.modelcontextprotocol/serverInfo";

        public const int ParseError = -32700, InvalidRequest = -32600, MethodNotFound = -32601, InvalidParams = -32602,
                         InternalError = -32603, HeaderMismatch = -32020, UnsupportedProtocolVersion = -32022;

        private readonly McpServerInfo _info;
        private readonly ToolRegistry _tools;
        private readonly Log _log;
        private readonly HttpServer _http;

        public McpServer(McpServerInfo info, ToolRegistry tools, Log log)
        {
            _info = info;
            _tools = tools;
            _log = log;
            _http = new HttpServer(Handle, log);
        }

        public int Port { get { return _http.Port; } }
        public bool IsRunning { get { return _http.IsRunning; } }
        public string Url { get { return "http://127.0.0.1:" + Port + Endpoint; } }

        public static IEnumerable<string> SupportedVersions { get { return ModernVersions.Concat(LegacyVersions); } }

        public void Start(int port)
        {
            _http.Start(port);
            _log.Info("MCP server listening on " + Url);
        }

        public void Stop() { _http.Stop(); }

        // ------------------------------------------------------------------ HTTP level

        public HttpResponse Handle(HttpRequest request)
        {
            string why;
            if (!IsLocalRequest(request, out why))
            {
                _log.Info("refused request: " + why);
                return HttpResponse.Json(403, ErrorJson(null, InvalidRequest, "Forbidden: " + why, null));
            }
            if (request.Path != Endpoint) return HttpResponse.Empty(404);
            if (request.Method != "POST")
            {
                var r = HttpResponse.Empty(405);
                r.Headers = new Dictionary<string, string> { { "Allow", "POST" } };
                return r;
            }
            return HandlePost(request);
        }

        /// <summary>Loopback peer, a loopback Host header for our port, and no foreign Origin (DNS rebinding).</summary>
        private bool IsLocalRequest(HttpRequest request, out string why)
        {
            why = "";
            if (!IPAddress.IsLoopback(request.RemoteAddress))
            {
                why = "not a local connection";
                return false;
            }
            var allowed = new[] { "127.0.0.1:" + Port, "localhost:" + Port, "[::1]:" + Port };
            string host = request.Header("Host");
            if (host == null || !allowed.Contains(host.Trim().ToLowerInvariant()))
            {
                why = "unexpected Host header '" + host + "'";
                return false;
            }
            string origin = request.Header("Origin");
            if (origin != null && !allowed.Any(h => origin.Trim().ToLowerInvariant() == "http://" + h))
            {
                why = "unexpected Origin '" + origin + "'";
                return false;
            }
            return true;
        }

        private HttpResponse HandlePost(HttpRequest request)
        {
            object parsed;
            try
            {
                parsed = Json.Parse(request.Body.Length == 0 ? "null" : Encoding.UTF8.GetString(request.Body));
            }
            catch (FormatException)
            {
                return HttpResponse.Json(400, ErrorJson(null, ParseError, "Parse error: the body is not valid JSON", null));
            }
            if (parsed is List<object>)
                return HttpResponse.Json(400, ErrorJson(null, InvalidRequest, "Batch requests are not supported", null));
            var message = parsed as Dictionary<string, object>;
            if (message == null || Json.GetString(message, "jsonrpc") != "2.0")
                return HttpResponse.Json(400, ErrorJson(null, InvalidRequest, "Invalid request: expected a JSON-RPC 2.0 object", null));

            bool hasId = message.ContainsKey("id");
            object id = Json.Get(message, "id");
            string method = Json.GetString(message, "method");

            if (!hasId)
            {
                // A notification (or a client response, legacy): accepted, nothing to answer.
                return method != null || message.ContainsKey("result") || message.ContainsKey("error")
                    ? HttpResponse.Empty(202)
                    : HttpResponse.Json(400, ErrorJson(null, InvalidRequest, "Invalid request", null));
            }
            if (method == null)
                return HttpResponse.Json(400, ErrorJson(id, InvalidRequest, "Invalid request: 'method' is required", null));

            var parameters = Json.AsObject(Json.Get(message, "params"));
            var meta = Json.AsObject(Json.Get(parameters, "_meta"));
            string modernVersion = Json.GetString(meta, MetaVersion);
            string headerVersion = request.Header("MCP-Protocol-Version");
            if (headerVersion != null) headerVersion = headerVersion.Trim();

            bool modern = modernVersion != null;
            _log.Info(method + " (" + (modern ? "modern " + modernVersion : "legacy" + (headerVersion == null ? "" : " " + headerVersion)) + ")");
            if (modern)
            {
                // 2026-07-28: headers mirror the body and must match it.
                if (headerVersion != modernVersion)
                    return Mismatch(id, "MCP-Protocol-Version header '" + headerVersion + "' does not match _meta protocol version '" + modernVersion + "'");
                string headerMethod = request.Header("Mcp-Method");
                if (headerMethod == null || headerMethod.Trim() != method)
                    return Mismatch(id, "Mcp-Method header '" + headerMethod + "' does not match method '" + method + "'");
                if (method == "tools/call" || method == "prompts/get" || method == "resources/read")
                {
                    string bodyName = Json.GetString(parameters, "name") ?? Json.GetString(parameters, "uri");
                    string headerName = DecodeHeaderValue(request.Header("Mcp-Name"));
                    if (headerName == null || headerName != bodyName)
                        return Mismatch(id, "Mcp-Name header '" + request.Header("Mcp-Name") + "' does not match '" + bodyName + "'");
                }
                if (!SupportedVersions.Contains(modernVersion))
                    return HttpResponse.Json(400, UnsupportedVersionJson(id, modernVersion));
            }
            else if (headerVersion != null && !SupportedVersions.Contains(headerVersion))
            {
                return HttpResponse.Json(400, UnsupportedVersionJson(id, headerVersion));
            }

            Dictionary<string, object> result;
            try
            {
                switch (method)
                {
                    case "initialize":
                        result = Initialize(parameters);
                        break;
                    case "server/discover":
                        result = Discover();
                        break;
                    case "ping":
                        result = Json.Obj();
                        break;
                    case "tools/list":
                        result = Json.Obj();
                        result["tools"] = _tools.All.Select(t => (object)t.ToJson()).ToList();
                        result["ttlMs"] = 3600000L;
                        result["cacheScope"] = "private";
                        break;
                    case "tools/call":
                        int errorCode;
                        string errorMessage;
                        result = CallTool(parameters, out errorCode, out errorMessage);
                        if (result == null) return HttpResponse.Json(200, ErrorJson(id, errorCode, errorMessage, null));
                        break;
                    default:
                        return HttpResponse.Json(modern ? 404 : 200, ErrorJson(id, MethodNotFound, "Method not found: " + method, null));
                }
            }
            catch (Exception ex)
            {
                _log.Error(method + " failed", ex);
                return HttpResponse.Json(200, ErrorJson(id, InternalError, "Internal error", null));
            }

            result["resultType"] = "complete";
            var resultMeta = Json.AsObject(Json.Get(result, "_meta")) ?? Json.Obj();
            resultMeta[MetaServerInfo] = ServerInfoJson();
            result["_meta"] = resultMeta;
            var response = Json.Obj();
            response["jsonrpc"] = "2.0";
            response["id"] = id;
            response["result"] = result;
            return HttpResponse.Json(200, Json.Write(response));
        }

        // ------------------------------------------------------------------ methods

        private Dictionary<string, object> Initialize(Dictionary<string, object> parameters)
        {
            string requested = Json.GetString(parameters, "protocolVersion");
            var result = Json.Obj();
            result["protocolVersion"] = requested != null && LegacyVersions.Contains(requested) ? requested : LatestLegacy;
            result["capabilities"] = Capabilities();
            result["serverInfo"] = ServerInfoJson();
            if (_info.Instructions != null) result["instructions"] = _info.Instructions;
            return result;
        }

        private Dictionary<string, object> Discover()
        {
            var result = Json.Obj();
            result["supportedVersions"] = SupportedVersions.Cast<object>().ToList();
            result["capabilities"] = Capabilities();
            result["ttlMs"] = 3600000L;
            result["cacheScope"] = "private";
            if (_info.Instructions != null) result["instructions"] = _info.Instructions;
            return result;
        }

        private static Dictionary<string, object> Capabilities()
        {
            var tools = Json.Obj();
            tools["listChanged"] = false;
            var caps = Json.Obj();
            caps["tools"] = tools;
            return caps;
        }

        private Dictionary<string, object> ServerInfoJson()
        {
            var info = Json.Obj();
            info["name"] = _info.Name;
            info["title"] = _info.Title;
            info["version"] = _info.Version;
            return info;
        }

        private Dictionary<string, object> CallTool(Dictionary<string, object> parameters, out int errorCode, out string errorMessage)
        {
            errorCode = 0;
            errorMessage = null;
            string name = Json.GetString(parameters, "name");
            if (name == null)
            {
                errorCode = InvalidParams;
                errorMessage = "tools/call needs 'name'";
                return null;
            }
            var tool = _tools.Find(name);
            if (tool == null)
            {
                errorCode = InvalidParams;
                errorMessage = "Unknown tool: " + name + ". Available: " + string.Join(", ", _tools.All.Select(t => t.Name));
                return null;
            }
            object arguments = Json.Get(parameters, "arguments");
            if (arguments != null && !(arguments is Dictionary<string, object>))
            {
                errorCode = InvalidParams;
                errorMessage = "'arguments' must be an object";
                return null;
            }

            var watch = Stopwatch.StartNew();
            try
            {
                var structured = tool.Handler(new Args(arguments as Dictionary<string, object>));
                _log.Info("tool " + name + " ok in " + watch.ElapsedMilliseconds + " ms");
                var text = Json.Obj();
                text["type"] = "text";
                text["text"] = Json.Write(structured);
                var result = Json.Obj();
                result["content"] = new List<object> { text };
                result["structuredContent"] = structured;
                result["isError"] = false;
                return result;
            }
            catch (ToolException ex)
            {
                _log.Info("tool " + name + " refused in " + watch.ElapsedMilliseconds + " ms: " + ex.Message);
                return ToolError(ex.Message);
            }
            catch (Exception ex)
            {
                _log.Error("tool " + name + " failed after " + watch.ElapsedMilliseconds + " ms", ex);
                Exception inner = ex;
                while (inner is System.Reflection.TargetInvocationException && inner.InnerException != null) inner = inner.InnerException;
                if (inner is ToolException) return ToolError(inner.Message);
                return ToolError("The bimai OpenRoads bridge hit an unexpected error (" + inner.GetType().Name + ": " + inner.Message
                                 + "). Details are in the bridge log (" + _log.Path + ").");
            }
        }

        private static Dictionary<string, object> ToolError(string message)
        {
            var text = Json.Obj();
            text["type"] = "text";
            text["text"] = message;
            var result = Json.Obj();
            result["content"] = new List<object> { text };
            result["isError"] = true;
            return result;
        }

        // ------------------------------------------------------------------ helpers

        private static HttpResponse Mismatch(object id, string message)
        {
            return HttpResponse.Json(400, ErrorJson(id, HeaderMismatch, "Header mismatch: " + message, null));
        }

        private static string UnsupportedVersionJson(object id, string requested)
        {
            var data = Json.Obj();
            data["supported"] = SupportedVersions.Cast<object>().ToList();
            data["requested"] = requested;
            return ErrorJson(id, UnsupportedProtocolVersion, "Unsupported protocol version", data);
        }

        public static string ErrorJson(object id, int code, string message, object data)
        {
            var error = Json.Obj();
            error["code"] = (long)code;
            error["message"] = message;
            if (data != null) error["data"] = data;
            var o = Json.Obj();
            o["jsonrpc"] = "2.0";
            o["id"] = id;
            o["error"] = error;
            return Json.Write(o);
        }

        /// <summary>Decodes the 2026-07-28 Base64 sentinel form "=?base64?…?=" used for non-ASCII header values.</summary>
        public static string DecodeHeaderValue(string value)
        {
            if (value == null) return null;
            value = value.Trim();
            if (value.StartsWith("=?base64?", StringComparison.Ordinal) && value.EndsWith("?=", StringComparison.Ordinal) && value.Length >= 11)
            {
                try { return Encoding.UTF8.GetString(Convert.FromBase64String(value.Substring(9, value.Length - 11))); }
                catch (FormatException) { return null; }
            }
            return value;
        }
    }
}
