import csv
import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

if "colorama" not in sys.modules:
    sys.modules["colorama"] = SimpleNamespace(
        Fore=SimpleNamespace(GREEN="", YELLOW="", RED="", CYAN=""),
        Style=SimpleNamespace(RESET_ALL=""),
        init=lambda autoreset=True: None,
    )

import main


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, message, status="info", package_name="-"):
        self.messages.append(("info", status, package_name, message))

    def warning(self, message, status="warning", package_name="-"):
        self.messages.append(("warning", status, package_name, message))

    def error(self, message, status="error", package_name="-"):
        self.messages.append(("error", status, package_name, message))

    def success(self, package_name, status="success"):
        self.messages.append(("success", status, package_name, package_name))


class FakeWinget:
    def __init__(
        self,
        installed=True,
        detected_ids=None,
        install_success_ids=None,
        install_timeout_ids=None,
        detect_after_timeout_ids=None,
        upgrade_success_ids=None,
        uninstall_success_ids=None,
        install_failure_detail=None,
        upgrade_failure_detail=None,
        uninstall_failure_detail=None,
    ):
        self.installed = installed
        self.detected_ids = set(detected_ids or [])
        self.install_success_ids = set(install_success_ids or [])
        self.install_timeout_ids = set(install_timeout_ids or [])
        self.detect_after_timeout_ids = set(detect_after_timeout_ids or [])
        self.upgrade_success_ids = set(upgrade_success_ids or [])
        self.uninstall_success_ids = set(uninstall_success_ids or [])
        self.install_failure_detail = install_failure_detail or "Falha na instalacao automatizada pelo WinGet."
        self.upgrade_failure_detail = upgrade_failure_detail or "Falha na atualizacao automatizada pelo WinGet."
        self.uninstall_failure_detail = uninstall_failure_detail or "Falha na desinstalacao automatizada pelo WinGet."
        self.systemic_install_failure = False
        self.systemic_install_failure_diagnostics = ""
        self.install_requests = []

    def is_installed(self):
        return self.installed

    def check_package_status(self, package_id):
        return package_id in self.detected_ids

    def check_package_status_details(self, package_id):
        found = package_id in self.detected_ids
        if not found and package_id in self.detect_after_timeout_ids and package_id in self.install_requests:
            found = True
        return {
            "found": found,
            "detail": "Pacote localizado pelo WinGet antes da operacao." if found else "Pacote nao localizado pelo WinGet antes da operacao.",
        }

    def install_package(self, package_id):
        return package_id in self.install_success_ids

    def install_package_details(self, package_id):
        self.install_requests.append(package_id)
        if package_id in self.install_timeout_ids:
            return {
                "success": False,
                "detail": "Falha na instalacao do pacote: Comando excedeu o tempo limite de 900s.",
                "diagnostics": f"comando=winget install --id {package_id} | timeout=900",
                "timed_out": True,
            }
        success = package_id in self.install_success_ids
        if not success and "2316632079" in self.install_failure_detail:
            self.systemic_install_failure = True
            self.systemic_install_failure_diagnostics = (
                f"comando=winget install --id {package_id} | codigo=2316632079"
            )
        return {
            "success": success,
            "detail": "Instalado com sucesso pelo WinGet." if success else self.install_failure_detail,
            "diagnostics": self.systemic_install_failure_diagnostics if not success else "",
            "timed_out": False,
        }

    def upgrade_package(self, package_id):
        return package_id in self.upgrade_success_ids

    def upgrade_package_details(self, package_id):
        success = package_id in self.upgrade_success_ids
        return {
            "success": success,
            "detail": "Atualizado com sucesso pelo WinGet." if success else self.upgrade_failure_detail,
        }

    def uninstall_package(self, package_id):
        return package_id in self.uninstall_success_ids

    def uninstall_package_details(self, package_id):
        success = package_id in self.uninstall_success_ids
        return {
            "success": success,
            "detail": "Desinstalado com sucesso pelo WinGet." if success else self.uninstall_failure_detail,
        }

    def has_systemic_install_failure(self):
        return self.systemic_install_failure

    def get_systemic_install_failure_diagnostics(self):
        return self.systemic_install_failure_diagnostics


class FakeDirectInstaller:
    def __init__(self, present_names=None, install_success_names=None, manual_download_paths=None):
        self.present_names = set(present_names or [])
        self.install_success_names = set(install_success_names or [])
        self.manual_download_paths = manual_download_paths or {}

    def is_package_present(self, package):
        return package["software"] in self.present_names

    def install_package(self, package, logger):
        return package["software"] in self.install_success_names

    def download_manual_installer(self, package, logger):
        software_name = package["software"]
        if software_name not in self.manual_download_paths:
            raise RuntimeError(f"Download manual nao configurado para {software_name}")
        return Path(self.manual_download_paths[software_name])


class ConfigRuntimeTests(unittest.TestCase):
    def test_resolve_dirs_use_bundle_for_resources_and_executable_for_runtime(self):
        import config

        original_frozen = getattr(sys, "frozen", None)
        original_meipass = getattr(sys, "_MEIPASS", None)
        original_executable = sys.executable
        had_frozen = hasattr(sys, "frozen")
        had_meipass = hasattr(sys, "_MEIPASS")

        sys.frozen = True
        sys._MEIPASS = r"C:\bundle"
        sys.executable = r"D:\Apps\InstaladorLabs\InstaladorLabs.exe"
        try:
            importlib.reload(config)
            self.assertEqual(str(config.RESOURCE_DIR), r"C:\bundle")
            self.assertEqual(str(config.RUNTIME_DIR), r"D:\Apps\InstaladorLabs")
            self.assertEqual(str(config.DEFAULT_PACKAGE_PROFILE), r"C:\bundle\packages\ads_lab.json")
            self.assertEqual(str(config.REPORTS_DIR), r"D:\Apps\InstaladorLabs\reports")
            self.assertEqual(str(config.LOGS_DIR), r"D:\Apps\InstaladorLabs\logs")
        finally:
            if had_frozen:
                sys.frozen = original_frozen
            else:
                delattr(sys, "frozen")

            if had_meipass:
                sys._MEIPASS = original_meipass
            else:
                delattr(sys, "_MEIPASS")

            sys.executable = original_executable
            importlib.reload(config)


