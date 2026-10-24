"""Build a Mac launcher with explicit runtime paths; never installs automatically."""

import argparse
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def build(destination, python):
    if destination.exists():
        raise ValueError("Choose a new output path; existing apps are not overwritten")
    with tempfile.TemporaryDirectory(prefix="income-app-") as temporary:
        stage = Path(temporary) / "Income Opportunities.app"
        contents = stage / "Contents"
        (contents / "MacOS").mkdir(parents=True)
        (contents / "Resources").mkdir()
        shutil.copyfile(
            ROOT / "macos/DollarIcon.icns", contents / "Resources/DollarIcon.icns"
        )
        subprocess.run(
            [
                "swiftc",
                "-module-cache-path",
                str(ROOT / ".build/modules"),
                "-target",
                "arm64-apple-macos13.0",
                str(ROOT / "macos/IncomeOpportunities.swift"),
                "-o",
                str(contents / "MacOS/IncomeOpportunities"),
                "-framework",
                "Cocoa",
                "-framework",
                "WebKit",
            ],
            check=True,
        )
        metadata = {
            "CFBundleName": "Income Opportunities",
            "CFBundleDisplayName": "Income Opportunities",
            "CFBundleIdentifier": "org.example.incomeopportunities",
            "CFBundleExecutable": "IncomeOpportunities",
            "CFBundleIconFile": "DollarIcon",
            "CFBundlePackageType": "APPL",
            "CFBundleVersion": "3",
            "LSMinimumSystemVersion": "13.0",
            "NSHighResolutionCapable": True,
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
            "IncomeAgentRoot": str(ROOT),
            "IncomeAgentPython": str(python.resolve()),
        }
        with (contents / "Info.plist").open("wb") as stream:
            plistlib.dump(metadata, stream)
        subprocess.run(
            ["codesign", "--force", "--deep", "--sign", "-", str(stage)], check=True
        )
        subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", str(stage)], check=True
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(stage, destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    args = parser.parse_args()
    print(build(args.output, args.python))


if __name__ == "__main__":
    main()
