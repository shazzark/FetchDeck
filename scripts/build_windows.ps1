$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$dashboard = Join-Path $repoRoot 'apps\dashboard\out'
$entryPoint = Join-Path $repoRoot 'scripts\launcher.py'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'Create .venv and install requirements-build.txt before packaging.'
}
if (-not (Test-Path -LiteralPath (Join-Path $dashboard 'index.html'))) {
    throw 'Build the dashboard first: npm run build --workspace @fetchdeck/dashboard'
}

Push-Location $repoRoot
try {
    & $python -m PyInstaller --noconfirm --clean --onedir --windowed `
        --name FetchDeck `
        --paths src `
        --add-data "$dashboard;dashboard" `
        $entryPoint
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }

    $package = Join-Path $repoRoot 'dist\FetchDeck'
    if (-not (Test-Path -LiteralPath (Join-Path $package '_internal\dashboard\index.html'))) {
        throw 'PyInstaller did not place the dashboard under the one-folder package.'
    }
    $licenseDir = Join-Path $package 'licenses'
    New-Item -ItemType Directory -Force -Path $licenseDir | Out-Null

    $sitePackages = Join-Path $repoRoot '.venv\Lib\site-packages'
    Copy-Item (Join-Path $sitePackages 'pyside6-6.9.2.dist-info\licenses\LicenseRef-Qt-Commercial.txt') $licenseDir
    Copy-Item (Join-Path $sitePackages 'pyside6_essentials-6.9.2.dist-info\licenses\LicenseRef-Qt-Commercial.txt') (Join-Path $licenseDir 'Qt-for-Python-Essentials-LicenseRef.txt')
    Copy-Item (Join-Path $sitePackages 'shiboken6-6.9.2.dist-info\licenses\LicenseRef-Qt-Commercial.txt') (Join-Path $licenseDir 'Shiboken6-LicenseRef.txt')
    Copy-Item (Join-Path $sitePackages 'pyinstaller-6.22.3.dist-info\licenses\COPYING.txt') $licenseDir
    Copy-Item (Join-Path $repoRoot 'docs\THIRD-PARTY-NOTICES.md') $package

    $archive = Join-Path $repoRoot 'dist\FetchDeck-windows-x64.zip'
    Compress-Archive -Path (Join-Path $package '*') -DestinationPath $archive -Force
    if (-not (Test-Path -LiteralPath $archive)) {
        throw 'Portable archive was not created.'
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($archive)
    try {
        $entries = $zip.Entries | ForEach-Object { $_.FullName.Replace('\', '/') }
        if ($entries -notcontains 'FetchDeck.exe' -or $entries -notcontains '_internal/dashboard/index.html') {
            throw 'Portable archive is missing the application or dashboard.'
        }
    }
    finally {
        $zip.Dispose()
    }

    Write-Host "Package created at $package"
    Write-Host "Portable archive created at $archive"
}
finally {
    Pop-Location
}