class ExecutePackagePlanTests(unittest.TestCase):
    def test_execute_package_plan_summarizes_install_flow(self):
        profile = {
            "profile": "teste",
            "description": "cenario com winget disponivel",
            "packages": [
                {"software": "Ja Instalado", "install_type": "winget", "winget_id": "Vendor.Installed", "notes": "Detectado previamente."},
                {"software": "Instalacao OK", "install_type": "winget", "winget_id": "Vendor.Success", "notes": "Deve instalar."},
                {"software": "Instalacao Falha", "install_type": "winget", "winget_id": "Vendor.Fail", "notes": "Deve falhar."},
                {"software": "Pendente", "install_type": "winget_pending", "winget_id": "Vendor.Pending", "notes": "Ainda pendente."},
                {"software": "Manual", "install_type": "manual", "notes": "Intervencao humana."},
            ],
        }
        logger = FakeLogger()
        winget = FakeWinget(installed=True, detected_ids={"Vendor.Installed"}, install_success_ids={"Vendor.Success"})
        direct_installer = FakeDirectInstaller()

        results = main.execute_package_plan(profile, logger, winget, direct_installer, operation="install")

        self.assertEqual(results["operation"], "install")
        self.assertEqual(
            results["summary"],
            {
                "installed": 1,
                "already_installed": 1,
                "pending": 1,
                "manual": 1,
                "failed": 1,
                "blocked": 0,
            },
        )
        self.assertEqual(results["packages"][0]["install_method"], "winget_detect")
        self.assertEqual(results["packages"][1]["install_method"], "winget")
        self.assertEqual(results["packages"][2]["status"], "failed")
        self.assertEqual(results["packages"][3]["status"], "pending")
        self.assertEqual(results["packages"][4]["status"], "manual")

    def test_execute_package_plan_uses_fallback_and_blocks_without_winget(self):
        profile = {
            "profile": "teste",
            "description": "cenario degradado",
            "packages": [
                {
                    "software": "Fallback OK",
                    "install_type": "winget",
                    "winget_id": "Vendor.Fallback",
                    "fallback_installer": {"download_url": "https://example.invalid/fallback.exe", "install_args": ["/quiet"]},
                    "notes": "Fallback oficial.",
                },
                {"software": "Sem Automacao", "install_type": "winget", "winget_id": "Vendor.Blocked", "notes": "Sem winget nem fallback."},
            ],
        }
        logger = FakeLogger()
        winget = FakeWinget(installed=False)
        direct_installer = FakeDirectInstaller(install_success_names={"Fallback OK"})

        results = main.execute_package_plan(profile, logger, winget, direct_installer, operation="install")

        self.assertEqual(
            results["summary"],
            {
                "installed": 1,
                "already_installed": 0,
                "pending": 0,
                "manual": 0,
                "failed": 0,
                "blocked": 1,
            },
        )
        self.assertEqual(results["packages"][0]["install_method"], "fallback_direct")
        self.assertEqual(results["packages"][1]["install_method"], "blocked_no_winget")

    def test_execute_package_plan_detects_installed_package_via_registry_before_winget(self):
        profile = {
            "profile": "teste",
            "description": "deteccao local antes do winget",
            "packages": [
                {
                    "software": "Visual Studio Code",
                    "install_type": "winget",
                    "winget_id": "Microsoft.VisualStudioCode",
                    "detect_names": ["Microsoft Visual Studio Code"],
                    "notes": "Deve ser identificado localmente sem chamar winget install.",
                }
            ],
        }
        logger = FakeLogger()
        winget = FakeWinget(installed=True)
        direct_installer = FakeDirectInstaller(present_names={"Visual Studio Code"})

        results = main.execute_package_plan(profile, logger, winget, direct_installer, operation="install")

        self.assertEqual(results["summary"]["already_installed"], 1)
        self.assertEqual(results["packages"][0]["status"], "already_installed")
        self.assertEqual(results["packages"][0]["install_method"], "registry_detect")

    def test_execute_package_plan_preserves_detailed_install_failure_reason(self):
        profile = {
            "profile": "teste",
            "description": "falha detalhada do winget",
            "packages": [{"software": "Pacote Problematico", "install_type": "winget", "winget_id": "Vendor.Broken", "notes": "Deve expor o motivo da falha."}],
        }
        logger = FakeLogger()
        winget = FakeWinget(
            installed=True,
            install_failure_detail="Falha na instalacao do pacote (codigo 1978335212): instalador exigiu interacao manual.",
        )
        direct_installer = FakeDirectInstaller()

        results = main.execute_package_plan(profile, logger, winget, direct_installer, operation="install")

        self.assertEqual(results["summary"]["failed"], 1)
        self.assertEqual(results["packages"][0]["status"], "failed")
        self.assertIn("codigo 1978335212", results["packages"][0]["detail"])
        self.assertIn("interacao manual", results["packages"][0]["detail"])

    def test_execute_package_plan_uses_direct_fallback_after_retryable_winget_source_failure(self):
        profile = {
            "profile": "teste",
            "description": "falha recuperavel do winget com fallback direto",
            "packages": [
                {
                    "software": "Visual Studio Code",
                    "install_type": "winget",
                    "winget_id": "Microsoft.VisualStudioCode",
                    "fallback_installer": {"download_url": "https://example.invalid/vscode.exe", "install_args": ["/quiet"]},
                    "notes": "Deve cair para fallback quando o winget quebrar por source.",
                }
            ],
        }
        logger = FakeLogger()
        winget = FakeWinget(
            installed=True,
            install_failure_detail=(
                "Falha na instalacao do pacote (codigo 2316632079): "
                "As fontes do WinGet foram resetadas e atualizadas automaticamente antes da nova tentativa."
            ),
        )
        direct_installer = FakeDirectInstaller(install_success_names={"Visual Studio Code"})

        results = main.execute_package_plan(profile, logger, winget, direct_installer, operation="install")

        self.assertEqual(results["summary"]["installed"], 1)
        self.assertEqual(results["packages"][0]["status"], "installed")
        self.assertEqual(results["packages"][0]["install_method"], "fallback_direct_after_winget")
        self.assertIn("fallback direto oficial", results["packages"][0]["detail"])

    def test_execute_package_plan_uses_direct_fallback_after_retryable_winget_source_failure_for_catalog_package(self):
        profile = {
            "profile": "teste",
            "description": "falha recuperavel do winget com fallback direto em outro pacote",
            "packages": [
                {
                    "software": "XAMPP",
                    "install_type": "winget",
                    "winget_id": "ApacheFriends.Xampp.8.2",
                    "fallback_installer": {"download_url": "https://example.invalid/xampp.exe", "install_args": ["--mode", "unattended"]},
                    "notes": "Deve cair para fallback quando o winget falhar.",
                }
            ],
        }
        logger = FakeLogger()
        winget = FakeWinget(
            installed=True,
            install_failure_detail="Falha na instalacao do pacote (codigo 2316632079): Sources do WinGet foram resetadas e atualizadas, mas a operacao ainda falhou.",
        )
        direct_installer = FakeDirectInstaller(install_success_names={"XAMPP"})

        results = main.execute_package_plan(profile, logger, winget, direct_installer, operation="install")

        self.assertEqual(results["summary"]["installed"], 1)
        self.assertEqual(results["packages"][0]["install_method"], "fallback_direct_after_winget")

    def test_execute_package_plan_marks_installed_when_winget_times_out_but_package_is_present(self):
        profile = {
            "profile": "teste",
            "description": "timeout do winget com pacote detectado depois",
            "packages": [
                {
                    "software": "VLC media player",
                    "install_type": "winget",
                    "winget_id": "VideoLAN.VLC",
                    "notes": "Pode demorar e exceder o tempo limite do winget.",
                }
            ],
        }
        logger = FakeLogger()
        winget = FakeWinget(
            installed=True,
            install_timeout_ids={"VideoLAN.VLC"},
            detect_after_timeout_ids={"VideoLAN.VLC"},
        )
        direct_installer = FakeDirectInstaller()

        results = main.execute_package_plan(profile, logger, winget, direct_installer, operation="install")

        self.assertEqual(results["summary"]["installed"], 1)
        self.assertEqual(results["packages"][0]["status"], "installed")
        self.assertEqual(results["packages"][0]["install_method"], "winget_timeout_but_present")

    def test_execute_package_plan_bypasses_future_winget_installs_after_systemic_failure(self):
        profile = {
            "profile": "teste",
            "description": "falha sistemica do winget na mesma execucao",
            "packages": [
                {
                    "software": "Figma",
                    "install_type": "winget",
                    "winget_id": "Figma.Figma",
                    "fallback_installer": {"download_url": "https://example.invalid/figma.exe", "install_args": ["/S"]},
                    "notes": "Primeiro pacote dispara falha sistemica do winget.",
                },
                {
                    "software": "XAMPP",
                    "install_type": "winget",
                    "winget_id": "ApacheFriends.Xampp.8.2",
                    "fallback_installer": {"download_url": "https://example.invalid/xampp.exe", "install_args": ["--mode", "unattended"]},
                    "notes": "Segundo pacote deve pular o winget e ir direto ao fallback.",
                },
            ],
        }
        logger = FakeLogger()
        winget = FakeWinget(
            installed=True,
            install_failure_detail="Falha na instalacao do pacote (codigo 2316632079): Sources do WinGet foram resetadas e atualizadas, mas a operacao ainda falhou.",
        )
        direct_installer = FakeDirectInstaller(install_success_names={"Figma", "XAMPP"})

        results = main.execute_package_plan(profile, logger, winget, direct_installer, operation="install")

        self.assertEqual(results["summary"]["installed"], 2)
        self.assertEqual(results["packages"][0]["install_method"], "fallback_direct_after_winget")
        self.assertEqual(
            results["packages"][1]["install_method"],
            "fallback_direct_after_systemic_winget_failure",
        )

    def test_execute_package_plan_supports_update_operation(self):
        profile = {
            "profile": "teste",
            "description": "atualizacao controlada",
            "packages": [
                {"software": "Atualiza OK", "install_type": "winget", "winget_id": "Vendor.UpdateOK", "notes": "Atualizacao valida."},
                {"software": "Nao Instalado", "install_type": "winget", "winget_id": "Vendor.Missing", "notes": "Nao encontrado para atualizar."},
                {"software": "Manual", "install_type": "manual", "notes": "Atualizacao manual."},
            ],
        }
        logger = FakeLogger()
        winget = FakeWinget(installed=True, detected_ids={"Vendor.UpdateOK"}, upgrade_success_ids={"Vendor.UpdateOK"})
        direct_installer = FakeDirectInstaller()

        results = main.execute_package_plan(profile, logger, winget, direct_installer, operation="update")

        self.assertEqual(results["operation"], "update")
        self.assertEqual(
            results["summary"],
            {
                "updated": 1,
                "not_installed": 1,
                "pending": 0,
                "manual": 1,
                "failed": 0,
                "blocked": 0,
            },
        )
        self.assertEqual(results["packages"][0]["install_method"], "winget_upgrade")
        self.assertEqual(results["packages"][1]["status"], "not_installed")
        self.assertEqual(results["packages"][2]["status"], "manual")

    def test_execute_package_plan_installs_catalog_prerequisite_before_winget_package(self):
        profile = {
            "profile": "teste",
            "description": "pre-requisito declarado no catalogo",
            "packages": [
                {
                    "software": "MySQL Workbench",
                    "install_type": "winget",
                    "winget_id": "Oracle.MySQLWorkbench",
                    "detect_names": ["MySQL Workbench"],
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
                    "notes": "Deve instalar o pre-requisito antes do pacote principal.",
                }
            ],
        }
        logger = FakeLogger()
        winget = FakeWinget(installed=True, install_success_ids={"Oracle.MySQLWorkbench"})
        direct_installer = FakeDirectInstaller(install_success_names={"Microsoft Visual C++ Redistributable (x64)"})

        results = main.execute_package_plan(profile, logger, winget, direct_installer, operation="install")

        self.assertEqual(results["summary"]["installed"], 1)
        self.assertEqual(results["packages"][0]["install_method"], "winget")
        self.assertTrue(
            any(item[1] == "prerequisite_installed" for item in logger.messages),
            logger.messages,
        )

    def test_execute_package_plan_downloads_official_installer_for_manual_item(self):
        profile = {
            "profile": "teste",
            "description": "download oficial para item manual",
            "packages": [
                {
                    "software": "Astah Community",
                    "install_type": "manual",
                    "official_download": {
                        "download_url": "https://example.invalid/astah-installer.exe",
                        "file_name": "astah-installer.exe",
                    },
                    "notes": "Baixar instalador oficial e orientar operador.",
                }
            ],
        }
        logger = FakeLogger()
        winget = FakeWinget(installed=True)
        direct_installer = FakeDirectInstaller(
            manual_download_paths={
                "Astah Community": r"D:\Apps\InstaladorLabs\.downloads\astah-installer.exe"
            }
        )

        results = main.execute_package_plan(profile, logger, winget, direct_installer, operation="install")

        self.assertEqual(results["summary"]["manual"], 1)
        self.assertEqual(results["packages"][0]["status"], "manual")
        self.assertEqual(results["packages"][0]["install_method"], "manual_download")
        self.assertIn("astah-installer.exe", results["packages"][0]["detail"])

    def test_execute_package_plan_exposes_manual_reference_url_when_no_download_exists(self):
        profile = {
            "profile": "teste",
            "description": "referencia oficial para item manual",
            "packages": [
                {
                    "software": "Astah Community",
                    "install_type": "manual",
                    "manual_reference_url": "https://astah.net/products/astah-community/",
                    "notes": "Item manual com referencia oficial.",
                }
            ],
        }
        logger = FakeLogger()
        winget = FakeWinget(installed=True)
        direct_installer = FakeDirectInstaller()

        results = main.execute_package_plan(profile, logger, winget, direct_installer, operation="install")

        self.assertEqual(results["packages"][0]["status"], "manual")
        self.assertEqual(results["packages"][0]["install_method"], "manual")
        self.assertIn("https://astah.net/products/astah-community/", results["packages"][0]["detail"])

    def test_execute_package_plan_supports_uninstall_operation(self):
        profile = {
            "profile": "teste",
            "description": "desinstalacao controlada",
            "packages": [
                {"software": "Remove OK", "install_type": "winget", "winget_id": "Vendor.RemoveOK", "notes": "Desinstalacao valida."},
                {"software": "Nao Instalado", "install_type": "winget", "winget_id": "Vendor.Missing", "notes": "Nao encontrado para remover."},
                {"software": "Manual", "install_type": "manual", "notes": "Desinstalacao manual."},
            ],
        }
        logger = FakeLogger()
        winget = FakeWinget(installed=True, detected_ids={"Vendor.RemoveOK"}, uninstall_success_ids={"Vendor.RemoveOK"})
        direct_installer = FakeDirectInstaller()

        results = main.execute_package_plan(profile, logger, winget, direct_installer, operation="uninstall")

        self.assertEqual(results["operation"], "uninstall")
        self.assertEqual(
            results["summary"],
            {
                "removed": 1,
                "not_installed": 1,
                "pending": 0,
                "manual": 1,
                "failed": 0,
                "blocked": 0,
            },
        )
        self.assertEqual(results["packages"][0]["install_method"], "winget_uninstall")
        self.assertEqual(results["packages"][1]["status"], "not_installed")
        self.assertEqual(results["packages"][2]["status"], "manual")

    def test_execute_package_plan_switches_to_fallback_first_after_systemic_winget_failure(self):
        profile = {
            "profile": "teste",
            "description": "fallback-first apos falha sistemica do winget",
            "packages": [
                {
                    "software": "Primeiro Pacote",
                    "install_type": "winget",
                    "winget_id": "Vendor.FailFirst",
                    "fallback_installer": {"download_url": "https://example.invalid/first.exe", "install_args": ["/quiet"]},
                },
                {
                    "software": "Segundo Pacote",
                    "install_type": "winget",
                    "winget_id": "Vendor.FallbackSecond",
                    "fallback_installer": {"download_url": "https://example.invalid/second.exe", "install_args": ["/quiet"]},
                },
            ],
        }
        logger = FakeLogger()
        winget = FakeWinget(
            installed=True,
            install_failure_detail="Failed when opening source(s); try the 'source reset' command if the problem persists. codigo 2316632079",
        )
        direct_installer = FakeDirectInstaller(install_success_names={"Segundo Pacote"})

        results = main.execute_package_plan(profile, logger, winget, direct_installer, operation="install")

        self.assertEqual(winget.install_requests, ["Vendor.FailFirst"])
        self.assertEqual(results["packages"][0]["status"], "failed")
        self.assertEqual(
            results["packages"][1]["install_method"],
            "fallback_direct_after_systemic_winget_failure",
        )
        self.assertTrue(any(item[1] == "winget_session_degraded" for item in logger.messages))

    def test_load_package_catalog_warns_when_endpoint_diagnostics_find_issues(self):
        logger = FakeLogger()
        fake_profile = {
            "profile": "ads_lab",
            "description": "perfil de teste",
            "packages": [
                {
                    "software": "Pacote A",
                    "install_type": "winget",
                    "winget_id": "Vendor.A",
                    "fallback_installer": {
                        "download_url": "https://example.invalid/a.exe",
                        "file_name": "shared-installer.exe",
                        "install_args": ["/quiet"],
                    },
                },
                {
                    "software": "Pacote B",
                    "install_type": "manual",
                    "official_download": {
                        "download_url": "https://example.invalid/b.exe",
                        "file_name": "shared-installer.exe",
                    },
                },
            ],
        }

        with patch("main.load_default_package_profile", return_value=fake_profile), patch(
            "main.select_profile_packages",
            side_effect=lambda profile, selected: profile,
        ):
            profile = main.load_package_catalog(logger)

        self.assertEqual(profile["profile"], "ads_lab")
        self.assertTrue(any(item[1] == "catalog_endpoint_warning" for item in logger.messages))

    def test_load_package_catalog_warns_when_endpoint_connectivity_fails(self):
        logger = FakeLogger()
        fake_profile = {
            "profile": "ads_lab",
            "description": "perfil de teste",
            "packages": [
                {
                    "software": "Pacote A",
                    "install_type": "winget",
                    "winget_id": "Vendor.A",
                    "fallback_installer": {
                        "download_url": "https://example.invalid/a.exe",
                        "file_name": "a.exe",
                        "install_args": ["/quiet"],
                    },
                }
            ],
        }

        with patch("main.load_default_package_profile", return_value=fake_profile), patch(
            "main.select_profile_packages",
            side_effect=lambda profile, selected: profile,
        ), patch(
            "main.probe_catalog_endpoint_connectivity",
            return_value={
                "detail": "Diagnostico de conectividade dos endpoints: hosts_testados=1 | hosts_ok=0 | falhas=1",
                "issues": ["example.invalid: falha no teste HEAD (Timeout)"],
                "probes": [],
            },
        ):
            profile = main.load_package_catalog(logger)

        self.assertEqual(profile["profile"], "ads_lab")
        self.assertTrue(any(item[1] == "catalog_connectivity_warning" for item in logger.messages))

    def test_load_package_catalog_accepts_custom_dynamic_packages(self):
        logger = FakeLogger()

        profile = main.load_package_catalog(
            logger,
            custom_packages=[
                {"software": "Visual Studio Code", "winget_id": "Microsoft.VisualStudioCode"},
                {"software": "Python 3.12", "winget_id": "Python.Python.3.12"},
            ],
        )

        self.assertEqual(profile["profile"], "dynamic_winget")
        self.assertEqual(len(profile["packages"]), 2)
        self.assertEqual(profile["packages"][0]["winget_id"], "Microsoft.VisualStudioCode")


