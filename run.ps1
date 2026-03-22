$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BootstrapScript = Join-Path $ProjectRoot "bootstrap.ps1"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$MainScript = Join-Path $ProjectRoot "main.py"

if (-not (Test-Path $MainScript)) {
    throw "Arquivo principal nao encontrado em $MainScript"
}

if (-not (Test-Path $BootstrapScript)) {
    throw "Bootstrap nao encontrado em $BootstrapScript"
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "[run] Ambiente virtual ausente. Executando bootstrap..." -ForegroundColor Yellow
    & $BootstrapScript
}

if (-not (Test-Path $VenvPython)) {
    throw "Falha ao preparar a venv do projeto em $VenvPython"
}

Write-Host "[run] Executando projeto com a venv local..." -ForegroundColor Cyan
& $VenvPython $MainScript
