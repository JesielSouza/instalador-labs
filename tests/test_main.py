import csv
import importlib
import sys
import tempfile
import unittest
from pathlib import Path

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
        upgrade_success_ids=None,
        uninstall_success_ids=None,
        install_failure_detail=None,
        upgrade_failure_detail=None,
        uninstall_failure_detail=None,
    ):
        self.installed = installed
        self.detected_ids = set(detected_ids or [])
        self.install_success_ids = set(install_success_ids or [])
        self.upgrade_success_ids = set(upgrade_success_ids or [])
        self.uninstall_success_ids = set(uninstall_success_ids or [])
        self.install_failure_detail = install_failure_detail or "Falha na instalacao automatizada pelo WinGet."
        self.upgrade_failure_detail = upgrade_failure_detail or "Falha na atualizacao automatizada pelo WinGet."
        self.uninstall_failure_detail = uninstall_failure_detail or "Falha na desinstalacao automatizada pelo WinGet."

    def is_installed(self):
        return self.installed

    def check_package_status(self, package_id):
        return package_id in self.detected_ids

    def check_package_status_details(self, package_id):
        found = package_id in self.detected_ids
        return {
            "found": found,
            "detail": "Pacote localizado pelo WinGet antes da operacao." if found else "Pacote nao localizado pelo WinGet antes da operacao.",
        }

    def install_package(self, package_id):
        return package_id in self.install_success_ids

    def install_package_details(self, package_id):
        success = package_id in self.install_success_ids
        return {
            "success": success,
            "detail": "Instalado com sucesso pelo WinGet." if success else self.install_failure_detail,
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

        with tempfile.TemporaryDirectory() as temp_dir:
            original_reports_dir = main.REPORTS_DIR
            main.REPORTS_DIR = Path(temp_dir)
            try:
                report_path = main.write_execution_report(profile, results, logger)
            finally:
                main.REPORTS_DIR = original_reports_dir

            with report_path.open("r", encoding="utf-8", newline="") as report_file:
                rows = list(csv.reader(report_file))

        self.assertIn(["summary", "operation", "install"], rows)
        package_header = [
            "packages",
            "software",
            "operation",
            "status",
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
        self.assertEqual(package_row[7], "Licenca estudantil; requer intervencao manual.")
        self.assertEqual(package_row[8], "https://astah.net/products/astah-community/")


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
        self.assertIn(str(report_path), summary_text)
        self.assertIn(str(log_path), summary_text)


if __name__ == "__main__":
    unittest.main()
