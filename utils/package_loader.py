import json
from pathlib import Path

from config import DEFAULT_PACKAGE_PROFILE


def load_package_profile(file_path: str | Path) -> dict:
    """Carrega um perfil JSON de pacotes a partir do caminho informado."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Perfil de pacotes nao encontrado: {path}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_ads_lab_profile() -> dict:
    """Carrega o perfil padrao do laboratorio ADS."""
    profile = load_package_profile(DEFAULT_PACKAGE_PROFILE)
    if not isinstance(profile, dict):
        raise ValueError("Perfil de pacotes invalido: raiz JSON deve ser um objeto.")
    return profile
