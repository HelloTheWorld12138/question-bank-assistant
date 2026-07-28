$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Venv = Join-Path $Root ".venv-build-win"
$Python = Join-Path $Venv "Scripts\python.exe"
$Dist = Join-Path $Root "dist"
$Build = Join-Path $Root "build\windows"
$AppName = "题搭子"

Set-Location $Root
py -3 -m venv $Venv
& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $Root "requirements-build.txt")

Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $Build $AppName), (Join-Path $Dist $AppName)
& $Python -m PyInstaller --noconfirm --clean --windowed --onedir `
  --name $AppName `
  --icon (Join-Path $Root "assets\tidazi.ico") `
  --distpath $Dist `
  --workpath $Build `
  --specpath $Build `
  --add-data "$(Join-Path $Root 'static');static" `
  --add-data "$(Join-Path $Root 'data');data" `
  --add-data "$(Join-Path $Root 'templates');templates" `
  --collect-all webview `
  --hidden-import app.main `
  --hidden-import uvicorn.logging `
  --hidden-import uvicorn.loops.auto `
  --hidden-import uvicorn.protocols.http.auto `
  desktop.py

Compress-Archive -Path (Join-Path $Dist $AppName) -DestinationPath (Join-Path $Dist "$AppName-Windows.zip") -Force
Write-Host "Created: $Dist\$AppName-Windows.zip" -ForegroundColor Green
