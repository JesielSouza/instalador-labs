import subprocess
import unittest
from unittest.mock import patch

from utils.winget import WinGetManager


class WinGetManagerCommandTests(unittest.TestCase):
    def setUp(self):
        self.manager = WinGetManager()
        self.manager.executable = "winget"

    def test_check_package_status_uses_exact_id_and_winget_source(self):
        with patch("subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="Microsoft.VisualStudioCode",
                stderr="",
            )

            result = self.manager.check_package_status_details("Microsoft.VisualStudioCode")

        command = run_mock.call_args.args[0]
        self.assertEqual(
            command,
            [
                "winget",
                "list",
                "--id",
                "Microsoft.VisualStudioCode",
                "--exact",
                "--source",
                "winget",
            ],
        )
        self.assertTrue(result["found"])

    def test_install_uses_non_interactive_flags_and_winget_source(self):
        with patch("subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="",
                stderr="",
            )

            result = self.manager.install_package_details("Microsoft.VisualStudioCode")

        command = run_mock.call_args.args[0]
        self.assertEqual(
            command,
            [
                "winget",
                "install",
                "--id",
                "Microsoft.VisualStudioCode",
                "--exact",
                "--source",
                "winget",
                "--silent",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
        )
        self.assertTrue(result["success"])

    def test_uninstall_uses_winget_source_to_avoid_store_prompt(self):
        with patch("subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="",
                stderr="",
            )

            result = self.manager.uninstall_package_details("Microsoft.VisualStudioCode")

        command = run_mock.call_args.args[0]
        self.assertEqual(
            command,
            [
                "winget",
                "uninstall",
                "--id",
                "Microsoft.VisualStudioCode",
                "--exact",
                "--source",
                "winget",
                "--silent",
                "--accept-source-agreements",
            ],
        )
        self.assertTrue(result["success"])


if __name__ == "__main__":
    unittest.main()
