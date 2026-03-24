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

    def test_install_repairs_client_then_sources_and_retries_when_winget_cannot_open_sources(self):
        with patch("subprocess.run") as run_mock:
            run_mock.side_effect = [
                subprocess.CalledProcessError(
                    returncode=2316632079,
                    cmd=[],
                    output="",
                    stderr="Failed when opening source(s); try the 'source reset' command.",
                ),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
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
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "Add-AppxPackage -RegisterByFamilyName -MainPackage Microsoft.DesktopAppInstaller_8wekyb3d8bbwe",
            ],
        )
        self.assertEqual(commands[2][1:], commands[0][1:])
        self.assertTrue(str(commands[2][0]).lower().endswith("winget.exe"))
        self.assertEqual(commands[3][1:], ["source", "reset", "--force", "--disable-interactivity"])
        self.assertTrue(str(commands[3][0]).lower().endswith("winget.exe"))
        self.assertEqual(commands[4][1:], ["source", "update", "--disable-interactivity"])
        self.assertTrue(str(commands[4][0]).lower().endswith("winget.exe"))
        self.assertEqual(commands[5][1:], commands[0][1:])
        self.assertTrue(str(commands[5][0]).lower().endswith("winget.exe"))
        self.assertTrue(result["success"])
        self.assertTrue(result["repair_attempted"])
        self.assertTrue(result["repair_succeeded"])
        self.assertTrue(result["client_repair_attempted"])
        self.assertTrue(result["client_repair_succeeded"])

    def test_ensure_client_ready_refreshes_client_when_reregister_is_not_enough(self):
        with patch("subprocess.run") as run_mock:
            run_mock.side_effect = [
                subprocess.CalledProcessError(
                    returncode=2316632079,
                    cmd=[],
                    output="",
                    stderr="Failed when opening source(s); try the 'source reset' command.",
                ),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
                subprocess.CalledProcessError(
                    returncode=2316632079,
                    cmd=[],
                    output="",
                    stderr="Failed when opening source(s); try the 'source reset' command.",
                ),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="winget source list", stderr=""),
            ]

            result = self.manager.ensure_client_ready()

        commands = [call.args[0] for call in run_mock.call_args_list]
        self.assertEqual(commands[0][1:], ["source", "list", "--disable-interactivity"])
        self.assertEqual(
            commands[1],
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "Add-AppxPackage -RegisterByFamilyName -MainPackage Microsoft.DesktopAppInstaller_8wekyb3d8bbwe",
            ],
        )
        self.assertEqual(commands[2][1:], ["source", "list", "--disable-interactivity"])
        self.assertEqual(
            commands[3],
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                (
                    "$bundle = Join-Path $env:TEMP 'Microsoft.DesktopAppInstaller.msixbundle'; "
                    "Invoke-WebRequest -Uri 'https://aka.ms/getwinget' -OutFile $bundle; "
                    "Add-AppxPackage -Path $bundle -ForceApplicationShutdown"
                ),
            ],
        )
        self.assertEqual(commands[4][1:], ["source", "list", "--disable-interactivity"])
        self.assertTrue(result["healthy"])
        self.assertEqual(result["action"], "refreshed_client")

    def test_install_details_include_raw_diagnostics_for_failed_winget_command(self):
        with patch("subprocess.run") as run_mock:
            run_mock.side_effect = subprocess.CalledProcessError(
                returncode=1978335212,
                cmd=[],
                output="Installer failed in phase download.",
                stderr="The installer hash does not match.",
            )

            result = self.manager.install_package_details("Microsoft.VisualStudioCode")

        self.assertFalse(result["success"])
        self.assertIn("comando=", result["diagnostics"])
        self.assertIn("codigo=1978335212", result["diagnostics"])
        self.assertIn("stdout=Installer failed in phase download.", result["diagnostics"])
        self.assertIn("stderr=The installer hash does not match.", result["diagnostics"])

    def test_proxy_diagnostics_detect_winhttp_proxy(self):
        with patch.dict("os.environ", {}, clear=True), patch("subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="Current WinHTTP proxy settings:\n    Proxy Server(s) : proxy.campus.local:8080",
                stderr="",
            )

            result = self.manager.get_proxy_diagnostics()

        self.assertTrue(result["active"])
        self.assertTrue(result["winhttp_proxy_active"])
        self.assertIn("proxy.campus.local:8080", result["detail"])


if __name__ == "__main__":
    unittest.main()