class WriteExecutionReportTests(unittest.TestCase):
    def test_write_execution_report_includes_operation_and_catalog_notes(self):
        profile = {
            "profile": "ads_lab",
            "description": "perfil de teste",
            "packages": [{"software": "Astah Community", "install_type": "manual"}],
        }
        results = {
            "operation": "install",
            "summary": {
                "installed": 0,
                "already_installed": 0,
                "pending": 0,
                "manual": 1,
                "failed": 0,
                "blocked": 0,
            },
            "packages": [
                {
                    "package": "Astah Community",
                    "operation": "install",
                    "status": "manual",
                    "install_method": "manual",
                    "install_type": "manual",
                    "winget_id": "",
                    "catalog_notes": "Licenca estudantil; requer intervencao manual.",
                    "manual_reference_url": "https://astah.net/products/astah-community/",
                    "detail": "Requer intervencao manual. Consulte a referencia oficial em https://astah.net/products/astah-community/.",
                }
            ],
        }
        logger = FakeLogger()

        temp_dir = Path(".tmp-test-report-dir")
        temp_dir.mkdir(exist_ok=True)
        try:
            original_reports_dir = main.REPORTS_DIR
            main.REPORTS_DIR = temp_dir
            try:
                report_path = main.write_execution_report(profile, results, logger)
            finally:
                main.REPORTS_DIR = original_reports_dir

            with report_path.open("r", encoding="utf-8", newline="") as report_file:
                rows = list(csv.reader(report_file))
        finally:
            for child in temp_dir.glob("*"):
                child.unlink(missing_ok=True)
            temp_dir.rmdir()

        self.assertIn(["summary", "operation", "install"], rows)
        package_header = [
            "packages",
            "software",
            "operation",
            "status",
            "diagnostic_category",
            "install_method",
            "install_type",
            "winget_id",
            "catalog_notes",
            "manual_reference_url",
            "detail",
        ]
        package_header_index = rows.index(package_header)
        package_row = rows[package_header_index + 1]

        self.assertEqual(package_row[1], "Astah Community")
        self.assertEqual(package_row[2], "install")
        self.assertEqual(package_row[4], "manual_action_required")
        self.assertEqual(package_row[8], "Licenca estudantil; requer intervencao manual.")
        self.assertEqual(package_row[9], "https://astah.net/products/astah-community/")

    def test_classify_package_result_maps_common_lab_failures(self):
        self.assertEqual(
            main.classify_package_result(
                {
                    "status": "failed",
                    "install_method": "winget",
                    "detail": "Failed when opening source(s); codigo 2316632079",
                }
            ),
            "failed_winget_source",
        )
        self.assertEqual(
            main.classify_package_result(
                {
                    "status": "failed",
                    "install_method": "fallback_direct_after_winget",
                    "detail": "MSI retornou 1603 durante a execucao",
                }
            ),
            "failed_msi_1603",
        )


