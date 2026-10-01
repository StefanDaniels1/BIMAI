using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Bimai.Mcp;

/// <summary>An HTTP request as the MCP layer needs it.</summary>
public sealed class HttpRequest
{
    public required string Method { get; init; }
    public required string Path { get; init; }
    public required IReadOnlyDictionary<string, string> Headers { get; init; }   // case-insensitive names
    public required byte[] Body { get; init; }
    public required IPAddress RemoteAddress { get; init; }

    public string? Header(string name) => Headers.TryGetValue(name, out var v) ? v : null;
}

public sealed class HttpResponse
{
    public int Status { get; init; } = 200;
    public string? ContentType { get; init; }
    public byte[] Body { get; init; } = Array.Empty<byte>();
    public IReadOnlyDictionary<string, string>? Headers { get; init; }

    public static HttpResponse Empty(int status, IReadOnlyDictionary<string, string>? headers = null) =>
        new() { Status = status, Headers = headers };

    public static HttpResponse Json(int status, string json) =>
        new() { Status = status, ContentType = "application/json", Body = Encoding.UTF8.GetBytes(json) };
}

/// <summary>
/// A small HTTP/1.1 server bound to loopback addresses only (127.0.0.1 and ::1).
/// Built on TcpListener rather than HttpListener: it truly binds loopback only, needs no URL ACL or
/// administrator rights, and behaves the same on Windows, macOS and Linux.
/// </summary>
public sealed class HttpServer : IDisposable
{
    public const int MaxHeaderBytes = 32 * 1024;

    private readonly Func<HttpRequest, CancellationToken, Task<HttpResponse>> _handler;
    private readonly ILog _log;
    private readonly int _maxBodyBytes;
    private readonly TimeSpan _idleTimeout;
    private readonly List<TcpListener> _listeners = new();
    private readonly CancellationTokenSource _stop = new();

    public int Port { get; private set; }
    public bool IsRunning { get; private set; }

    public HttpServer(Func<HttpRequest, CancellationToken, Task<HttpResponse>> handler, ILog log,
                      int maxBodyBytes = 4 * 1024 * 1024, TimeSpan? idleTimeout = null)
    {
        _handler = handler;
        _log = log;
        _maxBodyBytes = maxBodyBytes;
        _idleTimeout = idleTimeout ?? TimeSpan.FromSeconds(30);
    }

    /// <summary>Start listening. Port 0 picks a free port (tests). Throws when IPv4 loopback can't be bound.</summary>
    public void Start(int port)
    {
        var v4 = new TcpListener(IPAddress.Loopback, port);
        v4.Start();
        _listeners.Add(v4);
        Port = ((IPEndPoint)v4.LocalEndpoint).Port;
        try
        {
            // IPv6 loopback too, so clients that resolve "localhost" to ::1 still connect. Optional.
            var v6 = new TcpListener(IPAddress.IPv6Loopback, Port);
            v6.Start();
            _listeners.Add(v6);
        }
        catch (Exception ex) when (ex is SocketException or NotSupportedException)
        {
            _log.Info($"IPv6 loopback not available ({ex.Message}); listening on 127.0.0.1 only");
        }
        IsRunning = true;
        foreach (var listener in _listeners)
            _ = Task.Run(() => AcceptLoop(listener));
    }

    private async Task AcceptLoop(TcpListener listener)
    {
        while (!_stop.IsCancellationRequested)
        {
            TcpClient client;
            try
            {
                client = await listener.AcceptTcpClientAsync(_stop.Token).ConfigureAwait(false);
            }
            catch (OperationCanceledException) { return; }
            catch (ObjectDisposedException) { return; }
            catch (SocketException ex)
            {
                if (_stop.IsCancellationRequested) return;
                _log.Error("accept failed", ex);
                continue;
            }
            _ = Task.Run(() => ServeConnection(client));
        }
    }

