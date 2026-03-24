import shutil
import subprocess
import sys
import time
import os
import unicodedata
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
        self.minimum_preferred_version = (1, 28, 0)
        self.systemic_install_failure = False
        self.systemic_install_failure_diagnostics = ""
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
        inferred_product_name = self._infer_windows_product_name(version.build, product_name)

        return {
            "major": version.major,
            "minor": version.minor,
            "build": version.build,
            "product_name": inferred_product_name,
            "raw_product_name": product_name or "Desconhecido",
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

    def get_proxy_diagnostics(self) -> dict:
        """Coleta sinais de proxy local que podem interferir no WinGet."""
        environment_values = {
            key: value
            for key, value in (
                ("HTTP_PROXY", os.environ.get("HTTP_PROXY")),
                ("HTTPS_PROXY", os.environ.get("HTTPS_PROXY")),
                ("ALL_PROXY", os.environ.get("ALL_PROXY")),
            )
            if value
        }
        netsh_result = self._run_system_command(["netsh", "winhttp", "show", "proxy"])
        netsh_text = " ".join(
            part for part in (netsh_result.get("stdout", ""), netsh_result.get("stderr", "")) if part
        ).strip()
        normalized_netsh = self._normalize_text(netsh_text)
        winhttp_proxy_active = (
            bool(netsh_result["success"])
            and "direct access (no proxy server)" not in normalized_netsh
            and "acesso direto (nenhum servidor proxy)" not in normalized_netsh
            and "acesso direto (sem servidor proxy)" not in normalized_netsh
        )
        proxy_active = bool(environment_values) or winhttp_proxy_active

        parts = []
        if environment_values:
            parts.append(
                "Variaveis de ambiente de proxy: "
                + ", ".join(f"{key}={value}" for key, value in environment_values.items())
            )
        if netsh_text:
            parts.append(f"WinHTTP: {' '.join(netsh_text.split())}")

        detail = " | ".join(parts) if parts else "Nenhum indicio local de proxy foi encontrado."
        return {
            "active": proxy_active,
            "environment": environment_values,
            "winhttp_proxy_active": winhttp_proxy_active,
            "detail": detail,
        }

    def build_network_guidance(self) -> str:
        proxy_info = self.get_proxy_diagnostics()
        if proxy_info["active"]:
            return (
                "Proxy ativo detectado. Em redes corporativas/campus, valide liberacao no proxy e no firewall "
                "para o trafego do WinGet/App Installer. "
                + proxy_info["detail"]
            )
        return "Sem indicio local de proxy; se a falha persistir, valide regras de firewall/proxy da rede."

    def validate_client_health(self) -> dict:
        """Valida se o cliente do WinGet responde a uma operacao basica de source."""
        result = self._run_winget_command(["source", "list", "--disable-interactivity"])
        if result["success"]:
            return {
                "healthy": True,
                "detail": "Cliente do WinGet respondeu normalmente ao listar as fontes.",
                "result": result,
            }

        return {
            "healthy": False,
            "detail": self._summarize_result(result, "validacao operacional do WinGet"),
            "result": result,
        }

    def ensure_client_ready(self) -> dict:
        """Tenta deixar o WinGet operacional antes do processamento dos pacotes."""
        proactive_refresh_result = None
        if self._needs_client_refresh():
            proactive_refresh_result = self.refresh_client_package()
            post_refresh_health = self.validate_client_health()
            if post_refresh_health["healthy"]:
                return {
                    "healthy": True,
                    "action": "refreshed_outdated_client",
                    "detail": "Cliente do WinGet atualizado preventivamente antes da execucao.",
                "health_result": post_refresh_health,
                "refresh_result": proactive_refresh_result,
                "initial_version": self._extract_version_from_refresh_result(proactive_refresh_result),
                "final_version": self.get_version(),
            }

        initial_version = self.get_version()
        initial_health = self.validate_client_health()
        if initial_health["healthy"]:
            return {
                "healthy": True,
                "action": "none",
                "detail": initial_health["detail"],
                "health_result": initial_health,
                "refresh_result": proactive_refresh_result,
                "initial_version": initial_version,
                "final_version": initial_version,
            }

        repair_result = self.repair_client_package()
        post_repair_health = self.validate_client_health()
        if post_repair_health["healthy"]:
            return {
                "healthy": True,
                "action": "reregistered_client",
                "detail": "Cliente do WinGet recuperado apos re-registro do App Installer.",
                "health_result": post_repair_health,
                "refresh_result": proactive_refresh_result,
                "repair_result": repair_result,
                "initial_version": initial_version,
                "final_version": self.get_version(),
            }

        refresh_result = self.refresh_client_package()
        post_refresh_health = self.validate_client_health()
        if post_refresh_health["healthy"]:
            return {
                "healthy": True,
                "action": "refreshed_client",
                "detail": "Cliente do WinGet recuperado apos atualizacao do App Installer.",
                "health_result": post_refresh_health,
                "repair_result": repair_result,
                "pre_refresh_result": proactive_refresh_result,
                "refresh_result": refresh_result,
                "initial_version": initial_version,
                "final_version": self.get_version(),
            }

        source_result = self.repair_sources()
        post_source_health = self.validate_client_health()
        return {
            "healthy": post_source_health["healthy"],
            "action": "full_recovery_attempt",
            "detail": (
                "O instalador tentou re-registrar, atualizar e resetar as fontes do WinGet. "
                + post_source_health["detail"]
            ),
            "health_result": post_source_health,
            "pre_refresh_result": proactive_refresh_result,
            "repair_result": repair_result,
            "refresh_result": refresh_result,
            "source_result": source_result,
            "initial_version": initial_version,
            "final_version": self.get_version(),
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
            "diagnostics": self._build_diagnostics(result),
        }

    def has_systemic_install_failure(self) -> bool:
        """Indica se o host ja exibiu falha sistemica do WinGet em instalacoes desta sessao."""
        return self.systemic_install_failure

    def get_systemic_install_failure_diagnostics(self) -> str:
        return self.systemic_install_failure_diagnostics

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
            "diagnostics": self._build_diagnostics(result),
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
            "diagnostics": self._build_diagnostics(result),
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

        client_repair_result = self.repair_client_package()
        if client_repair_result["success"]:
            retried_after_client_repair = self._run_winget_command(args)
            if retried_after_client_repair["success"]:
                retried_after_client_repair["repair_attempted"] = True
                retried_after_client_repair["repair_succeeded"] = True
                retried_after_client_repair["client_repair_attempted"] = True
                retried_after_client_repair["client_repair_succeeded"] = True
                retried_after_client_repair["client_repair_result"] = client_repair_result
                return retried_after_client_repair

        repair_result = self.repair_sources()
        if not repair_result["success"]:
            client_repair_detail = ""
            if client_repair_result.get("attempted"):
                client_repair_detail = self._summarize_result(
                    client_repair_result,
                    "recuperacao do App Installer/WinGet",
                )
            repair_detail = self._summarize_result(repair_result, "recuperacao das fontes do WinGet")
            combined_detail = " | ".join(
                part for part in (client_repair_detail, repair_detail) if part
            )
            return {
                **result,
                "stderr": " | ".join(
                    part for part in (result["stderr"], combined_detail) if part
                ),
                "repair_attempted": True,
                "repair_succeeded": False,
                "client_repair_attempted": client_repair_result.get("attempted", False),
                "client_repair_succeeded": client_repair_result["success"],
                "client_repair_result": client_repair_result,
                "repair_result": repair_result,
            }

        retried_result = self._run_winget_command(args)
        if retried_result["success"]:
            retried_result["repair_attempted"] = True
            retried_result["repair_succeeded"] = True
            retried_result["client_repair_attempted"] = client_repair_result.get("attempted", False)
            retried_result["client_repair_succeeded"] = client_repair_result["success"]
            retried_result["client_repair_result"] = client_repair_result
            retried_result["repair_result"] = repair_result
            return retried_result

        retry_detail = self._summarize_result(retried_result, repair_label)
        failed_result = {
            **retried_result,
            "stderr": (
                f"{retried_result['stderr']} | Sources do WinGet foram resetadas e atualizadas, "
                f"mas a operacao ainda falhou. {retry_detail}"
            ).strip(),
            "repair_attempted": True,
            "repair_succeeded": True,
            "client_repair_attempted": client_repair_result.get("attempted", False),
            "client_repair_succeeded": client_repair_result["success"],
            "client_repair_result": client_repair_result,
            "repair_result": repair_result,
        }
        if args and args[0] == "install":
            self._record_systemic_install_failure(failed_result)
        return failed_result

    def repair_client_package(self) -> dict:
        command = [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            (
                "Add-AppxPackage -RegisterByFamilyName "
                "-MainPackage Microsoft.DesktopAppInstaller_8wekyb3d8bbwe"
            ),
        ]
        result = self._run_system_command(command)
        result["attempted"] = True
        if result["success"]:
            time.sleep(2)
            self.executable = shutil.which("winget") or resolve_winget_executable()
        return result

    def refresh_client_package(self) -> dict:
        observed_version_before_refresh = self.get_version()
        command = [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            (
                "$bundle = Join-Path $env:TEMP 'Microsoft.DesktopAppInstaller.msixbundle'; "
                "Invoke-WebRequest -Uri 'https://aka.ms/getwinget' -OutFile $bundle; "
                "Add-AppxPackage -Path $bundle -ForceApplicationShutdown"
            ),
        ]
        result = self._run_system_command(command)
        result["attempted"] = True
        result["observed_version_before_refresh"] = observed_version_before_refresh
        if result["success"]:
            time.sleep(3)
            self.executable = shutil.which("winget") or resolve_winget_executable()
        return result

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
        return self._run_system_command(command)

    def _record_systemic_install_failure(self, result: dict) -> None:
        self.systemic_install_failure = True
        self.systemic_install_failure_diagnostics = self._build_diagnostics(result)

    def get_version_tuple(self) -> tuple[int, ...]:
        version_text = (self.get_version() or "").strip().lower().lstrip("v")
        parts = []
        for chunk in version_text.split("."):
            if not chunk.isdigit():
                break
            parts.append(int(chunk))
        return tuple(parts)

    def _needs_client_refresh(self) -> bool:
        version_tuple = self.get_version_tuple()
        if not version_tuple:
            return False
        return version_tuple < self.minimum_preferred_version

    @staticmethod
    def _infer_windows_product_name(build: int, raw_product_name: str | None) -> str:
        normalized = (raw_product_name or "").strip()
        if build >= 22000:
            if normalized and "windows 11" in normalized.lower():
                return normalized
            if normalized and "windows 10" in normalized.lower():
                return normalized.replace("Windows 10", "Windows 11")
            return "Windows 11"
        return normalized or "Windows"

    @staticmethod
    def _extract_version_from_refresh_result(refresh_result: dict | None) -> str:
        if not refresh_result:
            return "Desconhecida"
        return refresh_result.get("observed_version_before_refresh", "Desconhecida")

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value or "")
        ascii_only = "".join(char for char in normalized if not unicodedata.combining(char))
        return " ".join(ascii_only.lower().split())

    def _run_system_command(self, command: list[str]) -> dict:
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

        if result.get("client_repair_attempted") and result.get("client_repair_succeeded"):
            message = (
                "O instalador tentou reativar o App Installer/WinGet antes de repetir a operacao. "
                + message
            )
        elif result.get("client_repair_attempted"):
            message = (
                "O instalador tentou reativar o App Installer/WinGet automaticamente, mas sem sucesso. "
                + message
            )

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
    def _build_diagnostics(result: dict) -> str:
        command = " ".join(str(part) for part in result.get("command", []))
        stdout = " ".join((result.get("stdout") or "").split())
        stderr = " ".join((result.get("stderr") or "").split())

        if len(stdout) > 320:
            stdout = stdout[:317] + "..."
        if len(stderr) > 320:
            stderr = stderr[:317] + "..."

        sections = []
        if command:
            sections.append(f"comando={command}")
        if result.get("returncode") is not None:
            sections.append(f"codigo={result['returncode']}")
        if stdout:
            sections.append(f"stdout={stdout}")
        if stderr:
            sections.append(f"stderr={stderr}")
        return " | ".join(sections) if sections else "Sem diagnostico bruto do WinGet."

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
