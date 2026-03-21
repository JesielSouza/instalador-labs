import sys
from pathlib import Path


def _resolve_base_dir() -> Path:
    """Retorna a base do projeto ou do executavel empacotado."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = _resolve_base_dir()
BRAIN_DIR = BASE_DIR / "brain"
PACKAGES_DIR = BASE_DIR / "packages"
LOGS_DIR = BASE_DIR / "logs"
REPORTS_DIR = BASE_DIR / "reports"
DOWNLOADS_DIR = BASE_DIR / ".downloads"
DEFAULT_PACKAGE_PROFILE = PACKAGES_DIR / "ads_lab.json"
VENV_DIR = BASE_DIR / ".venv"
VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"

KNOWN_PYTHON_CANDIDATES = (
    VENV_PYTHON,
    Path(sys.executable) if sys.executable else None,
    Path(r"C:\Users\Administrador\AppData\Local\Programs\Python\Python314\python.exe"),
)

WINGET_CANDIDATES = (
    Path(r"C:\Users\Administrador\AppData\Local\Microsoft\WindowsApps\winget.exe"),
    Path(r"C:\Program Files\WindowsApps\Microsoft.DesktopAppInstaller_8wekyb3d8bbwe\winget.exe"),
)


def resolve_python_executable() -> str:
    """Retorna o Python preferencial do projeto, priorizando a venv local."""
    for candidate in KNOWN_PYTHON_CANDIDATES:
        if candidate and candidate.exists():
            return str(candidate)
    return sys.executable or "python"


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
