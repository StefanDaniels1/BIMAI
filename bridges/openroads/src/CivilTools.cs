using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Linq;

namespace Bimai.OpenRoads
{
    /// <summary>
    /// The civil model of the drawing open in OpenRoads Designer, through Bentley's CifNET SDK:
    /// Session.Instance.GetActiveDgnModel() → new ConsensusConnection(model) → GetActiveGeometricModel()
    /// (as in the OpenRoads Designer SDK examples). Read-only: nothing here changes the drawing.
    /// Lengths, distances and coordinates are as the civil API returns them (metres, OpenRoads' storage
    /// units); stations are formatted the way OpenRoads displays them.
    /// </summary>
    internal sealed class Civil : IDisposable
    {
        public object Model;
        public object Connection;
        public object Geometry;

        public static Civil Open()
        {
            Type session = Reflect.FindType("Bentley.MstnPlatformNET.Session", "Bentley.MstnPlatformNET");
            if (session == null)
                throw new ToolException("OpenRoads Designer's API isn't available here: the bridge only works inside OpenRoads Designer.");
            object model = Reflect.Call(Reflect.GetStatic(session, "Instance"), "GetActiveDgnModel");
            if (model == null) throw new ToolException("No drawing is open in OpenRoads Designer. Open a drawing and try again.");
            Type connectionType = Reflect.FindType("Bentley.CifNET.SDK.ConsensusConnection", "Bentley.CifNET.SDK");
            if (connectionType == null)
                throw new ToolException("OpenRoads' civil API (Bentley.CifNET.SDK) isn't loaded. Is this OpenRoads Designer " +
                                        "(not plain MicroStation)? Start a civil tool once and try again.");
            object connection = Activator.CreateInstance(connectionType, model);
            object geometry = Reflect.Call(connection, "GetActiveGeometricModel");
            if (geometry == null)
            {
                var d = connection as IDisposable;
                if (d != null) d.Dispose();
                throw new ToolException("The active model has no civil geometry (no alignments, corridors or terrains). " +
                                        "Open the design model of the drawing.");
            }
            return new Civil { Model = model, Connection = connection, Geometry = geometry };
        }

        public IEnumerable<object> Alignments { get { return Reflect.Items(Reflect.TryGet(Geometry, "Alignments")); } }
        public IEnumerable<object> Corridors { get { return Reflect.Items(Reflect.TryGet(Geometry, "Corridors")); } }
        public IEnumerable<object> Terrains { get { return Reflect.Items(Reflect.TryGet(Geometry, "TerrainSurfaces")); } }

        public object FindAlignment(string name)
        {
            var all = Alignments.ToList();
            var match = all.FirstOrDefault(a => string.Equals(Reflect.Text(Reflect.TryGet(a, "Name")), name, StringComparison.OrdinalIgnoreCase));
            if (match != null) return match;
            var names = all.Select(a => Reflect.Text(Reflect.TryGet(a, "Name"))).Where(n => !string.IsNullOrEmpty(n)).Take(30).ToList();
            throw new ToolException("No alignment named '" + name + "'. " +
                                    (names.Count == 0 ? "The drawing has no named alignments." : "Alignments: " + string.Join(", ", names)));
        }

        public object Point(double x, double y, double z)
        {
            Type t = Reflect.FindType("Bentley.GeometryNET.DPoint3d", "Bentley.GeometryNET");
            if (t == null) throw new ToolException("Bentley's geometry library (Bentley.GeometryNET) isn't loaded.");
            try { return Activator.CreateInstance(t, x, y, z); }
            catch (MissingMethodException) { return Activator.CreateInstance(t, x, y); }
        }

        /// <summary>A station the way OpenRoads shows it (station equations and format included), or null.</summary>
        public string Station(object alignment, double distance)
        {
            try
            {
                Type formatterType = Reflect.FindType("Bentley.CifNET.GeometryModel.SDK.StationingFormatter", "Bentley.CifNET.GeometryModel.SDK");
                Type settingsType = Reflect.FindType("Bentley.CifNET.GeometryModel.SDK.StationFormatSettings", "Bentley.CifNET.GeometryModel.SDK");
                if (formatterType == null || settingsType == null) return null;
                object formatter = Activator.CreateInstance(formatterType, alignment);
                object settings = Reflect.CallStatic(settingsType, "GetStationFormatSettingsForModel", Model);
                var args = new object[] { "", distance, settings };
                Reflect.Call(formatter, "FormatStation", args);
                var text = args[0] as string;
                return string.IsNullOrEmpty(text) ? null : text;
            }
            catch (Exception) { return null; }
        }

