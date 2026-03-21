import ctypes
import sys

from utils.logger import LabLogger
from utils.package_loader import PackageProfileValidationError, load_ads_lab_profile
from utils.winget import WinGetManager


def is_admin():
    """Verifica se o script esta rodando com privilegios de Administrador."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def bootstrap():
    """Inicializa o sistema e valida requisitos basicos do ambiente."""
    logger = LabLogger()
    winget = WinGetManager()

    logger.info("Iniciando GSD - Instalador de Laboratorios...", status="bootstrap")

    if not is_admin():
        logger.error(
            "ERRO DE PRIVILEGIO: O script deve ser executado como Administrador.",
            status="bootstrap_error",
        )
        sys.exit(1)
    logger.info("Privilegios de Administrador confirmados.", status="bootstrap")

    if not winget.is_installed():
        logger.error(
            "WinGet nao encontrado no sistema. Abortando execucao.",
            status="bootstrap_error",
        )
        sys.exit(1)

    version = winget.get_version()
    logger.info(f"WinGet detectado: Versao {version}", status="bootstrap")
    logger.info(
        "Ambiente validado com sucesso. Pronto para carregar pacotes.",
        status="bootstrap",
    )
    return logger, winget


def load_package_catalog(logger):
    """Carrega o catalogo JSON padrao do laboratorio."""
    try:
        profile = load_ads_lab_profile()
    except (FileNotFoundError, PackageProfileValidationError) as error:
        logger.error(
            f"Falha ao carregar catalogo de pacotes: {error}",
            status="catalog_error",
        )
        sys.exit(1)

    package_count = len(profile.get("packages", []))
    logger.info(
        f"Catalogo carregado: perfil '{profile.get('profile', 'desconhecido')}' com {package_count} pacote(s).",
        status="catalog_loaded",
    )
    return profile


def process_package(package, logger, winget):
    """Processa um pacote do catalogo de acordo com seu tipo de instalacao."""
    package_name = package["software"]
    install_type = package["install_type"]
    winget_id = package.get("winget_id", "")

    if install_type == "manual":
        logger.warning(
            f"Pacote '{package_name}' requer instalacao manual. Nenhuma acao automatica executada.",
            status="manual",
            package_name=package_name,
        )
        return "manual"

    if install_type == "winget_pending":
        logger.warning(
            f"Pacote '{package_name}' esta marcado como winget_pending e sera apenas sinalizado para teste manual.",
            status="winget_pending",
            package_name=package_name,
        )
        return "pending"

    logger.info(
        f"Validando pacote '{package_name}' ({winget_id})...",
        status="checking",
        package_name=package_name,
    )

    if winget.check_package_status(winget_id):
        logger.success(package_name, status="already_installed")
        return "already_installed"

    logger.info(
        f"Iniciando instalacao automatizada de '{package_name}' ({winget_id}).",
        status="installing",
        package_name=package_name,
    )

    if winget.install_package(winget_id):
        logger.success(package_name, status="installed")
        return "installed"

    logger.error(
        f"Falha na instalacao automatizada de '{package_name}' ({winget_id}).",
        status="install_error",
        package_name=package_name,
    )
    return "failed"


def execute_package_plan(profile, logger, winget):
    """Executa o plano de processamento dos pacotes do perfil."""
    packages = profile.get("packages", [])
    if not packages:
        logger.warning(
            "O catalogo nao possui pacotes cadastrados. Nenhuma acao sera executada.",
            status="empty_catalog",
        )
        return {"installed": 0, "already_installed": 0, "pending": 0, "manual": 0, "failed": 0}

    results = {"installed": 0, "already_installed": 0, "pending": 0, "manual": 0, "failed": 0}

    for package in packages:
        result = process_package(package, logger, winget)
        if result in results:
            results[result] += 1

    logger.info(
        "Execucao concluida: "
        f"{results['installed']} instalado(s), "
        f"{results['already_installed']} ja presente(s), "
        f"{results['pending']} pendente(s), "
        f"{results['manual']} manual(is), "
        f"{results['failed']} falha(s).",
        status="execution_summary",
    )
    return results


if __name__ == "__main__":
    logger, winget = bootstrap()
    package_profile = load_package_catalog(logger)
    execution_results = execute_package_plan(package_profile, logger, winget)
    # Proxima fase (V3): gerar relatorio final em CSV na pasta reports
