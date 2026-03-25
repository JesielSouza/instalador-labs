import unittest
from pathlib import Path

from utils.package_loader import (
    PackageSelectionError,
    build_dynamic_package_profile,
    list_package_profiles,
    save_package_profile,
    select_profile_packages,
    validate_package_profile,
)


class PackageLoaderSelectionTests(unittest.TestCase):
    def setUp(self):
        self.profile = validate_package_profile(
            {
                "profile": "teste",
                "description": "perfil para validar selecao de pacotes",
                "packages": [
                    {"software": "Visual Studio Code", "install_type": "winget", "winget_id": "Microsoft.VisualStudioCode"},
                    {"software": "Python 3.12", "install_type": "winget", "winget_id": "Python.Python.3.12"},
                    {"software": "Astah Community", "install_type": "manual"},
                ],
            }
        )

    def test_select_profile_packages_preserves_requested_order(self):
        filtered = select_profile_packages(self.profile, ["Astah Community", "Visual Studio Code"])

        self.assertEqual(filtered["selection"], ["Astah Community", "Visual Studio Code"])
        self.assertEqual(
            [package["software"] for package in filtered["packages"]],
            ["Astah Community", "Visual Studio Code"],
        )

    def test_select_profile_packages_rejects_empty_selection(self):
        with self.assertRaises(PackageSelectionError):
            select_profile_packages(self.profile, [])

    def test_select_profile_packages_rejects_unknown_package(self):
        with self.assertRaises(PackageSelectionError):
            select_profile_packages(self.profile, ["Pacote Inexistente"])

    def test_validate_profile_accepts_manual_official_download(self):
        profile = validate_package_profile(
            {
                "profile": "manual_download",
                "description": "perfil com download oficial catalogado",
                "packages": [
                    {
                        "software": "Astah Community",
                        "install_type": "manual",
                        "official_download": {
                            "download_url": "https://example.invalid/astah-installer.exe",
                            "file_name": "astah-installer.exe",
                        },
                    }
                ],
            }
        )

        self.assertEqual(profile["packages"][0]["official_download"]["file_name"], "astah-installer.exe")

    def test_build_dynamic_package_profile_deduplicates_by_winget_id(self):
        profile = build_dynamic_package_profile(
            [
                {"software": "Visual Studio Code", "winget_id": "Microsoft.VisualStudioCode"},
                {"software": "VS Code Duplicate", "winget_id": "Microsoft.VisualStudioCode"},
                {"software": "Python 3.12", "winget_id": "Python.Python.3.12"},
            ]
        )

        self.assertEqual(profile["profile"], "dynamic_winget")
        self.assertEqual(len(profile["packages"]), 2)
        self.assertEqual(profile["packages"][0]["software"], "Visual Studio Code")
        self.assertEqual(profile["packages"][1]["winget_id"], "Python.Python.3.12")

    def test_build_dynamic_package_profile_sanitizes_polluted_winget_id(self):
        profile = build_dynamic_package_profile(
            [
                {
                    "software": "VLC media player",
                    "winget_id": "VideoLAN.VLC          3.0.23                  Moniker: vlc",
                },
                {
                    "software": "Antigravity",
                    "winget_id": "Google.Antigravity                   1.20.5",
                },
            ]
        )

        self.assertEqual(profile["packages"][0]["winget_id"], "VideoLAN.VLC")
        self.assertEqual(profile["packages"][1]["winget_id"], "Google.Antigravity")

    def test_save_package_profile_persists_valid_json(self):
        profile = build_dynamic_package_profile(
            [{"software": "Visual Studio Code", "winget_id": "Microsoft.VisualStudioCode"}]
        )
        target_path = Path(".tmp-test-dynamic-profile.json")
        try:
            saved_path = save_package_profile(profile, target_path)
            reloaded = saved_path.read_text(encoding="utf-8")
        finally:
            target_path.unlink(missing_ok=True)

        self.assertEqual(saved_path, target_path)
        self.assertIn('"profile": "dynamic_winget"', reloaded)
        self.assertIn('"winget_id": "Microsoft.VisualStudioCode"', reloaded)



class PackageLoaderListingTests(unittest.TestCase):
    def test_list_package_profiles_includes_ads_lab(self):
        profiles = list_package_profiles()

        self.assertTrue(any(profile["profile"] == "ads_lab" for profile in profiles))


if __name__ == "__main__":
    unittest.main()
