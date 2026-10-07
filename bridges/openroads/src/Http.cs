using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;

namespace Bimai.OpenRoads
{
    public sealed class HttpRequest
    {
        public string Method;
        public string Path;
        public Dictionary<string, string> Headers;   // case-insensitive names
        public byte[] Body;
        public IPAddress RemoteAddress;

        public string Header(string name)
        {
            string v;
            return Headers.TryGetValue(name, out v) ? v : null;
        }
    }

    public sealed class HttpResponse
    {
        public int Status = 200;
        public string ContentType;
        public byte[] Body = new byte[0];
        public Dictionary<string, string> Headers;

        public static HttpResponse Empty(int status)
        {
            return new HttpResponse { Status = status };
        }

        public static HttpResponse Json(int status, string json)
        {
            return new HttpResponse { Status = status, ContentType = "application/json", Body = Encoding.UTF8.GetBytes(json) };
        }
    }

    public sealed class HttpProtocolException : Exception
    {
        public readonly int Status;
        public HttpProtocolException(int status, string message) : base(message) { Status = status; }
    }

    /// <summary>
    /// A small HTTP/1.1 server bound to loopback only (127.0.0.1 and ::1). TcpListener instead of
    /// HttpListener: it binds loopback only and needs no URL reservation or administrator rights.
    /// One background thread per connection; synchronous I/O with timeouts.
    /// </summary>
    public sealed class HttpServer
    {
        public const int MaxHeaderBytes = 32 * 1024;
        public const int MaxBodyBytes = 4 * 1024 * 1024;

        private readonly Func<HttpRequest, HttpResponse> _handler;
        private readonly Log _log;
        private readonly List<TcpListener> _listeners = new List<TcpListener>();
        private volatile bool _running;

        public int Port { get; private set; }
        public bool IsRunning { get { return _running; } }

        public HttpServer(Func<HttpRequest, HttpResponse> handler, Log log)
        {
            _handler = handler;
            _log = log;
        }

        /// <summary>Port 0 picks a free port (tests). Throws when 127.0.0.1 can't be bound.</summary>
        public void Start(int port)
        {
            var v4 = new TcpListener(IPAddress.Loopback, port);
            v4.Start();
            _listeners.Add(v4);
            Port = ((IPEndPoint)v4.LocalEndpoint).Port;
            try
            {
                var v6 = new TcpListener(IPAddress.IPv6Loopback, Port);
                v6.Start();
                _listeners.Add(v6);
            }
            catch (Exception ex)
            {
                _log.Info("IPv6 loopback not available (" + ex.Message + "); listening on 127.0.0.1 only");
            }
            _running = true;
            foreach (var listener in _listeners)
            {
                var l = listener;
                var thread = new Thread(() => AcceptLoop(l)) { IsBackground = true, Name = "bimai-accept" };
                thread.Start();
            }
        }

        public void Stop()
        {
            _running = false;
            foreach (var listener in _listeners)
            {
                try { listener.Stop(); } catch (Exception) { }
            }
            _listeners.Clear();
        }

        private void AcceptLoop(TcpListener listener)
        {
            while (_running)
            {
                TcpClient client;
                try { client = listener.AcceptTcpClient(); }
                catch (Exception)
                {
                    if (!_running) return;
                    Thread.Sleep(100);
                    continue;
                }
                var c = client;
                var thread = new Thread(() => Serve(c)) { IsBackground = true, Name = "bimai-connection" };
                thread.Start();
            }
        }

