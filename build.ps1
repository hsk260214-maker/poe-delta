# POE Delta build + run script (keep this file ASCII-only: Windows PowerShell 5.1)
#   1) stop only this dist\PoeDelta.exe
#   2) build mod data (if missing) and icon
#   3) PyInstaller -> dist\PoeDelta.exe
#   4) launch the new exe
#   -Name X : output exe name (default PoeDelta), -Zip : also make dist\X.zip
#   after a successful build, only older dist\PoeDelta*.exe / .zip are removed
param([switch]$NoRun, [switch]$RefreshData, [string]$Name = 'PoeDelta', [switch]$Zip)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$name = $Name
$work = Join-Path (Join-Path $env:TEMP 'poedelta_build') ([guid]::NewGuid().ToString('N'))
try {
New-Item -ItemType Directory -Path $work -Force | Out-Null
$exe = Join-Path $root "dist\$name.exe"

function Get-BuildProcesses([string]$Executable) {
    $fullPath = [System.IO.Path]::GetFullPath($Executable)
    Get-Process -Name ([System.IO.Path]::GetFileNameWithoutExtension($fullPath)) -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path -ieq $fullPath }
}

Write-Host "[1/4] stop running $name"
$deadline = (Get-Date).AddSeconds(20)
while (Test-Path $exe) {
    $procs = Get-BuildProcesses $exe
    if ($procs) {
        Write-Host ("      killing PID " + (($procs | ForEach-Object { $_.Id }) -join ', '))
        $procs | Stop-Process -Force -ErrorAction SilentlyContinue
        $procs | Wait-Process -Timeout 5 -ErrorAction SilentlyContinue
    }
    try {
        Remove-Item $exe -Force -ErrorAction Stop
    } catch {
        if ((Get-Date) -gt $deadline) { throw "cannot remove $exe (still running or locked)" }
        Start-Sleep -Milliseconds 500
    }
}

Write-Host "[2/4] data / icon"
if ($RefreshData -or -not (Test-Path "$root\data\mods_ko.json")) {
    if ($RefreshData) { python "$root\tools\build_data.py" --refresh } else { python "$root\tools\build_data.py" }
    if ($LASTEXITCODE -ne 0) { throw 'data build failed' }
}
if ($RefreshData -or -not (Test-Path "$root\data\names_ko.json") -or -not (Test-Path "$root\data\ko_en.json")) {
    if ($RefreshData) { python "$root\tools\build_names.py" --refresh } else { python "$root\tools\build_names.py" }
    if ($LASTEXITCODE -ne 0) { throw 'names build failed' }
}
python "$root\tools\make_icon.py"
if ($LASTEXITCODE -ne 0) { throw 'icon build failed' }

Write-Host "[3/4] PyInstaller"
# app code is NOT compiled into the exe: launcher\launcher.py runs it from files
#   - built-in copy:  <exe>\appsrc\{app,data}   (staged below)
#   - downloaded:     %LOCALAPPDATA%\PoeDelta\app\<ver>\   (GitHub release app-<ver>.zip)
# dist\app-<ver>.zip + dist\manifest.json are the update payload (release.ps1 uploads them)
$stage = Join-Path $work 'appsrc'
python "$root\tools\pack_app.py" $stage "$root\dist"
if ($LASTEXITCODE -ne 0) { throw 'pack_app failed' }
python -m PyInstaller --noconfirm --onefile --windowed --uac-admin --log-level WARN `
    --name $name `
    --icon "$root\assets\icon.ico" `
    --add-data "$stage;appsrc" `
    --hidden-import lupa.luajit21 `
    --exclude-module lupa.lua51 --exclude-module lupa.lua52 --exclude-module lupa.lua53 `
    --exclude-module lupa.lua54 --exclude-module lupa.luajit20 `
    --workpath $work --specpath $work --distpath "$root\dist" `
    "$root\launcher\launcher.py"
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }

if ($Zip) {
    $zipPath = Join-Path $root "dist\$name.zip"
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
    Compress-Archive -Path $exe -DestinationPath $zipPath
    Write-Host "      zip: $zipPath"
}

# remove only older PoeDelta builds in this dist; never touch upstream names
Get-ChildItem (Join-Path $root 'dist') -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like 'PoeDelta*' -and ($_.Extension -eq '.exe' -or $_.Extension -eq '.zip') -and $_.BaseName -ne $name } |
    ForEach-Object {
        $old = $_
        if ($old.Extension -eq '.exe') {
            $procs = Get-BuildProcesses $old.FullName
            if ($procs) {
                Write-Host ("      stop old " + $old.BaseName + " (PID " + (($procs | ForEach-Object { $_.Id }) -join ', ') + ")")
                $procs | Stop-Process -Force -ErrorAction SilentlyContinue
                $procs | Wait-Process -Timeout 5 -ErrorAction SilentlyContinue
            }
        }
        $removed = $false
        for ($i = 0; $i -lt 10 -and -not $removed; $i++) {
            try { Remove-Item $old.FullName -Force -ErrorAction Stop; $removed = $true }
            catch { Start-Sleep -Milliseconds 500 }
        }
        if ($removed) { Write-Host ("      removed old " + $old.Name) }
        else { Write-Host ("      WARNING: could not remove " + $old.Name + " (in use on another PC?)") }
    }

if (-not $NoRun) {
    Write-Host "[4/4] launch $exe"
    # Smart App Control may block a freshly written unsigned exe for a few seconds -> retry
    $started = $false
    for ($i = 1; $i -le 8 -and -not $started; $i++) {
        try {
            Start-Process -FilePath $exe -ErrorAction Stop
            $started = $true
        } catch {
            Write-Host "      launch blocked (try $i/8), retrying..."
            Start-Sleep -Seconds 2
        }
    }
    if (-not $started) { throw "launch failed: $exe" }
} else {
    Write-Host "[4/4] launch skipped (-NoRun)"
}
} finally {
    if (Test-Path -LiteralPath $work) {
        Remove-Item -LiteralPath $work -Recurse -Force
    }
}
