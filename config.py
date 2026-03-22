import os
import sys
from pathlib import Path


def _resolve_resource_dir() -> Path:
    """Retorna o diretorio de recursos do projeto ou do bundle empacotado."""
    if getattr(sys, "frozen", False):
        bundle_dir = getattr(sys, "_MEIPASS", None)
        if bundle_dir:
            return Path(bundle_dir).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _resolve_runtime_dir() -> Path:
    """Retorna o diretorio onde o operador deve encontrar artefatos do instalador."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


RESOURCE_DIR = _resolve_resource_dir()
RUNTIME_DIR = _resolve_runtime_dir()
BASE_DIR = RESOURCE_DIR
BRAIN_DIR = RUNTIME_DIR / "brain"
PACKAGES_DIR = RESOURCE_DIR / "packages"
LOGS_DIR = RUNTIME_DIR / "logs"
REPORTS_DIR = RUNTIME_DIR / "reports"
DOWNLOADS_DIR = RUNTIME_DIR / ".downloads"
DEFAULT_PACKAGE_PROFILE = PACKAGES_DIR / "ads_lab.json"
VENV_DIR = RUNTIME_DIR / ".venv"
VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"

def _build_python_candidates() -> tuple[Path | None, ...]:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", "")) if os.environ.get("LOCALAPPDATA") else None
    program_files = Path(os.environ.get("ProgramFiles", "")) if os.environ.get("ProgramFiles") else None
    system_drive = Path(os.environ.get("SystemDrive", "C:"))
    admin_local_app_data = system_drive / "Users" / "Administrador" / "AppData" / "Local"

    candidates = [
        VENV_PYTHON,
        Path(sys.executable) if sys.executable else None,
    ]

    python_locations = []
    if local_app_data:
        python_locations.append(local_app_data / "Programs" / "Python")
    python_locations.append(admin_local_app_data / "Programs" / "Python")

    for location in python_locations:
        candidates.extend(
            [
                location / "Python312" / "python.exe",
                location / "Python311" / "python.exe",
                location / "Python314" / "python.exe",
            ]
        )

    if program_files:
        candidates.extend(
            [
                program_files / "Python312" / "python.exe",
                program_files / "Python311" / "python.exe",
                program_files / "Python314" / "python.exe",
            ]
        )

    unique_candidates: list[Path | None] = []
    seen = set()
    for candidate in candidates:
        key = str(candidate) if candidate else None
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(candidate)

    return tuple(unique_candidates)


KNOWN_PYTHON_CANDIDATES = _build_python_candidates()

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
