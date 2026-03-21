$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$BootstrapTemp = Join-Path $ProjectRoot ".tmp-bootstrap"

if (-not (Test-Path $BootstrapTemp)) {
    New-Item -ItemType Directory -Path $BootstrapTemp | Out-Null
}

$env:TMP = $BootstrapTemp
$env:TEMP = $BootstrapTemp

function Resolve-BasePython {
    $candidates = @()

    $knownPaths = @(
        "C:\Users\Administrador\AppData\Local\Programs\Python\Python314\python.exe"
    )

    foreach ($path in $knownPaths) {
        if (Test-Path $path) {
            $candidates += @{ Command = $path; Arguments = @() }
        }
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        $candidates += @(
            @{ Command = "py"; Arguments = @("-3.14") },
            @{ Command = "py"; Arguments = @("-3") },
            @{ Command = "py"; Arguments = @() }
        )
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        $candidates += @{ Command = "python"; Arguments = @() }
    }

    foreach ($candidate in $candidates) {
        try {
            & $candidate.Command @($candidate.Arguments + @("-c", "import sys; print(sys.executable)")) *> $null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        } catch {
        }
    }

    throw "Nenhum interpretador Python compativel foi encontrado para criar a venv."
}

$basePython = Resolve-BasePython

if (-not (Test-Path $VenvPython)) {
    Write-Host "[bootstrap] Criando ambiente virtual em .venv..." -ForegroundColor Cyan
    & $basePython.Command @($basePython.Arguments + @("-m", "venv", ".venv"))
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao criar a venv do projeto."
    }
}

Write-Host "[bootstrap] Atualizando pip..." -ForegroundColor Cyan
& $basePython.Command @(
    $basePython.Arguments + @("-m", "pip", "--python", $VenvPython, "install", "--upgrade", "pip")
)
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao atualizar o pip da venv."
}

Write-Host "[bootstrap] Instalando dependencias do requirements.txt..." -ForegroundColor Cyan
& $basePython.Command @(
    $basePython.Arguments + @("-m", "pip", "--python", $VenvPython, "install", "-r", (Join-Path $ProjectRoot "requirements.txt"))
)
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao instalar as dependencias do projeto."
}

Write-Host "[bootstrap] Ambiente pronto. Use .\run.ps1 para executar o projeto." -ForegroundColor Green
