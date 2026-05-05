Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Virtual environment not found. Create .venv first."
}

Push-Location $projectRoot
try {
    & $python -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    & $python -m PyInstaller --noconfirm --clean eargrape.spec
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
