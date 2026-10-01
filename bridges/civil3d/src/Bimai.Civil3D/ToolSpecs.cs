using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Bimai.Mcp;

namespace Bimai.Civil3D;

/// <summary>
/// Names, descriptions and input schemas of the Civil 3D tools. No Autodesk dependencies, so the same
/// definitions are used by the add-in, the development server and the tests.
/// </summary>
public static class ToolSpecs
{
    public const int DefaultLimit = 200;
    public const int MaxLimit = 2000;
    public const int MaxPoints = 1000;

    private const string Units = " Distances, stations and elevations are in drawing units (see get_drawing).";

    public sealed record Spec(string Name, string Title, string Description, JsonObject Schema);

    public static readonly IReadOnlyList<Spec> All = new List<Spec>
    {
        new("get_drawing", "Drawing info",
            "The drawing open in Civil 3D: file name and path, drawing units, coordinate system, angular units, and how " +
            "many alignments, surfaces, corridors, pipe networks, COGO points and layers it has. Call this first.",
            Obj()),
        new("list_layers", "List layers",
            "Layers in the drawing with on/off, frozen, locked, plottable, color and description.",
            Obj(("name_contains", Str("Only layers whose name contains this text (case-insensitive)."), false), Limit())),
        new("count_objects", "Count objects",
            "Counts objects in model space by object type (for example LINE, AECC_ALIGNMENT, AECC_PIPE), optionally " +
            "only on one layer or also per layer.",
            Obj(("layer", Str("Only count objects on this layer."), false),
                ("by_layer", Bool("Also count per layer (slower in very large drawings)."), false), Limit())),
        new("list_alignments", "List alignments",
            "Alignments with type, site, style, length, start and end station and number of profiles." + Units,
            Obj(Limit())),
        new("get_alignment", "Alignment details",
            "One alignment with its stations, length, design speeds, station equations and all its profiles " +
            "(type, station range, lowest and highest elevation)." + Units,
            Obj(("name", Str("Alignment name."), true))),
        new("alignment_point", "Station to coordinates",
            "Converts stations (and optional offsets, right positive) on an alignment to easting and northing. " +
            "Stations outside the alignment are reported per point." + Units,
            Obj(("alignment", Str("Alignment name."), true),
                ("points", Arr(Obj(("station", Num("Station."), true), ("offset", Num("Offset from the alignment; default 0."), false)),
                               $"Up to {MaxPoints} stations."), true))),
        new("alignment_station", "Coordinates to station",
            "Converts easting/northing points to station and offset on an alignment. Points that can't be " +
            "projected onto the alignment are reported per point." + Units,
            Obj(("alignment", Str("Alignment name."), true),
                ("points", Arr(Obj(("x", Num("Easting."), true), ("y", Num("Northing."), true)), $"Up to {MaxPoints} points."), true))),
        new("profile_elevations", "Profile elevations",
            "Elevations of a profile at given stations, or at a regular interval between two stations. Stations " +
            "outside the profile are reported per station." + Units,
            Obj(("alignment", Str("Alignment name."), true),
                ("profile", Str("Profile name."), true),
                ("stations", Arr(Num("Station."), $"Stations to sample (up to {MaxPoints}). Or use start, end and interval."), false),
                ("start", Num("First station (with end and interval)."), false),
                ("end", Num("Last station (with start and interval)."), false),
                ("interval", Num("Distance between samples (with start and end)."), false))),
        new("list_surfaces", "List surfaces",
            "Surfaces with type (TIN, grid, volume), style, lowest, highest and mean elevation, number of points " +
            "and triangles, and whether the surface is out of date." + Units,
            Obj(Limit())),
        new("surface_elevations", "Surface elevations",
            "Elevation of a surface at easting/northing points. Points outside the surface are reported per point." + Units,
            Obj(("surface", Str("Surface name."), true),
                ("points", Arr(Obj(("x", Num("Easting."), true), ("y", Num("Northing."), true)), $"Up to {MaxPoints} points."), true))),
        new("list_corridors", "List corridors",
            "Corridors with whether they are out of date, and for each baseline its alignment, profile and regions " +
            "(station range and assembly)." + Units,
            Obj(Limit())),
        new("list_pipe_networks", "List pipe networks",
            "Pipe networks with their number of pipes and structures.",
            Obj(Limit())),
        new("get_pipe_network", "Pipe network details",
            "Pipes (size, material, inner diameter or width, 2D length, slope as an absolute value, start and end " +
            "structure, minimum and maximum cover, start and end point) and structures (size, location, rim and sump " +
            "elevation, sump depth) of one pipe network. Invert levels are not calculated." + Units,
            Obj(("name", Str("Pipe network name."), true),
                ("limit", Int($"Maximum number of pipes and of structures to return (default 500, max {MaxLimit})."), false))),
    };

