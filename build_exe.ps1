$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BootstrapScript = Join-Path $ProjectRoot "bootstrap.ps1"
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvConfig = Join-Path $VenvDir "pyvenv.cfg"
$MainScript = Join-Path $ProjectRoot "main.py"

function Test-VenvHealthy {
    if (-not (Test-Path $VenvPython) -or -not (Test-Path $VenvConfig)) {
        return $false
    }

    $executableLine = Get-Content $VenvConfig -ErrorAction SilentlyContinue |
        Where-Object { $_ -like "executable = *" } |
        Select-Object -First 1

    if (-not $executableLine) {
        return $false
    }

    $baseExecutable = $executableLine.Substring("executable = ".Length).Trim()
    if ([string]::IsNullOrWhiteSpace($baseExecutable)) {
        return $false
    }

    return Test-Path $baseExecutable
}

if (-not (Test-VenvHealthy)) {
    Write-Host "[build] Ambiente virtual ausente. Executando bootstrap..." -ForegroundColor Yellow
    powershell -ExecutionPolicy Bypass -File $BootstrapScript
}

if (-not (Test-VenvHealthy)) {
    throw "Falha ao preparar uma venv valida do projeto em $VenvPython"
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
