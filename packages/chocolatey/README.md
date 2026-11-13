# SpecStream for Chocolatey

The Chocolatey package of the SpecStream desktop app for Windows (64-bit).

```powershell
choco install specstream
```

The package downloads the installer from `https://specstream.ai/download/windows-x64/<version>`, checks it against the SHA-256 in `tools/chocolateyinstall.ps1`, and runs it without its pages (`/S /allusers`).
`choco uninstall specstream` removes the app with the installer's own uninstaller.

## Files

- `specstream.nuspec`: the package's name, version and description.
- `tools/chocolateyinstall.ps1`: the installer's address and checksum.
- `update.py <installer>`: writes a new version, address and checksum into the two files above.
- `pack.py [folder]`: makes `specstream.<version>.nupkg`, the file Chocolatey takes. `choco pack` makes the same package on Windows.

## A new version of the app

1. Put the new installer where `https://specstream.ai/download/windows-x64/<version>` serves it.
2. `python3 update.py <installer>`
3. `python3 pack.py`
4. `choco push specstream.<version>.nupkg --source https://push.chocolatey.org/`
