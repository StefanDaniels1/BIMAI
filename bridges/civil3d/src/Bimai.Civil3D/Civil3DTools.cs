using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Bimai.Mcp;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using C = Autodesk.Civil.DatabaseServices;

namespace Bimai.Civil3D;

/// <summary>
/// The Civil 3D tools. Arguments are parsed before anything runs on Civil 3D's main thread; every read
/// goes through DrawingAccess.Read (quiescent, read lock, transaction, ForRead only).
/// </summary>
internal static class Civil3DTools
{
    public static ToolRegistry Create(IHostDispatcher dispatcher)
    {
        Task<JsonObject> Run(Func<Reading, JsonObject> work, CancellationToken ct) =>
            dispatcher.InvokeAsync(() => DrawingAccess.Read(work), ct);

        return new ToolRegistry()
            .Add(ToolSpecs.Define("get_drawing", (_, ct) => Run(GetDrawing, ct)))
            .Add(ToolSpecs.Define("list_layers", (a, ct) =>
            {
                var filter = a.OptionalString("name_contains");
                var limit = Limit(a);
                return Run(r => ListLayers(r, filter, limit), ct);
            }))
            .Add(ToolSpecs.Define("count_objects", (a, ct) =>
            {
                var layer = a.OptionalString("layer");
                var byLayer = a.Boolean("by_layer", false);
                var limit = Limit(a);
                return Run(r => CountObjects(r, layer, byLayer, limit), ct);
            }))
            .Add(ToolSpecs.Define("list_alignments", (a, ct) =>
            {
                var limit = Limit(a);
                return Run(r => ListAlignments(r, limit), ct);
            }))
            .Add(ToolSpecs.Define("get_alignment", (a, ct) =>
            {
                var name = a.RequiredString("name");
                return Run(r => GetAlignment(r, name), ct);
            }))
            .Add(ToolSpecs.Define("alignment_point", (a, ct) =>
            {
                var name = a.RequiredString("alignment");
                var points = a.Objects("points", ToolSpecs.MaxPoints)
                    .Select((p, i) => (station: Args.ToNumber(p["station"] ?? throw new ToolException($"Point {i} needs 'station'."), $"Point {i} station"),
                                       offset: p["offset"] is null ? 0.0 : Args.ToNumber(p["offset"]!, $"Point {i} offset")))
                    .ToList();
                return Run(r => AlignmentPoints(r, name, points), ct);
            }))
            .Add(ToolSpecs.Define("alignment_station", (a, ct) =>
            {
                var name = a.RequiredString("alignment");
                var points = XY(a);
                return Run(r => AlignmentStations(r, name, points), ct);
            }))
            .Add(ToolSpecs.Define("profile_elevations", (a, ct) =>
            {
                var alignment = a.RequiredString("alignment");
                var profile = a.RequiredString("profile");
                var stations = ToolSpecs.ParseStations(a);
                return Run(r => ProfileElevations(r, alignment, profile, stations), ct);
            }))
            .Add(ToolSpecs.Define("list_surfaces", (a, ct) =>
            {
                var limit = Limit(a);
                return Run(r => ListSurfaces(r, limit), ct);
            }))
            .Add(ToolSpecs.Define("surface_elevations", (a, ct) =>
            {
                var name = a.RequiredString("surface");
                var points = XY(a);
                return Run(r => SurfaceElevations(r, name, points), ct);
            }))
            .Add(ToolSpecs.Define("list_corridors", (a, ct) =>
            {
                var limit = Limit(a);
                return Run(r => ListCorridors(r, limit), ct);
            }))
            .Add(ToolSpecs.Define("list_pipe_networks", (a, ct) =>
            {
                var limit = Limit(a);
                return Run(r => ListPipeNetworks(r, limit), ct);
            }))
            .Add(ToolSpecs.Define("get_pipe_network", (a, ct) =>
            {
                var name = a.RequiredString("name");
                var limit = a.Integer("limit", 500, 1, ToolSpecs.MaxLimit);
                return Run(r => GetPipeNetwork(r, name, limit), ct);
            }));
    }

    // ------------------------------------------------------------------ argument helpers

    private static int Limit(Args a) => a.Integer("limit", ToolSpecs.DefaultLimit, 1, ToolSpecs.MaxLimit);