        public void Dispose()
        {
            var d = Connection as IDisposable;
            if (d != null)
            {
                try { d.Dispose(); } catch (Exception) { }
            }
        }
    }

    public static class CivilTools
    {
        private const string Units = "m";

        public static ToolRegistry Create(IDispatcher dispatcher)
        {
            var tools = new ToolRegistry();
            Func<Func<Civil, Args, Dictionary<string, object>>, Func<Args, Dictionary<string, object>>> onMain =
                work => args => dispatcher.Invoke(() =>
                {
                    using (var civil = Civil.Open()) return work(civil, args);
                });

            tools.Add(new ToolDefinition
            {
                Name = "get_drawing_info",
                Title = "Drawing info",
                Description = "The drawing open in OpenRoads Designer: file, model, OpenRoads version, and how many alignments, " +
                              "corridors and terrains it has. Start here.",
                InputSchema = Schema.Object(new string[0][]),
                Handler = onMain(DrawingInfo),
            });
            tools.Add(new ToolDefinition
            {
                Name = "list_alignments",
                Title = "List alignments",
                Description = "All horizontal alignments in the active model: name, length, start and end distance and station, " +
                              "feature definition and the active profile.",
                InputSchema = Schema.Object(new string[0][]),
                Handler = onMain(ListAlignments),
            });
            tools.Add(new ToolDefinition
            {
                Name = "get_alignment",
                Title = "Alignment details",
                Description = "One alignment: its geometry elements where available, and points along it every `interval` " +
                              "metres (distance, station, x, y).",
                InputSchema = Schema.Object(new[]
                {
                    Schema.P("alignment", "string", "Alignment name (see list_alignments)"),
                    Schema.P("interval", "number", "Distance between points in metres (default 25, 1 to 1000)"),
                }, "alignment"),
                Handler = onMain(GetAlignment),
            });
            tools.Add(new ToolDefinition
            {
                Name = "locate_on_alignment",
                Title = "Station and offset of a point",
                Description = "Where a point (x, y in drawing coordinates) lies relative to an alignment: distance, station " +
                              "and offset (right positive, left negative).",
                InputSchema = Schema.Object(new[]
                {
                    Schema.P("alignment", "string", "Alignment name"),
                    Schema.P("x", "number", "X (easting)"),
                    Schema.P("y", "number", "Y (northing)"),
                }, "alignment", "x", "y"),
                Handler = onMain(LocateOnAlignment),
            });
            tools.Add(new ToolDefinition
            {
                Name = "list_profiles",
                Title = "List profiles",
                Description = "The vertical profiles of an alignment: name, length and which one is active.",
                InputSchema = Schema.Object(new[] { Schema.P("alignment", "string", "Alignment name") }, "alignment"),
                Handler = onMain(ListProfiles),
            });
            tools.Add(new ToolDefinition
            {
                Name = "get_profile",
                Title = "Profile details",
                Description = "A vertical profile's control points (such as start, end and vertical intersection points): " +
                              "distance along the alignment, station and elevation. Uses the active profile unless one is named.",
                InputSchema = Schema.Object(new[]
                {
                    Schema.P("alignment", "string", "Alignment name"),
                    Schema.P("profile", "string", "Profile name (default: the active profile)"),
                }, "alignment"),
                Handler = onMain(GetProfile),
            });
            tools.Add(new ToolDefinition
            {
                Name = "list_corridors",
                Title = "List corridors",
                Description = "All corridors in the active model: name, alignment, start and end distance and station.",
                InputSchema = Schema.Object(new string[0][]),
                Handler = onMain(ListCorridors),
            });
            tools.Add(new ToolDefinition
            {
                Name = "list_terrains",
                Title = "List terrains",
                Description = "All terrain models in the active model: name, whether it is the active terrain, and its statistics.",
                InputSchema = Schema.Object(new string[0][]),
                Handler = onMain(ListTerrains),
            });
            tools.Add(new ToolDefinition
            {
                Name = "get_terrain_elevation",
                Title = "Terrain elevation at a point",
                Description = "The elevation of a terrain at x, y (drawing coordinates). Uses the active terrain unless one is named.",
                InputSchema = Schema.Object(new[]
                {
                    Schema.P("x", "number", "X (easting)"),
                    Schema.P("y", "number", "Y (northing)"),
                    Schema.P("terrain", "string", "Terrain name (default: the active terrain)"),
                }, "x", "y"),
                Handler = onMain(TerrainElevation),
            });
            return tools;
        }

