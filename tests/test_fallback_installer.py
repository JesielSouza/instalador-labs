import ssl
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch

import utils.fallback_installer as fallback_installer_module
from utils.fallback_installer import DirectInstallerManager


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, message, status="info", package_name="-"):
        self.messages.append(("info", status, package_name, message))

    def warning(self, message, status="warning", package_name="-"):
        self.messages.append(("warning", status, package_name, message))

    def error(self, message, status="error", package_name="-"):
        self.messages.append(("error", status, package_name, message))


class DirectInstallerManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = DirectInstallerManager()
        self.package = {
            "software": "Figma",
            "fallback_installer": {
                "download_url": "https://desktop.figma.com/win/FigmaSetup.exe",
                "file_name": "FigmaSetup.exe",
                "install_args": ["/S"],
            },
        }

    def test_build_install_command_uses_msiexec_for_msi(self):
        temp_dir = Path(".tmp-test-msi-logs")
        temp_dir.mkdir(exist_ok=True)
        try:
            with patch.object(fallback_installer_module, "LOGS_DIR", temp_dir):
                command = self.manager._build_install_command(Path(r"C:\tmp\mysql.msi"), ["/qn"])
            self.assertEqual(
                command,
                [
                    "msiexec.exe",
                    "/i",
                    r"C:\tmp\mysql.msi",
                    "/L*V",
                    str(temp_dir / "mysql_msi.log"),
                    "/qn",
                ],
            )
        finally:
            for child in temp_dir.glob("*"):
                child.unlink(missing_ok=True)
            temp_dir.rmdir()

    def test_download_installer_rejects_invalid_executable_payload(self):
        logger = FakeLogger()
        temp_dir = Path(".tmp-test-fallback-installer")
        temp_dir.mkdir(exist_ok=True)
        try:
            with patch("utils.fallback_installer.DOWNLOADS_DIR", temp_dir), patch(
                "urllib.request.urlretrieve"
            ) as urlretrieve_mock:
                def fake_download(_url, target_path):
                    Path(target_path).write_text("<html>not an exe</html>", encoding="utf-8")

                urlretrieve_mock.side_effect = fake_download

                with self.assertRaisesRegex(ValueError, "nao parece ser um instalador Windows valido"):
                    self.manager.download_installer(self.package, logger)
        finally:
            for child in temp_dir.glob("*"):
                child.unlink(missing_ok=True)
            temp_dir.rmdir()

    def test_download_installer_rejects_too_small_payload_even_with_valid_magic(self):
        logger = FakeLogger()
        temp_dir = Path(".tmp-test-fallback-small-installer")
        temp_dir.mkdir(exist_ok=True)
        try:
            with patch("utils.fallback_installer.DOWNLOADS_DIR", temp_dir), patch(
                "urllib.request.urlretrieve"
            ) as urlretrieve_mock:
                def fake_download(_url, target_path):
                    Path(target_path).write_bytes(b"MZtiny")

                urlretrieve_mock.side_effect = fake_download

                with self.assertRaisesRegex(ValueError, "arquivo muito pequeno"):
                    self.manager.download_installer(self.package, logger)
        finally:
            for child in temp_dir.glob("*"):
                child.unlink(missing_ok=True)
            temp_dir.rmdir()

    def test_install_package_handles_os_error_without_crashing(self):
        logger = FakeLogger()
        with patch.object(
            self.manager,
            "download_installer",
            return_value=Path(r"C:\tmp\FigmaSetup.exe"),
        ), patch("subprocess.run", side_effect=OSError(193, "%1 nao e um aplicativo Win32 valido")):
            result = self.manager.install_package(self.package, logger)

        self.assertFalse(result)
        self.assertTrue(any(item[0] == "error" for item in logger.messages))

    def test_download_installer_retries_with_powershell_after_ssl_error(self):
        logger = FakeLogger()
        temp_dir = Path(".tmp-test-fallback-ssl")
        temp_dir.mkdir(exist_ok=True)
        try:
            with patch("utils.fallback_installer.DOWNLOADS_DIR", temp_dir), patch(
                "urllib.request.urlretrieve",
                side_effect=ssl.SSLCertVerificationError(1, "certificate verify failed"),
            ), patch.object(DirectInstallerManager, "_download_with_powershell") as powershell_download_mock:
                def fake_powershell_download(_url, target_path):
                    Path(target_path).write_bytes(b"MZ" + (b"x" * 2048))

                powershell_download_mock.side_effect = fake_powershell_download

                installer_path = self.manager.download_installer(self.package, logger)

            self.assertEqual(installer_path, temp_dir / "FigmaSetup.exe")
            self.assertTrue(any(item[1] == "fallback_download_ssl_retry" for item in logger.messages))
        finally:
            for child in temp_dir.glob("*"):
                child.unlink(missing_ok=True)
            temp_dir.rmdir()

    def test_download_installer_retries_with_bits_after_powershell_failure(self):
        logger = FakeLogger()
        temp_dir = Path(".tmp-test-fallback-bits")
        temp_dir.mkdir(exist_ok=True)
        try:
            with patch("utils.fallback_installer.DOWNLOADS_DIR", temp_dir), patch(
                "urllib.request.urlretrieve",
                side_effect=ssl.SSLCertVerificationError(1, "certificate verify failed"),
            ), patch.object(
                DirectInstallerManager,
                "_download_with_powershell",
                side_effect=RuntimeError("PowerShell falhou"),
            ), patch.object(DirectInstallerManager, "_download_with_bits") as bits_download_mock:
                def fake_bits_download(_url, target_path):
                    Path(target_path).write_bytes(b"MZ" + (b"x" * 2048))

                bits_download_mock.side_effect = fake_bits_download

                installer_path = self.manager.download_installer(self.package, logger)

            self.assertEqual(installer_path, temp_dir / "FigmaSetup.exe")
            self.assertTrue(any(item[1] == "fallback_download_bits_retry" for item in logger.messages))
        finally:
            for child in temp_dir.glob("*"):
                child.unlink(missing_ok=True)
            temp_dir.rmdir()

    def test_install_package_handles_download_failure_without_crashing(self):
        logger = FakeLogger()
        with patch.object(
            self.manager,
            "download_installer",
            side_effect=RuntimeError("Falha SSL ao baixar arquivo"),
        ):
            result = self.manager.install_package(self.package, logger)

        self.assertFalse(result)
        self.assertTrue(any(item[0] == "error" for item in logger.messages))

    def test_install_package_fails_when_installer_finishes_without_detecting_software(self):
        logger = FakeLogger()
        package = {
            "software": "Figma",
            "detect_names": ["Figma"],
            "fallback_installer": {
                "download_url": "https://desktop.figma.com/win/FigmaSetup.exe",
                "file_name": "FigmaSetup.exe",
                "install_args": ["/S"],
            },
        }
        with patch.object(
            self.manager,
            "download_installer",
            return_value=Path(r"C:\tmp\FigmaSetup.exe"),
        ), patch.object(self.manager, "is_package_present", return_value=False), patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        ):
            result = self.manager.install_package(package, logger)

        self.assertFalse(result)
        self.assertTrue(any(item[0] == "error" for item in logger.messages))

    def test_extract_msi_log_hint_returns_log_path(self):
        hint = self.manager._extract_msi_log_hint(
            ["msiexec.exe", "/i", r"C:\tmp\mysql.msi", "/L*V", r"C:\logs\mysql_msi.log", "/qn"]
        )
        self.assertEqual(hint, r"C:\logs\mysql_msi.log")

    def test_install_package_runs_prerequisite_before_main_installer(self):
        logger = FakeLogger()
        package = {
            "software": "MySQL Workbench",
            "prerequisites": [
                {
                    "software": "Microsoft Visual C++ Redistributable (x64)",
                    "detect_names": ["Microsoft Visual C++ 2015-2022 Redistributable (x64)"],
                    "fallback_installer": {
                        "download_url": "https://example.invalid/vc_redist.x64.exe",
                        "install_args": ["/install", "/quiet", "/norestart"],
                    },
                }
            ],
            "fallback_installer": {
                "download_url": "https://example.invalid/mysql.msi",
                "install_args": ["/qn", "/norestart"],
            },
        }

        with patch.object(
            self.manager,
            "download_installer",
            side_effect=[Path(r"C:\tmp\vc_redist.x64.exe"), Path(r"C:\tmp\mysql.msi")],
        ), patch.object(
            self.manager,
            "is_package_present",
            side_effect=[False, True, False, True],
        ), patch(
            "subprocess.run"
        ) as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

            result = self.manager.install_package(package, logger)

        commands = [call.args[0] for call in run_mock.call_args_list]
        self.assertTrue(result)
        self.assertEqual(
            commands[0],
            [r"C:\tmp\vc_redist.x64.exe", "/install", "/quiet", "/norestart"],
        )
        self.assertEqual(commands[1][0:3], ["msiexec.exe", "/i", r"C:\tmp\mysql.msi"])

    def test_install_package_accepts_reboot_required_when_software_is_detected(self):
        logger = FakeLogger()
        package = {
            "software": "MySQL Workbench",
            "detect_names": ["MySQL Workbench 8.0 CE"],
            "fallback_installer": {
                "download_url": "https://example.invalid/mysql.msi",
                "install_args": ["/qn", "/norestart"],
            },
        }

        with patch.object(
            self.manager,
            "download_installer",
            return_value=Path(r"C:\tmp\mysql.msi"),
        ), patch.object(
            self.manager,
            "is_package_present",
            return_value=True,
        ), patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(
                returncode=3010,
                cmd=["msiexec.exe", "/i", r"C:\tmp\mysql.msi", "/qn"],
                stderr="Restart required",
            ),
        ):
            result = self.manager.install_package(package, logger)

        self.assertTrue(result)
        self.assertTrue(any(item[1] == "fallback_install_reboot_required" for item in logger.messages))

    def test_format_process_failure_explains_msi_1603(self):
        error = subprocess.CalledProcessError(
            returncode=1603,
            cmd=["msiexec.exe", "/i", r"C:\tmp\mysql.msi", "/qn"],
            stderr="Fatal error during installation",
        )

        detail = self.manager._format_process_failure(error)

        self.assertIn("1603", detail)
        self.assertIn("log MSI detalhado", detail)


if __name__ == "__main__":
    unittest.main()