class OperatorSummaryTests(unittest.TestCase):
    def test_build_execution_summary_text_includes_operation_and_totals(self):
        profile = {"profile": "ads_lab"}
        results = {
            "operation": "uninstall",
            "summary": {
                "removed": 3,
                "not_installed": 2,
                "pending": 0,
                "manual": 1,
                "failed": 0,
                "blocked": 0,
            },
            "packages": [{"package": "Astah Community", "status": "manual"}],
        }
        report_path = Path(r"D:\Apps\InstaladorLabs\reports\execution_report_20260322_000741.csv")
        log_path = Path(r"D:\Apps\InstaladorLabs\logs\session_20260322_113118.log")

        summary_text = main.build_execution_summary_text(profile, results, report_path, log_path)

        self.assertIn("Perfil: ads_lab", summary_text)
        self.assertIn("Operacao: Desinstalacao", summary_text)
        self.assertIn("Removidos: 3", summary_text)
        self.assertIn("Nao instalados: 2", summary_text)
        self.assertIn("Manuais: 1", summary_text)
        self.assertIn("Atencao: existe item que requer acao manual.", summary_text)
        self.assertIn("Itens manuais: Astah Community", summary_text)
        self.assertIn("Diagnostico dominante da execucao:", summary_text)
        self.assertIn(str(report_path), summary_text)
        self.assertIn(str(log_path), summary_text)

    def test_summarize_execution_diagnostics_groups_common_failures(self):
        results = {
            "packages": [
                {"package": "Python 3.12", "status": "failed", "install_method": "winget", "detail": "certificate_verify_failed"},
                {"package": "MySQL Workbench", "status": "failed", "install_method": "fallback_direct_after_winget", "detail": "MSI retornou 1603"},
                {"package": "Visual Studio Code", "status": "blocked", "install_method": "blocked_no_winget", "detail": "Sem WinGet"},
                {"package": "Figma", "status": "installed", "install_method": "fallback_direct_after_winget", "detail": "Instalado via fallback"},
            ]
        }

        diagnostics = main.summarize_execution_diagnostics(results)

        self.assertEqual(diagnostics["counts"]["network_or_policy"], 1)
        self.assertEqual(diagnostics["counts"]["msi_or_prerequisite"], 1)
        self.assertEqual(diagnostics["counts"]["winget"], 1)
        self.assertEqual(diagnostics["counts"]["fallback"], 1)
        self.assertIn("Diagnostico dominante da execucao:", diagnostics["detail"])


