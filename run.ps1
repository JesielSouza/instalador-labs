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

if (-not (Test-Path $MainScript)) {
    throw "Arquivo principal nao encontrado em $MainScript"
}

if (-not (Test-Path $BootstrapScript)) {
    throw "Bootstrap nao encontrado em $BootstrapScript"
}

if (-not (Test-VenvHealthy)) {
    Write-Host "[run] Ambiente virtual ausente. Executando bootstrap..." -ForegroundColor Yellow
    & $BootstrapScript
}

if (-not (Test-VenvHealthy)) {
    throw "Falha ao preparar uma venv valida do projeto em $VenvPython"
}

Write-Host "[run] Executando projeto com a venv local..." -ForegroundColor Cyan
& $VenvPython $MainScript
