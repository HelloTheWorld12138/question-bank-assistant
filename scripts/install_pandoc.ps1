$ErrorActionPreference = "Stop"

$Version = "3.10.1"
$AssetName = "pandoc-$Version-windows-x86_64.zip"
$ExpectedSha256 = "4725a1883e2171c2e181e6fd45003acb59ca4e9cbe031fdd3b79ef0d697d36aa"
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

$Headers = @{ "User-Agent" = "Question-Bank-Assistant-Packager" }
$DownloadUrl = "https://github.com/jgm/pandoc/releases/download/$Version/$AssetName"
$Zip = Join-Path $TempDir $AssetName
Write-Host "Downloading $AssetName"
Invoke-WebRequest -Headers $Headers -Uri $DownloadUrl -OutFile $Zip

$ActualHash = (Get-FileHash -Algorithm SHA256 $Zip).Hash.ToLowerInvariant()
if ($ActualHash -ne $ExpectedSha256) {
  Remove-Item $Zip -Force
  throw "Pandoc checksum verification failed."
}

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
