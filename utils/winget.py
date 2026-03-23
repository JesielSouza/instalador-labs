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
        self.default_source = "winget"
        self.source_repair_error_markers = (
            "failed when opening source",
            "source reset",
            "0x8a15000f",
            "2316632079",
        )

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
        return self.check_package_status_details(package_id)["found"]

    def check_package_status_details(self, package_id: str) -> dict:
        """Retorna diagnosticos completos da consulta `winget list --id`."""
        result = self._run_winget_command(self._build_package_command_args("list", package_id))
        stdout = result["stdout"]
        found = result["success"] and package_id.lower() in stdout.lower()
        detail = self._summarize_result(result, "consulta do pacote")
        return {
            **result,
            "found": found,
            "detail": detail,
        }

    def install_package(self, package_id: str) -> bool:
        """Executa a instalacao silenciosa de um pacote."""
        return self.install_package_details(package_id)["success"]

    def install_package_details(self, package_id: str) -> dict:
        """Executa a instalacao silenciosa com retorno detalhado para auditoria."""
        result = self._run_winget_command_with_source_repair(
            self._build_package_command_args(
                "install",
                package_id,
                extra_args=[
                    "--silent",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                    "--disable-interactivity",
                ],
            ),
            repair_label="instalacao do pacote",
        )
        detail = self._summarize_result(result, "instalacao do pacote")
        return {
            **result,
            "detail": detail,
        }

    def upgrade_package(self, package_id: str) -> bool:
        """Executa a atualizacao silenciosa de um pacote."""
        return self.upgrade_package_details(package_id)["success"]

    def upgrade_package_details(self, package_id: str) -> dict:
        """Executa a atualizacao silenciosa com retorno detalhado para auditoria."""
        result = self._run_winget_command_with_source_repair(
            self._build_package_command_args(
                "upgrade",
                package_id,
                extra_args=[
                    "--silent",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                    "--disable-interactivity",
                ],
            ),
            repair_label="atualizacao do pacote",
        )
        detail = self._summarize_result(result, "atualizacao do pacote")
        return {
            **result,
            "detail": detail,
        }

    def uninstall_package(self, package_id: str) -> bool:
        """Executa a desinstalacao silenciosa de um pacote."""
        return self.uninstall_package_details(package_id)["success"]

    def uninstall_package_details(self, package_id: str) -> dict:
        """Executa a desinstalacao silenciosa com retorno detalhado para auditoria."""
        result = self._run_winget_command_with_source_repair(
            self._build_package_command_args(
                "uninstall",
                package_id,
                extra_args=[
                    "--silent",
                    "--accept-source-agreements",
                    "--disable-interactivity",
                ],
            ),
            repair_label="desinstalacao do pacote",
        )
        detail = self._summarize_result(result, "desinstalacao do pacote")
        return {
            **result,
            "detail": detail,
        }

    def _build_package_command_args(
        self,
        action: str,
        package_id: str,
        extra_args: list[str] | None = None,
    ) -> list[str]:
        args = [
            action,
            "--id",
            package_id,
            "--exact",
            "--source",
            self.default_source,
        ]
        if extra_args:
            args.extend(extra_args)
        return args

    def _run_winget_command_with_source_repair(self, args: list[str], repair_label: str) -> dict:
        result = self._run_winget_command(args)
        if result["success"] or not self._looks_like_source_failure(result):
            return result

        repair_result = self.repair_sources()
        if not repair_result["success"]:
            repair_detail = self._summarize_result(repair_result, "recuperacao das fontes do WinGet")
            return {
                **result,
                "stderr": (
                    f"{result['stderr']} | {repair_detail}" if result["stderr"] else repair_detail
                ),
                "repair_attempted": True,
                "repair_succeeded": False,
                "repair_result": repair_result,
            }

        retried_result = self._run_winget_command(args)
        if retried_result["success"]:
            retried_result["repair_attempted"] = True
            retried_result["repair_succeeded"] = True
            retried_result["repair_result"] = repair_result
            return retried_result

        retry_detail = self._summarize_result(retried_result, repair_label)
        return {
            **retried_result,
            "stderr": (
                f"{retried_result['stderr']} | Sources do WinGet foram resetadas e atualizadas, "
                f"mas a operacao ainda falhou. {retry_detail}"
            ).strip(),
            "repair_attempted": True,
            "repair_succeeded": True,
            "repair_result": repair_result,
        }

    def repair_sources(self) -> dict:
        reset_result = self._run_winget_command(
            [
                "source",
                "reset",
                "--force",
                "--disable-interactivity",
            ]
        )
        if not reset_result["success"]:
            return reset_result

        update_result = self._run_winget_command(
            [
                "source",
                "update",
                "--disable-interactivity",
            ]
        )
        if update_result["success"]:
            combined_stdout = " ".join(
                part for part in (reset_result["stdout"], update_result["stdout"]) if part
            ).strip()
            combined_stderr = " ".join(
                part for part in (reset_result["stderr"], update_result["stderr"]) if part
            ).strip()
            return {
                "success": True,
                "returncode": update_result["returncode"],
                "stdout": combined_stdout,
                "stderr": combined_stderr,
                "command": [
                    [self.executable, "source", "reset", "--force", "--disable-interactivity"],
                    [self.executable, "source", "update", "--disable-interactivity"],
                ],
            }
        return update_result

    def _looks_like_source_failure(self, result: dict) -> bool:
        haystack = " ".join(
            part for part in (result.get("stdout", ""), result.get("stderr", "")) if part
        ).lower()
        return any(marker in haystack for marker in self.source_repair_error_markers)

    def _run_winget_command(self, args: list[str]) -> dict:
        command = [self.executable, *args]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            return {
                "success": True,
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
                "command": command,
            }
        except subprocess.CalledProcessError as error:
            return {
                "success": False,
                "returncode": error.returncode,
                "stdout": (error.stdout or "").strip(),
                "stderr": (error.stderr or "").strip(),
                "command": command,
            }
        except Exception as error:
            return {
                "success": False,
                "returncode": None,
                "stdout": "",
                "stderr": str(error),
                "command": command,
            }

    @staticmethod
    def _summarize_result(result: dict, operation_label: str) -> str:
        if result["success"]:
            return f"Sucesso na {operation_label}."

        message = result["stderr"] or result["stdout"] or "Sem saida detalhada do WinGet."
        message = " ".join(message.split())
        if len(message) > 240:
            message = message[:237] + "..."

        if result.get("repair_attempted") and result.get("repair_succeeded"):
            message = (
                "As fontes do WinGet foram resetadas e atualizadas automaticamente antes da nova tentativa. "
                + message
            )
        elif result.get("repair_attempted"):
            message = (
                "O instalador tentou recuperar as fontes do WinGet automaticamente, mas sem sucesso. "
                + message
            )

        return (
            f"Falha na {operation_label}"
            + (f" (codigo {result['returncode']})" if result["returncode"] is not None else "")
            + f": {message}"
        )

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
