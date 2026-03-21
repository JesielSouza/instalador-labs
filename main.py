import sys
import ctypes
from utils.logger import LabLogger
from utils.winget import WinGetManager

def is_admin():
    """Verifica se o script está rodando com privilégios de Administrador."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def bootstrap():
    """Inicializa o sistema, valida ambiente e requisitos."""
    logger = LabLogger()
    winget = WinGetManager()
    
    logger.info("Iniciando GSD - Instalador de Laboratórios...")

    # 1. Validação de Privilégios (Regra 02-regras-e-padroes)
    if not is_admin():
        logger.error("ERRO DE PRIVILÉGIO: O script deve ser executado como Administrador.")
        sys.exit(1)
    logger.info("Privilégios de Administrador confirmados.")

    # 2. Validação do WinGet
    if not winget.is_installed():
        logger.error("WinGet não encontrado no sistema. Abortando execução.")
        sys.exit(1)
    
    version = winget.get_version()
    logger.info(f"WinGet detectado: Versão {version}")
    
    logger.info("Ambiente validado com sucesso. Pronto para carregar pacotes.")
    return logger, winget

if __name__ == "__main__":
    logger, winget = bootstrap()
    # Próximas fases (V2): Carregar JSON e iniciar loop de instalação