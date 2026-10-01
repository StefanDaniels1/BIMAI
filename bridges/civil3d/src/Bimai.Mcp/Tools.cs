using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace Bimai.Mcp;

/// <summary>A problem the AI should see and can act on: wrong argument, unknown name, Civil 3D busy.</summary>
public sealed class ToolException : Exception
{
    public ToolException(string message) : base(message) { }
}

/// <summary>A read-only MCP tool: a name, a description, a JSON Schema for its input, and a handler.</summary>
public sealed class ToolDefinition
{
    public required string Name { get; init; }
    public required string Title { get; init; }
    public required string Description { get; init; }
    public required JsonObject InputSchema { get; init; }
    public required Func<Args, CancellationToken, Task<JsonObject>> Handler { get; init; }

    public JsonObject ToJson() => new()
    {
        ["name"] = Name,
        ["title"] = Title,
        ["description"] = Description,
        ["inputSchema"] = InputSchema.DeepClone(),
        ["annotations"] = new JsonObject
        {
            ["title"] = Title,
            ["readOnlyHint"] = true,
            ["destructiveHint"] = false,
            ["idempotentHint"] = true,
            ["openWorldHint"] = false,
        },
    };
}

public sealed class ToolRegistry
{
    private readonly List<ToolDefinition> _tools = new();

    public ToolRegistry Add(ToolDefinition tool)
    {
        if (_tools.Any(t => t.Name == tool.Name)) throw new ArgumentException($"duplicate tool {tool.Name}");
        _tools.Add(tool);
        return this;
    }

    /// <summary>Deterministic order (sorted by name), as the 2026-07-28 spec recommends for caching.</summary>
    public IReadOnlyList<ToolDefinition> All => _tools.OrderBy(t => t.Name, StringComparer.Ordinal).ToList();

    public ToolDefinition? Find(string name) => _tools.FirstOrDefault(t => t.Name == name);
}

/// <summary>Typed access to tool arguments; every violation is a ToolException with a clear message.</summary>
public sealed class Args
{
    private readonly JsonObject _json;

    public Args(JsonObject? json) { _json = json ?? new JsonObject(); }

    private JsonNode? Get(string name) => _json.TryGetPropertyValue(name, out var v) ? v : null;

    public string? OptionalString(string name)
    {
        var node = Get(name);
        if (node is null) return null;
        if (node is JsonValue v && v.TryGetValue(out string? s)) return s;
        throw new ToolException($"Argument '{name}' must be a text value.");
    }

    public string RequiredString(string name)
    {
        var s = OptionalString(name);
        if (string.IsNullOrWhiteSpace(s)) throw new ToolException($"Argument '{name}' is required.");
        return s;
    }

    public double? OptionalNumber(string name)
    {
        var node = Get(name);
        if (node is null) return null;
        return ToNumber(node, $"Argument '{name}'");
    }

    public double RequiredNumber(string name) =>
        OptionalNumber(name) ?? throw new ToolException($"Argument '{name}' is required.");

    public int Integer(string name, int defaultValue, int min, int max)
    {
        var node = Get(name);
        if (node is null) return defaultValue;
        var d = ToNumber(node, $"Argument '{name}'");
        if (d != Math.Floor(d)) throw new ToolException($"Argument '{name}' must be a whole number.");
        if (d < min || d > max) throw new ToolException($"Argument '{name}' must be between {min} and {max}.");
        return (int)d;
    }

    public bool Boolean(string name, bool defaultValue)
    {
        var node = Get(name);
        if (node is null) return defaultValue;
        if (node is JsonValue v && v.TryGetValue(out bool b)) return b;
        throw new ToolException($"Argument '{name}' must be true or false.");
    }

    /// <summary>An array of objects, at most maxItems long.</summary>
    public IReadOnlyList<JsonObject> Objects(string name, int maxItems, bool required = true)
    {
        var node = Get(name);
        if (node is null)
        {
            if (required) throw new ToolException($"Argument '{name}' is required.");
            return Array.Empty<JsonObject>();
        }
        if (node is not JsonArray array) throw new ToolException($"Argument '{name}' must be a list.");
        if (array.Count > maxItems) throw new ToolException($"Argument '{name}' may contain at most {maxItems} items.");
        var result = new List<JsonObject>();
        for (int i = 0; i < array.Count; i++)
        {
            if (array[i] is not JsonObject o) throw new ToolException($"Item {i} of '{name}' must be an object.");
            result.Add(o);
        }
        return result;
    }

    /// <summary>An array of numbers, at most maxItems long.</summary>
    public IReadOnlyList<double> Numbers(string name, int maxItems)
    {
        var node = Get(name);
        if (node is null) return Array.Empty<double>();
        if (node is not JsonArray array) throw new ToolException($"Argument '{name}' must be a list of numbers.");
        if (array.Count > maxItems) throw new ToolException($"Argument '{name}' may contain at most {maxItems} items.");
        return array.Select((n, i) => n is null
            ? throw new ToolException($"Item {i} of '{name}' must be a number.")
            : ToNumber(n, $"Item {i} of '{name}'")).ToList();
    }

    public static double ToNumber(JsonNode node, string what)
    {
        if (node is JsonValue v)
        {
            if (v.TryGetValue(out double d) && double.IsFinite(d)) return d;
            if (v.TryGetValue(out long l)) return l;
            if (v.TryGetValue(out int i)) return i;
            if (v.TryGetValue(out string? s) && double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out var p) && double.IsFinite(p))
                return p;
        }
        throw new ToolException($"{what} must be a number.");
    }

    /// <summary>A number for output: rounded to 6 decimals; NaN and infinity become null.</summary>
    public static JsonNode? Num(double value) => double.IsFinite(value) ? JsonValue.Create(Math.Round(value, 6)) : null;
}

/// <summary>Runs work in the host application's context (Civil 3D's main thread). Tests run it inline.</summary>
public interface IHostDispatcher
{
    Task<T> InvokeAsync<T>(Func<T> work, CancellationToken cancellationToken);
}

public sealed class InlineDispatcher : IHostDispatcher
{
    public Task<T> InvokeAsync<T>(Func<T> work, CancellationToken cancellationToken)
    {
        try { return Task.FromResult(work()); }
        catch (Exception ex) { return Task.FromException<T>(ex); }
    }
}
