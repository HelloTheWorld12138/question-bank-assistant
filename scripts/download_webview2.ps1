$ErrorActionPreference = "Stop"

# pywebview uses Microsoft's Edge WebView2 Runtime on Windows.  The small
# bootstrapper is shipped in the installer and obtains the runtime only when
# a target machine does not already have it.
$Root = Split-Path -Parent $PSScriptRoot
$DestinationDirectory = Join-Path $Root "tools\webview2"
$Destination = Join-Path $DestinationDirectory "MicrosoftEdgeWebView2Setup.exe"
$DownloadUrl = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"

if (Test-Path $Destination) {
    Write-Host "WebView2 bootstrapper is already ready: $Destination"
    return
}

New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null
$Temporary = "$Destination.download"
try {
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $Temporary -UseBasicParsing
    Move-Item $Temporary $Destination -Force
}
finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $Temporary
}

Write-Host "WebView2 bootstrapper downloaded: $Destination"
