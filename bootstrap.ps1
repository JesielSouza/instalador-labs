$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$BootstrapTemp = Join-Path $ProjectRoot ".tmp-bootstrap"
$DownloadsDir = Join-Path $ProjectRoot ".downloads"
$CatalogPath = Join-Path $ProjectRoot "packages\ads_lab.json"

if (-not (Test-Path $BootstrapTemp)) {
    New-Item -ItemType Directory -Path $BootstrapTemp | Out-Null
}

if (-not (Test-Path $DownloadsDir)) {
    New-Item -ItemType Directory -Path $DownloadsDir | Out-Null
}

$env:TMP = $BootstrapTemp
$env:TEMP = $BootstrapTemp
$progressPreference = "SilentlyContinue"

function Test-WinGet {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        return $true
    }

    $candidates = @(
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\winget.exe",
        "C:\Program Files\WindowsApps\Microsoft.DesktopAppInstaller_8wekyb3d8bbwe\winget.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $true
        }
    }

    return $false
}

function Ensure-WinGet {
    if (Test-WinGet) {
        Write-Host "[bootstrap] WinGet ja esta disponivel." -ForegroundColor Green
        return
    }

    Write-Host "[bootstrap] WinGet ausente. Tentando bootstrap oficial via PowerShell module..." -ForegroundColor Cyan
    Install-PackageProvider -Name NuGet -Force | Out-Null
    Install-Module -Name Microsoft.WinGet.Client -Force -Repository PSGallery | Out-Null
    Import-Module Microsoft.WinGet.Client -Force | Out-Null
    Repair-WinGetPackageManager -AllUsers | Out-Null

    if (Test-WinGet) {
        Write-Host "[bootstrap] WinGet restaurado com sucesso." -ForegroundColor Green
        return
    }

    Write-Host "[bootstrap] WinGet continua indisponivel. O projeto seguira com fallback direto quando necessario." -ForegroundColor Yellow
}

function Resolve-BasePython {
    $candidates = @()

    $knownPaths = @(
        "C:\Users\Administrador\AppData\Local\Programs\Python\Python314\python.exe",
        "C:\Program Files\Python312\python.exe",
        "C:\Program Files\Python311\python.exe"
    )

    foreach ($path in $knownPaths) {
        if (Test-Path $path) {
            $candidates += @{ Command = $path; Arguments = @() }
        }
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        $candidates += @(
            @{ Command = "py"; Arguments = @("-3.12") },
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

    return $null
}

function Install-PythonFromWinget {
    if (-not (Test-WinGet)) {
        return
    }

    Write-Host "[bootstrap] Tentando instalar Python 3.12 via WinGet..." -ForegroundColor Cyan
    & winget install --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
}

function Install-PythonDirectly {
    $catalog = Get-Content $CatalogPath -Raw | ConvertFrom-Json
    $pythonPackage = $catalog.packages | Where-Object { $_.software -eq "Python 3.12" } | Select-Object -First 1

    if (-not $pythonPackage -or -not $pythonPackage.fallback_installer) {
        throw "Nao foi possivel localizar o fallback oficial do Python 3.12 no catalogo."
    }

    $downloadUrl = $pythonPackage.fallback_installer.download_url
    $fileName = $pythonPackage.fallback_installer.file_name
    $installerPath = Join-Path $DownloadsDir $fileName

    if (-not (Test-Path $installerPath)) {
        Write-Host "[bootstrap] Baixando instalador oficial do Python 3.12..." -ForegroundColor Cyan
        Invoke-WebRequest -Uri $downloadUrl -OutFile $installerPath
    } else {
        Write-Host "[bootstrap] Reutilizando instalador do Python 3.12 em cache..." -ForegroundColor Cyan
    }

    $arguments = @("/quiet", "InstallAllUsers=1", "PrependPath=1", "Include_test=0", "Include_pip=1")
    Write-Host "[bootstrap] Instalando Python 3.12 via fallback direto..." -ForegroundColor Cyan
    & $installerPath @arguments
}

function Ensure-BasePython {
    $basePython = Resolve-BasePython
    if ($basePython) {
        Write-Host "[bootstrap] Python base localizado." -ForegroundColor Green
        return $basePython
    }

    Install-PythonFromWinget
    $basePython = Resolve-BasePython
    if ($basePython) {
        Write-Host "[bootstrap] Python base instalado via WinGet." -ForegroundColor Green
        return $basePython
    }

    Install-PythonDirectly
    $basePython = Resolve-BasePython
    if ($basePython) {
        Write-Host "[bootstrap] Python base instalado via fallback direto." -ForegroundColor Green
        return $basePython
    }

    throw "Nenhum interpretador Python compativel foi encontrado para criar a venv."
}

Ensure-WinGet
$basePython = Ensure-BasePython

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
