using System;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Bimai.Civil3D;
using Bimai.Mcp;

// Sample data in the shape the real tools return. Usage: Bimai.Mcp.DevServer [port]
var port = args.Length > 0 ? int.Parse(args[0]) : 27199;
var log = new ConsoleLog();

JsonObject Drawing() => new()
{
    ["name"] = "KNO-ROAD-ZONE-A.dwg", ["file"] = @"C:\Projects\Knooppunt\KNO-ROAD-ZONE-A.dwg", ["read_only"] = false,
    ["civil3d_version"] = "R26.0s (DEV SAMPLE)",
    ["units"] = new JsonObject { ["drawing_units"] = "Meters", ["insertion_units"] = "Meters", ["angular_units"] = "Degree", ["drawing_scale"] = 1000 },
    ["coordinate_system"] = "RD-New",
    ["counts"] = new JsonObject { ["alignments"] = 2, ["surfaces"] = 1, ["corridors"] = 1, ["pipe_networks"] = 1, ["cogo_points"] = 412, ["layers"] = 87 },
};

Task<JsonObject> Done(JsonObject o) => Task.FromResult(o);
var tools = new ToolRegistry();
foreach (var name in ToolSpecs.Names)
{
    tools.Add(ToolSpecs.Define(name, (a, _) => name switch
    {
        "get_drawing" => Done(Drawing()),
        "list_alignments" => Done(new JsonObject
        {
            ["alignments"] = new JsonArray(
                new JsonObject { ["name"] = "A2-MAIN", ["type"] = "Centerline", ["length"] = 1840.25, ["start_station"] = 0, ["end_station"] = 1840.25, ["profiles"] = 2 },
                new JsonObject { ["name"] = "RAMP-NE", ["type"] = "Centerline", ["length"] = 412.7, ["start_station"] = 0, ["end_station"] = 412.7, ["profiles"] = 1 }),
            ["count"] = 2, ["truncated"] = false,
        }),
        "profile_elevations" => Done(new JsonObject
        {
            ["alignment"] = a.RequiredString("alignment"), ["profile"] = a.RequiredString("profile"),
            ["elevations"] = new JsonArray(ToolSpecs.ParseStations(a).Select(s => (JsonNode)new JsonObject { ["station"] = s, ["elevation"] = Math.Round(2.1 + s * 0.004, 3) }).ToArray()),
        }),
        _ => Done(new JsonObject { ["sample"] = true, ["tool"] = name, ["note"] = "development server: no Civil 3D attached" }),
    }));
}

using var server = new McpServer(new McpServerInfo
{
    Name = "bimai-civil3d", Title = "bimai Civil 3D bridge (dev sample)", Version = "0.1.0-dev",
    Instructions = "Development server with sample data. Start with get_drawing.",
}, tools, log);
server.Start(port);
Console.WriteLine($"dev server on {server.Url} (Ctrl+C to stop)");
var stop = new ManualResetEventSlim();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; stop.Set(); };
stop.Wait();

sealed class ConsoleLog : ILog
{
    public void Info(string message) => Console.WriteLine($"{DateTime.Now:HH:mm:ss.fff} {message}");
    public void Error(string message, Exception? exception = null) => Console.WriteLine($"{DateTime.Now:HH:mm:ss.fff} ERROR {message} {exception?.Message}");
}
