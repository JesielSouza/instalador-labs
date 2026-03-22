import csv
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
    def __init__(self, installed=True, detected_ids=None, install_success_ids=None):
        self.installed = installed
        self.detected_ids = set(detected_ids or [])
        self.install_success_ids = set(install_success_ids or [])

    def is_installed(self):
        return self.installed

    def check_package_status(self, package_id):
        return package_id in self.detected_ids

    def install_package(self, package_id):
        return package_id in self.install_success_ids


class FakeDirectInstaller:
    def __init__(self, present_names=None, install_success_names=None):
        self.present_names = set(present_names or [])
        self.install_success_names = set(install_success_names or [])

    def is_package_present(self, package):
        return package["software"] in self.present_names

    def install_package(self, package, logger):
        return package["software"] in self.install_success_names


class ExecutePackagePlanTests(unittest.TestCase):
    def test_execute_package_plan_summarizes_available_winget_flow(self):
        profile = {
            "profile": "teste",
            "description": "cenario com winget disponivel",
            "packages": [
                {
                    "software": "Ja Instalado",
                    "install_type": "winget",
                    "winget_id": "Vendor.Installed",
                    "notes": "Detectado previamente.",
                },
                {
                    "software": "Instalacao OK",
                    "install_type": "winget",
                    "winget_id": "Vendor.Success",
                    "notes": "Deve instalar.",
                },
                {
                    "software": "Instalacao Falha",
                    "install_type": "winget",
                    "winget_id": "Vendor.Fail",
                    "notes": "Deve falhar.",
                },
                {
                    "software": "Pendente",
                    "install_type": "winget_pending",
                    "winget_id": "Vendor.Pending",
                    "notes": "Ainda pendente.",
                },
                {
                    "software": "Manual",
                    "install_type": "manual",
                    "notes": "Intervencao humana.",
                },
            ],
        }
        logger = FakeLogger()
        winget = FakeWinget(
            installed=True,
            detected_ids={"Vendor.Installed"},
            install_success_ids={"Vendor.Success"},
        )
        direct_installer = FakeDirectInstaller()

        results = main.execute_package_plan(profile, logger, winget, direct_installer)

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
                    "fallback_installer": {
                        "download_url": "https://example.invalid/fallback.exe",
                        "install_args": ["/quiet"],
                    },
                    "notes": "Fallback oficial.",
                },
                {
                    "software": "Sem Automacao",
                    "install_type": "winget",
                    "winget_id": "Vendor.Blocked",
                    "notes": "Sem winget nem fallback.",
                },
            ],
        }
        logger = FakeLogger()
        winget = FakeWinget(installed=False)
        direct_installer = FakeDirectInstaller(install_success_names={"Fallback OK"})

        results = main.execute_package_plan(profile, logger, winget, direct_installer)

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


class WriteExecutionReportTests(unittest.TestCase):
    def test_write_execution_report_includes_catalog_notes_column(self):
        profile = {
            "profile": "ads_lab",
            "description": "perfil de teste",
            "packages": [{"software": "Astah Community", "install_type": "manual"}],
        }
        results = {
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
                    "status": "manual",
                    "install_method": "manual",
                    "install_type": "manual",
                    "winget_id": "",
                    "catalog_notes": "Licenca estudantil; requer intervencao manual.",
                    "detail": "Requer intervencao manual.",
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

        package_header = [
            "packages",
            "software",
            "status",
            "install_method",
            "install_type",
            "winget_id",
            "catalog_notes",
            "detail",
        ]
        package_header_index = rows.index(package_header)
        package_row = rows[package_header_index + 1]

        self.assertEqual(package_row[1], "Astah Community")
        self.assertEqual(package_row[6], "Licenca estudantil; requer intervencao manual.")


if __name__ == "__main__":
    unittest.main()
