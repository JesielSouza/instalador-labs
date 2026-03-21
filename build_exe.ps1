$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BootstrapScript = Join-Path $ProjectRoot "bootstrap.ps1"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$MainScript = Join-Path $ProjectRoot "main.py"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[build] Ambiente virtual ausente. Executando bootstrap..." -ForegroundColor Yellow
    powershell -ExecutionPolicy Bypass -File $BootstrapScript
}

Write-Host "[build] Instalando PyInstaller na venv..." -ForegroundColor Cyan
& $VenvPython -m pip install pyinstaller

Write-Host "[build] Gerando executavel..." -ForegroundColor Cyan
& $VenvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --name InstaladorLabs `
    --add-data "packages;packages" `
    --collect-all colorama `
    $MainScript

Write-Host "[build] Build concluido em dist\\InstaladorLabs" -ForegroundColor Green
