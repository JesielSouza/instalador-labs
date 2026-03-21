from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
BRAIN_DIR = BASE_DIR / "brain"
PACKAGES_DIR = BASE_DIR / "packages"
LOGS_DIR = BASE_DIR / "logs"
REPORTS_DIR = BASE_DIR / "reports"

PYTHON_EXECUTABLE = Path(
    r"C:\Users\Administrador\AppData\Local\Programs\Python\Python314\python.exe"
)

WINGET_CANDIDATES = (
    Path(r"C:\Users\Administrador\AppData\Local\Microsoft\WindowsApps\winget.exe"),
    Path(r"C:\Program Files\WindowsApps\Microsoft.DesktopAppInstaller_8wekyb3d8bbwe\winget.exe"),
)


def resolve_python_executable() -> str:
    """Retorna o Python padrao do projeto em caminho absoluto."""
    return str(PYTHON_EXECUTABLE)


def resolve_winget_executable() -> str | None:
    """
    Retorna o executavel do WinGet.

    Estrategia:
    1. Prioriza alias em `WindowsApps`, comum quando o binario nao esta no PATH do shell.
    2. Faz fallback para um caminho conhecido do App Installer.
    3. Mantem `None` se nenhum candidato existir.
    """
    for candidate in WINGET_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    return None
