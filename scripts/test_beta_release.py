import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import beta_release

TAG = "v2026.42.1-beta.1"


class BetaReleaseTests(unittest.TestCase):
    def test_versions_map_beta_to_numeric_installer_versions(self):
        self.assertEqual(beta_release.versions(TAG), {
            "version": "2026.42.1-beta.1", "cargo": "2026.42.1", "msi": "26.42.1",
        })
        for invalid in ("v2026.42.1", "v2026.54.1-beta.1", "v2026.42.1-beta.0", "v2026.42.65536-beta.1", "v2026.42.2-beta.1"):
            with self.subTest(tag=invalid), self.assertRaises(ValueError):
                beta_release.versions(invalid)

    def release(self):
        assets = {}
        for platform, suffixes in (
            ("windows", ("windows-x86_64-portable.exe", "windows-x86_64-installer.msi")),
            ("macos", ("macos-arm64.dmg",)),
        ):
            checksums = []
            for suffix in suffixes:
                name = f"OpenCADStudio-{TAG}-{suffix}"
                assets[name] = name.encode()
                checksums.append(f"{hashlib.sha256(assets[name]).hexdigest()}  {name}")
            assets[f"OpenCADStudio-{TAG}-{platform}-SHA256SUMS.txt"] = ("\n".join(checksums) + "\n").encode()
        return assets

    def verify(self, assets, corrupt=False):
        release = {"assets": [{"name": name, "size": len(data), "state": "uploaded"} for name, data in assets.items()], "body": "Beta release notes", "isPrerelease": True}

        def download(args, check):
            directory = Path(args[args.index("--dir") + 1])
            for name, data in assets.items():
                if corrupt and name.endswith(".exe"):
                    data += b"corrupt"
                (directory / name).write_bytes(data)

        with patch.object(beta_release.subprocess, "check_output", return_value=json.dumps(release)), patch.object(beta_release.subprocess, "run", side_effect=download):
            beta_release.verify(TAG, "GWydouw/OpenCADStudio")

    def test_complete_release_and_checksums(self):
        self.verify(self.release())

    def test_missing_installer_blocks_publication(self):
        assets = self.release()
        del assets[f"OpenCADStudio-{TAG}-windows-x86_64-installer.msi"]
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.verify(assets)

    def test_corrupt_download_blocks_publication(self):
        with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
            self.verify(self.release(), corrupt=True)


if __name__ == "__main__":
    unittest.main()