    private async Task ServeConnection(TcpClient client)
    {
        using (client)
        {
            var remote = (client.Client.RemoteEndPoint as IPEndPoint)?.Address ?? IPAddress.None;
            if (remote.IsIPv4MappedToIPv6) remote = remote.MapToIPv4();
            if (!IPAddress.IsLoopback(remote))
            {
                // Bound to loopback, so this should never happen; refuse anyway.
                _log.Info($"refused connection from {remote}");
                return;
            }
            try
            {
                var stream = client.GetStream();
                var reader = new RequestReader(stream, _maxBodyBytes);
                while (!_stop.IsCancellationRequested)
                {
                    using var idle = CancellationTokenSource.CreateLinkedTokenSource(_stop.Token);
                    idle.CancelAfter(_idleTimeout);
                    ParsedRequest? parsed;
                    try
                    {
                        parsed = await reader.ReadAsync(stream, idle.Token).ConfigureAwait(false);
                    }
                    catch (HttpProtocolException ex)
                    {
                        await WriteAsync(stream, HttpResponse.Empty(ex.Status), keepAlive: false, _stop.Token).ConfigureAwait(false);
                        return;
                    }
                    if (parsed is null) return;                                  // client closed the connection
                    var request = new HttpRequest
                    {
                        Method = parsed.Method, Path = parsed.Path, Headers = parsed.Headers,
                        Body = parsed.Body, RemoteAddress = remote,
                    };
                    HttpResponse response;
                    try
                    {
                        response = await _handler(request, _stop.Token).ConfigureAwait(false);
                    }
                    catch (Exception ex)
                    {
                        _log.Error("request handler failed", ex);
                        response = HttpResponse.Empty(500);
                    }
                    await WriteAsync(stream, response, parsed.KeepAlive, _stop.Token).ConfigureAwait(false);
                    if (!parsed.KeepAlive) return;
                }
            }
            catch (Exception ex) when (ex is IOException or OperationCanceledException or ObjectDisposedException or SocketException)
            {
                // Connection closed, idle timeout or shutdown: nothing to do.
            }
            catch (Exception ex)
            {
                _log.Error("connection failed", ex);
            }
        }
    }

    internal static async Task WriteAsync(Stream stream, HttpResponse response, bool keepAlive, CancellationToken ct)
    {
        var sb = new StringBuilder();
        sb.Append("HTTP/1.1 ").Append(response.Status).Append(' ').Append(Reason(response.Status)).Append("\r\n");
        if (response.ContentType is not null) sb.Append("Content-Type: ").Append(response.ContentType).Append("\r\n");
        sb.Append("Content-Length: ").Append(response.Body.Length).Append("\r\n");
        sb.Append("Cache-Control: no-store\r\n");
        sb.Append("Connection: ").Append(keepAlive ? "keep-alive" : "close").Append("\r\n");
        if (response.Headers is not null)
            foreach (var (name, value) in response.Headers) sb.Append(name).Append(": ").Append(value).Append("\r\n");
        sb.Append("\r\n");
        var head = Encoding.ASCII.GetBytes(sb.ToString());
        await stream.WriteAsync(head, ct).ConfigureAwait(false);
        if (response.Body.Length > 0) await stream.WriteAsync(response.Body, ct).ConfigureAwait(false);
        await stream.FlushAsync(ct).ConfigureAwait(false);
    }

    private static string Reason(int status) => status switch
    {
        100 => "Continue", 200 => "OK", 202 => "Accepted", 400 => "Bad Request", 403 => "Forbidden",
        404 => "Not Found", 405 => "Method Not Allowed", 408 => "Request Timeout", 411 => "Length Required",
        413 => "Content Too Large", 431 => "Request Header Fields Too Large", 500 => "Internal Server Error",
        501 => "Not Implemented", 505 => "HTTP Version Not Supported", _ => "Status",
    };

