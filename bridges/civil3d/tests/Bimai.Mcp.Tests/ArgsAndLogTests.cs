using System;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using Bimai.Mcp;
using Xunit;

namespace Bimai.Mcp.Tests;

public sealed class ArgsTests
{
    private static Args A(string json) => new(JsonNode.Parse(json) as JsonObject);

    [Fact]
    public void Strings()
    {
        Assert.Equal("CL-A", A("""{"name":"CL-A"}""").RequiredString("name"));
        Assert.Null(A("{}").OptionalString("name"));
        Assert.Contains("is required", Assert.Throws<ToolException>(() => A("{}").RequiredString("name")).Message);
        Assert.Contains("is required", Assert.Throws<ToolException>(() => A("""{"name":"  "}""").RequiredString("name")).Message);
        Assert.Contains("text value", Assert.Throws<ToolException>(() => A("""{"name":3}""").RequiredString("name")).Message);
    }

    [Fact]
    public void Numbers_accept_numbers_and_numeric_strings()
    {
        Assert.Equal(12.5, A("""{"s":12.5}""").RequiredNumber("s"));
        Assert.Equal(100, A("""{"s":100}""").RequiredNumber("s"));
        Assert.Equal(7.25, A("""{"s":"7.25"}""").RequiredNumber("s"));
        Assert.Null(A("{}").OptionalNumber("s"));
        Assert.Throws<ToolException>(() => A("""{"s":"abc"}""").RequiredNumber("s"));
        Assert.Throws<ToolException>(() => A("""{"s":true}""").RequiredNumber("s"));
    }

    [Fact]
    public void Integers_have_bounds_and_defaults()
    {
        Assert.Equal(200, A("{}").Integer("limit", 200, 1, 2000));
        Assert.Equal(5, A("""{"limit":5}""").Integer("limit", 200, 1, 2000));
        Assert.Contains("between 1 and 2000", Assert.Throws<ToolException>(() => A("""{"limit":0}""").Integer("limit", 200, 1, 2000)).Message);
        Assert.Contains("whole number", Assert.Throws<ToolException>(() => A("""{"limit":2.5}""").Integer("limit", 200, 1, 2000)).Message);
    }

    [Fact]
    public void Booleans()
    {
        Assert.True(A("""{"b":true}""").Boolean("b", false));
        Assert.False(A("{}").Boolean("b", false));
        Assert.Throws<ToolException>(() => A("""{"b":"yes"}""").Boolean("b", false));
    }

    [Fact]
    public void Object_lists_have_a_maximum()
    {
        var points = A("""{"points":[{"x":1,"y":2},{"x":3,"y":4}]}""").Objects("points", 10);
        Assert.Equal(2, points.Count);
        Assert.Contains("at most 1", Assert.Throws<ToolException>(() => A("""{"points":[{},{}]}""").Objects("points", 1)).Message);
        Assert.Contains("must be an object", Assert.Throws<ToolException>(() => A("""{"points":[1]}""").Objects("points", 10)).Message);
        Assert.Contains("is required", Assert.Throws<ToolException>(() => A("{}").Objects("points", 10)).Message);
        Assert.Empty(A("{}").Objects("points", 10, required: false));
    }

    [Fact]
    public void Number_lists()
    {
        Assert.Equal(new[] { 0.0, 20, 40.5 }, A("""{"st":[0,20,40.5]}""").Numbers("st", 10).ToArray());
        Assert.Throws<ToolException>(() => A("""{"st":[0,"x"]}""").Numbers("st", 10));
        Assert.Throws<ToolException>(() => A("""{"st":[1,2,3]}""").Numbers("st", 2));
    }

    [Fact]
    public void Output_numbers_are_rounded_and_never_nan()
    {
        Assert.Equal(1.234568, Args.Num(1.23456789)!.GetValue<double>());
        Assert.Null(Args.Num(double.NaN));
        Assert.Null(Args.Num(double.PositiveInfinity));
    }
}

public sealed class LogTests
{
    [Fact]
    public void File_log_rotates_and_keeps_last_error()
    {
        var dir = Path.Combine(Path.GetTempPath(), "bimai-log-" + Guid.NewGuid().ToString("N"));
        var path = Path.Combine(dir, "bridge.log");
        var log = new FileLog(path, maxBytes: 200);
        for (int i = 0; i < 20; i++) log.Info($"line {i} with some padding text");
        log.Error("port in use", new InvalidOperationException("address already in use"));
        Assert.True(File.Exists(path));
        Assert.True(File.Exists(path + ".1"));
        Assert.True(new FileInfo(path).Length < 1000);
        Assert.Contains("port in use", log.LastError);
        Directory.Delete(dir, recursive: true);
    }

    [Fact]
    public void Log_never_throws_on_an_unwritable_path()
    {
        var log = new FileLog("/dev/null/cannot/write/here.log");
        log.Info("hello");
        log.Error("still fine");
    }
}

public sealed class DecodeTests
{
    [Theory]
    [InlineData("list_layers", "list_layers")]
    [InlineData("=?base64?SGVsbG8sIOS4lueVjA==?=", "Hello, 世界")]
    [InlineData("=?base64?***?=", null)]
    public void Header_values(string raw, string? expected) => Assert.Equal(expected, McpServer.DecodeHeaderValue(raw));
}
