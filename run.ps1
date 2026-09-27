param([switch]$UpdateDependencies, [string]$Python)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPath = Join-Path $ProjectRoot '.venv'
$FallbackPython = Join-Path $VenvPath 'Scripts\python.exe'

if ($Python) {
    $PythonPath = $Python
} elseif ($env:CONDA_PREFIX -and (Test-Path -LiteralPath (Join-Path $env:CONDA_PREFIX 'python.exe'))) {
    $PythonPath = Join-Path $env:CONDA_PREFIX 'python.exe'
    Write-Host 'Using the active Conda environment.'
} else {
    $PythonPath = $FallbackPython
    if (-not (Test-Path -LiteralPath $PythonPath)) {
        python -m venv $VenvPath
        if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv. Install Python 3.10 or newer first.' }
    }
}

$DependencyCheck = & $PythonPath -c "import flask, yt_dlp" 2>$null
if ($LASTEXITCODE -ne 0 -or $UpdateDependencies) {
    Write-Host ($(if ($UpdateDependencies) { 'Updating ClipHarbor dependencies.' } else { 'Installing missing ClipHarbor dependencies.' }))
    & $PythonPath -m pip install --disable-pip-version-check -r (Join-Path $ProjectRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
} else {
    Write-Host 'Python dependencies are ready. Skipping the package check.'
}

foreach ($Tool in @('ffmpeg', 'ffprobe')) {
    if (-not (Get-Command $Tool -ErrorAction SilentlyContinue)) {
        throw "$Tool was not found on PATH. Install FFmpeg and restart the terminal."
    }
}

& $PythonPath (Join-Path $ProjectRoot 'app.py') --open
