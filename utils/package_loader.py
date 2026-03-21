import json
from pathlib import Path

from config import DEFAULT_PACKAGE_PROFILE

ALLOWED_INSTALL_TYPES = {"winget", "winget_pending", "manual"}


class PackageProfileValidationError(ValueError):
    """Erro de validacao do perfil de pacotes."""


def load_package_profile(file_path: str | Path) -> dict:
    """Carrega um perfil JSON de pacotes a partir do caminho informado."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Perfil de pacotes nao encontrado: {path}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def validate_package_profile(profile: dict) -> dict:
    """Valida a estrutura minima esperada para um perfil de pacotes."""
    if not isinstance(profile, dict):
        raise PackageProfileValidationError(
            "Perfil de pacotes invalido: raiz JSON deve ser um objeto."
        )

    required_root_fields = ("profile", "description", "packages")
    for field in required_root_fields:
        if field not in profile:
            raise PackageProfileValidationError(
                f"Perfil de pacotes invalido: campo obrigatorio ausente '{field}'."
            )

    if not isinstance(profile["profile"], str) or not profile["profile"].strip():
        raise PackageProfileValidationError(
            "Perfil de pacotes invalido: 'profile' deve ser uma string nao vazia."
        )

    if not isinstance(profile["description"], str) or not profile["description"].strip():
        raise PackageProfileValidationError(
            "Perfil de pacotes invalido: 'description' deve ser uma string nao vazia."
        )

    packages = profile["packages"]
    if not isinstance(packages, list):
        raise PackageProfileValidationError(
            "Perfil de pacotes invalido: 'packages' deve ser uma lista."
        )

    for index, package in enumerate(packages, start=1):
        if not isinstance(package, dict):
            raise PackageProfileValidationError(
                f"Pacote invalido na posicao {index}: cada item deve ser um objeto."
            )

        for field in ("software", "install_type"):
            if field not in package:
                raise PackageProfileValidationError(
                    f"Pacote invalido na posicao {index}: campo obrigatorio ausente '{field}'."
                )

        if not isinstance(package["software"], str) or not package["software"].strip():
            raise PackageProfileValidationError(
                f"Pacote invalido na posicao {index}: 'software' deve ser uma string nao vazia."
            )

        install_type = package["install_type"]
        if install_type not in ALLOWED_INSTALL_TYPES:
            raise PackageProfileValidationError(
                f"Pacote invalido na posicao {index}: 'install_type' deve ser um de {sorted(ALLOWED_INSTALL_TYPES)}."
            )

        winget_id = package.get("winget_id")
        if install_type in {"winget", "winget_pending"}:
            if not isinstance(winget_id, str) or not winget_id.strip():
                raise PackageProfileValidationError(
                    f"Pacote invalido na posicao {index}: 'winget_id' e obrigatorio para install_type '{install_type}'."
                )
        elif winget_id is not None and not isinstance(winget_id, str):
            raise PackageProfileValidationError(
                f"Pacote invalido na posicao {index}: 'winget_id' deve ser string quando informado."
            )

    return profile


def load_ads_lab_profile() -> dict:
    """Carrega o perfil padrao do laboratorio ADS."""
    profile = load_package_profile(DEFAULT_PACKAGE_PROFILE)
    return validate_package_profile(profile)
