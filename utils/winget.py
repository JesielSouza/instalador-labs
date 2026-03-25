import json
import locale
import re
import shutil
import subprocess
import sys
import time
import os
import unicodedata
import winreg
from pathlib import Path

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
        self.package_operation_timeout_seconds = 900
        self.metadata_operation_timeout_seconds = 120
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

    def get_store_stack_diagnostics(self) -> dict:
        """Diagnostica a presenca do App Installer e da Microsoft Store."""
        app_installer = self.get_appx_package_details("Microsoft.DesktopAppInstaller")
        store = self.get_appx_package_details("Microsoft.WindowsStore")
        appx_service = self.get_service_details("AppXSvc")
        clip_service = self.get_service_details("ClipSVC")
        install_service = self.get_service_details("InstallService")

        issues = []
        if not app_installer["installed"]:
            issues.append("App Installer ausente")
        if not store["installed"]:
            issues.append("Microsoft Store ausente")
        for label, service in (
            ("AppXSvc", appx_service),
            ("ClipSVC", clip_service),
            ("InstallService", install_service),
        ):
            if not service.get("available"):
                issues.append(f"{label} indisponivel")
            elif service.get("start_mode", "").lower() == "disabled":
                issues.append(f"{label} desabilitado")

        detail = (
            "Stack Store/App Installer: "
            f"AppInstaller={'presente' if app_installer['installed'] else 'ausente'}"
            + (f" ({app_installer['version']})" if app_installer.get("version") else "")
            + " | "
            f"Store={'presente' if store['installed'] else 'ausente'}"
            + (f" ({store['version']})" if store.get("version") else "")
            + " | "
            + f"AppXSvc={self._format_service_detail(appx_service)}"
            + " | "
            + f"ClipSVC={self._format_service_detail(clip_service)}"
            + " | "
            + f"InstallService={self._format_service_detail(install_service)}"
            + f" | winget_executavel={self.executable or 'nao localizado'}"
        )
        return {
            "app_installer": app_installer,
            "store": store,
            "services": {
                "AppXSvc": appx_service,
                "ClipSVC": clip_service,
                "InstallService": install_service,
            },
            "issues": issues,
            "detail": detail,
        }

    def get_windows_update_diagnostics(self) -> dict:
        """Coleta sinais locais de Windows Update pendente ou servicos essenciais indisponiveis."""
        pending_update = self._read_registry_key_exists(
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired"
        )
        uso_service = self.get_service_details("UsoSvc")
        wu_service = self.get_service_details("wuauserv")
        bits_service = self.get_service_details("BITS")

        issues = []
        if pending_update:
            issues.append("Windows Update com reboot pendente")
        for label, service in (
            ("UsoSvc", uso_service),
            ("wuauserv", wu_service),
            ("BITS", bits_service),
        ):
            if service.get("available") and service.get("start_mode", "").lower() == "disabled":
                issues.append(f"{label} desabilitado")

        detail = (
            "Diagnostico Windows Update: "
            f"reboot_required={'sim' if pending_update else 'nao'} | "
            f"UsoSvc={self._format_service_detail(uso_service)} | "
            f"wuauserv={self._format_service_detail(wu_service)} | "
            f"BITS={self._format_service_detail(bits_service)}"
        )
        return {
            "pending_update": pending_update,
            "services": {
                "UsoSvc": uso_service,
                "wuauserv": wu_service,
                "BITS": bits_service,
            },
            "issues": issues,
            "detail": detail,
        }

    def get_execution_alias_diagnostics(self) -> dict:
        """Diagnostica o caminho resolvido do winget e possiveis problemas de alias."""
        executable_path = self.executable or ""
        executable_exists = bool(executable_path) and Path(executable_path).exists()
        uses_windowsapps_alias = "windowsapps" in executable_path.lower()

        issues = []
        if not executable_path:
            issues.append("Executavel do winget nao resolvido")
        elif not executable_exists:
            issues.append(f"Executavel resolvido do winget nao existe em disco: {executable_path}")

        detail = (
            "Diagnostico de alias/executavel do WinGet: "
            f"caminho={executable_path or 'nao localizado'} | "
            f"existe={'sim' if executable_exists else 'nao'} | "
            f"windowsapps_alias={'sim' if uses_windowsapps_alias else 'nao'}"
        )
        return {
            "path": executable_path,
            "exists": executable_exists,
            "uses_windowsapps_alias": uses_windowsapps_alias,
            "issues": issues,
            "detail": detail,
        }

    def get_source_catalog_diagnostics(self) -> dict:
        """Coleta o estado das sources conhecidas do WinGet."""
        result = self._run_winget_command(["source", "list", "--disable-interactivity"])
        normalized_output = self._normalize_text(" ".join((result.get("stdout") or "").split()))
        winget_source_present = "winget" in normalized_output
        msstore_source_present = "msstore" in normalized_output

        issues = []
        if not result["success"]:
            issues.append("Falha ao listar as sources do WinGet")
        elif not winget_source_present:
            issues.append("Source 'winget' ausente na configuracao do cliente")

        detail = (
            "Diagnostico de sources do WinGet: "
            f"winget={'presente' if winget_source_present else 'ausente'} | "
            f"msstore={'presente' if msstore_source_present else 'ausente'}"
        )
        if result.get("stderr"):
            detail += f" | stderr={' '.join(result['stderr'].split())}"

        return {
            "success": result["success"],
            "winget_source_present": winget_source_present,
            "msstore_source_present": msstore_source_present,
            "issues": issues,
            "detail": detail,
        }

    def get_store_policy_diagnostics(self) -> dict:
        """Coleta sinais de politicas que podem afetar Store/App Installer."""
        remove_store = self._read_registry_dword(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Policies\Microsoft\WindowsStore",
            "RemoveWindowsStore",
        )
        disable_store_apps = self._read_registry_dword(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Policies\Microsoft\WindowsStore",
            "DisableStoreApps",
        )
        enable_app_installer = self._read_registry_dword(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Policies\Microsoft\Windows\AppInstaller",
            "EnableAppInstaller",
        )

        issues = []
        if remove_store == 1:
            issues.append("Politica RemoveWindowsStore ativa")
        if disable_store_apps == 1:
            issues.append("Politica DisableStoreApps ativa")
        if enable_app_installer == 0:
            issues.append("Politica EnableAppInstaller desabilitada")

        detail = (
            "Diagnostico de politicas Store/App Installer: "
            f"RemoveWindowsStore={remove_store if remove_store is not None else 'nao_configurado'} | "
            f"DisableStoreApps={disable_store_apps if disable_store_apps is not None else 'nao_configurado'} | "
            f"EnableAppInstaller={enable_app_installer if enable_app_installer is not None else 'nao_configurado'}"
        )
        return {
            "remove_store": remove_store,
            "disable_store_apps": disable_store_apps,
            "enable_app_installer": enable_app_installer,
            "issues": issues,
            "detail": detail,
        }

    def get_windows_security_diagnostics(self) -> dict:
        """Coleta sinais de Defender/SmartScreen que podem impactar binarios baixados."""
        smartscreen_shell = self._read_registry_dword(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Policies\Microsoft\Windows\System",
            "EnableSmartScreen",
        )
        smartscreen_store = self._read_registry_dword(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer",
            "SmartScreenEnabled",
        )
        realtime_monitoring = self._read_registry_dword(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Policies\Microsoft\Windows Defender\Real-Time Protection",
            "DisableRealtimeMonitoring",
        )
        defender_service = self.get_service_details("WinDefend")

        issues = []
        if smartscreen_shell == 0:
            issues.append("Politica EnableSmartScreen desabilitada")
        if realtime_monitoring == 1:
            issues.append("Politica DisableRealtimeMonitoring ativa")
        if defender_service.get("available") and defender_service.get("start_mode", "").lower() == "disabled":
            issues.append("Servico WinDefend desabilitado")

        detail = (
            "Diagnostico de seguranca do Windows: "
            f"EnableSmartScreen={smartscreen_shell if smartscreen_shell is not None else 'nao_configurado'} | "
            f"SmartScreenEnabled={smartscreen_store if smartscreen_store is not None else 'nao_configurado'} | "
            f"DisableRealtimeMonitoring={realtime_monitoring if realtime_monitoring is not None else 'nao_configurado'} | "
            f"WinDefend={self._format_service_detail(defender_service)}"
        )
        return {
            "smartscreen_shell": smartscreen_shell,
            "smartscreen_store": smartscreen_store,
            "realtime_monitoring": realtime_monitoring,
            "defender_service": defender_service,
            "issues": issues,
            "detail": detail,
        }

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
        result = self._run_winget_command(
            self._build_package_command_args("list", package_id),
            timeout_seconds=self.metadata_operation_timeout_seconds,
        )
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
            timeout_seconds=self.package_operation_timeout_seconds,
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
            timeout_seconds=self.package_operation_timeout_seconds,
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
            timeout_seconds=self.package_operation_timeout_seconds,
        )
        detail = self._summarize_result(result, "desinstalacao do pacote")
        return {
            **result,
            "detail": detail,
            "diagnostics": self._build_diagnostics(result),
        }

    def search_packages(self, query: str, limit: int = 12) -> dict:
        """Pesquisa pacotes no WinGet e retorna resultados resumidos para selecao dinamica."""
        cleaned_query = (query or "").strip()
        if not cleaned_query:
            return {
                "success": False,
                "query": cleaned_query,
                "results": [],
                "detail": "Consulta vazia para pesquisa de pacotes no WinGet.",
            }

        result = self._run_winget_command(
            [
                "search",
                cleaned_query,
                "--source",
                self.default_source,
                "--accept-source-agreements",
                "--disable-interactivity",
            ],
            timeout_seconds=self.metadata_operation_timeout_seconds,
        )
        parsed_results = self._parse_search_results(result.get("stdout", ""))
        ranked_results = self._rank_search_results(cleaned_query, parsed_results)
        return {
            **result,
            "query": cleaned_query,
            "results": ranked_results[:limit],
            "detail": self._summarize_result(result, "pesquisa de pacotes no WinGet"),
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

    @staticmethod
    def _parse_search_results(stdout: str) -> list[dict]:
        results = []
        lines = (stdout or "").splitlines()
        header_index = -1
        header_columns = []
        header_starts = []

        for index, raw_line in enumerate(lines):
            lowered = raw_line.strip().lower()
            if ("name" in lowered or "nome" in lowered) and "id" in lowered:
                header_index = index
                for match in re.finditer(r"\b(Name|Nome|Id|Version|Match|Source)\b", raw_line, flags=re.IGNORECASE):
                    header_columns.append(match.group(1).strip().lower())
                    header_starts.append(match.start())
                break

        if header_index == -1 or not header_columns or not header_starts:
            return results

        slice_bounds = header_starts + [None]
        for raw_line in lines[header_index + 1:]:
            line = raw_line.strip()
            if not line or line.startswith("-"):
                continue
            lowered = line.lower()
            if "no package found" in lowered or "nenhum pacote encontrado" in lowered:
                continue

            line_match = WinGetManager._parse_search_result_from_line_structure(line)
            if line_match:
                results.append(line_match)
                continue

            split_match = WinGetManager._parse_search_result_from_split_columns(line)
            if split_match:
                results.append(split_match)
                continue

            regex_match = re.match(
                r"^(?P<name>.+?)\s{2,}(?P<id>[A-Za-z0-9][\w\.-]+)\s{2,}(?P<version>\S+)(?:\s{2,}(?P<match>.*?))?\s{2,}(?P<source>\w+)\s*$",
                raw_line.rstrip(),
            )
            if regex_match:
                name = regex_match.group("name").strip()
                package_id = regex_match.group("id").strip()
                version = regex_match.group("version").strip()
                source = regex_match.group("source").strip()
                if "." in package_id:
                    results.append(
                        {
                            "name": name,
                            "id": package_id,
                            "version": version,
                            "source": source,
                            "score": 0,
                            "confidence": "baixa",
                            "automation_hint": "generico",
                            "automation_label": "Resultado generico",
                        }
                    )
                    continue

            parsed_columns = {}
            for index, column_name in enumerate(header_columns):
                start = slice_bounds[index]
                end = slice_bounds[index + 1]
                value = raw_line[start:end].strip() if end is not None else raw_line[start:].strip()
                parsed_columns[column_name] = value

            name = parsed_columns.get("name") or parsed_columns.get("nome") or ""
            package_id = parsed_columns.get("id", "")
            version = parsed_columns.get("version", "")
            source = parsed_columns.get("source", "")
            package_id = WinGetManager._sanitize_package_id(package_id)
            version = WinGetManager._sanitize_version(version)
            source = WinGetManager._sanitize_source(source)
            if not name or not package_id:
                continue
            if "." not in package_id:
                continue
            results.append(
                {
                    "name": name,
                    "id": package_id,
                    "version": version,
                    "source": source,
                    "score": 0,
                    "confidence": "baixa",
                    "automation_hint": "generico",
                    "automation_label": "Resultado generico",
                }
            )
        return results

    @staticmethod
    def _parse_search_result_from_line_structure(line: str) -> dict | None:
        working_line = line.strip()
        source = ""

        source_match = re.search(r"\s{2,}(winget|msstore)\s*$", working_line, flags=re.IGNORECASE)
        if source_match:
            source = source_match.group(1).lower()
            working_line = working_line[:source_match.start()].rstrip()

        package_id_pattern = (
            r"\b(?=[A-Za-z0-9._-]*[A-Za-z])[A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9][A-Za-z0-9_-]*)+\b"
        )
        version_pattern = r"(?P<version>[<>~=vV]?\d[\w.\-+]*)"

        for package_id_match in reversed(list(re.finditer(package_id_pattern, working_line))):
            trailing_text = working_line[package_id_match.end():].strip()
            if not trailing_text:
                continue
            version_match = re.match(version_pattern, trailing_text, flags=re.IGNORECASE)
            if not version_match:
                continue
            name = working_line[:package_id_match.start()].strip()
            if not name:
                continue
            return {
                "name": name,
                "id": package_id_match.group(0),
                "version": version_match.group("version"),
                "source": source,
                "score": 0,
                "confidence": "baixa",
                "automation_hint": "generico",
                "automation_label": "Resultado generico",
            }
        return None

    @staticmethod
    def _parse_search_result_from_split_columns(line: str) -> dict | None:
        segments = [segment.strip() for segment in re.split(r"\s{2,}", line.strip()) if segment.strip()]
        if len(segments) < 2:
            return None

        name = segments[0]
        package_id = WinGetManager._sanitize_package_id(segments[1])
        if not name or not package_id or "." not in package_id:
            return None

        remainder = segments[2:]
        source = ""
        if remainder:
            possible_source = WinGetManager._sanitize_source(remainder[-1])
            if possible_source:
                source = possible_source
                remainder = remainder[:-1]

        version = ""
        if remainder:
            version = WinGetManager._sanitize_version(remainder[0])

        return {
            "name": name,
            "id": package_id,
            "version": version,
            "source": source,
            "score": 0,
            "confidence": "baixa",
            "automation_hint": "generico",
            "automation_label": "Resultado generico",
        }

    @staticmethod
    def _sanitize_package_id(raw_value: str) -> str:
        value = (raw_value or "").strip()
        if not value:
            return ""
        match = re.search(
            r"\b(?=[A-Za-z0-9._-]*[A-Za-z])[A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9][A-Za-z0-9_-]*)+\b",
            value,
        )
        if match:
            return match.group(0)
        first_token = value.split()[0] if value.split() else ""
        return first_token.strip()

    @staticmethod
    def _sanitize_version(raw_value: str) -> str:
        value = (raw_value or "").strip()
        if not value:
            return ""
        token = value.split()[0]
        if re.match(r"^(unknown|latest|[<>~=vV]?\d[\w.\-+]*)$", token, flags=re.IGNORECASE):
            return token
        return ""

    @staticmethod
    def _sanitize_source(raw_value: str) -> str:
        value = (raw_value or "").strip().lower()
        if value in {"winget", "msstore"}:
            return value
        return ""

    @classmethod
    def _rank_search_results(cls, query: str, results: list[dict]) -> list[dict]:
        normalized_query = cls._normalize_text(query)
        query_tokens = [token for token in normalized_query.split() if token]
        ranked = []

        for item in results:
            name = cls._normalize_text(item.get("name", ""))
            package_id = cls._normalize_text(item.get("id", ""))
            score = 0
            if name == normalized_query:
                score += 120
            if package_id == normalized_query:
                score += 120
            if normalized_query and normalized_query in name:
                score += 60
            if normalized_query and normalized_query in package_id:
                score += 40
            score += sum(8 for token in query_tokens if token in name)
            score += sum(5 for token in query_tokens if token in package_id)
            if (item.get("source") or "").lower() == "winget":
                score += 5

            confidence = "baixa"
            if score >= 120:
                confidence = "alta"
            elif score >= 60:
                confidence = "media"

            automation_hint = cls._classify_automation_hint(
                query=normalized_query,
                name=name,
                package_id=package_id,
                confidence=confidence,
            )
            automation_labels = {
                "trusted": "Bom para automacao",
                "likely_official": "Provavel pacote oficial",
                "generic": "Resultado generico",
            }

            ranked_item = dict(item)
            ranked_item["score"] = score
            ranked_item["confidence"] = confidence
            ranked_item["automation_hint"] = automation_hint
            ranked_item["automation_label"] = automation_labels[automation_hint]
            ranked.append(ranked_item)

        ranked.sort(key=lambda entry: (-entry["score"], entry.get("name", "").lower()))
        return ranked

    @staticmethod
    def _classify_automation_hint(query: str, name: str, package_id: str, confidence: str) -> str:
        if confidence == "alta" and "." in package_id and query and query in name:
            return "trusted"
        if "." in package_id and confidence in {"alta", "media"}:
            return "likely_official"
        return "generic"

    def _run_winget_command_with_source_repair(
        self,
        args: list[str],
        repair_label: str,
        timeout_seconds: int | None = None,
    ) -> dict:
        result = self._run_winget_command(args, timeout_seconds=timeout_seconds)
        if result["success"] or not self._looks_like_source_failure(result):
            return result

        client_repair_result = self.repair_client_package()
        if client_repair_result["success"]:
            retried_after_client_repair = self._run_winget_command(args, timeout_seconds=timeout_seconds)
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

        retried_result = self._run_winget_command(args, timeout_seconds=timeout_seconds)
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
                    "Invoke-WebRequest -UseBasicParsing -Uri 'https://aka.ms/getwinget' -OutFile $bundle; "
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

    def _run_winget_command(self, args: list[str], timeout_seconds: int | None = None) -> dict:
        command = [self.executable, *args]
        return self._run_system_command(command, timeout_seconds=timeout_seconds)

    def _record_systemic_install_failure(self, result: dict) -> None:
        self.systemic_install_failure = True
        self.systemic_install_failure_diagnostics = self._build_diagnostics(result)

    def get_appx_package_details(self, package_name: str) -> dict:
        safe_name = package_name.replace("'", "''")
        command = [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            (
                f"$pkg = Get-AppxPackage -Name '{safe_name}' | "
                "Select-Object -First 1 Name, Version, PackageFamilyName; "
                "if ($pkg) { $pkg | ConvertTo-Json -Compress }"
            ),
        ]
        result = self._run_system_command(command)
        if not result["success"] or not result["stdout"]:
            return {
                "installed": False,
                "package_name": package_name,
                "version": "",
                "family": "",
            }

        try:
            payload = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {
                "installed": False,
                "package_name": package_name,
                "version": "",
                "family": "",
            }

        return {
            "installed": True,
            "package_name": str(payload.get("Name") or package_name),
            "version": str(payload.get("Version") or ""),
            "family": str(payload.get("PackageFamilyName") or ""),
        }

    def get_service_details(self, service_name: str) -> dict:
        command = [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            (
                f"$svc = Get-CimInstance Win32_Service -Filter \"Name='{service_name}'\" | "
                "Select-Object -First 1 Name, State, StartMode; "
                "if ($svc) { $svc | ConvertTo-Json -Compress }"
            ),
        ]
        result = self._run_system_command(command)
        if not result["success"] or not result["stdout"]:
            return {
                "available": False,
                "name": service_name,
                "state": "",
                "start_mode": "",
            }

        try:
            payload = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {
                "available": False,
                "name": service_name,
                "state": "",
                "start_mode": "",
            }

        return {
            "available": True,
            "name": str(payload.get("Name") or service_name),
            "state": str(payload.get("State") or ""),
            "start_mode": str(payload.get("StartMode") or ""),
        }

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

    @staticmethod
    def _format_service_detail(service: dict) -> str:
        if not service.get("available"):
            return "indisponivel"
        return (
            f"{service.get('state', 'desconhecido')}/"
            f"{service.get('start_mode', 'desconhecido')}"
        )

    def _run_system_command(self, command: list[str], timeout_seconds: int | None = None) -> dict:
        preferred_encoding = locale.getpreferredencoding(False) or "utf-8"
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding=preferred_encoding,
                errors="replace",
                check=True,
                timeout=timeout_seconds,
            )
            return {
                "success": True,
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
                "command": command,
                "timed_out": False,
            }
        except subprocess.CalledProcessError as error:
            return {
                "success": False,
                "returncode": error.returncode,
                "stdout": (error.stdout or "").strip(),
                "stderr": (error.stderr or "").strip(),
                "command": command,
                "timed_out": False,
            }
        except subprocess.TimeoutExpired as error:
            return {
                "success": False,
                "returncode": None,
                "stdout": ((error.stdout or "") if isinstance(error.stdout, str) else "").strip(),
                "stderr": f"Comando excedeu o tempo limite de {timeout_seconds}s.".strip(),
                "command": command,
                "timed_out": True,
            }
        except Exception as error:
            return {
                "success": False,
                "returncode": None,
                "stdout": "",
                "stderr": str(error),
                "command": command,
                "timed_out": False,
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

    @staticmethod
    def _read_registry_key_exists(subkey_path: str) -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey_path):
                return True
        except OSError:
            return False

    @staticmethod
    def _read_registry_dword(root, subkey_path: str, value_name: str) -> int | None:
        try:
            with winreg.OpenKey(root, subkey_path) as registry_key:
                value, _ = winreg.QueryValueEx(registry_key, value_name)
                return int(value)
        except (OSError, ValueError, TypeError):
            return None
