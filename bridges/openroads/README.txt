bimai OpenRoads bridge (beta)
=============================

A read-only add-in for Bentley OpenRoads Designer (2023 or newer, Windows) that lets Claude Code read the
open drawing: alignments, profiles, corridors and terrains. https://docs.bimai.nl/docs/guides/openroads-bridge

Install it with bimai, which builds it on your PC against your OpenRoads Designer:

    bimai bridge install openroads

What happens:
- bimai compiles src\*.cs with the C# compiler of Windows' .NET Framework 4.8
  (C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe), referencing Bentley.MstnPlatformNET.dll from
  your OpenRoads Designer folder. Bentley's assemblies are not included here; they can't be redistributed.
- The result, BimaiOpenRoads.dll, goes into C:\ProgramData\bimai\openroads\<your version>\.
- One file, config\appl\bimai-openroads.cfg in your OpenRoads Designer folder, makes OpenRoads load it at
  startup (Bentley's documented way: MS_ADDINPATH and MS_DGNAPPS). Writing it needs Windows' permission once.

The bridge listens on http://127.0.0.1:27185/mcp (this computer only) and never changes the drawing.
Log: %LOCALAPPDATA%\bimai\openroads-bridge.log. Load it by hand with the key-in: mdl load BimaiOpenRoads
Remove it with: bimai bridge uninstall openroads
