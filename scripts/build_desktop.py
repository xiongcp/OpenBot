"""Build a local unsigned macOS app; no publication or daemon installation. / 本地开发构建。"""

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-dir", type=Path)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("This development bundle is macOS-only / 仅 macOS 开发构建")
    cargo = shutil.which("cargo")
    if cargo is None:
        parser.error("Prepare Rust >= 1.90 first / 请先准备 Rust >= 1.90")
    manifest = ROOT / "apps/desktop/src-tauri/Cargo.toml"
    subprocess.run(
        [cargo, "build", "--manifest-path", str(manifest), "--locked", "--offline"],
        cwd=ROOT,
        check=True,
    )
    target = Path(os.environ.get("CARGO_TARGET_DIR", str(manifest.parent / "target")))
    bundle = ROOT / "apps/desktop/out/OpenBot.app/Contents"
    (bundle / "MacOS").mkdir(parents=True, exist_ok=True)
    shutil.copy2(target / "debug/openbot-desktop", bundle / "MacOS/OpenBot")
    info = {
        "CFBundleExecutable": "OpenBot",
        "CFBundleIdentifier": "dev.openbot.client",
        "CFBundleName": "OpenBot",
        "CFBundleDisplayName": "OpenBot",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
    }
    if args.profile_dir is not None:
        info["LSEnvironment"] = {"OPENBOT_PROFILE_DIR": str(args.profile_dir.resolve(strict=True))}
    with (bundle / "Info.plist").open("wb") as stream:
        plistlib.dump(info, stream)
    print(f"Unsigned development app / 未签名开发客户端: {bundle.parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