    private static List<(double x, double y)> XY(Args a) =>
        a.Objects("points", ToolSpecs.MaxPoints)
         .Select((p, i) => (Args.ToNumber(p["x"] ?? throw new ToolException($"Point {i} needs 'x'."), $"Point {i} x"),
                            Args.ToNumber(p["y"] ?? throw new ToolException($"Point {i} needs 'y'."), $"Point {i} y")))
         .ToList();

    // ------------------------------------------------------------------ output helpers

    private static JsonNode? N(double value) => Args.Num(value);

    private static JsonObject Point(Point3d p) => new() { ["x"] = N(p.X), ["y"] = N(p.Y), ["z"] = N(p.Z) };

    private static JsonObject Listed(string key, List<JsonNode> items, int total, int limit) => new()
    {
        [key] = new JsonArray(items.Take(limit).ToArray()),
        ["count"] = total,
        ["truncated"] = total > limit,
    };

    private static string Message(Exception ex) => ex is Autodesk.AutoCAD.Runtime.Exception ac ? ac.ErrorStatus.ToString() : ex.Message;

    // ------------------------------------------------------------------ tools

    private static JsonObject GetDrawing(Reading r)
    {
        var units = r.Civil.Settings.DrawingSettings.UnitZoneSettings;
        int layers = 0;
        foreach (ObjectId _ in r.Open<LayerTable>(r.Database.LayerTableId)) layers++;
        int cogoPoints = 0;
        foreach (ObjectId _ in r.Civil.CogoPoints) cogoPoints++;
        return new JsonObject
        {
            ["name"] = r.Document.Name,
            ["file"] = r.Database.Filename,
            ["read_only"] = r.Document.IsReadOnly,
            ["civil3d_version"] = AcApp.GetSystemVariable("ACADVER")?.ToString(),
            ["units"] = new JsonObject
            {
                ["drawing_units"] = units.DrawingUnits.ToString(),
                ["insertion_units"] = r.Database.Insunits.ToString(),
                ["angular_units"] = units.AngularUnits.ToString(),
                ["drawing_scale"] = N(units.DrawingScale),
            },
            ["coordinate_system"] = string.IsNullOrWhiteSpace(units.CoordinateSystemCode) ? null : units.CoordinateSystemCode,
            ["counts"] = new JsonObject
            {
                ["alignments"] = r.Civil.GetAlignmentIds().Count,
                ["surfaces"] = r.Civil.GetSurfaceIds().Count,
                ["corridors"] = r.Civil.CorridorCollection.Count,
                ["pipe_networks"] = r.Civil.GetPipeNetworkIds().Count,
                ["cogo_points"] = cogoPoints,
                ["layers"] = layers,
            },
        };
    }

    private static JsonObject ListLayers(Reading r, string? filter, int limit)
    {
        var items = new List<JsonNode>();
        foreach (ObjectId id in r.Open<LayerTable>(r.Database.LayerTableId))
        {
            var layer = r.Open<LayerTableRecord>(id);
            if (filter is not null && layer.Name.IndexOf(filter, StringComparison.OrdinalIgnoreCase) < 0) continue;
            items.Add(new JsonObject
            {
                ["name"] = layer.Name,
                ["on"] = !layer.IsOff,
                ["frozen"] = layer.IsFrozen,
                ["locked"] = layer.IsLocked,
                ["plottable"] = layer.IsPlottable,
                ["color"] = layer.Color.ToString(),
                ["description"] = string.IsNullOrEmpty(layer.Description) ? null : layer.Description,
            });
        }
        items = items.OrderBy(i => i!["name"]!.GetValue<string>(), StringComparer.OrdinalIgnoreCase).ToList();
        return Listed("layers", items, items.Count, limit);
    }

