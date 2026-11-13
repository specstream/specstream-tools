#!/usr/bin/env python3
"""Write vendor-data/cloud-config.yaml from the files of this folder.

    python3 build.py           write the file
    python3 build.py --check   fail when the file on disk is not what the sources give

Vultr builds a Marketplace image in two ways: from a snapshot (scripts/install.sh, then
scripts/clean-image.sh) or from vendor data, a cloud-init document that runs on the first boot of
a plain Ubuntu 24.04 server. This file is the second way: it carries the same files and runs the
same two scripts, so both ways give the same server.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "vendor-data" / "cloud-config.yaml"
SOURCE = "/opt/specstream-research/src"
FILES = (
    "app/research_agent.py",
    "files/specstream-research.service",
    "files/nginx.conf",
    "scripts/install.sh",
    "scripts/provision.sh",
)


def render() -> str:
    lines = [
        "#cloud-config",
        "# SpecStream research agent: vendor data for a Vultr Marketplace build on Ubuntu 24.04.",
        "# Written by integrations/vultr/build.py from the files beside it. Do not edit by hand.",
        "write_files:",
    ]
    for name in FILES:
        encoded = base64.b64encode((HERE / name).read_bytes()).decode("ascii")
        lines += [
            f"  - path: {SOURCE}/{name}",
            "    owner: root:root",
            f"    permissions: '{'0755' if name.endswith('.sh') else '0644'}'",
            "    encoding: b64",
            f"    content: {encoded}",
        ]
    lines += [
        "runcmd:",
        f"  - [bash, {SOURCE}/scripts/install.sh]",
        # cloud-init's per-instance scripts ran before runcmd on this boot, so the first-boot
        # script is called here; it does nothing when it ran before.
        "  - [bash, /var/lib/cloud/scripts/per-instance/provision.sh]",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        if not OUT.is_file() or OUT.read_text(encoding="utf-8") != text:
            print("vendor-data/cloud-config.yaml is out of date: run python3 integrations/vultr/build.py", file=sys.stderr)
            return 1
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