    public static IEnumerable<string> Names => All.Select(s => s.Name);

    public static ToolDefinition Define(string name, Func<Args, CancellationToken, Task<JsonObject>> handler)
    {
        var spec = All.FirstOrDefault(s => s.Name == name) ?? throw new ArgumentException($"no spec for tool {name}");
        return new ToolDefinition { Name = spec.Name, Title = spec.Title, Description = spec.Description, InputSchema = spec.Schema, Handler = handler };
    }

    /// <summary>Either an explicit list of stations, or start + end + interval (at most MaxPoints samples).</summary>
    public static List<double> ParseStations(Args a)
    {
        var listed = a.Numbers("stations", MaxPoints);
        var start = a.OptionalNumber("start");
        var end = a.OptionalNumber("end");
        var interval = a.OptionalNumber("interval");
        if (listed.Count > 0)
        {
            if (start is not null || end is not null || interval is not null)
                throw new ToolException("Give either 'stations' or 'start', 'end' and 'interval', not both.");
            return listed.ToList();
        }
        if (start is null || end is null || interval is null)
            throw new ToolException("Give 'stations', or 'start', 'end' and 'interval'.");
        if (interval <= 0) throw new ToolException("'interval' must be greater than 0.");
        if (end < start) throw new ToolException("'end' must not be smaller than 'start'.");
        var count = (int)Math.Floor((end.Value - start.Value) / interval.Value + 1e-9) + 1;
        if (count > MaxPoints)
            throw new ToolException($"That would be {count} stations; at most {MaxPoints}. Use a larger interval.");
        var result = Enumerable.Range(0, count).Select(i => start.Value + i * interval.Value).ToList();
        if (end.Value - result[^1] > 1e-9 && result.Count < MaxPoints) result.Add(end.Value);
        return result;
    }

    // ------------------------------------------------------------------ schema helpers

    private static (string, JsonObject, bool) Limit() =>
        ("limit", Int($"Maximum number of items to return (default {DefaultLimit}, max {MaxLimit})."), false);

    private static JsonObject Str(string description) => new() { ["type"] = "string", ["description"] = description };
    private static JsonObject Num(string description) => new() { ["type"] = "number", ["description"] = description };
    private static JsonObject Int(string description) => new() { ["type"] = "integer", ["description"] = description, ["minimum"] = 1 };
    private static JsonObject Bool(string description) => new() { ["type"] = "boolean", ["description"] = description };
    private static JsonObject Arr(JsonObject items, string description) =>
        new() { ["type"] = "array", ["items"] = items, ["description"] = description };

    private static JsonObject Obj(params (string name, JsonObject schema, bool required)[] props)
    {
        var properties = new JsonObject();
        foreach (var (name, schema, _) in props) properties[name] = schema;
        var result = new JsonObject { ["type"] = "object", ["properties"] = properties, ["additionalProperties"] = false };
        var required = props.Where(p => p.required).Select(p => (JsonNode)p.name).ToArray();
        if (required.Length > 0) result["required"] = new JsonArray(required);
        return result;
    }
}
