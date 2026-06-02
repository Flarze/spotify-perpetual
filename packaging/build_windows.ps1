# Build the branded Spotify Perpetual.exe and its installer on Windows.
#
# Run from the repo root in PowerShell:
#     .\packaging\build_windows.ps1
#
# Outputs:
#   dist\Spotify Perpetual.exe       single file, no console, runs the tray
#   dist\SpotifyPerpetualSetup.exe   double-click installer (if Inno Setup found)
#
# The installer step needs Inno Setup's ISCC.exe (https://jrsoftware.org/isdl.php).
# If it is not found the script still builds the exe and just skips the installer.

$ErrorActionPreference = "Stop"
$py = ".\.venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Error "No venv at .\.venv. Create one and 'pip install -e .[tray]' first."
}

# A running instance locks dist\Spotify Perpetual.exe and breaks the rebuild.
Write-Host "Stopping any running Spotify Perpetual..."
Stop-Process -Name "Spotify Perpetual" -Force -ErrorAction SilentlyContinue

Write-Host "Installing build dependencies..."
& $py -m pip install -e ".[tray,build,smtc]"

Write-Host "Building exe..."
& $py -m PyInstaller packaging\Spotify-Perpetual.spec --noconfirm --clean

# One-dir build: the exe lives inside dist\Spotify Perpetual\.
$exe = "dist\Spotify Perpetual\Spotify Perpetual.exe"
if (-not (Test-Path $exe)) {
    Write-Error "Build finished but $exe not found."
}
Write-Host "Built: $exe"

# Compile the installer if Inno Setup's ISCC.exe is available.
Write-Host "Looking for Inno Setup (ISCC.exe)..."
$iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    foreach ($p in @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )) {
        if (Test-Path $p) { $iscc = $p; break }
    }
}

if ($iscc) {
    Write-Host "Building installer with $iscc ..."
    & $iscc "packaging\installer.iss"
    $setup = "dist\SpotifyPerpetualSetup.exe"
    if (Test-Path $setup) {
        Write-Host "Done: $setup  (give this to users - double-click to install)"
    } else {
        Write-Error "ISCC ran but $setup not found."
    }
} else {
    Write-Host "Inno Setup not found; skipped installer."
    Write-Host "Install it from https://jrsoftware.org/isdl.php, then re-run this script."
    Write-Host "App folder is ready: dist\Spotify Perpetual\"
}
