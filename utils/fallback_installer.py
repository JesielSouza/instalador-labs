import subprocess
import urllib.parse
import urllib.request
import winreg
from pathlib import Path

from config import DOWNLOADS_DIR


class DirectInstallerManager:
    """Gerencia fallback por instalador direto quando o WinGet nao esta acessivel."""

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

    def download_installer(self, package: dict, logger) -> Path:
        """Baixa o instalador oficial para cache local."""
        fallback = package["fallback_installer"]
        download_url = fallback["download_url"]
        file_name = fallback.get("file_name") or self._infer_file_name(download_url)
        target_dir = DOWNLOADS_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / file_name

        if target_path.exists():
            logger.info(
                f"Instalador em cache reutilizado para '{package['software']}'.",
                status="fallback_cached",
                package_name=package["software"],
            )
            return target_path

        logger.info(
            f"Baixando instalador oficial de '{package['software']}'...",
            status="fallback_downloading",
            package_name=package["software"],
        )
        urllib.request.urlretrieve(download_url, target_path)
        return target_path

    def install_package(self, package: dict, logger) -> bool:
        """Executa o fallback por instalador direto."""
        installer_path = self.download_installer(package, logger)
        install_args = package["fallback_installer"]["install_args"]

        logger.info(
            f"Executando fallback por instalador direto para '{package['software']}'.",
            status="fallback_installing",
            package_name=package["software"],
        )

        try:
            subprocess.run(
                [str(installer_path), *install_args],
                check=True,
                capture_output=True,
                text=True,
            )
            return True
        except subprocess.CalledProcessError as error:
            logger.error(
                f"Falha no fallback direto de '{package['software']}': {error.stderr.strip() or error.stdout.strip() or error}",
                status="fallback_install_error",
                package_name=package["software"],
            )
            return False

    @staticmethod
    def _infer_file_name(download_url: str) -> str:
        parsed = urllib.parse.urlparse(download_url)
        candidate = Path(parsed.path).name
        return candidate or "installer.exe"
