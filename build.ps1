param(
    [ValidatePattern('^v?\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?$')]
    [string]$Version = 'v1.0.3',
    [string]$Python = 'python'
)

$ErrorActionPreference = 'Stop'
$repoDir = $PSScriptRoot
$Version = 'v' + $Version.TrimStart('v')
$distDir = Join-Path $repoDir 'dist'
$buildDir = Join-Path $repoDir 'build'
$exeDir = Join-Path $distDir 'executables'
$stageDir = Join-Path $distDir ('HHUCampusAutoLogin-' + $Version + '-windows-x64')
$smokeDir = Join-Path $buildDir ('smoke path 中文 ' + [guid]::NewGuid().ToString('N'))

if ($env:OS -ne 'Windows_NT') { throw 'Build the Windows release on Windows.' }
& $Python -c "import struct, sys; sys.exit(0 if struct.calcsize('P') == 8 and sys.version_info >= (3, 8) else 1)"
if ($LASTEXITCODE -ne 0) { throw 'A 64-bit Python 3.8+ interpreter is required.' }

Push-Location $repoDir
try {
    & $Python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Unit tests failed.' }
    New-Item -ItemType Directory -Force -Path $exeDir, $stageDir, $smokeDir | Out-Null

    $commonArgs = @(
        '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--noupx',
        '--distpath', $exeDir, '--workpath', (Join-Path $buildDir 'pyinstaller'),
        '--specpath', (Join-Path $buildDir 'spec')
    )
    & $Python @commonArgs --console --name HHUCampusAutoLogin auto_login.py
    if ($LASTEXITCODE -ne 0) { throw 'Console executable build failed.' }
    & $Python @commonArgs --noconsole --name HHUCampusAutoLogin-background auto_login.py
    if ($LASTEXITCODE -ne 0) { throw 'Background executable build failed.' }

    $fileNames = @(
        'HHUCampusAutoLogin.exe', 'HHUCampusAutoLogin-background.exe',
        'install.cmd', 'uninstall.cmd', 'config.example.json', 'README.md', 'LICENSE',
        'THIRD_PARTY_NOTICES.txt', 'licenses/Python.txt', 'licenses/PyInstaller.txt'
    )
    foreach ($fileName in $fileNames) {
        $sourceDir = if ($fileName.EndsWith('.exe')) { $exeDir } else { $repoDir }
        $destination = Join-Path $stageDir $fileName
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
        Copy-Item -LiteralPath (Join-Path $sourceDir $fileName) -Destination $destination -Force
    }

    # Exercise frozen paths from an unrelated working directory, with no configuration.
    Copy-Item -LiteralPath (Join-Path $exeDir 'HHUCampusAutoLogin.exe') -Destination $smokeDir
    Copy-Item -LiteralPath (Join-Path $exeDir 'HHUCampusAutoLogin-background.exe') -Destination $smokeDir
    $consoleExe = Join-Path $smokeDir 'HHUCampusAutoLogin.exe'
    & $consoleExe --help
    if ($LASTEXITCODE -ne 0) { throw 'Executable --help smoke check failed.' }
    & $consoleExe check
    if ($LASTEXITCODE -ne 2) { throw 'Missing-config smoke check should exit 2 without a network request.' }
    $background = Start-Process -FilePath (Join-Path $smokeDir 'HHUCampusAutoLogin-background.exe') -ArgumentList 'check' -WindowStyle Hidden -PassThru -Wait
    if ($background.ExitCode -ne 2) { throw 'Background executable missing-config smoke check failed.' }
    if (-not (Test-Path -LiteralPath (Join-Path $smokeDir 'logs\auto_login.log'))) {
        throw 'The executable did not create logs beside itself.'
    }

    $zipPath = Join-Path $distDir ('HHUCampusAutoLogin-' + $Version + '-windows-x64.zip')
    # Write explicit relative entries, so stale local files can never enter a release.
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zipStream = [IO.File]::Open($zipPath, [IO.FileMode]::Create)
    $zipArchive = [IO.Compression.ZipArchive]::new($zipStream, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($fileName in $fileNames) {
            [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $zipArchive, (Join-Path $stageDir $fileName), $fileName,
                [IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
        }
    }
    finally {
        $zipArchive.Dispose()
        $zipStream.Dispose()
    }
    $checksum = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $checksum + '  ' + [IO.Path]::GetFileName($zipPath) | Set-Content -LiteralPath ($zipPath + '.sha256') -Encoding ascii
    Write-Host ('Release ZIP: ' + $zipPath)
    Write-Host ('SHA256: ' + $checksum)
}
finally {
    Pop-Location
}

# The missing-config smoke check intentionally exits 2; do not leak it to CI.
exit 0
