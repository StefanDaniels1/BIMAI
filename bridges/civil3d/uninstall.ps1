#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Removes the bimai Civil 3D bridge.
  Run from an elevated PowerShell:  powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
#>
$ErrorActionPreference = 'Stop'
if (Get-Process -Name acad -ErrorAction SilentlyContinue) {
    throw 'Civil 3D (acad.exe) is running. Close Civil 3D first, then run this script again.'
}
$target = Join-Path $env:ProgramFiles 'Autodesk\ApplicationPlugins\bimai-civil3d.bundle'
if (Test-Path $target) {
    Remove-Item $target -Recurse -Force
    Write-Host "Removed: $target"
} else {
    Write-Host 'The bimai Civil 3D bridge is not installed.'
}
Write-Host 'In your project you can also run:  bimai disconnect civil3d'
