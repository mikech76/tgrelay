# =============================================================================
#  Build tgrelay.exe for Windows - single file, no Python needed by user.
#
#  Runs in a clean virtualenv (packaging\venv), so only tgrelay's own
#  dependencies end up in the binary - no IPython/pandas/matplotlib bloat.
#
#  Run from the desktop folder:
#      powershell -ExecutionPolicy Bypass -File packaging\build-windows.ps1
#
#  Result: dist\tgrelay.exe
# =============================================================================
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venv = Join-Path $root 'packaging\venv'
$py = Join-Path $venv 'Scripts\python.exe'

Write-Host "== venv =="
if (-not (Test-Path $py)) {
    python -m venv $venv
}
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r requirements-windows.txt "pyinstaller==6.21.0"

Write-Host "== icon =="
& $py packaging\make_icon.py

Write-Host "== building exe =="
& $py -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name tgrelay `
    --icon "$root\packaging\tgrelay.ico" `
    --add-data "$root\tgrelay.example.txt;." `
    --hidden-import pystray._win32 `
    --specpath packaging --workpath packaging\work --distpath dist `
    main.py

if (-not (Test-Path dist\tgrelay.exe)) {
    Write-Error "dist\tgrelay.exe was not created"
}

$size = [math]::Round((Get-Item dist\tgrelay.exe).Length / 1MB, 1)
Write-Host ""
Write-Host "Done: $root\dist\tgrelay.exe ($size MB)"
Write-Host "Test: copy dist\tgrelay.exe into an empty folder and run it."
