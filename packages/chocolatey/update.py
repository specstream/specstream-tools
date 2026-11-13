#!/usr/bin/env python3
"""Point the Chocolatey package at one Windows installer.

    python3 packages/chocolatey/update.py SpecStream-0.2.0-x64-setup.exe
    python3 packages/chocolatey/update.py --check <installer>     change nothing; fail when the package differs

The version comes from the installer's file name (SpecStream-<version>-x64-setup.exe, as electron-builder
names it) and the checksum from its bytes. Both go into specstream.nuspec and tools/chocolateyinstall.ps1,
whose address is https://specstream.ai/download/windows-x64/<version>: the one that keeps answering this
version. Then run pack.py.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NUSPEC = HERE / "specstream.nuspec"
INSTALL = HERE / "tools" / "chocolateyinstall.ps1"
INSTALLER_NAME = re.compile(r"^SpecStream-(\d+\.\d+\.\d+)-x64-setup\.exe$")
ADDRESS = "https://specstream.ai/download/windows-x64/"


def installer_facts(installer: Path) -> tuple[str, str]:
    """The version in the installer's name and the SHA-256 of its bytes."""
    match = INSTALLER_NAME.match(installer.name)
    if not match:
        raise SystemExit(f"{installer.name} is not named SpecStream-<version>-x64-setup.exe")
    digest = hashlib.sha256()
    with installer.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return match.group(1), digest.hexdigest()


def _replace_once(text: str, pattern: str, replacement: str, name: str) -> str:
    result, count = re.subn(pattern, replacement, text)
    if count != 1:
        raise SystemExit(f"{name}: expected one match of {pattern}, found {count}")
    return result


def rewritten(nuspec: str, install: str, version: str, sha256: str) -> tuple[str, str]:
    """Both package files with this version, its address and its checksum."""
    nuspec = _replace_once(nuspec, r"<version>[^<]*</version>", f"<version>{version}</version>", NUSPEC.name)
    install = _replace_once(
        install, r"(url64bit\s*=\s*')[^']*(')", rf"\g<1>{ADDRESS}{version}\g<2>", INSTALL.name
    )
    install = _replace_once(install, r"(checksum64\s*=\s*')[^']*(')", rf"\g<1>{sha256}\g<2>", INSTALL.name)
    return nuspec, install


def main(argv: list[str]) -> int:
    check = "--check" in argv
    paths = [arg for arg in argv if arg != "--check"]
    if len(paths) != 1:
        raise SystemExit(__doc__)
    version, sha256 = installer_facts(Path(paths[0]))
    before = NUSPEC.read_text(encoding="utf-8"), INSTALL.read_text(encoding="utf-8")
    after = rewritten(*before, version, sha256)
    if check:
        if before != after:
            print(f"The package does not match {paths[0]} (version {version}, sha256 {sha256}).")
            return 1
        print(f"The package matches version {version}, sha256 {sha256}.")
        return 0
    NUSPEC.write_text(after[0], encoding="utf-8")
    INSTALL.write_text(after[1], encoding="utf-8")
    print(f"specstream {version}, sha256 {sha256}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