        // ------------------------------------------------------------------ tools

        private static Dictionary<string, object> DrawingInfo(Civil civil, Args args)
        {
            var result = Json.Obj();
            object file = Reflect.TryCallSafe(civil.Model, "GetDgnFile");
            result["file"] = Reflect.Text(Reflect.TryCallSafe(file, "GetFileName") ?? Reflect.TryGet(file, "FileName"));
            result["model"] = Reflect.Text(Reflect.TryGet(civil.Model, "ModelName", "Name"));
            try
            {
                var info = Process.GetCurrentProcess().MainModule.FileVersionInfo;
                result["product"] = info.ProductName;
                result["product_version"] = info.ProductVersion;
            }
            catch (Exception) { }
            result["alignments"] = (long)civil.Alignments.Count();
            result["corridors"] = (long)civil.Corridors.Count();
            result["terrains"] = (long)civil.Terrains.Count();
            result["units"] = Units;
            result["bridge_version"] = Bridge.Version;
            return result;
        }

        private static Dictionary<string, object> ListAlignments(Civil civil, Args args)
        {
            var items = new List<object>();
            foreach (object al in civil.Alignments.Take(500)) items.Add(AlignmentSummary(civil, al));
            var result = Json.Obj();
            result["alignments"] = items;
            result["count"] = (long)items.Count;
            result["units"] = Units;
            return result;
        }

        private static Dictionary<string, object> AlignmentSummary(Civil civil, object al)
        {
            var o = Json.Obj();
            o["name"] = Reflect.Text(Reflect.TryGet(al, "Name"));
            object geometry = Reflect.TryGet(al, "LinearGeometry");
            o["length"] = Reflect.Number(Reflect.TryGet(geometry, "Length"));
            double? start = Reflect.Number(Reflect.TryGet(Reflect.TryGet(geometry, "StartPoint"), "DistanceAlong"));
            double? end = Reflect.Number(Reflect.TryGet(Reflect.TryGet(geometry, "EndPoint"), "DistanceAlong"));
            o["start_distance"] = start;
            o["end_distance"] = end;
            o["start_station"] = start.HasValue ? civil.Station(al, start.Value) : null;
            o["end_station"] = end.HasValue ? civil.Station(al, end.Value) : null;
            o["feature_definition"] = Reflect.Text(Reflect.TryGet(al, "FeatureDefinition", "FeatureDefinitionName"));
            object active = Reflect.TryGet(al, "ActiveProfile");
            o["active_profile"] = active == null ? null : Reflect.Text(Reflect.TryGet(active, "Name"));
            o["profiles"] = (long)Reflect.Items(Reflect.TryGet(al, "Profiles")).Count();
            o["properties"] = Reflect.Describe(al, 25);
            return o;
        }