    private static JsonObject CountObjects(Reading r, string? layer, bool byLayer, int limit)
    {
        var table = r.Open<BlockTable>(r.Database.BlockTableId);
        var modelSpace = r.Open<BlockTableRecord>(table[BlockTableRecord.ModelSpace]);
        var byType = new Dictionary<string, int>(StringComparer.Ordinal);
        var perLayer = new Dictionary<string, Dictionary<string, int>>(StringComparer.OrdinalIgnoreCase);
        int total = 0;
        bool needEntity = layer is not null || byLayer;
        foreach (ObjectId id in modelSpace)
        {
            var type = id.ObjectClass.DxfName;
            if (string.IsNullOrEmpty(type)) type = id.ObjectClass.Name;
            if (needEntity)
            {
                if (r.Transaction.GetObject(id, OpenMode.ForRead) is not Entity entity) continue;
                if (layer is not null && !string.Equals(entity.Layer, layer, StringComparison.OrdinalIgnoreCase)) continue;
                if (byLayer)
                {
                    if (!perLayer.TryGetValue(entity.Layer, out var counts)) perLayer[entity.Layer] = counts = new(StringComparer.Ordinal);
                    counts[type] = counts.GetValueOrDefault(type) + 1;
                }
            }
            byType[type] = byType.GetValueOrDefault(type) + 1;
            total++;
        }
        var result = new JsonObject
        {
            ["space"] = "model",
            ["layer"] = layer,
            ["total"] = total,
            ["by_type"] = new JsonObject(byType.OrderByDescending(kv => kv.Value).ThenBy(kv => kv.Key)
                                               .Select(kv => KeyValuePair.Create(kv.Key, (JsonNode?)kv.Value))),
        };
        if (byLayer)
        {
            var layers = perLayer.OrderBy(kv => kv.Key, StringComparer.OrdinalIgnoreCase).Select(kv => (JsonNode)new JsonObject
            {
                ["layer"] = kv.Key,
                ["total"] = kv.Value.Values.Sum(),
                ["by_type"] = new JsonObject(kv.Value.OrderByDescending(t => t.Value).Select(t => KeyValuePair.Create(t.Key, (JsonNode?)t.Value))),
            }).ToList();
            result["by_layer"] = new JsonArray(layers.Take(limit).ToArray());
            result["layers_truncated"] = layers.Count > limit;
        }
        return result;
    }

    private static JsonObject AlignmentSummary(Reading r, C.Alignment a) => new()
    {
        ["name"] = a.Name,
        ["description"] = string.IsNullOrEmpty(a.Description) ? null : a.Description,
        ["type"] = a.AlignmentType.ToString(),
        ["site"] = a.IsSiteless ? null : a.SiteName,
        ["style"] = a.StyleName,
        ["length"] = N(a.Length),
        ["start_station"] = N(a.StartingStation),
        ["end_station"] = N(a.EndingStation),
        ["profiles"] = a.GetProfileIds().Count,
    };

    private static JsonObject ListAlignments(Reading r, int limit)
    {
        var items = r.OpenAll<C.Alignment>(r.Civil.GetAlignmentIds().Cast<ObjectId>())
                     .OrderBy(a => a.Name, StringComparer.OrdinalIgnoreCase)
                     .Select(a => (JsonNode)AlignmentSummary(r, a)).ToList();
        return Listed("alignments", items, items.Count, limit);
    }

    private static C.Alignment FindAlignment(Reading r, string name) =>
        r.FindByName<C.Alignment>(r.Civil.GetAlignmentIds().Cast<ObjectId>(), name, "alignment");

    private static JsonObject GetAlignment(Reading r, string name)
    {
        var a = FindAlignment(r, name);
        var result = AlignmentSummary(r, a);
        result["end_station_with_equations"] = N(a.EndingStationWithEquations);
        result["design_speeds"] = a.DesignSpeeds.Count;
        result["station_equations"] = a.StationEquations.Count;
        var profiles = r.OpenAll<C.Profile>(a.GetProfileIds().Cast<ObjectId>())
            .OrderBy(p => p.Name, StringComparer.OrdinalIgnoreCase)
            .Select(p => (JsonNode)new JsonObject
            {
                ["name"] = p.Name,
                ["type"] = p.ProfileType.ToString(),
                ["style"] = p.StyleName,
                ["start_station"] = N(p.StartingStation),
                ["end_station"] = N(p.EndingStation),
                ["length"] = N(p.Length),
                ["lowest_elevation"] = N(p.ElevationMin),
                ["highest_elevation"] = N(p.ElevationMax),
            }).ToArray();
        result["profiles"] = new JsonArray(profiles);
        return result;
    }

