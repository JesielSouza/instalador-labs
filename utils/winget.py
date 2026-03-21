import shutil
import subprocess

from config import resolve_winget_executable

class WinGetManager:
    """
    Gerenciador de interface com o Windows Package Manager (WinGet).
    Focado em execução silenciosa e captura de logs para auditoria.
    """
    
    def __init__(self):
        self.executable = shutil.which("winget") or resolve_winget_executable()

    def is_installed(self) -> bool:
        """Verifica se o WinGet está acessível no PATH do sistema."""
        return self.executable is not None

    def get_version(self) -> str:
        """Retorna a versão do WinGet instalada."""
        if not self.is_installed():
            return "Não encontrado"
        
        try:
            result = subprocess.run(
                [self.executable, "--version"], 
                capture_output=True, 
                text=True, 
                check=True,
                encoding='utf-8' # Ajuste conforme necessário para o terminal Windows
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return "Erro ao obter versão"

    def check_package_status(self, package_id: str) -> bool:
        """
        Verifica se um pacote já está instalado (Idempotência).
        Retorna True se o pacote for encontrado pelo ID.
        """
        try:
            # Comando 'list' filtra pelo ID exato
            result = subprocess.run(
                [self.executable, "list", "--id", package_id],
                capture_output=True,
                text=True
            )
            return package_id.lower() in result.stdout.lower()
        except Exception:
            return False

    def install_package(self, package_id: str) -> bool:
        """
        Executa a instalação silenciosa de um pacote.
        --silent: instalação sem UI
        --accept-package-agreements: aceita termos automaticamente
        --accept-source-agreements: aceita termos da fonte (msstore/winget)
        """
        try:
            process = subprocess.run(
                [
                    self.executable, "install", "--id", package_id, 
                    "--silent", "--accept-package-agreements", "--accept-source-agreements"
                ],
                capture_output=True,
                text=True,
                check=True
            )
            return True
        except subprocess.CalledProcessError as e:
            # O Codex deve registrar este erro no brain/09-log-de-sessoes.md
            print(f"Erro ao instalar {package_id}: {e.stderr}")
            return False