        private static Dictionary<string, object> GetAlignment(Civil civil, Args args)
        {
            object al = civil.FindAlignment(args.String("alignment", true));
            double interval = args.NumberInRange("interval", 25, 1, 1000);
            var result = AlignmentSummary(civil, al);
            object geometry = Reflect.TryGet(al, "LinearGeometry");
            if (geometry == null) throw new ToolException("This alignment has no horizontal geometry.");
            result["geometry_type"] = geometry.GetType().Name;
            result["elements"] = Elements(geometry);

            double start = Reflect.Number(Reflect.TryGet(Reflect.TryGet(geometry, "StartPoint"), "DistanceAlong")) ?? 0;
            double end = Reflect.Number(Reflect.TryGet(Reflect.TryGet(geometry, "EndPoint"), "DistanceAlong"))
                         ?? (start + (Reflect.Number(Reflect.TryGet(geometry, "Length")) ?? 0));
            const int maxPoints = 1000;
            if ((end - start) / interval > maxPoints)
            {
                interval = Math.Ceiling((end - start) / maxPoints);
                result["note"] = "interval widened to " + interval.ToString(CultureInfo.InvariantCulture) + " m to stay within " + maxPoints + " points";
            }
            var points = new List<object>();
            for (double d = start; ; d += interval)
            {
                double at = Math.Min(d, end);
                object lp = Reflect.Call(geometry, "GetPointAtDistanceOffset", at, 0.0);
                object xyz = Reflect.TryGet(lp, "Coordinates");
                var p = Json.Obj();
                p["distance"] = Math.Round(at, 6);
                p["station"] = civil.Station(al, at);
                p["x"] = Reflect.Number(Reflect.TryGet(xyz, "X"));
                p["y"] = Reflect.Number(Reflect.TryGet(xyz, "Y"));
                points.Add(p);
                if (at >= end) break;
            }
            result["interval"] = interval;
            result["points"] = points;
            return result;
        }

        /// <summary>The horizontal elements (lines, arcs, spirals) when the geometry exposes them.</summary>
        private static List<object> Elements(object geometry)
        {
            var list = new List<object>();
            object subs = Reflect.TryCallSafe(geometry, "GetSubLinearElements") ?? Reflect.TryGet(geometry, "SubLinearElements", "Elements");
            foreach (object e in Reflect.Items(subs).Take(500))
            {
                var o = Json.Obj();
                o["type"] = e.GetType().Name;
                o["length"] = Reflect.Number(Reflect.TryGet(e, "Length"));
                o["radius"] = Reflect.Number(Reflect.TryGet(e, "Radius"));
                o["start_distance"] = Reflect.Number(Reflect.TryGet(Reflect.TryGet(e, "StartPoint"), "DistanceAlong"));
                o["end_distance"] = Reflect.Number(Reflect.TryGet(Reflect.TryGet(e, "EndPoint"), "DistanceAlong"));
                list.Add(o);
            }
            return list;
        }

        private static Dictionary<string, object> LocateOnAlignment(Civil civil, Args args)
        {
            object al = civil.FindAlignment(args.String("alignment", true));
            double x = args.Number("x", true).Value, y = args.Number("y", true).Value;
            object geometry = Reflect.TryGet(al, "LinearGeometry");
            if (geometry == null) throw new ToolException("This alignment has no horizontal geometry.");
            object projected = Reflect.Call(geometry, "ProjectPointOnPerpendicular", civil.Point(x, y, 0));
            if (projected == null) throw new ToolException("The point can't be projected onto this alignment.");
            double distance = Reflect.Number(Reflect.Get(projected, "DistanceAlong")) ?? 0;
            object on = Reflect.TryGet(projected, "Coordinates");
            double cx = Reflect.Number(Reflect.TryGet(on, "X")) ?? x, cy = Reflect.Number(Reflect.TryGet(on, "Y")) ?? y;

            // Side from the direction of travel at that point: right positive, left negative (OpenRoads' convention).
            object ahead = Reflect.TryGet(Reflect.Call(geometry, "GetPointAtDistanceOffset", distance + 0.5, 0.0), "Coordinates");
            double ax = Reflect.Number(Reflect.TryGet(ahead, "X")) ?? cx, ay = Reflect.Number(Reflect.TryGet(ahead, "Y")) ?? cy;
            double cross = (ax - cx) * (y - cy) - (ay - cy) * (x - cx);
            double offset = Math.Sqrt((x - cx) * (x - cx) + (y - cy) * (y - cy));
            var result = Json.Obj();
            result["alignment"] = Reflect.Text(Reflect.TryGet(al, "Name"));
            result["distance"] = Math.Round(distance, 6);
            result["station"] = civil.Station(al, distance);
            result["offset"] = Math.Round(cross > 0 ? -offset : offset, 6);
            result["side"] = offset < 1e-6 ? "on" : (cross > 0 ? "left" : "right");
            double? extension = Reflect.Number(Reflect.TryGet(projected, "DistanceOnExtension"));
            result["beyond_ends"] = extension.HasValue && Math.Abs(extension.Value) > 1e-6;
            result["units"] = Units;
            return result;
        }

