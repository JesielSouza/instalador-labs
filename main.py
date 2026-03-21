import ctypes
import csv
import sys
from datetime import datetime

from config import REPORTS_DIR
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

    winget_state = winget.classify_winget_state()
    diagnostics = winget_state["diagnostics"]
    logger.info(
        "Windows detectado: "
        f"{diagnostics['product_name']} | versao {diagnostics['display_version']} | build {diagnostics['build']}.",
        status="bootstrap",
    )

    if winget_state["state"] == "available":
        logger.info(winget_state["reason"], status="bootstrap")
    else:
        logger.warning(
            f"Modo degradado sem WinGet: {winget_state['reason']}",
            status="bootstrap_degraded",
        )

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

    if not winget.is_installed():
        logger.warning(
            f"Pacote '{package_name}' nao pode ser automatizado nesta maquina porque o WinGet nao esta disponivel.",
            status="winget_unavailable",
            package_name=package_name,
        )
        return "blocked"

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
        return {
            "installed": 0,
            "already_installed": 0,
            "pending": 0,
            "manual": 0,
            "failed": 0,
            "blocked": 0,
        }

    results = {
        "installed": 0,
        "already_installed": 0,
        "pending": 0,
        "manual": 0,
        "failed": 0,
        "blocked": 0,
    }

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
        f"{results['failed']} falha(s), "
        f"{results['blocked']} bloqueado(s).",
        status="execution_summary",
    )
    return results


def write_execution_report(profile, results, logger):
    """Gera um relatorio CSV simples a partir do resumo da execucao."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"execution_report_{timestamp}.csv"

    rows = [
        ("profile", profile.get("profile", "desconhecido")),
        ("description", profile.get("description", "")),
        ("total_packages", len(profile.get("packages", []))),
        ("installed", results["installed"]),
        ("already_installed", results["already_installed"]),
        ("pending", results["pending"]),
        ("manual", results["manual"]),
        ("failed", results["failed"]),
        ("blocked", results["blocked"]),
    ]

    with report_path.open("w", encoding="utf-8", newline="") as report_file:
        writer = csv.writer(report_file)
        writer.writerow(["metric", "value"])
        writer.writerows(rows)

    logger.info(
        f"Relatorio CSV gerado em '{report_path}'.",
        status="report_generated",
    )
    return report_path


if __name__ == "__main__":
    logger, winget = bootstrap()
    package_profile = load_package_catalog(logger)
    execution_results = execute_package_plan(package_profile, logger, winget)
    report_path = write_execution_report(package_profile, execution_results, logger)