        private void Serve(TcpClient client)
        {
            using (client)
            {
                var endpoint = client.Client.RemoteEndPoint as IPEndPoint;
                IPAddress remote = endpoint != null ? endpoint.Address : IPAddress.None;
                if (remote.IsIPv4MappedToIPv6) remote = remote.MapToIPv4();
                if (!IPAddress.IsLoopback(remote))
                {
                    _log.Info("refused connection from " + remote);
                    return;
                }
                try
                {
                    var stream = client.GetStream();
                    stream.ReadTimeout = 30000;
                    stream.WriteTimeout = 30000;
                    var reader = new RequestReader(stream);
                    while (_running)
                    {
                        HttpRequest request;
                        bool keepAlive;
                        try
                        {
                            request = reader.Read(out keepAlive);
                        }
                        catch (HttpProtocolException ex)
                        {
                            Write(stream, HttpResponse.Empty(ex.Status), false);
                            return;
                        }
                        if (request == null) return;                         // the client closed the connection
                        request.RemoteAddress = remote;
                        HttpResponse response;
                        try { response = _handler(request); }
                        catch (Exception ex)
                        {
                            _log.Error("request handler failed", ex);
                            response = HttpResponse.Empty(500);
                        }
                        Write(stream, response, keepAlive);
                        if (!keepAlive) return;
                    }
                }
                catch (IOException) { }                                       // closed, timed out or shut down
                catch (ObjectDisposedException) { }
                catch (SocketException) { }
                catch (Exception ex) { _log.Error("connection failed", ex); }
            }
        }

        private static void Write(Stream stream, HttpResponse response, bool keepAlive)
        {
            var sb = new StringBuilder();
            sb.Append("HTTP/1.1 ").Append(response.Status).Append(' ').Append(Reason(response.Status)).Append("\r\n");
            if (response.ContentType != null) sb.Append("Content-Type: ").Append(response.ContentType).Append("\r\n");
            sb.Append("Content-Length: ").Append(response.Body.Length).Append("\r\n");
            sb.Append("Cache-Control: no-store\r\n");
            sb.Append("Connection: ").Append(keepAlive ? "keep-alive" : "close").Append("\r\n");
            if (response.Headers != null)
                foreach (var kv in response.Headers) sb.Append(kv.Key).Append(": ").Append(kv.Value).Append("\r\n");
            sb.Append("\r\n");
            var head = Encoding.ASCII.GetBytes(sb.ToString());
            stream.Write(head, 0, head.Length);
            if (response.Body.Length > 0) stream.Write(response.Body, 0, response.Body.Length);
            stream.Flush();
        }

        private static string Reason(int status)
        {
            switch (status)
            {
                case 100: return "Continue";
                case 200: return "OK";
                case 202: return "Accepted";
                case 400: return "Bad Request";
                case 403: return "Forbidden";
                case 404: return "Not Found";
                case 405: return "Method Not Allowed";
                case 411: return "Length Required";
                case 413: return "Content Too Large";
                case 431: return "Request Header Fields Too Large";
                case 500: return "Internal Server Error";
                case 501: return "Not Implemented";
                case 505: return "HTTP Version Not Supported";
                default: return "Status";
            }
        }
    }

    /// <summary>Reads HTTP/1.1 requests: request line, headers, Content-Length or chunked body.</summary>
    internal sealed class RequestReader
    {
        private readonly Stream _stream;
        private readonly byte[] _buffer = new byte[16 * 1024];
        private int _start, _end;

        public RequestReader(Stream stream) { _stream = stream; }