class BootstrapDiagnosticsTests(unittest.TestCase):
    def test_bootstrap_warns_when_pending_reboot_is_detected(self):
        logger = FakeLogger()
        fake_winget = SimpleNamespace(
            classify_winget_state=lambda: {
                "state": "available",
                "reason": "WinGet disponivel: v1.28.220",
                "diagnostics": {
                    "product_name": "Windows 11 Pro",
                    "raw_product_name": "Windows 10 Pro",
                    "display_version": "25H2",
                    "build": 26200,
                },
            },
            executable=r"C:\Users\Administrator\AppData\Local\Microsoft\WindowsApps\winget.EXE",
            get_version=lambda: "v1.28.220",
            get_proxy_diagnostics=lambda: {"active": False, "detail": ""},
            get_store_stack_diagnostics=lambda: {"detail": "Stack Store/App Installer: ok", "issues": []},
            get_store_policy_diagnostics=lambda: {"detail": "Diagnostico de politicas Store/App Installer: ok", "issues": []},
            get_execution_alias_diagnostics=lambda: {"detail": "Diagnostico de alias/executavel do WinGet: ok", "issues": []},
            get_source_catalog_diagnostics=lambda: {"detail": "Diagnostico de sources do WinGet: ok", "issues": []},
            get_windows_update_diagnostics=lambda: {"detail": "Diagnostico Windows Update: ok", "issues": []},
            get_windows_security_diagnostics=lambda: {"detail": "Diagnostico de seguranca do Windows: ok", "issues": []},
            ensure_client_ready=lambda: {
                "healthy": True,
                "detail": "Cliente do WinGet respondeu normalmente ao listar as fontes.",
                "action": "none",
                "initial_version": "v1.28.220",
                "final_version": "v1.28.220",
            },
        )
        fake_direct_installer = object()

        with patch("main.is_admin", return_value=True), patch(
            "main.get_pending_reboot_diagnostics",
            return_value={"active": True, "signals": ["CBS/RebootPending"], "detail": "CBS/RebootPending"},
        ), patch(
            "main.get_host_capacity_diagnostics",
            return_value={"detail": "Diagnostico de host: ok", "issues": []},
        ), patch(
            "main.get_runtime_directory_diagnostics",
            return_value={"detail": "Diagnostico de diretorios: ok", "issues": []},
        ), patch("main.WinGetManager", return_value=fake_winget), patch(
            "main.DirectInstallerManager",
            return_value=fake_direct_installer,
        ):
            winget, direct_installer = main.bootstrap(logger)

        self.assertIs(winget, fake_winget)
        self.assertIs(direct_installer, fake_direct_installer)
        self.assertTrue(any(item[1] == "bootstrap_reboot_pending" for item in logger.messages))

    def test_bootstrap_warns_when_store_stack_or_windows_update_have_issues(self):
        logger = FakeLogger()
        fake_winget = SimpleNamespace(
            classify_winget_state=lambda: {
                "state": "available",
                "reason": "WinGet disponivel: v1.28.220",
                "diagnostics": {
                    "product_name": "Windows 11 Pro",
                    "raw_product_name": "Windows 10 Pro",
                    "display_version": "25H2",
                    "build": 26200,
                },
            },
            executable=r"C:\Users\Administrator\AppData\Local\Microsoft\WindowsApps\winget.EXE",
            get_version=lambda: "v1.28.220",
            get_proxy_diagnostics=lambda: {"active": False, "detail": ""},
            get_store_stack_diagnostics=lambda: {
                "detail": "Stack Store/App Installer: AppInstaller=ausente | Store=ausente",
                "issues": ["App Installer ausente", "Microsoft Store ausente"],
            },
            get_store_policy_diagnostics=lambda: {
                "detail": "Diagnostico de politicas Store/App Installer: ok",
                "issues": [],
            },
            get_execution_alias_diagnostics=lambda: {
                "detail": "Diagnostico de alias/executavel do WinGet: ok",
                "issues": [],
            },
            get_source_catalog_diagnostics=lambda: {
                "detail": "Diagnostico de sources do WinGet: ok",
                "issues": [],
            },
            get_windows_update_diagnostics=lambda: {
                "detail": "Diagnostico Windows Update: reboot_required=sim",
                "issues": ["Windows Update com reboot pendente", "BITS desabilitado"],
            },
            get_windows_security_diagnostics=lambda: {"detail": "Diagnostico de seguranca do Windows: ok", "issues": []},
            ensure_client_ready=lambda: {
                "healthy": True,
                "detail": "Cliente do WinGet respondeu normalmente ao listar as fontes.",
                "action": "none",
                "initial_version": "v1.28.220",
                "final_version": "v1.28.220",
            },
        )

        with patch("main.is_admin", return_value=True), patch(
            "main.get_pending_reboot_diagnostics",
            return_value={"active": False, "signals": [], "detail": "Nenhum indicio."},
        ), patch(
            "main.get_host_capacity_diagnostics",
            return_value={"detail": "Diagnostico de host: ok", "issues": []},
        ), patch(
            "main.get_runtime_directory_diagnostics",
            return_value={"detail": "Diagnostico de diretorios: ok", "issues": []},
        ), patch("main.WinGetManager", return_value=fake_winget), patch(
            "main.DirectInstallerManager",
            return_value=object(),
        ):
            main.bootstrap(logger)

        self.assertTrue(any(item[1] == "bootstrap_store_stack_warning" for item in logger.messages))
        self.assertTrue(any(item[1] == "bootstrap_windows_update_warning" for item in logger.messages))

    def test_bootstrap_warns_when_host_capacity_has_issues(self):
        logger = FakeLogger()
        fake_winget = SimpleNamespace(
            classify_winget_state=lambda: {
                "state": "available",
                "reason": "WinGet disponivel: v1.28.220",
                "diagnostics": {
                    "product_name": "Windows 11 Pro",
                    "raw_product_name": "Windows 10 Pro",
                    "display_version": "25H2",
                    "build": 26200,
                },
            },
            executable=r"C:\Users\Administrator\AppData\Local\Microsoft\WindowsApps\winget.EXE",
            get_version=lambda: "v1.28.220",
            get_proxy_diagnostics=lambda: {"active": False, "detail": ""},
            get_store_stack_diagnostics=lambda: {"detail": "Stack Store/App Installer: ok", "issues": []},
            get_store_policy_diagnostics=lambda: {"detail": "Diagnostico de politicas Store/App Installer: ok", "issues": []},
            get_execution_alias_diagnostics=lambda: {"detail": "Diagnostico de alias/executavel do WinGet: ok", "issues": []},
            get_source_catalog_diagnostics=lambda: {"detail": "Diagnostico de sources do WinGet: ok", "issues": []},
            get_windows_update_diagnostics=lambda: {"detail": "Diagnostico Windows Update: ok", "issues": []},
            get_windows_security_diagnostics=lambda: {"detail": "Diagnostico de seguranca do Windows: ok", "issues": []},
            ensure_client_ready=lambda: {
                "healthy": True,
                "detail": "Cliente do WinGet respondeu normalmente ao listar as fontes.",
                "action": "none",
                "initial_version": "v1.28.220",
                "final_version": "v1.28.220",
            },
        )

        with patch("main.is_admin", return_value=True), patch(
            "main.get_pending_reboot_diagnostics",
            return_value={"active": False, "signals": [], "detail": "Nenhum indicio."},
        ), patch(
            "main.get_host_capacity_diagnostics",
            return_value={
                "detail": "Diagnostico de host: arquitetura=x86 | espaco_livre_C:\\=3.2 GB",
                "issues": ["Arquitetura nao x64 detectada: x86", "Pouco espaco livre em C:\\: 3.2 GB"],
            },
        ), patch(
            "main.get_runtime_directory_diagnostics",
            return_value={"detail": "Diagnostico de diretorios: ok", "issues": []},
        ), patch("main.WinGetManager", return_value=fake_winget), patch(
            "main.DirectInstallerManager",
            return_value=object(),
        ):
            main.bootstrap(logger)

        self.assertTrue(any(item[1] == "bootstrap_host_capacity_warning" for item in logger.messages))

    def test_bootstrap_warns_when_policy_alias_or_source_diagnostics_have_issues(self):
        logger = FakeLogger()
        fake_winget = SimpleNamespace(
            classify_winget_state=lambda: {
                "state": "available",
                "reason": "WinGet disponivel: v1.28.220",
                "diagnostics": {
                    "product_name": "Windows 11 Pro",
                    "raw_product_name": "Windows 10 Pro",
                    "display_version": "25H2",
                    "build": 26200,
                },
            },
            executable=r"C:\Users\Administrator\AppData\Local\Microsoft\WindowsApps\winget.EXE",
            get_version=lambda: "v1.28.220",
            get_proxy_diagnostics=lambda: {"active": False, "detail": ""},
            get_store_stack_diagnostics=lambda: {"detail": "Stack Store/App Installer: ok", "issues": []},
            get_store_policy_diagnostics=lambda: {
                "detail": "Diagnostico de politicas Store/App Installer: RemoveWindowsStore=1",
                "issues": ["Politica RemoveWindowsStore ativa"],
            },
            get_execution_alias_diagnostics=lambda: {
                "detail": "Diagnostico de alias/executavel do WinGet: caminho=... | existe=nao",
                "issues": ["Executavel resolvido do winget nao existe em disco: C:\\x\\winget.exe"],
            },
            get_source_catalog_diagnostics=lambda: {
                "detail": "Diagnostico de sources do WinGet: winget=ausente | msstore=ausente",
                "issues": ["Source 'winget' ausente na configuracao do cliente"],
            },
            get_windows_update_diagnostics=lambda: {"detail": "Diagnostico Windows Update: ok", "issues": []},
            get_windows_security_diagnostics=lambda: {"detail": "Diagnostico de seguranca do Windows: ok", "issues": []},
            ensure_client_ready=lambda: {
                "healthy": True,
                "detail": "Cliente do WinGet respondeu normalmente ao listar as fontes.",
                "action": "none",
                "initial_version": "v1.28.220",
                "final_version": "v1.28.220",
            },
        )

        with patch("main.is_admin", return_value=True), patch(
            "main.get_pending_reboot_diagnostics",
            return_value={"active": False, "signals": [], "detail": "Nenhum indicio."},
        ), patch(
            "main.get_host_capacity_diagnostics",
            return_value={"detail": "Diagnostico de host: ok", "issues": []},
        ), patch(
            "main.get_runtime_directory_diagnostics",
            return_value={"detail": "Diagnostico de diretorios: ok", "issues": []},
        ), patch("main.WinGetManager", return_value=fake_winget), patch(
            "main.DirectInstallerManager",
            return_value=object(),
        ):
            main.bootstrap(logger)

        self.assertTrue(any(item[1] == "bootstrap_store_policy_warning" for item in logger.messages))
        self.assertTrue(any(item[1] == "bootstrap_winget_alias_warning" for item in logger.messages))
        self.assertTrue(any(item[1] == "bootstrap_winget_sources_warning" for item in logger.messages))

    def test_bootstrap_warns_when_runtime_directories_are_not_writable(self):
        logger = FakeLogger()
        fake_winget = SimpleNamespace(
            classify_winget_state=lambda: {
                "state": "available",
                "reason": "WinGet disponivel: v1.28.220",
                "diagnostics": {
                    "product_name": "Windows 11 Pro",
                    "raw_product_name": "Windows 10 Pro",
                    "display_version": "25H2",
                    "build": 26200,
                },
            },
            executable=r"C:\Users\Administrator\AppData\Local\Microsoft\WindowsApps\winget.EXE",
            get_version=lambda: "v1.28.220",
            get_proxy_diagnostics=lambda: {"active": False, "detail": ""},
            get_store_stack_diagnostics=lambda: {"detail": "Stack Store/App Installer: ok", "issues": []},
            get_store_policy_diagnostics=lambda: {"detail": "Diagnostico de politicas Store/App Installer: ok", "issues": []},
            get_execution_alias_diagnostics=lambda: {"detail": "Diagnostico de alias/executavel do WinGet: ok", "issues": []},
            get_source_catalog_diagnostics=lambda: {"detail": "Diagnostico de sources do WinGet: ok", "issues": []},
            get_windows_update_diagnostics=lambda: {"detail": "Diagnostico Windows Update: ok", "issues": []},
            get_windows_security_diagnostics=lambda: {"detail": "Diagnostico de seguranca do Windows: ok", "issues": []},
            ensure_client_ready=lambda: {
                "healthy": True,
                "detail": "Cliente do WinGet respondeu normalmente ao listar as fontes.",
                "action": "none",
                "initial_version": "v1.28.220",
                "final_version": "v1.28.220",
            },
        )

        with patch("main.is_admin", return_value=True), patch(
            "main.get_pending_reboot_diagnostics",
            return_value={"active": False, "signals": [], "detail": "Nenhum indicio."},
        ), patch(
            "main.get_host_capacity_diagnostics",
            return_value={"detail": "Diagnostico de host: ok", "issues": []},
        ), patch(
            "main.get_runtime_directory_diagnostics",
            return_value={
                "detail": "Diagnostico de diretorios: downloads=C:\\tmp (erro: acesso negado)",
                "issues": ["downloads sem escrita: C:\\tmp"],
            },
        ), patch("main.WinGetManager", return_value=fake_winget), patch(
            "main.DirectInstallerManager",
            return_value=object(),
        ):
            main.bootstrap(logger)

        self.assertTrue(any(item[1] == "bootstrap_runtime_dirs_warning" for item in logger.messages))

    def test_bootstrap_warns_when_windows_security_has_issues(self):
        logger = FakeLogger()
        fake_winget = SimpleNamespace(
            classify_winget_state=lambda: {
                "state": "available",
                "reason": "WinGet disponivel: v1.28.220",
                "diagnostics": {
                    "product_name": "Windows 11 Pro",
                    "raw_product_name": "Windows 10 Pro",
                    "display_version": "25H2",
                    "build": 26200,
                },
            },
            executable=r"C:\Users\Administrator\AppData\Local\Microsoft\WindowsApps\winget.EXE",
            get_version=lambda: "v1.28.220",
            get_proxy_diagnostics=lambda: {"active": False, "detail": ""},
            get_store_stack_diagnostics=lambda: {"detail": "Stack Store/App Installer: ok", "issues": []},
            get_store_policy_diagnostics=lambda: {"detail": "Diagnostico de politicas Store/App Installer: ok", "issues": []},
            get_execution_alias_diagnostics=lambda: {"detail": "Diagnostico de alias/executavel do WinGet: ok", "issues": []},
            get_source_catalog_diagnostics=lambda: {"detail": "Diagnostico de sources do WinGet: ok", "issues": []},
            get_windows_update_diagnostics=lambda: {"detail": "Diagnostico Windows Update: ok", "issues": []},
            get_windows_security_diagnostics=lambda: {
                "detail": "Diagnostico de seguranca do Windows: EnableSmartScreen=0",
                "issues": ["Politica EnableSmartScreen desabilitada", "Servico WinDefend desabilitado"],
            },
            ensure_client_ready=lambda: {
                "healthy": True,
                "detail": "Cliente do WinGet respondeu normalmente ao listar as fontes.",
                "action": "none",
                "initial_version": "v1.28.220",
                "final_version": "v1.28.220",
            },
        )

        with patch("main.is_admin", return_value=True), patch(
            "main.get_pending_reboot_diagnostics",
            return_value={"active": False, "signals": [], "detail": "Nenhum indicio."},
        ), patch(
            "main.get_host_capacity_diagnostics",
            return_value={"detail": "Diagnostico de host: ok", "issues": []},
        ), patch(
            "main.get_runtime_directory_diagnostics",
            return_value={"detail": "Diagnostico de diretorios: ok", "issues": []},
        ), patch("main.WinGetManager", return_value=fake_winget), patch(
            "main.DirectInstallerManager",
            return_value=object(),
        ):
            main.bootstrap(logger)

        self.assertTrue(any(item[1] == "bootstrap_windows_security_warning" for item in logger.messages))


if __name__ == "__main__":
    unittest.main()
