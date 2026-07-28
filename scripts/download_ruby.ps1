$ErrorActionPreference = "Stop"

# The MathType converter is a local Ruby program.  Bundle a private Ruby
# runtime so teachers do not have to install Ruby or modify PATH themselves.
$Version = "3.3.7-1"
$Asset = "rubyinstaller-$Version-x64.exe"
$Root = Split-Path -Parent $PSScriptRoot
$DestinationDirectory = Join-Path $Root "tools\ruby"
$Ruby = Join-Path $DestinationDirectory "bin\ruby.exe"
$DownloadUrl = "https://github.com/oneclick/rubyinstaller2/releases/download/RubyInstaller-$Version/$Asset"

if (Test-Path $Ruby) {
    Write-Host "Bundled Ruby is already ready: $Ruby"
    return
}

$TemporaryDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("rubyinstaller-" + [guid]::NewGuid())
$Installer = Join-Path $TemporaryDirectory $Asset
New-Item -ItemType Directory -Path $TemporaryDirectory -Force | Out-Null

try {
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $Installer -UseBasicParsing
    New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null
    $process = Start-Process -FilePath $Installer -ArgumentList @(
        "/verysilent",
        "/suppressmsgboxes",
        "/norestart",
        "/dir=`"$DestinationDirectory`""
    ) -Wait -PassThru
    if ($process.ExitCode -ne 0 -or -not (Test-Path $Ruby)) {
        throw "Ruby runtime installation failed."
    }
    # This is an application-private runtime, not a separately uninstallable app.
    Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $DestinationDirectory "unins000.exe"), (Join-Path $DestinationDirectory "unins000.dat")
}
finally {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $TemporaryDirectory
}

Write-Host "Ruby $Version downloaded: $Ruby"
