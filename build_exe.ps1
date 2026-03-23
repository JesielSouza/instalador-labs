$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BootstrapScript = Join-Path $ProjectRoot "bootstrap.ps1"
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvConfig = Join-Path $VenvDir "pyvenv.cfg"
$MainScript = Join-Path $ProjectRoot "main.py"
$TempDistRoot = Join-Path $ProjectRoot ".tmp-dist"
$TempBuildRoot = Join-Path $ProjectRoot ".tmp-build"
$FinalDistRoot = Join-Path $ProjectRoot "dist"
$FinalBundle = Join-Path $FinalDistRoot "InstaladorLabs"
$TempBundle = Join-Path $TempDistRoot "InstaladorLabs"
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

function Remove-DirectoryRobustly([string]$TargetPath) {
    if (-not (Test-Path $TargetPath)) {
        return
    }

    Start-Process -FilePath "cmd.exe" -ArgumentList @("/d", "/c", "rd /s /q `"$TargetPath`"") -Wait -NoNewWindow

    try {
        if (Test-Path $TargetPath) {
            [System.IO.Directory]::Delete($TargetPath, $true)
        }
    } catch {
    }

    try {
        if (Test-Path $TargetPath) {
            throw "Falha ao remover o diretorio $TargetPath"
        }
    } catch {
        throw "Falha ao remover o diretorio $TargetPath"
    }
}

function Publish-BundleRobustly([string]$SourcePath, [string]$DestinationPath) {
    try {
        Remove-DirectoryRobustly $DestinationPath
        Move-Item -Path $SourcePath -Destination $DestinationPath
        return
    } catch {
        Write-Host "[build] Publish direto falhou. Tentando sincronizacao robusta no caminho final..." -ForegroundColor Yellow
    }

    if (-not (Test-Path $DestinationPath)) {
        New-Item -ItemType Directory -Path $DestinationPath | Out-Null
    }

    & robocopy $SourcePath $DestinationPath /MIR /R:2 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw @"
Falha ao sincronizar o bundle final em $DestinationPath.

Provavel causa: o bundle atual ainda esta em uso por outro processo.

Como proceder:
1. Feche o aplicativo '$FinalBundle\InstaladorLabs.exe' se ele estiver aberto.
2. Feche janelas do Explorer, terminal ou visualizadores apontando para arquivos dentro de '$FinalBundle'.
3. Execute novamente: powershell -ExecutionPolicy Bypass -File .\build_exe.ps1

Se o problema persistir, apague manualmente a pasta '$FinalBundle' depois de fechar o aplicativo.
"@
    }

    Remove-DirectoryRobustly $SourcePath
}

if (-not (Test-VenvHealthy)) {
    Write-Host "[build] Ambiente virtual ausente. Executando bootstrap..." -ForegroundColor Yellow
    powershell -ExecutionPolicy Bypass -File $BootstrapScript
}

if (-not (Test-VenvHealthy)) {
    throw "Falha ao preparar uma venv valida do projeto em $VenvPython"
}

Remove-DirectoryRobustly $TempDistRoot
Remove-DirectoryRobustly $TempBuildRoot

Write-Host "[build] Instalando PyInstaller na venv..." -ForegroundColor Cyan
& $VenvPython -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao instalar o PyInstaller na venv."
}

Write-Host "[build] Gerando executavel em area temporaria..." -ForegroundColor Cyan
& $VenvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --name InstaladorLabs `
    --distpath $TempDistRoot `
    --workpath $TempBuildRoot `
    --add-data "packages;packages" `
    --collect-all colorama `
    $MainScript
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao gerar o executavel com PyInstaller."
}

$BundledCatalog = Join-Path $TempBundle "_internal\packages\ads_lab.json"
if (-not (Test-Path $BundledCatalog)) {
    throw "Build concluido sem catalogo empacotado em $BundledCatalog"
}

if (-not (Test-Path $FinalDistRoot)) {
    New-Item -ItemType Directory -Path $FinalDistRoot | Out-Null
}

$PublishBundle = $FinalBundle
Publish-BundleRobustly -SourcePath $TempBundle -DestinationPath $PublishBundle
Remove-DirectoryRobustly $TempDistRoot
Remove-DirectoryRobustly $TempBuildRoot

Write-Host "[build] Build concluido em $PublishBundle" -ForegroundColor Green
