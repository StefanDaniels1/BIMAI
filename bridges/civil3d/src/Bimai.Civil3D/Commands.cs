using Autodesk.AutoCAD.Runtime;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;

namespace Bimai.Civil3D;

public sealed class Commands
{
    /// <summary>BIMAIBRIDGE: is the bridge running, where, which version, and what went wrong last.</summary>
    [CommandMethod("BIMAI", "BIMAIBRIDGE", CommandFlags.Modal)]
    public void Status()
    {
        var editor = AcApp.DocumentManager.MdiActiveDocument?.Editor;
        if (editor is null) return;
        var plugin = Plugin.Current;
        if (plugin is null)
        {
            editor.WriteMessage("\nbimai Civil 3D bridge: not initialised.");
            return;
        }
        var server = plugin.Server;
        if (server is { IsRunning: true })
        {
            editor.WriteMessage($"\nbimai Civil 3D bridge {Plugin.Version}: running at {server.Url}" +
                                $"\n  Tool calls since start: {server.ToolCalls}" +
                                "\n  Connect it from your project: bimai connect civil3d");
        }
        else
        {
            editor.WriteMessage($"\nbimai Civil 3D bridge {Plugin.Version}: NOT running." +
                                (plugin.StartError is null ? "" : $"\n  Reason: {plugin.StartError}"));
        }
        if (plugin.Log.LastError is not null) editor.WriteMessage($"\n  Last error: {plugin.Log.LastError}");
        editor.WriteMessage($"\n  Log: {plugin.Log.Path}\n");
    }
}
