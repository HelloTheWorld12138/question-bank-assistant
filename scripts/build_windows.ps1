$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Venv = Join-Path $Root ".venv-build-win"
$Python = Join-Path $Venv "Scripts\python.exe"
$Dist = Join-Path $Root "dist"
$Build = Join-Path $Root "build\windows"
$AppName = "题搭子"
$InstallerScript = Join-Path $Root "scripts\windows-installer.iss"

Set-Location $Root
& (Join-Path $Root "scripts\download_pandoc.ps1")
& (Join-Path $Root "scripts\download_officecli.ps1")
& (Join-Path $Root "scripts\download_ruby.ps1")
& (Join-Path $Root "scripts\download_webview2.ps1")
py -3.10 -m venv $Venv
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
  --add-data "$(Join-Path $Root 'tools');tools" `
  --add-data "$(Join-Path $Root 'third_party\mathtype_to_mathml');third_party/mathtype_to_mathml" `
  --add-data "$(Join-Path $Root 'third_party\OfficeCLI');licenses/OfficeCLI" `
  --collect-all webview `
  --collect-all keyring `
  --hidden-import app.main `
  --hidden-import keyring.backends.Windows `
  --hidden-import uvicorn.logging `
  --hidden-import uvicorn.loops.auto `
  --hidden-import uvicorn.protocols.http.auto `
  desktop.py

& (Join-Path $Root "scripts\test_windows_bundle.ps1") -Dist $Dist -AppName $AppName

$AppVersion = & $Python -c "from app.config import APP_VERSION; print(APP_VERSION)"
$IsccCandidates = @(
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) }
if (-not $IsccCandidates) {
    throw "未找到 Inno Setup 6。请安装后重新运行：https://jrsoftware.org/isdl.php"
}
$Iscc = $IsccCandidates | Select-Object -First 1
& $Iscc "/DMyAppVersion=$AppVersion" $InstallerScript
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup 未能生成安装包。"
}

Write-Host "Created: $Dist\$AppName-Setup-$AppVersion.exe" -ForegroundColor Green
