using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

namespace Bimai.OpenRoads
{
    public interface IDispatcher
    {
        T Invoke<T>(Func<T> work);
    }

    /// <summary>Runs work on the calling thread (tests and the development host).</summary>
    public sealed class InlineDispatcher : IDispatcher
    {
        public T Invoke<T>(Func<T> work) { return work(); }
    }

    /// <summary>A refusal with a message for the person (bad arguments, no drawing open, …).</summary>
    public sealed class ToolException : Exception
    {
        public ToolException(string message) : base(message) { }
    }

    public sealed class ToolDefinition
    {
        public string Name;
        public string Title;
        public string Description;
        public Dictionary<string, object> InputSchema;
        public Func<Args, Dictionary<string, object>> Handler;    // runs on a connection thread

        public Dictionary<string, object> ToJson()
        {
            var annotations = Json.Obj();
            annotations["title"] = Title;
            annotations["readOnlyHint"] = true;
            annotations["destructiveHint"] = false;
            annotations["idempotentHint"] = true;
            annotations["openWorldHint"] = false;
            var o = Json.Obj();
            o["name"] = Name;
            o["title"] = Title;
            o["description"] = Description;
            o["inputSchema"] = InputSchema;
            o["annotations"] = annotations;
            return o;
        }
    }

    public sealed class ToolRegistry
    {
        private readonly List<ToolDefinition> _tools = new List<ToolDefinition>();

        public ToolRegistry Add(ToolDefinition tool)
        {
            if (_tools.Any(t => t.Name == tool.Name)) throw new ArgumentException("duplicate tool " + tool.Name);
            _tools.Add(tool);
            return this;
        }

        /// <summary>Sorted by name: a deterministic order, as the 2026-07-28 spec recommends for caching.</summary>
        public List<ToolDefinition> All
        {
            get { return _tools.OrderBy(t => t.Name, StringComparer.Ordinal).ToList(); }
        }

        public ToolDefinition Find(string name)
        {
            return _tools.FirstOrDefault(t => t.Name == name);
        }
    }

    /// <summary>Typed access to tool arguments; every violation is a ToolException with a clear message.</summary>
    public sealed class Args
    {
        private readonly Dictionary<string, object> _json;

        public Args(Dictionary<string, object> json) { _json = json ?? Json.Obj(); }

        public string String(string name, bool required)
        {
            object v = Json.Get(_json, name);
            if (v == null)
            {
                if (required) throw new ToolException("'" + name + "' is required.");
                return null;
            }
            var s = v as string;
            if (s == null) throw new ToolException("'" + name + "' must be a string.");
            if (required && s.Trim().Length == 0) throw new ToolException("'" + name + "' must not be empty.");
            return s;
        }

        public double? Number(string name, bool required)
        {
            object v = Json.Get(_json, name);
            if (v == null)
            {
                if (required) throw new ToolException("'" + name + "' is required.");
                return null;
            }
            if (v is long) return (long)v;
            if (v is double)
            {
                double d = (double)v;
                if (double.IsNaN(d) || double.IsInfinity(d)) throw new ToolException("'" + name + "' must be a finite number.");
                return d;
            }
            throw new ToolException("'" + name + "' must be a number.");
        }

        public double NumberInRange(string name, double fallback, double min, double max)
        {
            double? v = Number(name, false);
            double value = v.HasValue ? v.Value : fallback;
            if (value < min || value > max)
                throw new ToolException("'" + name + "' must be between " + min.ToString(CultureInfo.InvariantCulture)
                                        + " and " + max.ToString(CultureInfo.InvariantCulture) + ".");
            return value;
        }
    }

    public static class Schema
    {
        /// <summary>An object schema; properties as (name, type, description) triples, `required` by name.</summary>
        public static Dictionary<string, object> Object(string[][] properties, params string[] required)
        {
            var props = Json.Obj();
            foreach (var p in properties)
            {
                var prop = Json.Obj();
                prop["type"] = p[1];
                prop["description"] = p[2];
                props[p[0]] = prop;
            }
            var schema = Json.Obj();
            schema["type"] = "object";
            schema["properties"] = props;
            if (required.Length > 0) schema["required"] = required.ToList<object>();
            schema["additionalProperties"] = false;
            return schema;
        }

        public static string[] P(string name, string type, string description)
        {
            return new[] { name, type, description };
        }
    }
}
