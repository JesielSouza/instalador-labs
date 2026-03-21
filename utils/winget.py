import shutil
import subprocess
import sys
import winreg

from config import resolve_winget_executable


class WinGetManager:
    """
    Gerenciador de interface com o Windows Package Manager (WinGet).
    Focado em execucao silenciosa e captura de diagnosticos para auditoria.
    """

    def __init__(self):
        self.executable = shutil.which("winget") or resolve_winget_executable()

    def is_installed(self) -> bool:
        """Verifica se o WinGet esta acessivel no sistema."""
        return self.executable is not None

    def get_version(self) -> str:
        """Retorna a versao do WinGet instalada."""
        if not self.is_installed():
            return "Nao encontrado"

        try:
            result = subprocess.run(
                [self.executable, "--version"],
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return "Erro ao obter versao"

    def get_windows_diagnostics(self) -> dict:
        """Retorna diagnosticos do Windows para classificar a ausencia do WinGet."""
        version = sys.getwindowsversion()
        product_name = self._read_windows_registry_value("ProductName")
        display_version = self._read_windows_registry_value("DisplayVersion")
        release_id = self._read_windows_registry_value("ReleaseId")

        return {
            "major": version.major,
            "minor": version.minor,
            "build": version.build,
            "product_name": product_name or "Desconhecido",
            "display_version": display_version or release_id or "Desconhecida",
        }

    def classify_winget_state(self) -> dict:
        """
        Classifica o estado do WinGet no host atual.

        Regras praticas:
        - Build 17763+ (Windows 10 1809) e superior: base compativel com WinGet/App Installer.
        - LTSC costuma exigir estrategia degradada por ausencia de Store/App Installer.
        """
        diagnostics = self.get_windows_diagnostics()
        build = diagnostics["build"]
        product_name = diagnostics["product_name"]

        if self.is_installed():
            return {
                "state": "available",
                "reason": f"WinGet disponivel: {self.get_version()}",
                "diagnostics": diagnostics,
            }

        if build < 17763:
            return {
                "state": "unsupported_windows",
                "reason": (
                    f"Windows build {build} anterior ao baseline 17763 (Windows 10 1809) "
                    "necessario para WinGet/App Installer."
                ),
                "diagnostics": diagnostics,
            }

        if "LTSC" in product_name.upper():
            return {
                "state": "supported_build_without_winget",
                "reason": (
                    f"{product_name} build {build} atende o baseline tecnico, "
                    "mas esta sem WinGet/App Installer acessivel."
                ),
                "diagnostics": diagnostics,
            }

        return {
            "state": "missing_winget",
            "reason": f"Windows compativel (build {build}), mas o WinGet nao foi localizado.",
            "diagnostics": diagnostics,
        }

    def check_package_status(self, package_id: str) -> bool:
        """
        Verifica se um pacote ja esta instalado (Idempotencia).
        Retorna True se o pacote for encontrado pelo ID.
        """
        try:
            result = subprocess.run(
                [self.executable, "list", "--id", package_id],
                capture_output=True,
                text=True,
            )
            return package_id.lower() in result.stdout.lower()
        except Exception:
            return False

    def install_package(self, package_id: str) -> bool:
        """Executa a instalacao silenciosa de um pacote."""
        try:
            subprocess.run(
                [
                    self.executable,
                    "install",
                    "--id",
                    package_id,
                    "--silent",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError as error:
            print(f"Erro ao instalar {package_id}: {error.stderr}")
            return False

    @staticmethod
    def _read_windows_registry_value(value_name: str) -> str | None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            ) as registry_key:
                value, _ = winreg.QueryValueEx(registry_key, value_name)
                return str(value)
        except OSError:
            return None
