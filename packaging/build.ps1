param(
    [string]$Python = '..\.build-env\Scripts\python.exe',
    [string]$Iscc = '..\.build-tools\InnoSetup\ISCC.exe'
)
$ErrorActionPreference = 'Stop'
$OriginalPythonPath = $env:PYTHONPATH
Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath $Python)) { throw 'Create .build-env and install packaging/build-requirements.txt first.' }
    if (-not (Test-Path -LiteralPath $Iscc)) { throw 'Inno Setup compiler is missing. Pass -Iscc with its path.' }
    foreach ($name in @('ffmpeg.exe','ffprobe.exe','node.exe')) {
        if (-not (Test-Path -LiteralPath "vendor\$name")) { throw "Missing bundled tool vendor\$name" }
    }
    & $Python -m PyInstaller --noconfirm --distpath ..\dist --workpath ..\build ClipHarbor.spec
    if ($LASTEXITCODE -ne 0) { throw 'Application bundle failed.' }
    & $Iscc /Q ClipHarbor.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
    Get-FileHash ..\dist\installer\ClipHarbor-Setup-0.5.0-win-x64.exe -Algorithm SHA256
} finally { Pop-Location; $env:PYTHONPATH = $OriginalPythonPath }
