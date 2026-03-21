import logging
import os
from datetime import datetime
from colorama import Fore, Style, init

# Inicializa as cores do terminal (essencial para Windows)
init(autoreset=True)

class LabLogger:
    """
    Gerenciador de logs com suporte a cores no console e persistência em arquivo.
    Focado na observabilidade do status de instalação nos laboratórios.
    """
    
    def __init__(self, log_dir="logs"):
        self.log_dir = log_dir
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
            
        # Nome do arquivo baseado na data e hora da sessão
        self.log_file = os.path.join(
            self.log_dir, 
            f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        
        self._setup_logging()

    def _setup_logging(self):
        """Configura o logger para escrever no arquivo e no console."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s | %(levelname)s | %(message)s',
            handlers=[
                logging.FileHandler(self.log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger("InstaladorLabs")

    def info(self, message):
        """Log de informação geral (Verde no terminal)."""
        print(f"{Fore.GREEN}[INFO]{Style.RESET_ALL} {message}")
        self.logger.info(message)

    def warning(self, message):
        """Log de aviso/pendência (Amarelo no terminal)."""
        print(f"{Fore.YELLOW}[WARN]{Style.RESET_ALL} {message}")
        self.logger.warning(message)

    def error(self, message):
        """Log de erro crítico (Vermelho no terminal)."""
        print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} {message}")
        self.logger.error(message)

    def success(self, package_name):
        """Helper específico para sucesso de instalação."""
        msg = f"Sucesso: {package_name} instalado/validado."
        print(f"{Fore.CYAN}✔ {msg}{Style.RESET_ALL}")
        self.logger.info(msg)