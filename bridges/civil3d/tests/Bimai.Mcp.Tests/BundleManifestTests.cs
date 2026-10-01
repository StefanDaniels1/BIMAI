using System;
using System.IO;
using System.Linq;
using System.Xml.Linq;
using Xunit;

namespace Bimai.Mcp.Tests;

public sealed class BundleManifestTests
{
    private static string Root()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && !File.Exists(Path.Combine(dir.FullName, "bundle", "PackageContents.xml"))) dir = dir.Parent;
        return dir?.FullName ?? throw new InvalidOperationException("bridges/civil3d not found");
    }

    [Fact]
    public void Manifest_matches_the_add_in_builds_and_supported_versions()
    {
        var root = Root();
        var manifest = XDocument.Load(Path.Combine(root, "bundle", "PackageContents.xml")).Root!;
        Assert.Equal("ApplicationPackage", manifest.Name.LocalName);
        Assert.Equal("AutoCAD", manifest.Attribute("AutodeskProduct")!.Value);
        Assert.NotNull(manifest.Attribute("ProductCode"));
        Assert.NotNull(manifest.Attribute("UpgradeCode"));

        var components = manifest.Elements("Components").ToList();
        Assert.Equal(2, components.Count);
        Assert.Empty(manifest.Descendants("Commands"));          // would switch to load-on-command

        var expected = new[] { ("net8.0-windows", "R25.0", "R25.1"), ("net10.0-windows", "R26.0", "R26.0") };
        var csproj = XDocument.Load(Path.Combine(root, "src", "Bimai.Civil3D", "Bimai.Civil3D.csproj"));
        var tfms = csproj.Descendants("TargetFrameworks").Single().Value.Split(';');
        Assert.Equal(expected.Select(e => e.Item1).OrderBy(t => t), tfms.OrderBy(t => t));

        foreach (var (tfm, min, max) in expected)
        {
            var c = components.Single(x => x.Element("ComponentEntry")!.Attribute("ModuleName")!.Value.Contains("/" + tfm + "/"));
            var req = c.Element("RuntimeRequirements")!;
            Assert.Equal("Civil3D", req.Attribute("Platform")!.Value);
            Assert.Equal("Win64", req.Attribute("OS")!.Value);
            Assert.Equal(min, req.Attribute("SeriesMin")!.Value);
            Assert.Equal(max, req.Attribute("SeriesMax")!.Value);
            var entry = c.Element("ComponentEntry")!;
            Assert.Equal($"./Contents/{tfm}/Bimai.Civil3D.dll", entry.Attribute("ModuleName")!.Value);
            Assert.False(string.IsNullOrEmpty(entry.Attribute("AppName")!.Value));
            Assert.Null(entry.Attribute("LoadOnCommandInvocation"));
        }
    }

    [Fact]
    public void Manifest_version_matches_the_build_version()
    {
        var root = Root();
        var manifest = XDocument.Load(Path.Combine(root, "bundle", "PackageContents.xml")).Root!;
        var props = XDocument.Load(Path.Combine(root, "Directory.Build.props"));
        Assert.Equal(props.Descendants("Version").Single().Value, manifest.Attribute("AppVersion")!.Value);
    }
}
