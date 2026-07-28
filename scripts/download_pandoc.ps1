$ErrorActionPreference = "Stop"

# Pandoc is kept as a portable build so end users do not need a separate
# installation for Word import/export.  Keep this version in sync with the
# release notes when intentionally upgrading it.
$Version = "3.6.3"
$Asset = "pandoc-$Version-windows-x86_64.zip"
$Root = Split-Path -Parent $PSScriptRoot
$DestinationDirectory = Join-Path $Root "tools\pandoc"
$Destination = Join-Path $DestinationDirectory "pandoc.exe"
$DownloadUrl = "https://github.com/jgm/pandoc/releases/download/$Version/$Asset"

if (Test-Path $Destination) {
    Write-Host "Pandoc is already ready: $Destination"
    return
}

$TemporaryDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("pandoc-" + [guid]::NewGuid())
$Archive = Join-Path $TemporaryDirectory $Asset
New-Item -ItemType Directory -Path $TemporaryDirectory -Force | Out-Null

try {
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $Archive -UseBasicParsing
    Expand-Archive -Path $Archive -DestinationPath $TemporaryDirectory -Force
    $Extracted = Get-ChildItem -Path $TemporaryDirectory -Recurse -Filter "pandoc.exe" |
        Select-Object -First 1
    if (-not $Extracted) {
        throw "Pandoc archive did not contain pandoc.exe."
    }
    New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null
    # Preserve Pandoc's accompanying license and notices in the installed app.
    Copy-Item (Join-Path $Extracted.Directory.FullName "*") $DestinationDirectory -Recurse -Force
}
finally {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $TemporaryDirectory
}

Write-Host "Pandoc $Version downloaded: $Destination"
