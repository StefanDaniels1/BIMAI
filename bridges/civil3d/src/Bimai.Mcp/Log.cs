using System;
using System.Globalization;
using System.IO;
using System.Text;

namespace Bimai.Mcp;

public interface ILog
{
    void Info(string message);
    void Error(string message, Exception? exception = null);
}

public sealed class NullLog : ILog
{
    public static readonly NullLog Instance = new();
    public void Info(string message) { }
    public void Error(string message, Exception? exception = null) { }
}

/// <summary>
/// A small log file for troubleshooting. Never contains drawing contents: callers log events, tool names
/// and durations only. When the file passes maxBytes it is moved to "&lt;name&gt;.1" and a new one starts.
/// </summary>
public sealed class FileLog : ILog
{
    private readonly string _path;
    private readonly long _maxBytes;
    private readonly object _gate = new();

    public string Path => _path;
    public string? LastError { get; private set; }

    public FileLog(string path, long maxBytes = 1024 * 1024)
    {
        _path = path;
        _maxBytes = maxBytes;
    }

    public static string DefaultPath() => System.IO.Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "bimai", "civil3d-bridge.log");

    public void Info(string message) => Write("INFO", message);

    public void Error(string message, Exception? exception = null)
    {
        var text = exception is null ? message : $"{message}: {exception.GetType().Name}: {exception.Message}";
        LastError = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} {text}";
        Write("ERROR", exception is null ? message : $"{message}: {exception}");
    }

    private void Write(string level, string message)
    {
        try
        {
            lock (_gate)
            {
                Directory.CreateDirectory(System.IO.Path.GetDirectoryName(_path)!);
                var info = new FileInfo(_path);
                if (info.Exists && info.Length > _maxBytes)
                {
                    var old = _path + ".1";
                    if (File.Exists(old)) File.Delete(old);
                    File.Move(_path, old);
                }
                var line = string.Create(CultureInfo.InvariantCulture, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} {level} {message}{Environment.NewLine}");
                File.AppendAllText(_path, line, Encoding.UTF8);
            }
        }
        catch (Exception)
        {
            // Logging must never break the bridge or Civil 3D.
        }
    }
}
