import unittest

from utils.package_loader import (
    PackageSelectionError,
    list_package_profiles,
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



class PackageLoaderListingTests(unittest.TestCase):
    def test_list_package_profiles_includes_ads_lab(self):
        profiles = list_package_profiles()

        self.assertTrue(any(profile["profile"] == "ads_lab" for profile in profiles))


if __name__ == "__main__":
    unittest.main()
