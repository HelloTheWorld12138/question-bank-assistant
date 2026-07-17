$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$PandocExe = Join-Path $Root "tools\pandoc\pandoc.exe"

if (Test-Path $PandocExe) {
  Write-Host "Pandoc already exists: $PandocExe"
  exit 0
}

$SystemPandoc = Get-Command "pandoc" -ErrorAction SilentlyContinue
if ($SystemPandoc) {
  Write-Host "System Pandoc found: $($SystemPandoc.Source)"
  exit 0
}

$ToolsDir = Join-Path $Root "tools"
$TempDir = Join-Path $ToolsDir "pandoc-download"
$PandocDir = Join-Path $ToolsDir "pandoc"

New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null
New-Item -ItemType Directory -Force -Path $TempDir | Out-Null

$Headers = @{ "User-Agent" = "WhiteCaps-Pandoc-Installer" }
$Release = Invoke-RestMethod -Headers $Headers -Uri "https://api.github.com/repos/jgm/pandoc/releases/latest"
$Asset = $Release.assets | Where-Object { $_.name -match "windows-x86_64\.zip$" } | Select-Object -First 1

if (-not $Asset) {
  throw "Cannot find Pandoc Windows x86_64 zip asset."
}

$Zip = Join-Path $TempDir $Asset.name
Write-Host "Downloading $($Asset.name)"
Invoke-WebRequest -Headers $Headers -Uri $Asset.browser_download_url -OutFile $Zip

if (Test-Path $PandocDir) {
  Remove-Item -Recurse -Force $PandocDir
}

Expand-Archive -Path $Zip -DestinationPath $TempDir -Force
$Expanded = Get-ChildItem $TempDir -Directory | Where-Object { $_.Name -like "pandoc-*" } | Select-Object -First 1

if (-not $Expanded) {
  throw "Cannot find expanded Pandoc directory."
}

Move-Item -Path $Expanded.FullName -Destination $PandocDir
Remove-Item -Recurse -Force $TempDir

& $PandocExe --version | Select-Object -First 1
