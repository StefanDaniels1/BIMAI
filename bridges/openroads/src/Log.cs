using System;
using System.Globalization;
using System.IO;
using System.Text;

namespace Bimai.OpenRoads
{
    /// <summary>A small rotating log in %LOCALAPPDATA%\bimai\openroads-bridge.log. Never throws.</summary>
    public sealed class Log
    {
        private readonly string _path;
        private readonly object _gate = new object();

        public Log(string path) { _path = path; }

        public string Path { get { return _path; } }
        public string LastError { get; private set; }

        public static string DefaultPath()
        {
            return System.IO.Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "bimai", "openroads-bridge.log");
        }

        public void Info(string message) { Write("INFO", message); }

        public void Error(string message, Exception exception)
        {
            string text = exception == null ? message : message + ": " + exception.GetType().Name + ": " + exception.Message;
            LastError = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture) + " " + text;
            Write("ERROR", exception == null ? message : message + ": " + exception);
        }

        private void Write(string level, string message)
        {
            try
            {
                lock (_gate)
                {
                    Directory.CreateDirectory(System.IO.Path.GetDirectoryName(_path));
                    var info = new FileInfo(_path);
                    if (info.Exists && info.Length > 1024 * 1024)
                    {
                        string old = _path + ".1";
                        if (File.Exists(old)) File.Delete(old);
                        File.Move(_path, old);
                    }
                    File.AppendAllText(_path, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff", CultureInfo.InvariantCulture)
                        + " " + level + " " + message + Environment.NewLine, Encoding.UTF8);
                }
            }
            catch (Exception)
            {
                // Logging must never break the bridge or OpenRoads Designer.
            }
        }
    }
}
