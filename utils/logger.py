import getpass
import logging
import socket
from datetime import datetime
from pathlib import Path

from colorama import Fore, Style, init

from config import LOGS_DIR

# Inicializa as cores do terminal (essencial para Windows)
init(autoreset=True)


class LabLogger:
    """
    Gerenciador de logs com suporte a cores no console e persistencia em arquivo.
    Focado na observabilidade do status de instalacao nos laboratorios.
    """

    def __init__(self, log_dir=None, observer=None):
        self.log_dir = Path(log_dir) if log_dir else LOGS_DIR
        self.machine_name = socket.gethostname()
        self.user_name = getpass.getuser()
        self.observer = observer

        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.log_file = self.log_dir / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        self._setup_logging()

    def _setup_logging(self):
        """Configura o logger para escrever no arquivo e no console."""
        logger_name = f"InstaladorLabs.{id(self)}"
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.logger.handlers.clear()

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | machine=%(machine_name)s | user=%(user_name)s | "
            "status=%(status)s | package=%(package_name)s | %(message)s"
        )

        file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def _emit(self, level, prefix, color, message, status="general", package_name="-"):
        rendered_line = f"{prefix} {message}"
        print(f"{color}{rendered_line}{Style.RESET_ALL}")
        self.logger.log(
            level,
            message,
            extra={
                "machine_name": self.machine_name,
                "user_name": self.user_name,
                "status": status,
                "package_name": package_name,
            },
        )
        if self.observer:
            try:
                self.observer(rendered_line)
            except Exception:
                pass

    def info(self, message, status="info", package_name="-"):
        """Log de informacao geral."""
        self._emit(logging.INFO, "[INFO]", Fore.GREEN, message, status, package_name)

    def warning(self, message, status="warning", package_name="-"):
        """Log de aviso ou pendencia."""
        self._emit(logging.WARNING, "[WARN]", Fore.YELLOW, message, status, package_name)

    def error(self, message, status="error", package_name="-"):
        """Log de erro critico."""
        self._emit(logging.ERROR, "[ERROR]", Fore.RED, message, status, package_name)

    def success(self, package_name, status="success"):
        """Helper especifico para sucesso de instalacao."""
        msg = f"Sucesso: {package_name} instalado/validado."
        self._emit(logging.INFO, "[OK]", Fore.CYAN, msg, status, package_name)
