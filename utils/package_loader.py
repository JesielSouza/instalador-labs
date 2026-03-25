import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

from config import DEFAULT_PACKAGE_PROFILE, PACKAGES_DIR

ALLOWED_INSTALL_TYPES = {"winget", "winget_pending", "manual"}


class PackageProfileValidationError(ValueError):
    """Erro de validacao do perfil de pacotes."""


class PackageSelectionError(ValueError):
    """Erro ao filtrar ou localizar pacotes selecionados pelo operador."""


def build_dynamic_package_profile(packages: list[dict], profile_name: str = "dynamic_winget") -> dict:
    """Monta um perfil valido em memoria a partir de pacotes dinamicos pesquisados via WinGet."""
    normalized_packages = []
    seen_ids = set()
    seen_names = set()

    for index, package in enumerate(packages or [], start=1):
        software_name = (package.get("software") or "").strip()
        winget_id = _sanitize_dynamic_winget_id(package.get("winget_id"))
        if not software_name or not winget_id:
            raise PackageProfileValidationError(
                f"Pacote dinamico invalido na posicao {index}: 'software' e 'winget_id' sao obrigatorios."
            )
        if winget_id.lower() in seen_ids:
            continue
        seen_ids.add(winget_id.lower())
        unique_name = software_name
        if unique_name.lower() in seen_names:
            unique_name = f"{software_name} ({winget_id})"
        seen_names.add(unique_name.lower())
        normalized_packages.append(
            {
                "software": unique_name,
                "install_type": "winget",
                "winget_id": winget_id,
                "notes": package.get("notes", "Pacote adicionado dinamicamente via busca WinGet."),
            }
        )

    if not normalized_packages:
        raise PackageProfileValidationError("Nenhum pacote dinamico valido foi informado para execucao.")

    return validate_package_profile(
        {
            "profile": profile_name,
            "description": "Perfil dinamico montado a partir da busca de programas no WinGet.",
            "packages": normalized_packages,
        }
    )


def _sanitize_dynamic_winget_id(raw_value: str | None) -> str:
    value = (raw_value or "").strip()
    if not value:
        return ""
    match = re.search(
        r"\b(?=[A-Za-z0-9._-]*[A-Za-z])[A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9][A-Za-z0-9_-]*)+\b",
        value,
    )
    if match:
        return match.group(0)
    return value.split()[0] if value.split() else ""


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

        prerequisites = package.get("prerequisites")
        if prerequisites is not None:
            if not isinstance(prerequisites, list) or not prerequisites:
                raise PackageProfileValidationError(
                    f"Pacote invalido na posicao {index}: 'prerequisites' deve ser uma lista nao vazia quando informada."
                )

            for prerequisite_index, prerequisite in enumerate(prerequisites, start=1):
                if not isinstance(prerequisite, dict):
                    raise PackageProfileValidationError(
                        f"Pacote invalido na posicao {index}: pre-requisito {prerequisite_index} deve ser um objeto."
                    )

                if not isinstance(prerequisite.get("software"), str) or not prerequisite["software"].strip():
                    raise PackageProfileValidationError(
                        f"Pacote invalido na posicao {index}: pre-requisito {prerequisite_index} precisa de 'software' nao vazio."
                    )

                prerequisite_detect_names = prerequisite.get("detect_names")
                if prerequisite_detect_names is not None and (
                    not isinstance(prerequisite_detect_names, list)
                    or not all(isinstance(item, str) and item.strip() for item in prerequisite_detect_names)
                ):
                    raise PackageProfileValidationError(
                        f"Pacote invalido na posicao {index}: 'prerequisites[{prerequisite_index}].detect_names' deve ser uma lista de strings nao vazias."
                    )

                prerequisite_fallback = prerequisite.get("fallback_installer")
                if prerequisite_fallback is None or not isinstance(prerequisite_fallback, dict):
                    raise PackageProfileValidationError(
                        f"Pacote invalido na posicao {index}: pre-requisito {prerequisite_index} exige 'fallback_installer' valido."
                    )

                if not isinstance(prerequisite_fallback.get("download_url"), str) or not prerequisite_fallback["download_url"].strip():
                    raise PackageProfileValidationError(
                        f"Pacote invalido na posicao {index}: 'prerequisites[{prerequisite_index}].fallback_installer.download_url' deve ser string nao vazia."
                    )

                prerequisite_install_args = prerequisite_fallback.get("install_args")
                if not isinstance(prerequisite_install_args, list) or not all(
                    isinstance(arg, str) for arg in prerequisite_install_args
                ):
                    raise PackageProfileValidationError(
                        f"Pacote invalido na posicao {index}: 'prerequisites[{prerequisite_index}].fallback_installer.install_args' deve ser uma lista de strings."
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


def build_profile_endpoint_diagnostics(profile: dict) -> dict:
    """Resume riscos basicos de endpoints e cache do catalogo selecionado."""
    validated_profile = validate_package_profile(deepcopy(profile))
    downloads = []

    def collect_installer(owner_name: str, installer_key: str, installer_config: dict):
        if not installer_config:
            return
        download_url = installer_config.get("download_url", "")
        file_name = installer_config.get("file_name", "") or Path(urlparse(download_url).path).name or "installer.exe"
        parsed = urlparse(download_url)
        downloads.append(
            {
                "owner": owner_name,
                "installer_key": installer_key,
                "download_url": download_url,
                "scheme": parsed.scheme.lower(),
                "host": parsed.netloc.lower(),
                "file_name": file_name.lower(),
            }
        )

    for package in validated_profile["packages"]:
        collect_installer(package["software"], "fallback_installer", package.get("fallback_installer"))
        collect_installer(package["software"], "official_download", package.get("official_download"))
        for prerequisite in package.get("prerequisites", []):
            collect_installer(
                f"{package['software']}::{prerequisite['software']}",
                "fallback_installer",
                prerequisite.get("fallback_installer"),
            )

    issues = []
    non_https = [item for item in downloads if item["scheme"] and item["scheme"] != "https"]
    if non_https:
        issues.extend(
            f"Download nao HTTPS em {item['owner']} ({item['installer_key']}): {item['download_url']}"
            for item in non_https
        )

    file_name_counts = Counter(item["file_name"] for item in downloads if item["file_name"])
    duplicate_file_names = {name for name, count in file_name_counts.items() if count > 1}
    for file_name in sorted(duplicate_file_names):
        owners = [item["owner"] for item in downloads if item["file_name"] == file_name]
        issues.append(
            f"Nome de arquivo duplicado no cache '{file_name}' usado por: {', '.join(owners)}"
        )

    missing_hosts = [item for item in downloads if not item["host"]]
    if missing_hosts:
        issues.extend(
            f"Endpoint sem host valido em {item['owner']} ({item['installer_key']}): {item['download_url']}"
            for item in missing_hosts
        )

    detail = (
        f"Diagnostico de endpoints do catalogo: downloads={len(downloads)} | "
        f"hosts={len({item['host'] for item in downloads if item['host']})} | "
        f"problemas={len(issues)}"
    )
    return {
        "downloads": downloads,
        "issues": issues,
        "detail": detail,
    }


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


def save_package_profile(profile: dict, target_path: str | Path) -> Path:
    """Persiste um perfil JSON validado para reutilizacao posterior."""
    validated_profile = validate_package_profile(deepcopy(profile))
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(validated_profile, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return path


def load_ads_lab_profile() -> dict:
    """Mantido por compatibilidade com chamadas legadas do laboratorio ADS."""
    return load_profile_by_name('ads_lab')