        public HttpRequest Read(out bool keepAlive)
        {
            keepAlive = false;
            string requestLine = ReadLine(true);
            while (requestLine != null && requestLine.Length == 0) requestLine = ReadLine(true);   // stray CRLFs
            if (requestLine == null) return null;
            var parts = requestLine.Split(' ');
            if (parts.Length != 3) throw new HttpProtocolException(400, "bad request line");
            string method = parts[0], target = parts[1], version = parts[2];
            if (version != "HTTP/1.1" && version != "HTTP/1.0") throw new HttpProtocolException(505, "unsupported HTTP version");

            var headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            int headerBytes = requestLine.Length;
            while (true)
            {
                string line = ReadLine(false) ?? "";
                if (line.Length == 0) break;
                headerBytes += line.Length + 2;
                if (headerBytes > HttpServer.MaxHeaderBytes) throw new HttpProtocolException(431, "headers too large");
                int colon = line.IndexOf(':');
                if (colon <= 0) throw new HttpProtocolException(400, "bad header line");
                string name = line.Substring(0, colon).Trim();
                string value = line.Substring(colon + 1).Trim();
                string existing;
                headers[name] = headers.TryGetValue(name, out existing) ? existing + ", " + value : value;
            }

            keepAlive = version == "HTTP/1.1" ? !HasToken(headers, "Connection", "close") : HasToken(headers, "Connection", "keep-alive");
            if (HasToken(headers, "Expect", "100-continue"))
            {
                var cont = Encoding.ASCII.GetBytes("HTTP/1.1 100 Continue\r\n\r\n");
                _stream.Write(cont, 0, cont.Length);
            }

            byte[] body;
            string te, cl;
            if (headers.TryGetValue("Transfer-Encoding", out te))
            {
                if (!te.Trim().Equals("chunked", StringComparison.OrdinalIgnoreCase))
                    throw new HttpProtocolException(501, "unsupported transfer encoding");
                body = ReadChunked();
            }
            else if (headers.TryGetValue("Content-Length", out cl))
            {
                long length;
                if (!long.TryParse(cl, NumberStyles.Integer, CultureInfo.InvariantCulture, out length) || length < 0)
                    throw new HttpProtocolException(400, "bad Content-Length");
                if (length > HttpServer.MaxBodyBytes) throw new HttpProtocolException(413, "body too large");
                body = ReadExact((int)length);
            }
            else
            {
                body = new byte[0];
            }

            int q = target.IndexOf('?');
            return new HttpRequest { Method = method, Path = q >= 0 ? target.Substring(0, q) : target, Headers = headers, Body = body };
        }

        private static bool HasToken(Dictionary<string, string> headers, string name, string token)
        {
            string value;
            if (!headers.TryGetValue(name, out value)) return false;
            foreach (var part in value.Split(','))
                if (part.Trim().Equals(token, StringComparison.OrdinalIgnoreCase)) return true;
            return false;
        }

        private byte[] ReadChunked()
        {
            using (var body = new MemoryStream())
            {
                while (true)
                {
                    string sizeLine = ReadLine(false) ?? "";
                    int semi = sizeLine.IndexOf(';');
                    if (semi >= 0) sizeLine = sizeLine.Substring(0, semi);
                    int size;
                    if (!int.TryParse(sizeLine.Trim(), NumberStyles.HexNumber, CultureInfo.InvariantCulture, out size) || size < 0)
                        throw new HttpProtocolException(400, "bad chunk size");
                    if (size == 0)
                    {
                        while ((ReadLine(false) ?? "").Length > 0) { }              // trailers
                        return body.ToArray();
                    }
                    if (body.Length + size > HttpServer.MaxBodyBytes) throw new HttpProtocolException(413, "body too large");
                    var chunk = ReadExact(size);
                    body.Write(chunk, 0, chunk.Length);
                    string end = ReadLine(false);
                    if (end == null || end.Length != 0) throw new HttpProtocolException(400, "bad chunk terminator");
                }
            }
        }

        private bool Fill()
        {
            if (_start > 0 && _start == _end) { _start = _end = 0; }
            if (_end == _buffer.Length)
            {
                if (_start == 0) return true;
                Buffer.BlockCopy(_buffer, _start, _buffer, 0, _end - _start);
                _end -= _start;
                _start = 0;
            }
            int read = _stream.Read(_buffer, _end, _buffer.Length - _end);
            if (read == 0) return false;
            _end += read;
            return true;
        }

        private string ReadLine(bool allowEof)
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
                if (!Fill())
                {
                    if (allowEof && line.Length == 0 && _start == _end) return null;
                    throw new IOException("connection closed mid-request");
                }
            }
        }

        private byte[] ReadExact(int count)
        {
            var result = new byte[count];
            int copied = 0;
            while (copied < count)
            {
                if (_start == _end && !Fill()) throw new IOException("connection closed mid-body");
                int n = Math.Min(count - copied, _end - _start);
                Buffer.BlockCopy(_buffer, _start, result, copied, n);
                _start += n;
                copied += n;
            }
            return result;
        }
    }
}
