#!/usr/bin/env bash
# Builds the bimai Civil 3D bridge bundle (works on macOS, Linux and in CI; Windows: use build.ps1).
#   dist/bimai-civil3d.bundle/      the plug-in bundle
#   dist/bimai-civil3d-bridge.zip   bundle + install.ps1 + uninstall.ps1 + README.txt, for users
set -euo pipefail
cd "$(dirname "$0")"
DOTNET="${DOTNET:-dotnet}"
CONFIG="${CONFIG:-Release}"

"$DOTNET" build src/Bimai.Civil3D/Bimai.Civil3D.csproj -c "$CONFIG" -nologo -v q

rm -rf dist
BUNDLE=dist/bimai-civil3d.bundle
mkdir -p "$BUNDLE/Contents"
cp bundle/PackageContents.xml "$BUNDLE/"
for tfm in net8.0-windows net10.0-windows; do
  out="src/Bimai.Civil3D/bin/$CONFIG/$tfm"
  mkdir -p "$BUNDLE/Contents/$tfm"
  cp "$out/Bimai.Civil3D.dll" "$out/Bimai.Mcp.dll" "$BUNDLE/Contents/$tfm/"
done

# Every module the manifest names must exist, and no Autodesk assembly may be shipped.
grep -o 'ModuleName="[^"]*"' "$BUNDLE/PackageContents.xml" | sed 's/ModuleName="\.\/\(.*\)"/\1/' | while read -r module; do
  test -f "$BUNDLE/$module" || { echo "missing module: $module" >&2; exit 1; }
done
if find "$BUNDLE" -iname 'ac*mgd.dll' -o -iname 'aec*.dll' | grep -q .; then
  echo "an Autodesk assembly ended up in the bundle" >&2; exit 1
fi

cp install.ps1 uninstall.ps1 dist/
cp bundle/README.txt dist/
(cd dist && rm -f bimai-civil3d-bridge.zip && zip -qr bimai-civil3d-bridge.zip bimai-civil3d.bundle install.ps1 uninstall.ps1 README.txt)
echo "built dist/bimai-civil3d.bundle and dist/bimai-civil3d-bridge.zip"
