using System;
using System.Globalization;
using System.Reflection;
using Autodesk.AutoCAD.Runtime;
using Bimai.Mcp;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;

[assembly: ExtensionApplication(typeof(Bimai.Civil3D.Plugin))]
[assembly: CommandClass(typeof(Bimai.Civil3D.Commands))]

namespace Bimai.Civil3D;

/// <summary>
/// Loaded by Civil 3D at startup (from the bimai-civil3d.bundle plug-in). Starts the local MCP server.
/// Nothing in here may throw: an exception during Initialize would surface as a load error in Civil 3D.
/// </summary>
public sealed class Plugin : IExtensionApplication
{
    public const int DefaultPort = 27184;

    internal static Plugin? Current { get; private set; }

    internal FileLog Log { get; } = new(FileLog.DefaultPath());
    internal McpServer? Server { get; private set; }
    internal int Port { get; private set; } = DefaultPort;
    internal string? StartError { get; private set; }
    internal static string Version =>
        typeof(Plugin).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion?.Split('+')[0]
        ?? typeof(Plugin).Assembly.GetName().Version?.ToString() ?? "?";

    private AcadDispatcher? _dispatcher;

    public void Initialize()
    {
        Current = this;
        try
        {
            Log.Info($"bimai Civil 3D bridge {Version} loading in {AcApp.Version} (.NET {Environment.Version})");
            Port = ReadPort();
            // Created here, on Civil 3D's main thread: work posted to it runs on that thread.
            _dispatcher = new AcadDispatcher(TimeSpan.FromSeconds(30));
            var tools = Civil3DTools.Create(_dispatcher);
            Server = new McpServer(new McpServerInfo
            {
                Name = "bimai-civil3d",
                Title = "bimai Civil 3D bridge",
                Version = Version,
                Instructions = "Read-only access to the drawing open in Civil 3D on this computer: drawing info, layers, " +
                               "alignments, profiles, surfaces, corridors and pipe networks. Values are in drawing units " +
                               "(see get_drawing). Start with get_drawing.",
            }, tools, Log);
            Server.Start(Port);
            AcApp.QuitWillStart += OnQuitWillStart;
        }
        catch (System.Exception ex)
        {
            StartError = ex is System.Net.Sockets.SocketException se && se.SocketErrorCode == System.Net.Sockets.SocketError.AddressAlreadyInUse
                ? $"port {Port} is already in use (is another Civil 3D or another program using it?)"
                : $"{ex.GetType().Name}: {ex.Message}";
            Log.Error("bridge did not start: " + StartError, ex);
        }
    }

    private static int ReadPort()
    {
        var value = Environment.GetEnvironmentVariable("BIMAI_CIVIL3D_PORT");
        return int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out var port) && port is > 0 and < 65536
            ? port
            : DefaultPort;
    }

    private void OnQuitWillStart(object? sender, EventArgs e) => Shutdown();

    public void Terminate() => Shutdown();

    private void Shutdown()
    {
        try
        {
            if (Server is { IsRunning: true })
            {
                Server.Stop();
                Log.Info("bridge stopped");
            }
            _dispatcher?.Dispose();
        }
        catch (System.Exception ex)
        {
            Log.Error("shutdown failed", ex);
        }
    }
}
