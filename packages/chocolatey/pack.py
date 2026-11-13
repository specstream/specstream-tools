#!/usr/bin/env python3
"""Make specstream.<version>.nupkg from this folder, without Windows and without choco.

    python3 packages/chocolatey/pack.py [output folder]      default: the current folder

A .nupkg is a zip in the Open Packaging layout: the .nuspec, the tools folder, and three small files that
name the parts ([Content_Types].xml, _rels/.rels, the core properties). This writes the same layout
`choco pack` writes, so the file can go to community.chocolatey.org as it is
(`choco push`, or a PUT of the file to https://push.chocolatey.org/api/v2/package with the account's key).
The zip is the same byte for byte on every run, so a second pack of the same source is the same file.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
NUSPEC = HERE / "specstream.nuspec"
NS = {"n": "http://schemas.microsoft.com/packaging/2015/06/nuspec.xsd"}
FIXED_TIME = (2026, 1, 1, 0, 0, 0)

CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" />
  <Default Extension="psmdcp" ContentType="application/vnd.openxmlformats-package.core-properties+xml" />
  <Default Extension="nuspec" ContentType="application/octet" />
  <Default Extension="ps1" ContentType="application/octet" />
</Types>
"""

RELS = """<?xml version="1.0" encoding="utf-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Type="http://schemas.microsoft.com/packaging/2010/07/manifest" Target="/{nuspec}" Id="R1" />
  <Relationship Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="/package/services/metadata/core-properties/{core}.psmdcp" Id="R2" />
</Relationships>
"""

CORE = """<?xml version="1.0" encoding="utf-8"?>
<coreProperties xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://schemas.openxmlformats.org/package/2006/metadata/core-properties">
  <dc:creator>{authors}</dc:creator>
  <dc:description>{summary}</dc:description>
  <dc:identifier>{id}</dc:identifier>
  <version>{version}</version>
  <keywords>{tags}</keywords>
  <lastModifiedBy>choco, Version=2.0.0.0</lastModifiedBy>
</coreProperties>
"""


def metadata() -> dict[str, str]:
    """The package's fields as the .nuspec gives them."""
    root = ElementTree.parse(NUSPEC).getroot()
    found = root.find("n:metadata", NS)
    if found is None:
        raise SystemExit("specstream.nuspec has no metadata")
    return {child.tag.split("}", 1)[1]: (child.text or "").strip() for child in found}


def parts() -> dict[str, bytes]:
    """Each file of the package by its path in the zip."""
    fields = metadata()
    core = "specstream0000000000000000000000"
    files = {NUSPEC.name: NUSPEC.read_bytes()}
    for path in sorted((HERE / "tools").rglob("*")):
        if path.is_file():
            files["tools/" + path.relative_to(HERE / "tools").as_posix()] = path.read_bytes()
    files["[Content_Types].xml"] = CONTENT_TYPES.encode()
    files["_rels/.rels"] = RELS.format(nuspec=NUSPEC.name, core=core).encode()
    files[f"package/services/metadata/core-properties/{core}.psmdcp"] = CORE.format(
        **{key: escape(fields[key]) for key in ("authors", "summary", "id", "version", "tags")}
    ).encode()
    return files


def pack(out_dir: Path) -> Path:
    fields = metadata()
    target = out_dir / f"{fields['id']}.{fields['version']}.nupkg"
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts().items():
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return target


if __name__ == "__main__":
    print(pack(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()))
