import ctypes
import csv
import sys
from datetime import datetime

from config import REPORTS_DIR
from utils.fallback_installer import DirectInstallerManager
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
    direct_installer = DirectInstallerManager()

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
    return logger, winget, direct_installer


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


def process_package(package, logger, winget, direct_installer):
    """Processa um pacote do catalogo de acordo com seu tipo de instalacao."""
    package_name = package["software"]
    install_type = package["install_type"]
    winget_id = package.get("winget_id", "")
    result = {
        "package": package_name,
        "install_type": install_type,
        "winget_id": winget_id,
        "status": "",
        "install_method": "",
        "detail": "",
    }

    if install_type == "manual":
        logger.warning(
            f"Pacote '{package_name}' requer instalacao manual. Nenhuma acao automatica executada.",
            status="manual",
            package_name=package_name,
        )
        result["status"] = "manual"
        result["install_method"] = "manual"
        result["detail"] = "Requer intervencao manual."
        return result

    if install_type == "winget_pending":
        logger.warning(
            f"Pacote '{package_name}' esta marcado como winget_pending e sera apenas sinalizado para teste manual.",
            status="winget_pending",
            package_name=package_name,
        )
        result["status"] = "pending"
        result["install_method"] = "winget_pending"
        result["detail"] = "Aguardando validacao manual do fluxo WinGet."
        return result

    if not winget.is_installed():
        if direct_installer.is_package_present(package):
            logger.success(package_name, status="already_installed")
            result["status"] = "already_installed"
            result["install_method"] = "registry_detect"
            result["detail"] = "Pacote detectado no host sem necessidade de instalacao."
            return result

        if package.get("fallback_installer"):
            if direct_installer.install_package(package, logger):
                logger.success(package_name, status="installed")
                result["status"] = "installed"
                result["install_method"] = "fallback_direct"
                result["detail"] = "Instalado via instalador direto oficial."
                return result

            logger.error(
                f"Falha no fallback de instalacao de '{package_name}'.",
                status="fallback_failed",
                package_name=package_name,
            )
            result["status"] = "failed"
            result["install_method"] = "fallback_direct"
            result["detail"] = "Falha na execucao do instalador direto oficial."
            return result

        logger.warning(
            f"Pacote '{package_name}' nao pode ser automatizado nesta maquina porque o WinGet nao esta disponivel.",
            status="winget_unavailable",
            package_name=package_name,
        )
        result["status"] = "blocked"
        result["install_method"] = "blocked_no_winget"
        result["detail"] = "Sem WinGet acessivel e sem fallback direto configurado."
        return result

    logger.info(
        f"Validando pacote '{package_name}' ({winget_id})...",
        status="checking",
        package_name=package_name,
    )

    if winget.check_package_status(winget_id):
        logger.success(package_name, status="already_installed")
        result["status"] = "already_installed"
        result["install_method"] = "winget_detect"
        result["detail"] = "Pacote localizado pelo WinGet antes da instalacao."
        return result

    logger.info(
        f"Iniciando instalacao automatizada de '{package_name}' ({winget_id}).",
        status="installing",
        package_name=package_name,
    )

    if winget.install_package(winget_id):
        logger.success(package_name, status="installed")
        result["status"] = "installed"
        result["install_method"] = "winget"
        result["detail"] = "Instalado com sucesso pelo WinGet."
        return result

    logger.error(
        f"Falha na instalacao automatizada de '{package_name}' ({winget_id}).",
        status="install_error",
        package_name=package_name,
    )
    result["status"] = "failed"
    result["install_method"] = "winget"
    result["detail"] = "Falha na instalacao automatizada pelo WinGet."
    return result


def execute_package_plan(profile, logger, winget, direct_installer):
    """Executa o plano de processamento dos pacotes do perfil."""
    packages = profile.get("packages", [])
    if not packages:
        logger.warning(
            "O catalogo nao possui pacotes cadastrados. Nenhuma acao sera executada.",
            status="empty_catalog",
        )
        return {
            "summary": {
                "installed": 0,
                "already_installed": 0,
                "pending": 0,
                "manual": 0,
                "failed": 0,
                "blocked": 0,
            },
            "packages": [],
        }

    summary = {
        "installed": 0,
        "already_installed": 0,
        "pending": 0,
        "manual": 0,
        "failed": 0,
        "blocked": 0,
    }
    package_results = []

    for package in packages:
        package_result = process_package(package, logger, winget, direct_installer)
        package_results.append(package_result)
        status = package_result["status"]
        if status in summary:
            summary[status] += 1

    logger.info(
        "Execucao concluida: "
        f"{summary['installed']} instalado(s), "
        f"{summary['already_installed']} ja presente(s), "
        f"{summary['pending']} pendente(s), "
        f"{summary['manual']} manual(is), "
        f"{summary['failed']} falha(s), "
        f"{summary['blocked']} bloqueado(s).",
        status="execution_summary",
    )
    return {"summary": summary, "packages": package_results}


def write_execution_report(profile, results, logger):
    """Gera um relatorio CSV com resumo e rastreabilidade por pacote."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"execution_report_{timestamp}.csv"
    summary = results["summary"]
    package_results = results["packages"]

    summary_rows = [
        ("profile", profile.get("profile", "desconhecido")),
        ("description", profile.get("description", "")),
        ("total_packages", len(profile.get("packages", []))),
        ("installed", summary["installed"]),
        ("already_installed", summary["already_installed"]),
        ("pending", summary["pending"]),
        ("manual", summary["manual"]),
        ("failed", summary["failed"]),
        ("blocked", summary["blocked"]),
    ]

    with report_path.open("w", encoding="utf-8", newline="") as report_file:
        writer = csv.writer(report_file)
        writer.writerow(["section", "key", "value"])
        for key, value in summary_rows:
            writer.writerow(["summary", key, value])

        writer.writerow([])
        writer.writerow(
            [
                "packages",
                "software",
                "status",
                "install_method",
                "install_type",
                "winget_id",
                "detail",
            ]
        )
        for package_result in package_results:
            writer.writerow(
                [
                    "package",
                    package_result["package"],
                    package_result["status"],
                    package_result["install_method"],
                    package_result["install_type"],
                    package_result["winget_id"],
                    package_result["detail"],
                ]
            )

    logger.info(
        f"Relatorio CSV gerado em '{report_path}'.",
        status="report_generated",
    )
    return report_path


if __name__ == "__main__":
    logger, winget, direct_installer = bootstrap()
    package_profile = load_package_catalog(logger)
    execution_results = execute_package_plan(package_profile, logger, winget, direct_installer)
    report_path = write_execution_report(package_profile, execution_results, logger)
