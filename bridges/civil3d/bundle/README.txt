bimai Civil 3D bridge
=====================

Gives your bimai AI team read-only access to the drawing open in Civil 3D, through a local MCP server
on this computer (http://127.0.0.1:27184/mcp). Nothing leaves your computer through the bridge, and
the bridge never changes your drawing.

Supported: Civil 3D 2025, 2026 and 2027 on Windows.

Install (once, needs administrator rights)
  1. Close Civil 3D.
  2. Right-click Start > Terminal (Admin), go to this folder, and run:
       powershell -ExecutionPolicy Bypass -File .\install.ps1
  3. Start Civil 3D, open a drawing and type BIMAIBRIDGE. It should say "running".
  4. In your project folder: bimai connect civil3d

Remove
  powershell -ExecutionPolicy Bypass -File .\uninstall.ps1   (as administrator)

Help and troubleshooting: https://docs.bimai.nl/docs/guides/civil3d-bridge
Log file: %LOCALAPPDATA%\bimai\civil3d-bridge.log
