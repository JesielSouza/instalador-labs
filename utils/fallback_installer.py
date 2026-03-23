import subprocess
import urllib.parse
import urllib.request
import winreg
from pathlib import Path

from config import DOWNLOADS_DIR, LOGS_DIR


class DirectInstallerManager:
    """Gerencia fallback por instalador direto e downloads oficiais catalogados."""

    _MSI_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")

    def is_package_present(self, package: dict) -> bool:
        detect_names = package.get("detect_names", [])
        if not detect_names:
            return False

        registry_roots = (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        )

        normalized_targets = [item.lower() for item in detect_names]

        for root, subkey in registry_roots:
            try:
                with winreg.OpenKey(root, subkey) as uninstall_key:
                    for index in range(winreg.QueryInfoKey(uninstall_key)[0]):
                        try:
                            child_name = winreg.EnumKey(uninstall_key, index)
                            with winreg.OpenKey(uninstall_key, child_name) as child_key:
                                display_name, _ = winreg.QueryValueEx(child_key, "DisplayName")
                                if any(target in str(display_name).lower() for target in normalized_targets):
                                    return True
                        except OSError:
                            continue
            except OSError:
                continue

        return False

    def download_installer(self, package: dict, logger, config_key: str = "fallback_installer") -> Path:
        """Baixa um instalador oficial catalogado para cache local."""
        installer_config = package.get(config_key)
        if not installer_config:
            raise ValueError(f"Pacote sem configuracao '{config_key}': {package['software']}")

        download_url = installer_config["download_url"]
        file_name = installer_config.get("file_name") or self._infer_file_name(download_url)
        target_dir = DOWNLOADS_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / file_name

        if target_path.exists():
            if self._looks_like_valid_installer(target_path):
                logger.info(
                    f"Instalador em cache reutilizado para '{package['software']}'.",
                    status="fallback_cached" if config_key == "fallback_installer" else "manual_download_cached",
                    package_name=package["software"],
                )
                return target_path

            target_path.unlink(missing_ok=True)

        logger.info(
            f"Baixando instalador oficial de '{package['software']}'...",
            status="fallback_downloading" if config_key == "fallback_installer" else "manual_downloading",
            package_name=package["software"],
        )
        urllib.request.urlretrieve(download_url, target_path)
        self._ensure_valid_installer_file(target_path)
        return target_path

    def download_manual_installer(self, package: dict, logger) -> Path:
        """Baixa um instalador oficial de item manual para acao assistida do operador."""
        return self.download_installer(package, logger, config_key="official_download")

    def install_package(self, package: dict, logger) -> bool:
        """Executa o fallback por instalador direto."""
        installer_path = self.download_installer(package, logger, config_key="fallback_installer")
        install_args = package["fallback_installer"]["install_args"]

        logger.info(
            f"Executando fallback por instalador direto para '{package['software']}'.",
            status="fallback_installing",
            package_name=package["software"],
        )

        try:
            command = self._build_install_command(installer_path, install_args)
            subprocess.run(command, check=True, capture_output=True, text=True)
            return True
        except subprocess.CalledProcessError as error:
            msi_log_hint = self._extract_msi_log_hint(command)
            logger.error(
                f"Falha no fallback direto de '{package['software']}': "
                f"{error.stderr.strip() or error.stdout.strip() or error}"
                + (f" | Log MSI: {msi_log_hint}" if msi_log_hint else ""),
                status="fallback_install_error",
                package_name=package["software"],
            )
            return False
        except OSError as error:
            logger.error(
                f"Falha no fallback direto de '{package['software']}': {error}",
                status="fallback_install_error",
                package_name=package["software"],
            )
            return False

    @staticmethod
    def _infer_file_name(download_url: str) -> str:
        parsed = urllib.parse.urlparse(download_url)
        candidate = Path(parsed.path).name
        return candidate or "installer.exe"

    @staticmethod
    def _build_install_command(installer_path: Path, install_args: list[str]) -> list[str]:
        if installer_path.suffix.lower() == ".msi":
            msi_log_dir = LOGS_DIR
            msi_log_dir.mkdir(parents=True, exist_ok=True)
            msi_log_path = msi_log_dir / f"{installer_path.stem}_msi.log"
            return [
                "msiexec.exe",
                "/i",
                str(installer_path),
                "/L*V",
                str(msi_log_path),
                *install_args,
            ]
        return [str(installer_path), *install_args]

    def _ensure_valid_installer_file(self, installer_path: Path) -> None:
        if not self._looks_like_valid_installer(installer_path):
            raise ValueError(
                f"Arquivo baixado em '{installer_path.name}' nao parece ser um instalador Windows valido."
            )

    def _looks_like_valid_installer(self, installer_path: Path) -> bool:
        try:
            with installer_path.open("rb") as installer_file:
                header = installer_file.read(8)
        except OSError:
            return False

        suffix = installer_path.suffix.lower()
        if suffix == ".exe":
            return header.startswith(b"MZ")
        if suffix == ".msi":
            return header.startswith(self._MSI_SIGNATURE)
        return bool(header)

    @staticmethod
    def _extract_msi_log_hint(command: list[str]) -> str:
        if len(command) < 5 or str(command[0]).lower() != "msiexec.exe":
            return ""
        for index, part in enumerate(command):
            if str(part).upper() == "/L*V" and index + 1 < len(command):
                return str(command[index + 1])
        return ""
