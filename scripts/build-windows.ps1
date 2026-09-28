$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Build matching portable ZIP and MSI artifacts from the cx_Freeze configuration.
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$buildRoot = Join-Path $projectRoot "build\windows"
$frozenPath = Join-Path $buildRoot "bwVerify"
$installerPath = Join-Path $buildRoot "installer"
$runtimePath = Join-Path $buildRoot "gtk-runtime"
$metadataPath = Join-Path $projectRoot "pyproject.toml"
$gtkPrefix = if ($env:GTK_PREFIX) { $env:GTK_PREFIX } else { "C:\gtk" }
$metadata = Get-Content -Raw $metadataPath
$versionMatch = [regex]::Match($metadata, '(?m)^version\s*=\s*"(?<version>[^"]+)"')
if (-not $versionMatch.Success) {
    throw "Unable to determine the version from pyproject.toml."
}
$version = $versionMatch.Groups["version"].Value

# Stage GTK where cx_Freeze can include it in both artifact formats.
function Copy-GtkDirectory {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath
    )

    $sourcePath = Join-Path $gtkPrefix $RelativePath
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Container)) {
        throw "Required GTK directory was not found: $sourcePath"
    }
    $destinationPath = Join-Path $runtimePath $RelativePath
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destinationPath) | Out-Null
    Copy-Item -Path $sourcePath -Destination $destinationPath -Recurse -Force
}

Remove-Item -Recurse -Force $buildRoot -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $runtimePath | Out-Null

# GTK loads typelibs, modules, schemas, and icon themes dynamically at runtime.
foreach ($directory in @(
    "bin",
    "lib\girepository-1.0",
    "lib\gdk-pixbuf-2.0",
    "lib\gtk-4.0",
    "share\glib-2.0\schemas",
    "share\icons"
)) {
    Copy-GtkDirectory $directory
}

# Make the staged GTK libraries discoverable while cx_Freeze imports PyGObject.
$gtkBinPath = Join-Path $gtkPrefix "bin"
$env:PATH = "$gtkBinPath$([IO.Path]::PathSeparator)$env:PATH"
$env:PYGI_DLL_PATH = $gtkBinPath

# Install cx_Freeze and the local package into the environment that already has PyGObject.
python -m pip install --upgrade ".[release]"
if ($LASTEXITCODE -ne 0) {
    throw "Windows build dependency installation failed."
}

cxfreeze build
if ($LASTEXITCODE -ne 0) {
    throw "cx_Freeze portable build failed."
}
if (-not (Test-Path -LiteralPath $frozenPath -PathType Container)) {
    throw "cx_Freeze did not produce the expected portable directory: $frozenPath"
}

$portableArchive = Join-Path $buildRoot "bwverify-$version-win64-portable.zip"
Compress-Archive -Path $frozenPath -DestinationPath $portableArchive -Force

cxfreeze bdist_msi
if ($LASTEXITCODE -ne 0) {
    throw "cx_Freeze MSI build failed."
}
if (-not (Test-Path -LiteralPath $installerPath -PathType Container)) {
    throw "cx_Freeze did not produce the expected MSI directory: $installerPath"
}

Write-Host "Portable archive: $portableArchive"
Get-ChildItem -LiteralPath $installerPath -Filter "*.msi" | ForEach-Object {
    Write-Host "MSI: $($_.FullName)"
}