    public void Stop()
    {
        if (!IsRunning) return;
        IsRunning = false;
        _stop.Cancel();
        foreach (var listener in _listeners)
        {
            try { listener.Stop(); } catch (SocketException) { }
        }
        _listeners.Clear();
    }

    public void Dispose()
    {
        Stop();
        _stop.Dispose();
    }
}

public sealed class HttpProtocolException : Exception
{
    public int Status { get; }
    public HttpProtocolException(int status, string message) : base(message) { Status = status; }
}

internal sealed record ParsedRequest(string Method, string Path, Dictionary<string, string> Headers, byte[] Body, bool KeepAlive);

/// <summary>Reads HTTP/1.1 requests from a connection: request line, headers, Content-Length or chunked body.</summary>
internal sealed class RequestReader
{
    private readonly int _maxBody;
    private readonly byte[] _buffer = new byte[16 * 1024];
    private int _start, _end;
    private readonly Stream _stream;

    public RequestReader(Stream stream, int maxBody)
    {
        _stream = stream;
        _maxBody = maxBody;
    }

    public async Task<ParsedRequest?> ReadAsync(Stream stream, CancellationToken ct)
    {
        var requestLine = await ReadLineAsync(ct, allowEof: true).ConfigureAwait(false);
        if (requestLine is null) return null;
        while (requestLine.Length == 0)                                       // tolerate stray CRLFs between requests
        {
            requestLine = await ReadLineAsync(ct, allowEof: true).ConfigureAwait(false);
            if (requestLine is null) return null;
        }
        var parts = requestLine.Split(' ');
        if (parts.Length != 3) throw new HttpProtocolException(400, "bad request line");
        var (method, target, version) = (parts[0], parts[1], parts[2]);
        if (version != "HTTP/1.1" && version != "HTTP/1.0") throw new HttpProtocolException(505, "unsupported HTTP version");

        var headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        int headerBytes = requestLine.Length;
        while (true)
        {
            var line = await ReadLineAsync(ct, allowEof: false).ConfigureAwait(false) ?? "";
            if (line.Length == 0) break;
            headerBytes += line.Length + 2;
            if (headerBytes > HttpServer.MaxHeaderBytes) throw new HttpProtocolException(431, "headers too large");
            int colon = line.IndexOf(':');
            if (colon <= 0) throw new HttpProtocolException(400, "bad header line");
            var name = line[..colon].Trim();
            var value = line[(colon + 1)..].Trim();
            headers[name] = headers.TryGetValue(name, out var existing) ? existing + ", " + value : value;
        }

        bool keepAlive = version == "HTTP/1.1"
            ? !HasToken(headers, "Connection", "close")
            : HasToken(headers, "Connection", "keep-alive");

        if (HasToken(headers, "Expect", "100-continue"))
        {
            var cont = Encoding.ASCII.GetBytes("HTTP/1.1 100 Continue\r\n\r\n");
            await stream.WriteAsync(cont, ct).ConfigureAwait(false);
        }

        byte[] body;
        if (headers.TryGetValue("Transfer-Encoding", out var te))
        {
            if (!te.Trim().Equals("chunked", StringComparison.OrdinalIgnoreCase))
                throw new HttpProtocolException(501, "unsupported transfer encoding");
            body = await ReadChunkedAsync(ct).ConfigureAwait(false);
        }
        else if (headers.TryGetValue("Content-Length", out var cl))
        {
            if (!long.TryParse(cl, out var length) || length < 0) throw new HttpProtocolException(400, "bad Content-Length");
            if (length > _maxBody) throw new HttpProtocolException(413, "body too large");
            body = await ReadExactAsync((int)length, ct).ConfigureAwait(false);
        }
        else
        {
            body = Array.Empty<byte>();
        }

        var path = target;
        int q = path.IndexOf('?');
        if (q >= 0) path = path[..q];
        return new ParsedRequest(method, path, headers, body, keepAlive);
    }

