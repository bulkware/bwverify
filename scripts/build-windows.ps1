$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Keep every generated artifact beneath the checkout's Windows build directory.
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$buildRoot = Join-Path $projectRoot "build\windows"
$distPath = Join-Path $buildRoot "dist"
$workPath = Join-Path $buildRoot "work"
$specPath = Join-Path $buildRoot "spec"
$installerPath = Join-Path $buildRoot "installer"
$iconPath = Join-Path $projectRoot "data\icons\bwverify.ico"
$entryPoint = Join-Path $projectRoot "src\bwverify\bwverify.py"
$applicationIconPath = Join-Path $projectRoot "src\bwverify\icons"
$projectMetadataPath = Join-Path $projectRoot "pyproject.toml"
$installerScript = Join-Path $projectRoot "packaging\windows\bwverify.nsi"
$gtkPrefix = "C:\gtk"
$gtkBinPath = Join-Path $gtkPrefix "bin"
$gtkTypelibPath = Join-Path $gtkPrefix "lib\girepository-1.0"

# Read the installer version from the same project metadata used by other packages.
$projectMetadata = Get-Content -Raw $projectMetadataPath
$versionMatch = [regex]::Match(
    $projectMetadata,
    '(?m)^version\s*=\s*"(?<version>[^"]+)"'
)
if (-not $versionMatch.Success) {
    throw "Unable to determine the version from pyproject.toml."
}
$version = $versionMatch.Groups["version"].Value

# The prebuilt gvsbuild archive supplies the GTK runtime used by the package.
foreach ($requiredPath in @($gtkBinPath, $gtkTypelibPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Container)) {
        throw "Required GTK directory was not found: $requiredPath"
    }
}
if (-not (Test-Path -LiteralPath $applicationIconPath -PathType Container)) {
    throw "Required application icon directory was not found: $applicationIconPath"
}

# Keep application SVGs beside the bundled package for importlib.resources().
$applicationIconData = "$applicationIconPath;bwverify\icons"

# Start from a clean, self-contained PyInstaller staging area.
Remove-Item -Recurse -Force $buildRoot -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath $buildRoot) {
    throw (
        "Cannot clean $buildRoot. Close bwVerify.exe and any File Explorer window " +
        "open in the previous build directory, then run the build again."
    )
}
New-Item -ItemType Directory -Force -Path $distPath, $workPath, $specPath, $installerPath | Out-Null

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name bwVerify `
    --paths (Join-Path $projectRoot "src") `
    --add-data $applicationIconData `
    --icon $iconPath `
    --distpath $distPath `
    --workpath $workPath `
    --specpath $specPath `
    $entryPoint
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed."
}

# PyInstaller's GI hook can omit Gtk 4 typelibs from a gvsbuild installation.
# Copy the GTK runtime explicitly so the portable folder works without C:\gtk.
$runtimePath = Join-Path $distPath "bwVerify\_internal"
$typelibDestination = Join-Path $runtimePath "gi_typelibs"
New-Item -ItemType Directory -Force -Path $typelibDestination | Out-Null
Copy-Item -Path (Join-Path $gtkTypelibPath "*") -Destination $typelibDestination `
    -Recurse -Force
Copy-Item -Path (Join-Path $gtkBinPath "*.dll") -Destination $runtimePath -Force

# Image loaders and GTK modules are loaded dynamically rather than imported by Python.
foreach ($runtimeDirectory in @("gdk-pixbuf-2.0", "gtk-4.0")) {
    $sourcePath = Join-Path $gtkPrefix "lib\$runtimeDirectory"
    if (Test-Path -LiteralPath $sourcePath -PathType Container) {
        $destinationPath = Join-Path $runtimePath "lib\$runtimeDirectory"
        New-Item -ItemType Directory -Force -Path $destinationPath | Out-Null
        Copy-Item -Path (Join-Path $sourcePath "*") -Destination $destinationPath `
            -Recurse -Force
    }
}

# GTK resolves symbolic icon names from the installed icon theme at runtime.
$gtkIconsPath = Join-Path $gtkPrefix "share\icons"
if (Test-Path -LiteralPath $gtkIconsPath -PathType Container) {
    $iconDestination = Join-Path $runtimePath "share\icons"
    New-Item -ItemType Directory -Force -Path $iconDestination | Out-Null
    Copy-Item -Path (Join-Path $gtkIconsPath "*") -Destination $iconDestination `
        -Recurse -Force
}

# NSIS is optional: without it, retain the portable PyInstaller distribution.
$nsisCommand = Get-Command makensis.exe -ErrorAction SilentlyContinue
if ($null -eq $nsisCommand) {
    $nsisCommand = Get-Command makensis -ErrorAction SilentlyContinue
}
$nsisPath = if ($null -ne $nsisCommand) { $nsisCommand.Path } else { $null }

# NSIS's normal installer path is not always added to the Windows PATH variable.
if ($null -eq $nsisPath) {
    foreach ($candidatePath in @(
        "C:\Program Files (x86)\NSIS\makensis.exe",
        "C:\Program Files\NSIS\makensis.exe"
    )) {
        if (Test-Path -LiteralPath $candidatePath -PathType Leaf) {
            $nsisPath = $candidatePath
            break
        }
    }
}

if ($null -eq $nsisPath) {
    Write-Warning "NSIS was not found. The portable distribution is $distPath\bwVerify."
    exit 0
}

# Pass build locations explicitly so the installer never relies on its working directory.
$nsisArguments = @(
    "/DVERSION=$version",
    "/DAPP_DIR=$distPath\bwVerify",
    "/DOUT_DIR=$installerPath",
    $installerScript
)
& $nsisPath @nsisArguments
if ($LASTEXITCODE -ne 0) {
    throw "NSIS failed."
}

Write-Host "Portable distribution: $distPath\bwVerify"
Write-Host "Installer: $installerPath\bwverify-$version-setup.exe"
