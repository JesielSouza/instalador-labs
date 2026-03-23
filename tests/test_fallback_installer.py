import unittest
from pathlib import Path
from unittest.mock import patch

from utils.fallback_installer import DirectInstallerManager


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, message, status="info", package_name="-"):
        self.messages.append(("info", status, package_name, message))

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
        command = self.manager._build_install_command(Path(r"C:\tmp\mysql.msi"), ["/qn"])
        self.assertEqual(command, ["msiexec.exe", "/i", r"C:\tmp\mysql.msi", "/qn"])

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

                with self.assertRaises(ValueError):
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


if __name__ == "__main__":
    unittest.main()
