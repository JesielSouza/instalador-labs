import getpass
import logging
import os
import socket
from datetime import datetime

from colorama import Fore, Style, init

# Inicializa as cores do terminal (essencial para Windows)
init(autoreset=True)


class LabLogger:
    """
    Gerenciador de logs com suporte a cores no console e persistencia em arquivo.
    Focado na observabilidade do status de instalacao nos laboratorios.
    """

    def __init__(self, log_dir="logs"):
        self.log_dir = log_dir
        self.machine_name = socket.gethostname()
        self.user_name = getpass.getuser()

        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        self.log_file = os.path.join(
            self.log_dir,
            f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
        )

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
        print(f"{color}{prefix}{Style.RESET_ALL} {message}")
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
