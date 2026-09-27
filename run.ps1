param(
    [switch]$InstallRepository,
    [switch]$UpdateDependencies,
    [switch]$SetupOnly,
    [string]$Python,
    [string]$ProjectDirectory = $PSScriptRoot
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Repository = 'https://github.com/CarlFriGauss/clipharbor.git'
$BootstrapRoot = if ($env:CLIPHARBOR_BOOTSTRAP_DIR) { $env:CLIPHARBOR_BOOTSTRAP_DIR } else { Join-Path $env:LOCALAPPDATA 'ClipHarbor\bootstrap' }
$BootstrapRoot = [IO.Path]::GetFullPath($BootstrapRoot)
$ToolsPrefix = Join-Path $BootstrapRoot 'tools'
$Manager = Join-Path $BootstrapRoot 'helper-2.9.0\micromamba.exe'
$OriginalPath = $env:PATH
$OriginalPythonPath = $env:PYTHONPATH
$OriginalPythonHome = $env:PYTHONHOME

function Use-LocalTools {
    $env:PATH = "$ToolsPrefix;$ToolsPrefix\Library\bin;$ToolsPrefix\Scripts;$ToolsPrefix\bin;$OriginalPath"
}
function Test-Tool([string]$Name, [string[]]$Arguments) {
    if (-not (Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue)) { return $false }
    try { $null = & $Name @Arguments 2>&1; return $LASTEXITCODE -eq 0 } catch { return $false }
}
function Install-Missing([string[]]$Packages) {
    $Expected = 'a6d804394b2418991c4e29562853eaace2f2ce9d9da661a98e74e02e8dbb44b0'
    if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64' -and $env:PROCESSOR_ARCHITEW6432 -ne 'AMD64') {
        throw 'Automatic setup currently supports Windows x64. Use manual source setup on other architectures.'
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Manager) | Out-Null
    if (-not (Test-Path -LiteralPath $Manager) -or (Get-FileHash -LiteralPath $Manager -Algorithm SHA256).Hash -ne $Expected) {
        Write-Host 'Downloading the setup helper...'
        $Partial = "$Manager.$PID.download"
        try {
            Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/mamba-org/micromamba-releases/releases/download/2.9.0-0/micromamba-win-64.exe' -OutFile $Partial
            if ((Get-FileHash -LiteralPath $Partial -Algorithm SHA256).Hash -ne $Expected) { throw 'Setup helper checksum did not match. Nothing will be executed.' }
            Move-Item -LiteralPath $Partial -Destination $Manager -Force
        } finally { if (Test-Path -LiteralPath $Partial) { Remove-Item -LiteralPath $Partial } }
    }
    Write-Host 'Installing missing components locally. Existing system installations are not changed.'
    $Action = if (Test-Path -LiteralPath (Join-Path $ToolsPrefix 'conda-meta/history')) { 'install' } else { 'create' }
    & $Manager --no-rc --root-prefix (Join-Path $BootstrapRoot 'cache') $Action --yes --prefix $ToolsPrefix --override-channels --channel conda-forge @Packages | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Component setup failed. Check your connection and rerun to retry.' }
    Use-LocalTools
}
function Find-Python {
    $Candidates = @()
    if ($Python) { $Candidates += $Python }
    $Candidates += (Join-Path $ToolsPrefix 'python.exe')
    if ($env:CONDA_PREFIX) { $Candidates += (Join-Path $env:CONDA_PREFIX 'python.exe') }
    $Candidates += 'python'
    foreach ($Candidate in $Candidates) {
        $Found = Get-Command $Candidate -CommandType Application -ErrorAction SilentlyContinue
        if (-not $Found -or $Found.Source -like '*WindowsApps*') { continue }
        if (Test-Tool $Found.Source @('-c', 'import sys, venv, ensurepip, tkinter; assert sys.version_info >= (3,10)')) { return $Found.Source }
    }
    return $null
}
try {
    # Process-local changes only: no shell profiles or global environment edits.
    Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue
    Remove-Item Env:\PYTHONHOME -ErrorAction SilentlyContinue
    Use-LocalTools
    Write-Host 'Checking ClipHarbor setup...'
    if (-not (Test-Tool 'git' @('--version'))) { Install-Missing @('git') }
    if ($InstallRepository) {
        $ProjectDirectory = Join-Path $BootstrapRoot 'source'
        if (Test-Path -LiteralPath $ProjectDirectory) {
            $Remote = & git -C $ProjectDirectory remote get-url origin 2>$null
            if ($LASTEXITCODE -ne 0 -or $Remote -ne $Repository) { throw "Cannot reuse ${ProjectDirectory}: it is not the ClipHarbor repository. No files were changed." }
        } else {
            $CloneDirectory = Join-Path $BootstrapRoot ('source-download-' + [Guid]::NewGuid().ToString('N'))
            & git clone --depth 1 $Repository $CloneDirectory
            if ($LASTEXITCODE -ne 0) { throw 'Could not download ClipHarbor. Check the connection and retry.' }
            if (-not ([IO.Path]::GetFullPath($CloneDirectory).StartsWith($BootstrapRoot + [IO.Path]::DirectorySeparatorChar))) { throw 'Unexpected clone location.' }
            [IO.Directory]::Move($CloneDirectory, $ProjectDirectory)
        }
    }
    if (-not $ProjectDirectory -or -not (Test-Path -LiteralPath (Join-Path $ProjectDirectory 'app.py'))) { throw 'Run this inside the repository, or use -InstallRepository.' }
    $ProjectDirectory = [IO.Path]::GetFullPath($ProjectDirectory)
    $Missing = @()
    $Runtime = Find-Python
    if (-not $Runtime) { $Missing += @('python=3.12', 'pip', 'tk') }
    if (-not (Test-Tool 'ffmpeg' @('-version')) -or -not (Test-Tool 'ffprobe' @('-version'))) { $Missing += 'ffmpeg' }
    if (-not (Test-Tool 'node' @('-e', 'if(parseInt(process.versions.node)<22)process.exit(1)'))) { $Missing += 'nodejs>=22' }
    if ($Missing.Count) { Install-Missing $Missing }
    $Runtime = Find-Python
    if (-not $Runtime) { throw 'The app runtime is not usable after setup.' }
    foreach ($Tool in @('git', 'ffmpeg', 'ffprobe', 'node')) {
        $Flag = if ($Tool -in @('ffmpeg','ffprobe')) { '-version' } else { '--version' }
        if (-not (Test-Tool $Tool @($Flag))) { throw "$Tool did not start after setup. Rerun the command or report this error." }
    }
    $Venv = Join-Path $ProjectDirectory '.venv'
    $AppPython = Join-Path $Venv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $AppPython)) {
        Write-Host 'Preparing the app environment...'
        & $Runtime -m venv $Venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the app environment. Check write permissions and free disk space.' }
    }
    if (-not (Test-Tool $AppPython @('-c', 'import sys; assert sys.version_info >= (3,10)'))) { throw "The environment at $Venv is not usable. Rename that folder and rerun; projects and media are separate." }
    $Requirements = Join-Path $ProjectDirectory 'requirements.txt'
    $Fingerprint = (Get-FileHash -LiteralPath $Requirements -Algorithm SHA256).Hash
    $Stamp = Join-Path $Venv '.clipharbor-requirements'
    $Previous = if (Test-Path -LiteralPath $Stamp) { [IO.File]::ReadAllText($Stamp).Trim() } else { '' }
    if ($UpdateDependencies -or $Previous -ne $Fingerprint -or -not (Test-Tool $AppPython @('-c', 'import flask, waitress, yt_dlp, yt_dlp_ejs'))) {
        Write-Host 'Preparing ClipHarbor components...'
        & $AppPython -m pip install --disable-pip-version-check --upgrade -r $Requirements
        if ($LASTEXITCODE -ne 0) { throw 'App setup failed. Check your connection and rerun to retry.' }
        [IO.File]::WriteAllText($Stamp, $Fingerprint)
    }
    if ($SetupOnly) { Write-Host "ClipHarbor setup is ready: $ProjectDirectory"; return }
    Write-Host 'Opening ClipHarbor. Keep this terminal open; press Ctrl+C here when finished.'
    & $AppPython (Join-Path $ProjectDirectory 'app.py') --open
    if ($LASTEXITCODE -ne 0) { throw "ClipHarbor stopped with exit code $LASTEXITCODE." }
} finally {
    $env:PATH = $OriginalPath
    $env:PYTHONPATH = $OriginalPythonPath
    $env:PYTHONHOME = $OriginalPythonHome
}
