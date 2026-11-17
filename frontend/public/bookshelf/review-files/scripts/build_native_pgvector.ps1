param([string]$VisualStudio = 'C:\Program Files\Microsoft Visual Studio\18\Community')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pgRoot = Join-Path $projectRoot '.local\native-postgres\pgsql'
$sourceRoot = Join-Path $projectRoot '.local\native-postgres\pgvector-0.8.7'
if (!(Test-Path -LiteralPath (Join-Path $pgRoot 'include\server\postgres.h'))) { throw 'Prepare portable PostgreSQL first.' }
& (Join-Path $VisualStudio 'Common7\Tools\Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$previousPgRoot = $env:PGROOT
try {
    $env:PGROOT = $pgRoot
    Push-Location -LiteralPath $sourceRoot
    try {
        nmake /NOLOGO /F Makefile.win
        if ($LASTEXITCODE -ne 0) { throw 'pgvector build failed' }
        nmake /NOLOGO /F Makefile.win install
        if ($LASTEXITCODE -ne 0) { throw 'pgvector local install failed' }
    } finally { Pop-Location }
} finally {
    if ($null -eq $previousPgRoot) { Remove-Item Env:PGROOT -ErrorAction SilentlyContinue }
    else { $env:PGROOT = $previousPgRoot }
}
Write-Output 'pgvector was built and installed only inside this project portable PostgreSQL folder.'
