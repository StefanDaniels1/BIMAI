# bimai installer for Windows.  Usage (PowerShell):  irm https://docs.bimai.nl/install.ps1 | iex
#   or from Command Prompt:  powershell -ExecutionPolicy ByPass -c "irm https://docs.bimai.nl/install.ps1 | iex"
#
# What it does, for the current user only (no administrator rights, no Python or git needed):
#   1. installs uv (Astral's Python tool manager) into %USERPROFILE%\.local\bin if it isn't there yet
#   2. installs or updates bimai with `uv tool install --upgrade bimai`
#      (uv downloads a suitable Python by itself when none is found)
#   3. makes sure that folder is on your PATH
# Run it again at any time to update bimai. $env:BIMAI_PACKAGE overrides what is installed (a version or a wheel).
$ErrorActionPreference = 'Stop'

function Fail([string]$message) {
    Write-Host "bimai install: $message" -ForegroundColor Red
    # Stop without closing the window when run through `irm | iex`.
    throw $message
}

$package = if ($env:BIMAI_PACKAGE) { $env:BIMAI_PACKAGE } else { 'bimai' }
$localBin = Join-Path $env:USERPROFILE '.local\bin'

$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv -and (Test-Path (Join-Path $localBin 'uv.exe'))) { $uv = Join-Path $localBin 'uv.exe' }
if (-not $uv) {
    Write-Host 'Installing uv (the tool that installs bimai and its Python) into your user folder ...'
    try {
        $installer = Invoke-RestMethod -Uri 'https://astral.sh/uv/install.ps1'
        & ([scriptblock]::Create($installer)) | Out-Null
    } catch {
        Fail "couldn't install uv from astral.sh ($($_.Exception.Message)). Check your internet connection or proxy."
    }
    $uv = Join-Path $localBin 'uv.exe'
    if (-not (Test-Path $uv)) { $uv = (Get-Command uv -ErrorAction SilentlyContinue).Source }
    if (-not $uv) { Fail 'uv was installed but cannot be found. Open a new terminal and run this again.' }
}

Write-Host 'Installing bimai ...'
& $uv tool install --upgrade --quiet $package
if ($LASTEXITCODE -ne 0) { Fail "couldn't install bimai. Check your internet connection or proxy (pypi.org must be reachable)." }
& $uv tool update-shell --quiet *> $null

$bin = (& $uv tool dir --bin 2>$null)
if (-not $bin) { $bin = $localBin }
$bimai = Join-Path $bin 'bimai.exe'
$version = if (Test-Path $bimai) { (& $bimai --version 2>$null) } else { $null }
if (-not $version) { Fail 'bimai was installed but does not start. Please report this at https://github.com/StefanDaniels1/BIMAI/issues' }

# Make `bimai` work in this window too, not only in new ones.
if (($env:Path -split ';') -notcontains $bin) { $env:Path = "$bin;$env:Path" }

Write-Host ''
Write-Host "Done: $version is installed." -ForegroundColor Green
Write-Host 'Next: go to your project folder and run  bimai init'
