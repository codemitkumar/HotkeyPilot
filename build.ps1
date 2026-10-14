# Builds dist\HotkeyPilot\HotkeyPilot.exe and dist\HotkeyPilot-Setup-<version>.exe
param([string]$Version = "")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not $Version) { $Version = (python -c "from version import __version__; print(__version__)").Trim() }

python -m pip install -q -r requirements.txt pyinstaller
if ($LASTEXITCODE) { throw "pip install failed" }

New-Item -ItemType Directory -Force build | Out-Null
python -c "from main import make_icon; make_icon(256).save('build/icon.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
if ($LASTEXITCODE) { throw "icon generation failed" }

python -m PyInstaller main.py --name HotkeyPilot --noconsole --onedir --noconfirm --clean `
    --icon "$PSScriptRoot\build\icon.ico" --hidden-import pystray._win32 `
    --distpath dist --workpath build\pyinstaller --specpath build
if ($LASTEXITCODE) { throw "PyInstaller failed" }

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found. Install it with: winget install JRSoftware.InnoSetup" }
& $iscc /Q "/DAppVersion=$Version" installer\HotkeyPilot.iss
if ($LASTEXITCODE) { throw "Inno Setup failed" }

Write-Host "Built dist\HotkeyPilot-Setup-$Version.exe"
