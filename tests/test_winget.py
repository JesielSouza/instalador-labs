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
                subprocess.CompletedProcess(args=[], returncode=0, stdout="v1.28.220", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="v1.28.220", stderr=""),
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
                subprocess.CompletedProcess(args=[], returncode=0, stdout="v1.28.220", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="v1.28.220", stderr=""),
            ]

            result = self.manager.ensure_client_ready()

        commands = [call.args[0] for call in run_mock.call_args_list]
        self.assertEqual(commands[0], ["winget", "--version"])
        self.assertEqual(commands[1], ["winget", "--version"])
        self.assertEqual(commands[2][1:], ["source", "list", "--disable-interactivity"])
        self.assertEqual(
            commands[3],
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "Add-AppxPackage -RegisterByFamilyName -MainPackage Microsoft.DesktopAppInstaller_8wekyb3d8bbwe",
            ],
        )
        self.assertEqual(commands[4][1:], ["source", "list", "--disable-interactivity"])
        self.assertEqual(commands[5][1:], ["--version"])
        self.assertEqual(
            commands[6],
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                (
                    "$bundle = Join-Path $env:TEMP 'Microsoft.DesktopAppInstaller.msixbundle'; "
                    "Invoke-WebRequest -UseBasicParsing -Uri 'https://aka.ms/getwinget' -OutFile $bundle; "
                    "Add-AppxPackage -Path $bundle -ForceApplicationShutdown"
                ),
            ],
        )
        self.assertEqual(commands[7][1:], ["source", "list", "--disable-interactivity"])
        self.assertEqual(commands[8][1:], ["--version"])
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

    def test_install_details_marks_timeout_when_winget_hangs(self):
        with patch("subprocess.run") as run_mock:
            run_mock.side_effect = subprocess.TimeoutExpired(
                cmd=["winget", "install"],
                timeout=900,
            )

            result = self.manager.install_package_details("Microsoft.VisualStudioCode")

        self.assertFalse(result["success"])
        self.assertTrue(result["timed_out"])
        self.assertIn("tempo limite", result["detail"].lower())

    def test_search_packages_uses_winget_source_and_parses_results(self):
        with patch("subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=(
                    "Name                           Id                               Version Source\n"
                    "--------------------------------------------------------------------------------\n"
                    "Visual Studio Code             Microsoft.VisualStudioCode       1.99.0  winget\n"
                    "Visual Studio Code Insiders    Microsoft.VisualStudioCode.Insiders 1.100.0 winget\n"
                ),
                stderr="",
            )

            result = self.manager.search_packages("visual studio code")

        command = run_mock.call_args.args[0]
        self.assertEqual(
            command,
            [
                "winget",
                "search",
                "visual studio code",
                "--source",
                "winget",
                "--accept-source-agreements",
                "--disable-interactivity",
            ],
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["results"][0]["id"], "Microsoft.VisualStudioCode")
        self.assertEqual(result["results"][1]["name"], "Visual Studio Code Insiders")
        self.assertEqual(result["results"][0]["confidence"], "alta")
        self.assertGreaterEqual(result["results"][0]["score"], result["results"][1]["score"])
        self.assertEqual(result["results"][0]["automation_hint"], "trusted")
        self.assertEqual(result["results"][0]["automation_label"], "Bom para automacao")

    def test_search_packages_parses_vlc_style_columns_without_merging_name_and_id(self):
        with patch("subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=(
                    "Name                          Id                           Version      Match          Source\n"
                    "-------------------------------------------------------------------------------------------------\n"
                    "VLC media player              VideoLAN.VLC                 3.0.23                       winget\n"
                    "VLC media player skins pack   VideoLAN.VLCSkinsPack       12.0                         winget\n"
                ),
                stderr="",
            )

            result = self.manager.search_packages("vlc")

        self.assertTrue(result["success"])
        self.assertEqual(result["results"][0]["name"], "VLC media player")
        self.assertEqual(result["results"][0]["id"], "VideoLAN.VLC")
        self.assertEqual(result["results"][1]["id"], "VideoLAN.VLCSkinsPack")

    def test_search_packages_parses_match_column_without_source_column(self):
        with patch("subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=(
                    "Name                           Id                               Version                Match\n"
                    "------------------------------------------------------------------------------------------------\n"
                    "VLC media player               VideoLAN.VLC                     3.0.23                 Moniker: vlc\n"
                    "Antigravity                    Google.Antigravity               1.20.5\n"
                ),
                stderr="",
            )

            result = self.manager.search_packages("vlc")

        self.assertTrue(result["success"])
        self.assertEqual(result["results"][0]["id"], "VideoLAN.VLC")
        self.assertEqual(result["results"][0]["version"], "3.0.23")
        self.assertEqual(result["results"][0]["source"], "")
        antigravity = next(item for item in result["results"] if item["name"] == "Antigravity")
        self.assertEqual(antigravity["id"], "Google.Antigravity")
        self.assertEqual(antigravity["version"], "1.20.5")

    def test_search_packages_parses_when_name_touches_id_column(self):
        with patch("subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=(
                    "Name                           Id                               Version                Match\n"
                    "------------------------------------------------------------------------------------------------\n"
                    "VLC media player VideoLAN.VLC                     3.0.23                 Moniker: vlc\n"
                ),
                stderr="",
            )

            result = self.manager.search_packages("vlc")

        self.assertTrue(result["success"])
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["name"], "VLC media player")
        self.assertEqual(result["results"][0]["id"], "VideoLAN.VLC")
        self.assertEqual(result["results"][0]["version"], "3.0.23")

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

    def test_proxy_diagnostics_recognize_direct_access_in_portuguese_without_false_positive(self):
        with patch.dict("os.environ", {}, clear=True), patch("subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="Configuracoes do proxy WinHTTP atuais:\n    Acesso direto (nenhum servidor proxy)",
                stderr="",
            )

            result = self.manager.get_proxy_diagnostics()

        self.assertFalse(result["active"])
        self.assertFalse(result["winhttp_proxy_active"])

    def test_ensure_client_ready_refreshes_outdated_client_before_install_flow(self):
        with patch("subprocess.run") as run_mock:
            run_mock.side_effect = [
                subprocess.CompletedProcess(args=[], returncode=0, stdout="v1.12.470", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="v1.12.470", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="winget source list", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="v1.28.220", stderr=""),
            ]

            result = self.manager.ensure_client_ready()

        commands = [call.args[0] for call in run_mock.call_args_list]
        self.assertEqual(commands[0], ["winget", "--version"])
        self.assertEqual(commands[1], ["winget", "--version"])
        self.assertEqual(
            commands[2],
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                (
                    "$bundle = Join-Path $env:TEMP 'Microsoft.DesktopAppInstaller.msixbundle'; "
                    "Invoke-WebRequest -UseBasicParsing -Uri 'https://aka.ms/getwinget' -OutFile $bundle; "
                    "Add-AppxPackage -Path $bundle -ForceApplicationShutdown"
                ),
            ],
        )
        self.assertEqual(commands[3][1:], ["source", "list", "--disable-interactivity"])
        self.assertEqual(commands[4][1:], ["--version"])
        self.assertTrue(result["healthy"])
        self.assertEqual(result["action"], "refreshed_outdated_client")
        self.assertEqual(result["final_version"], "v1.28.220")

    def test_get_windows_diagnostics_infers_windows_11_from_build_when_registry_is_legacy(self):
        fake_version = type("FakeVersion", (), {"major": 10, "minor": 0, "build": 26200})()
        with patch("sys.getwindowsversion", return_value=fake_version), patch.object(
            self.manager,
            "_read_windows_registry_value",
            side_effect=["Windows 10 Pro", "25H2", None],
        ):
            diagnostics = self.manager.get_windows_diagnostics()

        self.assertEqual(diagnostics["product_name"], "Windows 11 Pro")
        self.assertEqual(diagnostics["raw_product_name"], "Windows 10 Pro")

    def test_get_store_stack_diagnostics_flags_missing_components(self):
        with patch.object(
            self.manager,
            "get_appx_package_details",
            side_effect=[
                {"installed": False, "package_name": "Microsoft.DesktopAppInstaller", "version": "", "family": ""},
                {"installed": False, "package_name": "Microsoft.WindowsStore", "version": "", "family": ""},
            ],
        ), patch.object(
            self.manager,
            "get_service_details",
            side_effect=[
                {"available": False, "name": "AppXSvc", "state": "", "start_mode": ""},
                {"available": False, "name": "ClipSVC", "state": "", "start_mode": ""},
                {"available": False, "name": "InstallService", "state": "", "start_mode": ""},
            ],
        ):
            diagnostics = self.manager.get_store_stack_diagnostics()

        self.assertIn("App Installer ausente", diagnostics["issues"])
        self.assertIn("Microsoft Store ausente", diagnostics["issues"])
        self.assertIn("AppXSvc indisponivel", diagnostics["issues"])

    def test_get_windows_update_diagnostics_flags_pending_update_and_disabled_service(self):
        with patch.object(
            self.manager,
            "_read_registry_key_exists",
            return_value=True,
        ), patch.object(
            self.manager,
            "get_service_details",
            side_effect=[
                {"available": True, "name": "UsoSvc", "state": "Running", "start_mode": "Manual"},
                {"available": True, "name": "wuauserv", "state": "Stopped", "start_mode": "Disabled"},
                {"available": True, "name": "BITS", "state": "Stopped", "start_mode": "Manual"},
            ],
        ):
            diagnostics = self.manager.get_windows_update_diagnostics()

        self.assertIn("Windows Update com reboot pendente", diagnostics["issues"])
        self.assertIn("wuauserv desabilitado", diagnostics["issues"])

    def test_get_execution_alias_diagnostics_flags_missing_resolved_binary(self):
        self.manager.executable = r"C:\nao-existe\winget.exe"

        diagnostics = self.manager.get_execution_alias_diagnostics()

        self.assertIn("Executavel resolvido do winget nao existe em disco: C:\\nao-existe\\winget.exe", diagnostics["issues"])

    def test_get_source_catalog_diagnostics_flags_missing_winget_source(self):
        with patch.object(
            self.manager,
            "_run_winget_command",
            return_value={"success": True, "stdout": "msstore", "stderr": "", "command": []},
        ):
            diagnostics = self.manager.get_source_catalog_diagnostics()

        self.assertIn("Source 'winget' ausente na configuracao do cliente", diagnostics["issues"])

    def test_get_store_policy_diagnostics_flags_enabled_blocking_policies(self):
        with patch.object(
            self.manager,
            "_read_registry_dword",
            side_effect=[1, 1, 0],
        ):
            diagnostics = self.manager.get_store_policy_diagnostics()

        self.assertIn("Politica RemoveWindowsStore ativa", diagnostics["issues"])
        self.assertIn("Politica DisableStoreApps ativa", diagnostics["issues"])
        self.assertIn("Politica EnableAppInstaller desabilitada", diagnostics["issues"])

    def test_get_windows_security_diagnostics_flags_security_issues(self):
        with patch.object(
            self.manager,
            "_read_registry_dword",
            side_effect=[0, None, 1],
        ), patch.object(
            self.manager,
            "get_service_details",
            return_value={"available": True, "name": "WinDefend", "state": "Stopped", "start_mode": "Disabled"},
        ):
            diagnostics = self.manager.get_windows_security_diagnostics()

        self.assertIn("Politica EnableSmartScreen desabilitada", diagnostics["issues"])
        self.assertIn("Politica DisableRealtimeMonitoring ativa", diagnostics["issues"])
        self.assertIn("Servico WinDefend desabilitado", diagnostics["issues"])


if __name__ == "__main__":
    unittest.main()
