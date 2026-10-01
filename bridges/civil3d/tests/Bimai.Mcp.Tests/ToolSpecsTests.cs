using System;
using System.Linq;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Bimai.Civil3D;
using Bimai.Mcp;
using Xunit;

namespace Bimai.Mcp.Tests;

public sealed class ToolSpecsTests
{
    [Fact]
    public void All_thirteen_tools_are_defined()
    {
        Assert.Equal(new[]
        {
            "alignment_point", "alignment_station", "count_objects", "get_alignment", "get_drawing", "get_pipe_network",
            "list_alignments", "list_corridors", "list_layers", "list_pipe_networks", "list_surfaces", "profile_elevations",
            "surface_elevations",
        }, ToolSpecs.Names.OrderBy(n => n, StringComparer.Ordinal).ToArray());
    }

    [Fact]
    public void Schemas_are_well_formed()
    {
        foreach (var spec in ToolSpecs.All)
        {
            Assert.Matches(new Regex("^[a-z][a-z0-9_]*$"), spec.Name);
            Assert.False(string.IsNullOrWhiteSpace(spec.Title), spec.Name);
            Assert.True(spec.Description.Length > 40, spec.Name);
            Assert.Equal("object", spec.Schema["type"]!.GetValue<string>());
            Assert.False(spec.Schema["additionalProperties"]!.GetValue<bool>());
            var properties = spec.Schema["properties"]!.AsObject();
            foreach (var required in spec.Schema["required"]?.AsArray() ?? new JsonArray())
                Assert.True(properties.ContainsKey(required!.GetValue<string>()), $"{spec.Name}: required '{required}' not in properties");
            foreach (var (name, schema) in properties)
            {
                Assert.Contains(schema!["type"]!.GetValue<string>(), new[] { "string", "number", "integer", "boolean", "array" });
                Assert.False(string.IsNullOrWhiteSpace(schema["description"]?.GetValue<string>()), $"{spec.Name}.{name}");
            }
        }
    }

    [Fact]
    public void Unit_hint_on_every_tool_that_returns_measurements()
    {
        foreach (var name in new[] { "list_alignments", "get_alignment", "alignment_point", "alignment_station", "profile_elevations",
                                     "list_surfaces", "surface_elevations", "list_corridors", "get_pipe_network" })
            Assert.Contains("drawing units", ToolSpecs.All.Single(s => s.Name == name).Description);
    }

    [Fact]
    public void Pipe_tool_says_inverts_are_not_calculated()
    {
        Assert.Contains("Invert levels are not calculated", ToolSpecs.All.Single(s => s.Name == "get_pipe_network").Description);
    }

    [Fact]
    public void Define_builds_a_registered_tool()
    {
        var tool = ToolSpecs.Define("get_drawing", (_, _) => Task.FromResult(new JsonObject()));
        Assert.Equal("Drawing info", tool.Title);
        Assert.True(tool.ToJson()["annotations"]!["readOnlyHint"]!.GetValue<bool>());
        Assert.Throws<ArgumentException>(() => ToolSpecs.Define("nope", (_, _) => Task.FromResult(new JsonObject())));
    }

    private static Args A(string json) => new(JsonNode.Parse(json) as JsonObject);

    [Fact]
    public void Stations_from_a_list()
    {
        Assert.Equal(new[] { 0.0, 12.5, 100 }, ToolSpecs.ParseStations(A("""{"stations":[0,12.5,100]}""")).ToArray());
    }

    [Fact]
    public void Stations_from_an_interval_include_the_end()
    {
        Assert.Equal(new[] { 0.0, 25, 50, 75, 100 }, ToolSpecs.ParseStations(A("""{"start":0,"end":100,"interval":25}""")).ToArray());
        Assert.Equal(new[] { 0.0, 30, 60, 90, 100 }, ToolSpecs.ParseStations(A("""{"start":0,"end":100,"interval":30}""")).ToArray());
        Assert.Equal(new[] { 50.0 }, ToolSpecs.ParseStations(A("""{"start":50,"end":50,"interval":10}""")).ToArray());
    }

    [Theory]
    [InlineData("""{}""", "Give 'stations'")]
    [InlineData("""{"start":0,"end":100}""", "Give 'stations'")]
    [InlineData("""{"stations":[1],"start":0,"end":1,"interval":1}""", "not both")]
    [InlineData("""{"start":0,"end":100,"interval":0}""", "greater than 0")]
    [InlineData("""{"start":100,"end":0,"interval":10}""", "must not be smaller")]
    [InlineData("""{"start":0,"end":100000,"interval":1}""", "at most 1000")]
    public void Station_errors(string json, string message)
    {
        Assert.Contains(message, Assert.Throws<ToolException>(() => ToolSpecs.ParseStations(A(json))).Message);
    }
}