        private static List<object> ProfilesOf(object alignment)
        {
            return Reflect.Items(Reflect.TryGet(alignment, "Profiles")).ToList();
        }

        private static bool SameProfile(object a, object b)
        {
            if (a == null || b == null) return false;
            return ReferenceEquals(a, b) || a.Equals(b) ||
                   (Reflect.Text(Reflect.TryGet(a, "Name")) == Reflect.Text(Reflect.TryGet(b, "Name")) &&
                    Reflect.Number(Reflect.TryGet(Reflect.TryGet(a, "ProfileGeometry"), "Length")) ==
                    Reflect.Number(Reflect.TryGet(Reflect.TryGet(b, "ProfileGeometry"), "Length")));
        }

        private static Dictionary<string, object> ListProfiles(Civil civil, Args args)
        {
            object al = civil.FindAlignment(args.String("alignment", true));
            object active = Reflect.TryGet(al, "ActiveProfile");
            var items = new List<object>();
            foreach (object p in ProfilesOf(al))
            {
                var o = Json.Obj();
                o["name"] = Reflect.Text(Reflect.TryGet(p, "Name"));
                o["length"] = Reflect.Number(Reflect.TryGet(Reflect.TryGet(p, "ProfileGeometry"), "Length"));
                o["active"] = SameProfile(p, active);
                o["properties"] = Reflect.Describe(p, 20);
                items.Add(o);
            }
            var result = Json.Obj();
            result["alignment"] = Reflect.Text(Reflect.TryGet(al, "Name"));
            result["profiles"] = items;
            result["units"] = Units;
            return result;
        }

        private static Dictionary<string, object> GetProfile(Civil civil, Args args)
        {
            object al = civil.FindAlignment(args.String("alignment", true));
            string wanted = args.String("profile", false);
            var profiles = ProfilesOf(al);
            object active = Reflect.TryGet(al, "ActiveProfile");
            object profile = wanted == null
                ? (active ?? profiles.FirstOrDefault())
                : profiles.FirstOrDefault(p => string.Equals(Reflect.Text(Reflect.TryGet(p, "Name")), wanted, StringComparison.OrdinalIgnoreCase));
            if (profile == null)
            {
                var names = profiles.Select(p => Reflect.Text(Reflect.TryGet(p, "Name"))).ToList();
                throw new ToolException(wanted == null
                    ? "This alignment has no profile."
                    : "No profile named '" + wanted + "'. Profiles: " + (names.Count == 0 ? "none" : string.Join(", ", names)));
            }
            object geometry = Reflect.TryGet(profile, "ProfileGeometry");
            if (geometry == null) throw new ToolException("This profile has no geometry.");

            // GetVerticalControlPoints(VerticalControlPointTypes) as in Bentley's example; every type the enum offers.
            var controlPoints = Json.Obj();
            var method = geometry.GetType().GetMethods().FirstOrDefault(m => m.Name == "GetVerticalControlPoints" && m.GetParameters().Length == 1);
            if (method != null && method.GetParameters()[0].ParameterType.IsEnum)
            {
                foreach (object kind in Enum.GetValues(method.GetParameters()[0].ParameterType))
                {
                    try
                    {
                        object collection = method.Invoke(geometry, new[] { kind });
                        var vertices = Reflect.Items(Reflect.Call(collection, "GetVertices")).Take(500).ToList();
                        if (vertices.Count == 0) continue;
                        var points = new List<object>();
                        foreach (object v in vertices)
                        {
                            double? distance = Reflect.Number(Reflect.TryGet(v, "X"));
                            var p = Json.Obj();
                            p["distance"] = distance;
                            p["station"] = distance.HasValue ? civil.Station(al, distance.Value) : null;
                            p["elevation"] = Reflect.Number(Reflect.TryGet(v, "Y"));
                            points.Add(p);
                        }
                        controlPoints[kind.ToString()] = points;
                    }
                    catch (Exception) { }
                }
            }
            var result = Json.Obj();
            result["alignment"] = Reflect.Text(Reflect.TryGet(al, "Name"));
            result["profile"] = Reflect.Text(Reflect.TryGet(profile, "Name"));
            result["active"] = SameProfile(profile, active);
            result["length"] = Reflect.Number(Reflect.TryGet(geometry, "Length"));
            result["control_points"] = controlPoints;
            result["units"] = Units;
            return result;
        }

