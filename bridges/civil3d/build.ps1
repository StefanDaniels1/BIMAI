# Builds the bimai Civil 3D bridge bundle on Windows (macOS/Linux/CI: build.sh).
#   dist\bimai-civil3d.bundle\      the plug-in bundle
#   dist\bimai-civil3d-bridge.zip   bundle + install.ps1 + uninstall.ps1 + README.txt, for users
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$config = if ($env:CONFIG) { $env:CONFIG } else { 'Release' }

dotnet build src\Bimai.Civil3D\Bimai.Civil3D.csproj -c $config -nologo -v q
if ($LASTEXITCODE -ne 0) { throw 'build failed' }

if (Test-Path dist) { Remove-Item dist -Recurse -Force }
$bundle = 'dist\bimai-civil3d.bundle'
New-Item -ItemType Directory -Force "$bundle\Contents" | Out-Null
Copy-Item bundle\PackageContents.xml $bundle
foreach ($tfm in 'net8.0-windows', 'net10.0-windows') {
    $out = "src\Bimai.Civil3D\bin\$config\$tfm"
    New-Item -ItemType Directory -Force "$bundle\Contents\$tfm" | Out-Null
    Copy-Item "$out\Bimai.Civil3D.dll", "$out\Bimai.Mcp.dll" "$bundle\Contents\$tfm"
}

# Every module the manifest names must exist, and no Autodesk assembly may be shipped.
[xml]$manifest = Get-Content "$bundle\PackageContents.xml"
foreach ($entry in $manifest.ApplicationPackage.Components.ComponentEntry) {
    $module = Join-Path $bundle ($entry.ModuleName -replace '^\./', '' -replace '/', '\')
    if (-not (Test-Path $module)) { throw "missing module: $module" }
}
if (Get-ChildItem $bundle -Recurse -Include 'ac*mgd.dll', 'aec*.dll') { throw 'an Autodesk assembly ended up in the bundle' }

Copy-Item install.ps1, uninstall.ps1, bundle\README.txt dist
Compress-Archive -Path "$bundle", 'dist\install.ps1', 'dist\uninstall.ps1', 'dist\README.txt' -DestinationPath 'dist\bimai-civil3d-bridge.zip' -Force
Write-Host 'built dist\bimai-civil3d.bundle and dist\bimai-civil3d-bridge.zip'
