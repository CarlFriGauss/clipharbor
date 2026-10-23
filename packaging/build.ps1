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
    foreach ($name in @('node.exe')) {
        if (-not (Test-Path -LiteralPath "vendor\$name")) { throw "Missing bundled tool vendor\$name" }
    }
    $AppVersion = & $Python -c "import runpy; print(runpy.run_path('../mediaforge/runtime.py')['VERSION'])"
    if ($LASTEXITCODE -ne 0 -or $AppVersion -notmatch '^\d+\.\d+\.\d+$') { throw 'Application version is invalid.' }
    & $Python -m PyInstaller --noconfirm --distpath ..\dist --workpath ..\build ClipHarbor.spec
    if ($LASTEXITCODE -ne 0) { throw 'Application bundle failed.' }
    New-Item -ItemType Directory -Force -Path '..\dist\ClipHarbor\browser-extension' | Out-Null
    $ExtensionFiles = Get-ChildItem -LiteralPath '..\browser-extension' -File
    $ExtensionFiles | Copy-Item -Destination '..\dist\ClipHarbor\browser-extension' -Force
    Copy-Item -LiteralPath '..\browser-extension\native-host.json' -Destination '..\dist\ClipHarbor\clipharbor-native-host.json' -Force
    & $Python ..\tests\packaged_smoke.py ..\dist\ClipHarbor\ClipHarbor.exe --graphical-setup
    if ($LASTEXITCODE -ne 0) { throw 'Graphical first-run smoke test failed. Installer will not be built.' }
    & $Iscc /Q "/DAppVersion=$AppVersion" ClipHarbor.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
    Compress-Archive -LiteralPath $ExtensionFiles.FullName -DestinationPath "..\dist\installer\ClipHarbor-Extension-$AppVersion.zip" -Force
    Get-FileHash "..\dist\installer\ClipHarbor-Setup-$AppVersion-win-x64.exe" -Algorithm SHA256
} finally { Pop-Location; $env:PYTHONPATH = $OriginalPythonPath }