    private static bool HasToken(Dictionary<string, string> headers, string name, string token)
    {
        if (!headers.TryGetValue(name, out var value)) return false;
        foreach (var part in value.Split(','))
            if (part.Trim().Equals(token, StringComparison.OrdinalIgnoreCase)) return true;
        return false;
    }

    private async Task<byte[]> ReadChunkedAsync(CancellationToken ct)
    {
        using var body = new MemoryStream();
        while (true)
        {
            var sizeLine = await ReadLineAsync(ct, allowEof: false).ConfigureAwait(false) ?? "";
            int semi = sizeLine.IndexOf(';');
            if (semi >= 0) sizeLine = sizeLine[..semi];
            if (!int.TryParse(sizeLine.Trim(), System.Globalization.NumberStyles.HexNumber, null, out var size) || size < 0)
                throw new HttpProtocolException(400, "bad chunk size");
            if (size == 0)
            {
                // Trailers until the empty line.
                while ((await ReadLineAsync(ct, allowEof: false).ConfigureAwait(false) ?? "").Length > 0) { }
                return body.ToArray();
            }
            if (body.Length + size > _maxBody) throw new HttpProtocolException(413, "body too large");
            var chunk = await ReadExactAsync(size, ct).ConfigureAwait(false);
            body.Write(chunk, 0, chunk.Length);
            var end = await ReadLineAsync(ct, allowEof: false).ConfigureAwait(false);
            if (end is null || end.Length != 0) throw new HttpProtocolException(400, "bad chunk terminator");
        }
    }

    private async Task<bool> FillAsync(CancellationToken ct)
    {
        if (_start > 0 && _start == _end) { _start = _end = 0; }
        if (_end == _buffer.Length)
        {
            if (_start == 0) return true;                                      // full; caller handles limits
            Buffer.BlockCopy(_buffer, _start, _buffer, 0, _end - _start);
            _end -= _start;
            _start = 0;
        }
        int read = await _stream.ReadAsync(_buffer.AsMemory(_end), ct).ConfigureAwait(false);
        if (read == 0) return false;
        _end += read;
        return true;
    }

    /// <summary>Reads one CRLF- (or LF-) terminated line as ASCII. Null at a clean end of stream.</summary>
    private async Task<string?> ReadLineAsync(CancellationToken ct, bool allowEof)
    {
        var line = new StringBuilder();
        while (true)
        {
            for (int i = _start; i < _end; i++)
            {
                if (_buffer[i] == (byte)'\n')
                {
                    int len = i - _start;
                    if (len > 0 && _buffer[i - 1] == (byte)'\r') len--;
                    line.Append(Encoding.ASCII.GetString(_buffer, _start, len));
                    _start = i + 1;
                    return line.ToString();
                }
            }
            if (_end - _start >= HttpServer.MaxHeaderBytes) throw new HttpProtocolException(431, "line too long");
            if (_end == _buffer.Length && _start == 0)
            {
                line.Append(Encoding.ASCII.GetString(_buffer, 0, _end));
                _start = _end = 0;
                if (line.Length > HttpServer.MaxHeaderBytes) throw new HttpProtocolException(431, "line too long");
            }
            if (!await FillAsync(ct).ConfigureAwait(false))
            {
                if (allowEof && line.Length == 0 && _start == _end) return null;
                throw new IOException("connection closed mid-request");
            }
        }
    }

    private async Task<byte[]> ReadExactAsync(int count, CancellationToken ct)
    {
        var result = new byte[count];
        int copied = 0;
        while (copied < count)
        {
            if (_start == _end && !await FillAsync(ct).ConfigureAwait(false))
                throw new IOException("connection closed mid-body");
            int n = Math.Min(count - copied, _end - _start);
            Buffer.BlockCopy(_buffer, _start, result, copied, n);
            _start += n;
            copied += n;
        }
        return result;
    }
}
