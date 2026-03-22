$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BootstrapScript = Join-Path $ProjectRoot "bootstrap.ps1"
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvConfig = Join-Path $VenvDir "pyvenv.cfg"
$TestsDir = Join-Path $ProjectRoot "tests"

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

if (-not (Test-Path $BootstrapScript)) {
    throw "Bootstrap nao encontrado em $BootstrapScript"
}

if (-not (Test-VenvHealthy)) {
    Write-Host "[verify] Ambiente virtual ausente ou invalido. Executando bootstrap..." -ForegroundColor Yellow
    & $BootstrapScript
}

if (-not (Test-VenvHealthy)) {
    throw "Falha ao preparar uma venv valida do projeto em $VenvPython"
}

Write-Host "[verify] Validando perfil ADS..." -ForegroundColor Cyan
@"
from utils.package_loader import load_ads_lab_profile
profile = load_ads_lab_profile()
print(f"Perfil {profile['profile']} validado com {len(profile['packages'])} pacote(s).")
"@ | & $VenvPython -
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao validar o perfil ADS."
}

if (-not (Test-Path $TestsDir)) {
    throw "Pasta de testes nao encontrada em $TestsDir"
}

Write-Host "[verify] Executando suite automatizada..." -ForegroundColor Cyan
& $VenvPython -m unittest discover -s $TestsDir -p "test_*.py"
if ($LASTEXITCODE -ne 0) {
    throw "Falha na suite de testes automatizados."
}

Write-Host "[verify] Verificacao concluida com sucesso." -ForegroundColor Green
