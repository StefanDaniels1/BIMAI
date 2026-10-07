using System;
using System.Globalization;
using System.Net.Sockets;

namespace Bimai.OpenRoads
{
    /// <summary>Starts and stops the bridge's MCP server. Nothing in here may throw into OpenRoads Designer.</summary>
    public sealed class Bridge
    {
        public const string Version = "0.1.0";
        public const int DefaultPort = 27185;

        public static Bridge Current { get; private set; }

        public Log Log { get; private set; }
        public McpServer Server { get; private set; }
        public int Port { get; private set; }
        public string StartError { get; private set; }

        public static Bridge Start(IDispatcher dispatcher, ToolRegistry tools, Log log, int port)
        {
            var bridge = new Bridge { Log = log, Port = port };
            Current = bridge;
            try
            {
                log.Info("bimai OpenRoads bridge " + Version + " starting (.NET " + Environment.Version + ")");
                bridge.Server = new McpServer(new McpServerInfo
                {
                    Name = "bimai-openroads",
                    Title = "bimai OpenRoads bridge",
                    Version = Version,
                    Instructions = "Read-only access to the drawing open in OpenRoads Designer on this computer: alignments, " +
                                   "profiles, corridors and terrains. Distances and coordinates are in metres as OpenRoads' " +
                                   "civil model stores them; stations are formatted as OpenRoads shows them. Start with get_drawing_info.",
                }, tools, log);
                bridge.Server.Start(port);
                AppDomain.CurrentDomain.ProcessExit += (s, e) => bridge.Stop();
            }
            catch (Exception ex)
            {
                var se = ex as SocketException;
                bridge.StartError = se != null && se.SocketErrorCode == SocketError.AddressAlreadyInUse
                    ? "port " + port + " is already in use (is another OpenRoads Designer or another program using it?)"
                    : ex.GetType().Name + ": " + ex.Message;
                log.Error("bridge did not start: " + bridge.StartError, ex);
            }
            return bridge;
        }

        public static int ReadPort()
        {
            int port;
            string value = Environment.GetEnvironmentVariable("BIMAI_OPENROADS_PORT");
            return int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out port) && port > 0 && port < 65536
                ? port
                : DefaultPort;
        }

        public void Stop()
        {
            try
            {
                if (Server != null && Server.IsRunning)
                {
                    Server.Stop();
                    Log.Info("bridge stopped");
                }
            }
            catch (Exception ex)
            {
                Log.Error("shutdown failed", ex);
            }
        }
    }
}
