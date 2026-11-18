# POE Delta release script (keep this file ASCII-only: Windows PowerShell 5.1)
#   powershell -ExecutionPolicy Bypass -File .\release.ps1 -NotesFile notes.md [-Pre]
#   1) read version from app\version.py (tag v<ver> must not exist yet)
#   2) build.ps1 -Name PoeDelta -NoRun  -> dist\PoeDelta.exe, dist\app-<ver>.zip, dist\manifest.json
#   3) dist\PoeDelta-<ver>.zip (exe and licenses for first install)
#   4) git commit + tag + push, gh release create (assets: PoeDelta-<ver>.zip, app-<ver>.zip, manifest.json)
#   -Pre : mark as pre-release (apps do NOT auto-update to it; for testing)
param([Parameter(Mandatory = $true)][string]$NotesFile, [switch]$Pre)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

function Test-ReleaseOrigin([string]$Url) {
    $normalized = ($Url.Trim() -replace '^git@github\.com:', 'https://github.com/').TrimEnd('/')
    $normalized = ($normalized -replace '\.git$', '').ToLowerInvariant()
    return $normalized -eq 'https://github.com/hsk260214-maker/poe-delta'
}

function Assert-ReleaseOrigin([string]$Url) {
    if (-not (Test-ReleaseOrigin $Url)) { throw 'origin must be hsk260214-maker/poe-delta' }
}

$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
Set-Location $root
$origin = git remote get-url origin
if ($LASTEXITCODE -ne 0) { throw 'cannot read origin' }
Assert-ReleaseOrigin $origin

$vtext = Get-Content (Join-Path $root 'app\version.py') -Raw
if ($vtext -notmatch 'VERSION\s*=\s*"([^"]+)"') { throw 'VERSION not found in app\version.py' }
$ver = $Matches[1]
$tag = "v$ver"
Write-Host "release $tag"

$existing = git tag --list $tag
if ($existing) { throw "tag $tag already exists - bump VERSION in app\version.py" }
if (-not (Test-Path $NotesFile)) { throw "notes file not found: $NotesFile" }

powershell -ExecutionPolicy Bypass -File (Join-Path $root 'build.ps1') -Name PoeDelta -NoRun
if ($LASTEXITCODE -ne 0) { throw 'build failed' }

$exe = Join-Path $root 'dist\PoeDelta.exe'
$full = Join-Path $root "dist\PoeDelta-$ver.zip"
$app = Join-Path $root "dist\app-$ver.zip"
$man = Join-Path $root 'dist\manifest.json'
$license = Join-Path $root 'LICENSE'
$aptLicense = Join-Path $root 'data\LICENSE-awakened-poe-trade.txt'
foreach ($f in @($exe, $app, $man, $license, $aptLicense)) { if (-not (Test-Path $f)) { throw "missing $f" } }
if (Test-Path $full) { Remove-Item $full -Force }
# the fresh exe is often locked for a while (antivirus scan) -> retry
$zipped = $false
for ($i = 1; $i -le 12 -and -not $zipped; $i++) {
    try {
        Compress-Archive -Path @($exe, $license, $aptLicense) -DestinationPath $full -ErrorAction Stop
        $zipped = $true
    } catch {
        Write-Host "      exe locked, retry $i/12 ..."
        if (Test-Path $full) { Remove-Item $full -Force }
        Start-Sleep -Seconds 5
    }
}
if (-not $zipped) { throw 'could not zip the exe (still locked)' }

gh auth setup-git  # git push uses the gh login
git add -A
$changes = git status --porcelain
if ($changes) { git commit -q -m "Release $tag" }
git tag $tag
git push -q origin HEAD
git push -q origin $tag

$ghArgs = @('release', 'create', $tag, $full, $app, $man, '--repo', 'hsk260214-maker/poe-delta', '--title', "POE Delta $tag", '--notes-file', $NotesFile)
if ($Pre) { $ghArgs += '--prerelease' }
gh @ghArgs
if ($LASTEXITCODE -ne 0) { throw 'gh release create failed' }
Write-Host "done: https://github.com/hsk260214-maker/poe-delta/releases/tag/$tag"
