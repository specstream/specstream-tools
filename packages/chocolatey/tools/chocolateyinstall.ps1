$ErrorActionPreference = 'Stop'

# The address answers this one version for good (specstream.ai/download/windows-x64/<version>), so the
# checksum below keeps matching after a newer installer is out. update.py writes both lines.
$packageArgs = @{
  packageName    = $env:ChocolateyPackageName
  fileType       = 'exe'
  url64bit       = 'https://specstream.ai/download/windows-x64/0.1.0'
  checksum64     = 'aeccc41c2c1268b0b1bb1889b5add4f44a634904d86de23c993f47ebf974c842'
  checksumType64 = 'sha256'
  softwareName   = 'SpecStream*'
  # The installer is NSIS: /S runs it without its pages, /allusers installs for every user of the PC.
  silentArgs     = '/S /allusers'
  validExitCodes = @(0)
}

Install-ChocolateyPackage @packageArgs
