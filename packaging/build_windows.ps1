# Build the branded Spotify Perpetual.exe on Windows.
#
# Run from the repo root in PowerShell:
#     .\packaging\build_windows.ps1
#
# Output: dist\Spotify Perpetual.exe (single file, no console, runs the tray).

$ErrorActionPreference = "Stop"
$py = ".\.venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Error "No venv at .\.venv. Create one and 'pip install -e .[tray]' first."
}

Write-Host "Installing build dependencies..."
& $py -m pip install -e ".[tray,build]"

Write-Host "Building exe..."
& $py -m PyInstaller packaging\Spotify-Perpetual.spec --noconfirm --clean

$exe = "dist\Spotify Perpetual.exe"
if (Test-Path $exe) {
    Write-Host "Done: $exe"
    Write-Host "First run: open a terminal and run  & '.\$exe' setup   then  & '.\$exe' auth"
} else {
    Write-Error "Build finished but $exe not found."
}
