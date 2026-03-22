import json
from copy import deepcopy
from pathlib import Path

from config import DEFAULT_PACKAGE_PROFILE, PACKAGES_DIR

ALLOWED_INSTALL_TYPES = {"winget", "winget_pending", "manual"}


class PackageProfileValidationError(ValueError):
    """Erro de validacao do perfil de pacotes."""


class PackageSelectionError(ValueError):
    """Erro ao filtrar ou localizar pacotes selecionados pelo operador."""


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

    seen_software_names = set()

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

        software_name = package["software"].strip()
        if software_name in seen_software_names:
            raise PackageProfileValidationError(
                f"Pacote invalido na posicao {index}: nome de software duplicado '{software_name}'."
            )
        seen_software_names.add(software_name)

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

        detect_names = package.get("detect_names")
        if detect_names is not None:
            if not isinstance(detect_names, list) or not all(
                isinstance(item, str) and item.strip() for item in detect_names
            ):
                raise PackageProfileValidationError(
                    f"Pacote invalido na posicao {index}: 'detect_names' deve ser uma lista de strings nao vazias."
                )

        for installer_key, require_install_args in (("fallback_installer", True), ("official_download", False)):
            installer_config = package.get(installer_key)
            if installer_config is None:
                continue

            if not isinstance(installer_config, dict):
                raise PackageProfileValidationError(
                    f"Pacote invalido na posicao {index}: '{installer_key}' deve ser um objeto."
                )

            required_fields = ["download_url"]
            if require_install_args:
                required_fields.append("install_args")

            for field in required_fields:
                if field not in installer_config:
                    raise PackageProfileValidationError(
                        f"Pacote invalido na posicao {index}: campo obrigatorio ausente em '{installer_key}': '{field}'."
                    )

            if not isinstance(installer_config["download_url"], str) or not installer_config["download_url"].strip():
                raise PackageProfileValidationError(
                    f"Pacote invalido na posicao {index}: '{installer_key}.download_url' deve ser string nao vazia."
                )

            install_args = installer_config.get("install_args")
            if install_args is not None and (not isinstance(install_args, list) or not all(isinstance(arg, str) for arg in install_args)):
                raise PackageProfileValidationError(
                    f"Pacote invalido na posicao {index}: '{installer_key}.install_args' deve ser uma lista de strings quando informada."
                )

            file_name = installer_config.get("file_name")
            if file_name is not None and (not isinstance(file_name, str) or not file_name.strip()):
                raise PackageProfileValidationError(
                    f"Pacote invalido na posicao {index}: '{installer_key}.file_name' deve ser string nao vazia quando informado."
                )

    return profile


def list_package_profiles() -> list[dict]:
    """Lista os perfis JSON disponiveis na pasta de catalogos."""
    profiles = []
    for file_path in sorted(PACKAGES_DIR.glob('*.json')):
        profile = validate_package_profile(load_package_profile(file_path))
        profiles.append(
            {
                'profile': profile['profile'],
                'description': profile['description'],
                'path': file_path,
                'package_count': len(profile.get('packages', [])),
            }
        )
    return profiles


def load_profile_by_name(profile_name: str) -> dict:
    """Carrega um perfil pelo identificador declarado no JSON."""
    for profile_metadata in list_package_profiles():
        if profile_metadata['profile'] == profile_name:
            return validate_package_profile(load_package_profile(profile_metadata['path']))

    raise FileNotFoundError(f"Perfil de pacotes nao encontrado: {profile_name}")


def select_profile_packages(profile: dict, selected_software_names: list[str] | None) -> dict:
    """Retorna uma copia do perfil contendo apenas os pacotes selecionados."""
    validated_profile = validate_package_profile(deepcopy(profile))
    if selected_software_names is None:
        return validated_profile

    normalized_names = []
    for software_name in selected_software_names:
        if not isinstance(software_name, str) or not software_name.strip():
            raise PackageSelectionError('Selecao de pacotes invalida: nomes devem ser strings nao vazias.')
        candidate = software_name.strip()
        if candidate not in normalized_names:
            normalized_names.append(candidate)

    if not normalized_names:
        raise PackageSelectionError('Selecao de pacotes vazia: escolha ao menos um software para executar.')

    package_map = {package['software']: package for package in validated_profile['packages']}
    missing_names = [name for name in normalized_names if name not in package_map]
    if missing_names:
        raise PackageSelectionError(
            'Pacotes selecionados nao encontrados no perfil: ' + ', '.join(missing_names)
        )

    filtered_profile = deepcopy(validated_profile)
    filtered_profile['packages'] = [deepcopy(package_map[name]) for name in normalized_names]
    filtered_profile['selection'] = normalized_names
    return filtered_profile


def load_default_package_profile() -> dict:
    """Carrega o perfil padrao configurado pelo projeto."""
    profile = load_package_profile(DEFAULT_PACKAGE_PROFILE)
    return validate_package_profile(profile)


def load_ads_lab_profile() -> dict:
    """Mantido por compatibilidade com chamadas legadas do laboratorio ADS."""
    return load_profile_by_name('ads_lab')
