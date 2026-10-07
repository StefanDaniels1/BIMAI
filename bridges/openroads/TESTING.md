# Testing the bimai OpenRoads bridge (beta)

Thank you for trying this. The bridge was written from Bentley's OpenRoads Designer SDK documentation and
has been tested everywhere **except inside OpenRoads Designer itself**. These steps take about 20 minutes and
tell us exactly what works. You don't need to know programming.

You need: a Windows PC with **OpenRoads Designer 2023 or newer**, a drawing with at least one alignment
(ideally with a profile, a corridor and a terrain), and permission to approve one Windows prompt (or IT
nearby).

## 1. Install bimai and the bridge (5 minutes)

Close OpenRoads Designer. Open **PowerShell** (not as administrator) and run:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://docs.bimai.nl/install.ps1 | iex"
```

Close and reopen PowerShell, then:

```powershell
bimai --version
bimai bridge install openroads
```

Windows asks once for permission; click **Yes**. Expected: `✓ OpenRoads Designer (bimai bridge, read-only,
beta) installed for OpenRoads Designer 20xx`.

**If it fails:** copy the whole output. Most likely it says the bridge didn't compile and lists errors;
those lines are exactly what we need.

## 2. Does OpenRoads load it? (5 minutes)

Start OpenRoads Designer and open your drawing. Then in PowerShell:

```powershell
bimai bridge status openroads
Get-Content "$env:LOCALAPPDATA\bimai\openroads-bridge.log" -Tail 20
```

Expected: `running: yes`, and the log shows `MCP server listening on http://127.0.0.1:27185/mcp`.

**If `running: no` and there's no log:** OpenRoads didn't load the bridge automatically. In OpenRoads, open
the key-in window (**Utilities → Key-in**, or press Enter in the drawing) and type:

```
mdl load C:\ProgramData\bimai\openroads\<your version folder>\BimaiOpenRoads.dll
```

(The folder name is shown by `dir C:\ProgramData\bimai\openroads`.) Then check `bimai bridge status openroads`
again. Tell us whether the manual load worked; that tells us whether only the automatic loading needs a fix.

## 3. Ask the bridge directly (5 minutes)

With OpenRoads open and the drawing loaded, paste this into PowerShell. It calls every tool once and saves
the answers to a file:

```powershell
$url = "http://127.0.0.1:27185/mcp"
function Call($name, $arguments) {
  $body = @{ jsonrpc = "2.0"; id = 1; method = "tools/call"; params = @{ name = $name; arguments = $arguments } } | ConvertTo-Json -Depth 10
  try { (Invoke-RestMethod -Uri $url -Method Post -ContentType "application/json" -Body $body).result | ConvertTo-Json -Depth 20 }
  catch { "ERROR: $($_.Exception.Message)" }
}
$out = "$env:USERPROFILE\Desktop\bimai-openroads-test.txt"
"== get_drawing_info"  | Out-File $out
Call "get_drawing_info" @{} | Out-File $out -Append
"== list_alignments"  | Out-File $out -Append
$alignments = Call "list_alignments" @{}
$alignments | Out-File $out -Append
"== list_corridors"   | Out-File $out -Append
Call "list_corridors" @{} | Out-File $out -Append
"== list_terrains"    | Out-File $out -Append
Call "list_terrains" @{} | Out-File $out -Append
Write-Host "Saved to $out"
```

Then, with the name of one of your alignments (replace `My alignment`) and a point near it (replace the
coordinates with real ones from your drawing):

```powershell
$a = "My alignment"; $x = 155000.0; $y = 463000.0
"== get_alignment"         | Out-File $out -Append; Call "get_alignment" @{ alignment = $a; interval = 50 } | Out-File $out -Append
"== list_profiles"         | Out-File $out -Append; Call "list_profiles" @{ alignment = $a } | Out-File $out -Append
"== get_profile"           | Out-File $out -Append; Call "get_profile" @{ alignment = $a } | Out-File $out -Append
"== locate_on_alignment"   | Out-File $out -Append; Call "locate_on_alignment" @{ alignment = $a; x = $x; y = $y } | Out-File $out -Append
"== get_terrain_elevation" | Out-File $out -Append; Call "get_terrain_elevation" @{ x = $x; y = $y } | Out-File $out -Append
Write-Host "Saved to $out"
```

Please compare a few values with what OpenRoads shows you:
- an alignment's **length** and **start/end station**,
- a profile's **vertical intersection points** (station and elevation),
- the **station and offset** of your point (use OpenRoads' station/offset readout on the same point),
- the **terrain elevation** at that point.

Are the numbers in metres? Do the stations look like OpenRoads' own?

## 4. With Claude Code (optional, 5 minutes)

In a project folder: `bimai init` (choose OpenRoads as a tool), then `bimai connect openroads`, start a new
Claude Code session and ask for example *"Which alignments are in my drawing, and how long are they?"*

## 5. Send us

- the output of step 1 (especially if something failed),
- `bimai bridge status openroads` and the log (`%LOCALAPPDATA%\bimai\openroads-bridge.log`),
- the file `bimai-openroads-test.txt` from your desktop,
- your OpenRoads Designer version (**Help → About**), and which values matched or didn't.

Open an issue at https://github.com/StefanDaniels1/BIMAI/issues (or send it to the person who asked you).
The file contains names and coordinates from your drawing; remove anything confidential first.

To remove everything afterwards: `bimai bridge uninstall openroads`.
