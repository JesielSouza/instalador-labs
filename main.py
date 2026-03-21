import ctypes
import sys

from utils.logger import LabLogger
from utils.package_loader import load_ads_lab_profile
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

    logger.info("Iniciando GSD - Instalador de Laboratorios...")

    if not is_admin():
        logger.error("ERRO DE PRIVILEGIO: O script deve ser executado como Administrador.")
        sys.exit(1)
    logger.info("Privilegios de Administrador confirmados.")

    if not winget.is_installed():
        logger.error("WinGet nao encontrado no sistema. Abortando execucao.")
        sys.exit(1)

    version = winget.get_version()
    logger.info(f"WinGet detectado: Versao {version}")
    logger.info("Ambiente validado com sucesso. Pronto para carregar pacotes.")
    return logger, winget


def load_package_catalog(logger):
    """Carrega o catalogo JSON padrao do laboratorio."""
    profile = load_ads_lab_profile()
    package_count = len(profile.get("packages", []))
    logger.info(
        f"Catalogo carregado: perfil '{profile.get('profile', 'desconhecido')}' com {package_count} pacote(s)."
    )
    return profile


if __name__ == "__main__":
    logger, winget = bootstrap()
    package_profile = load_package_catalog(logger)
    # Proximas fases (V2): validar esquema do JSON e iniciar loop de instalacao
