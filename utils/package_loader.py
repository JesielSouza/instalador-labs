import json
from pathlib import Path


def load_package_profile(file_path: str | Path) -> dict:
    """Carrega um perfil JSON de pacotes a partir do caminho informado."""
    path = Path(file_path)
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)