    private static JsonObject AlignmentPoints(Reading r, string name, List<(double station, double offset)> points)
    {
        var a = FindAlignment(r, name);
        var results = new JsonArray();
        foreach (var (station, offset) in points)
        {
            var item = new JsonObject { ["station"] = N(station), ["offset"] = N(offset) };
            try
            {
                double easting = 0, northing = 0;
                a.PointLocation(station, offset, ref easting, ref northing);
                item["x"] = N(easting);
                item["y"] = N(northing);
            }
            catch (Exception ex)
            {
                item["error"] = $"station outside the alignment ({N(a.StartingStation)} to {N(a.EndingStation)}): {Message(ex)}";
            }
            results.Add(item);
        }
        return new JsonObject { ["alignment"] = a.Name, ["points"] = results };
    }

    private static JsonObject AlignmentStations(Reading r, string name, List<(double x, double y)> points)
    {
        var a = FindAlignment(r, name);
        var results = new JsonArray();
        foreach (var (x, y) in points)
        {
            var item = new JsonObject { ["x"] = N(x), ["y"] = N(y) };
            try
            {
                double station = 0, offset = 0;
                a.StationOffset(x, y, ref station, ref offset);
                item["station"] = N(station);
                item["offset"] = N(offset);
            }
            catch (Exception ex)
            {
                item["error"] = $"point can't be projected onto the alignment: {Message(ex)}";
            }
            results.Add(item);
        }
        return new JsonObject { ["alignment"] = a.Name, ["points"] = results };
    }

    private static JsonObject ProfileElevations(Reading r, string alignmentName, string profileName, List<double> stations)
    {
        var a = FindAlignment(r, alignmentName);
        var profile = r.FindByName<C.Profile>(a.GetProfileIds().Cast<ObjectId>(), profileName, $"profile on alignment '{a.Name}'");
        var results = new JsonArray();
        foreach (var station in stations)
        {
            var item = new JsonObject { ["station"] = N(station) };
            try
            {
                item["elevation"] = N(profile.ElevationAt(station));
            }
            catch (Exception ex)
            {
                item["error"] = $"station outside the profile ({N(profile.StartingStation)} to {N(profile.EndingStation)}): {Message(ex)}";
            }
            results.Add(item);
        }
        return new JsonObject { ["alignment"] = a.Name, ["profile"] = profile.Name, ["elevations"] = results };
    }

    private static JsonObject ListSurfaces(Reading r, int limit)
    {
        var items = new List<JsonNode>();
        foreach (var s in r.OpenAll<C.Surface>(r.Civil.GetSurfaceIds().Cast<ObjectId>()).OrderBy(s => s.Name, StringComparer.OrdinalIgnoreCase))
        {
            var item = new JsonObject
            {
                ["name"] = s.Name,
                ["type"] = s.GetType().Name,
                ["style"] = s.StyleName,
                ["out_of_date"] = s.IsOutOfDate,
            };
            try
            {
                var g = s.GetGeneralProperties();
                item["lowest_elevation"] = N(g.MinimumElevation);
                item["highest_elevation"] = N(g.MaximumElevation);
                item["mean_elevation"] = N(g.MeanElevation);
                item["points"] = g.NumberOfPoints;
            }
            catch (Exception ex)
            {
                item["properties_error"] = $"no statistics (empty surface?): {Message(ex)}";
            }
            if (s is C.TinSurface tin)
            {
                try { item["triangles"] = tin.GetTinProperties().NumberOfTriangles; }
                catch (Exception) { /* empty TIN: no triangle statistics */ }
            }
            items.Add(item);
        }
        return Listed("surfaces", items, items.Count, limit);
    }

    private static JsonObject SurfaceElevations(Reading r, string name, List<(double x, double y)> points)
    {
        var surface = r.FindByName<C.Surface>(r.Civil.GetSurfaceIds().Cast<ObjectId>(), name, "surface");
        var results = new JsonArray();
        foreach (var (x, y) in points)
        {
            var item = new JsonObject { ["x"] = N(x), ["y"] = N(y) };
            try
            {
                item["elevation"] = N(surface.FindElevationAtXY(x, y));
            }
            catch (Exception)
            {
                item["outside"] = true;     // Autodesk: thrown when the location is outside the surface
            }
            results.Add(item);
        }
        return new JsonObject { ["surface"] = surface.Name, ["points"] = results };
    }

