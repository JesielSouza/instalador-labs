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
                "--disable-interactivity",
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
                "--disable-interactivity",
            ],
        )
        self.assertTrue(result["success"])

    def test_install_repairs_sources_and_retries_when_winget_cannot_open_sources(self):
        with patch("subprocess.run") as run_mock:
            run_mock.side_effect = [
                subprocess.CalledProcessError(
                    returncode=2316632079,
                    cmd=[],
                    output="",
                    stderr="Failed when opening source(s); try the 'source reset' command.",
                ),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="Sources reset.", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="Sources updated.", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            ]

            result = self.manager.install_package_details("Microsoft.VisualStudioCode")

        commands = [call.args[0] for call in run_mock.call_args_list]
        self.assertEqual(
            commands[1],
            [
                "winget",
                "source",
                "reset",
                "--force",
                "--accept-source-agreements",
                "--disable-interactivity",
            ],
        )
        self.assertEqual(
            commands[2],
            [
                "winget",
                "source",
                "update",
                "--accept-source-agreements",
                "--disable-interactivity",
            ],
        )
        self.assertEqual(commands[3], commands[0])
        self.assertTrue(result["success"])
        self.assertTrue(result["repair_attempted"])
        self.assertTrue(result["repair_succeeded"])


if __name__ == "__main__":
    unittest.main()