        private static Dictionary<string, object> ListCorridors(Civil civil, Args args)
        {
            var items = new List<object>();
            foreach (object c in civil.Corridors.Take(500))
            {
                var o = Json.Obj();
                o["name"] = Reflect.Text(Reflect.TryGet(c, "Name"));
                object al = Reflect.TryGet(c, "CorridorAlignment", "Alignment");
                o["alignment"] = al == null ? null : Reflect.Text(Reflect.TryGet(al, "Name"));
                double? start = Reflect.Number(Reflect.TryGet(c, "StartDistance"));
                double? end = Reflect.Number(Reflect.TryGet(c, "EndDistance", "StopDistance"));
                o["start_distance"] = start;
                o["end_distance"] = end;
                o["start_station"] = al != null && start.HasValue ? civil.Station(al, start.Value) : null;
                o["end_station"] = al != null && end.HasValue ? civil.Station(al, end.Value) : null;
                o["properties"] = Reflect.Describe(c, 25);
                items.Add(o);
            }
            var result = Json.Obj();
            result["corridors"] = items;
            result["count"] = (long)items.Count;
            result["units"] = Units;
            return result;
        }

        private static Dictionary<string, object> ListTerrains(Civil civil, Args args)
        {
            object active = Reflect.TryGet(civil.Geometry, "ActiveSurface");
            var items = new List<object>();
            foreach (object t in civil.Terrains.Take(200))
            {
                var o = Json.Obj();
                o["name"] = Reflect.Text(Reflect.TryGet(t, "Name"));
                o["active"] = active != null && (ReferenceEquals(t, active) || t.Equals(active));
                o["properties"] = Reflect.Describe(t, 20);
                o["statistics"] = Reflect.Describe(Reflect.TryGet(t, "DTM"), 25);
                items.Add(o);
            }
            var result = Json.Obj();
            result["terrains"] = items;
            result["count"] = (long)items.Count;
            return result;
        }

        private static Dictionary<string, object> TerrainElevation(Civil civil, Args args)
        {
            double x = args.Number("x", true).Value, y = args.Number("y", true).Value;
            string wanted = args.String("terrain", false);
            var terrains = civil.Terrains.ToList();
            object terrain = wanted == null
                ? (Reflect.TryGet(civil.Geometry, "ActiveSurface") ?? terrains.FirstOrDefault())
                : terrains.FirstOrDefault(t => string.Equals(Reflect.Text(Reflect.TryGet(t, "Name")), wanted, StringComparison.OrdinalIgnoreCase));
            if (terrain == null)
            {
                var names = terrains.Select(t => Reflect.Text(Reflect.TryGet(t, "Name"))).ToList();
                throw new ToolException(wanted == null
                    ? "The drawing has no terrain."
                    : "No terrain named '" + wanted + "'. Terrains: " + (names.Count == 0 ? "none" : string.Join(", ", names)));
            }
            object dtm = Reflect.TryGet(terrain, "DTM");
            if (dtm == null) throw new ToolException("This terrain has no terrain model (DTM).");
            object draped = Reflect.Call(dtm, "DrapePoint", civil.Point(x, y, 0));
            string code = Reflect.Text(Reflect.TryGet(draped, "Code"));
            bool outside = code != null && (code.IndexOf("External", StringComparison.OrdinalIgnoreCase) >= 0
                                            || code.IndexOf("Void", StringComparison.OrdinalIgnoreCase) >= 0);
            var result = Json.Obj();
            result["terrain"] = Reflect.Text(Reflect.TryGet(terrain, "Name"));
            result["x"] = x;
            result["y"] = y;
            result["elevation"] = outside ? null : Reflect.Number(Reflect.TryGet(Reflect.TryGet(draped, "Coordinates"), "Z"));
            result["code"] = code;
            result["inside"] = !outside;
            result["units"] = Units;
            return result;
        }
    }
}
