#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Installs the bimai Civil 3D bridge for every user of this computer.
.DESCRIPTION
  Copies bimai-civil3d.bundle to C:\Program Files\Autodesk\ApplicationPlugins. Civil 3D always trusts
  that folder, so the bridge loads at startup without security warnings (also with SECURELOAD = 2).
  Run from an elevated PowerShell:  powershell -ExecutionPolicy Bypass -File .\install.ps1
#>
param(
    [string]$Bundle = (Join-Path $PSScriptRoot 'bimai-civil3d.bundle')
)
$ErrorActionPreference = 'Stop'

if (-not (Test-Path (Join-Path $Bundle 'PackageContents.xml'))) {
    throw "No bundle found at '$Bundle'. Run this script from the unzipped bimai-civil3d-bridge folder."
}
if (Get-Process -Name acad -ErrorAction SilentlyContinue) {
    throw 'Civil 3D (acad.exe) is running. Close Civil 3D first, then run this script again.'
}

$plugins = Join-Path $env:ProgramFiles 'Autodesk\ApplicationPlugins'
$target = Join-Path $plugins 'bimai-civil3d.bundle'
New-Item -ItemType Directory -Force $plugins | Out-Null
if (Test-Path $target) { Remove-Item $target -Recurse -Force }
Copy-Item $Bundle $target -Recurse

# Files downloaded from the internet carry a "blocked" mark that stops .NET assemblies from loading.
Get-ChildItem $target -Recurse -File | Unblock-File

Write-Host ''
Write-Host "Installed: $target"
Write-Host 'Next:'
Write-Host '  1. Start Civil 3D and open a drawing. Type BIMAIBRIDGE to check that the bridge is running.'
Write-Host '  2. In your project folder, run:  bimai connect civil3d'