    private static JsonObject ListCorridors(Reading r, int limit)
    {
        var items = new List<JsonNode>();
        foreach (var corridor in r.OpenAll<C.Corridor>(r.Civil.CorridorCollection).OrderBy(c => c.Name, StringComparer.OrdinalIgnoreCase))
        {
            var baselines = new JsonArray();
            foreach (var baseline in corridor.Baselines)
            {
                var regions = new JsonArray();
                foreach (var region in baseline.BaselineRegions)
                {
                    regions.Add(new JsonObject
                    {
                        ["name"] = region.Name,
                        ["start_station"] = N(region.StartStation),
                        ["end_station"] = N(region.EndStation),
                        ["assembly"] = r.NameOf(region.AssemblyId),
                    });
                }
                baselines.Add(new JsonObject
                {
                    ["name"] = baseline.Name,
                    ["alignment"] = r.NameOf(baseline.AlignmentId),
                    ["profile"] = r.NameOf(baseline.ProfileId),
                    ["regions"] = regions,
                });
            }
            items.Add(new JsonObject
            {
                ["name"] = corridor.Name,
                ["description"] = string.IsNullOrEmpty(corridor.Description) ? null : corridor.Description,
                ["out_of_date"] = corridor.IsOutOfDate,
                ["baselines"] = baselines,
            });
        }
        return Listed("corridors", items, items.Count, limit);
    }

    private static JsonObject ListPipeNetworks(Reading r, int limit)
    {
        var items = r.OpenAll<C.Network>(r.Civil.GetPipeNetworkIds().Cast<ObjectId>())
            .OrderBy(n => n.Name, StringComparer.OrdinalIgnoreCase)
            .Select(n => (JsonNode)new JsonObject
            {
                ["name"] = n.Name,
                ["description"] = string.IsNullOrEmpty(n.Description) ? null : n.Description,
                ["pipes"] = n.GetPipeIds().Count,
                ["structures"] = n.GetStructureIds().Count,
            }).ToList();
        return Listed("pipe_networks", items, items.Count, limit);
    }

    private static JsonObject GetPipeNetwork(Reading r, string name, int limit)
    {
        var network = r.FindByName<C.Network>(r.Civil.GetPipeNetworkIds().Cast<ObjectId>(), name, "pipe network");
        var pipeIds = network.GetPipeIds().Cast<ObjectId>().ToList();
        var structureIds = network.GetStructureIds().Cast<ObjectId>().ToList();
        var pipes = r.OpenAll<C.Pipe>(pipeIds.Take(limit)).Select(p => (JsonNode)new JsonObject
        {
            ["name"] = p.Name,
            ["size"] = p.PartSizeName,
            ["material"] = p.Material,
            ["inner_diameter_or_width"] = N(p.InnerDiameterOrWidth),
            ["length_2d"] = N(p.Length2D),
            ["slope"] = N(p.Slope),
            ["start_structure"] = r.NameOf(p.StartStructureId),
            ["end_structure"] = r.NameOf(p.EndStructureId),
            ["minimum_cover"] = N(p.MinimumCover),
            ["maximum_cover"] = N(p.MaximumCover),
            ["start_point"] = Point(p.StartPoint),
            ["end_point"] = Point(p.EndPoint),
        }).ToArray();
        var structures = r.OpenAll<C.Structure>(structureIds.Take(limit)).Select(s => (JsonNode)new JsonObject
        {
            ["name"] = s.Name,
            ["size"] = s.PartSizeName,
            ["location"] = Point(s.Location),
            ["rim_elevation"] = N(s.RimElevation),
            ["sump_elevation"] = N(s.SumpElevation),
            ["sump_depth"] = N(s.SumpDepth),
        }).ToArray();
        return new JsonObject
        {
            ["name"] = network.Name,
            ["pipes"] = new JsonArray(pipes),
            ["structures"] = new JsonArray(structures),
            ["pipe_count"] = pipeIds.Count,
            ["structure_count"] = structureIds.Count,
            ["truncated"] = pipeIds.Count > limit || structureIds.Count > limit,
            ["note"] = "Slope is an absolute value. Cover is measured from the top outside of the pipe to the reference surface. Invert levels are not calculated.",
        };
    }
}
