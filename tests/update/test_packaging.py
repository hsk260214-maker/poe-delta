import base64
import hashlib
import importlib.util
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def powershell(script):
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def test_package_contains_notices_and_trade_without_manifest_change(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("isolated_pack_app", ROOT / "tools" / "pack_app.py")
    pack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pack)
    relative = {path.relative_to(ROOT).as_posix() for path in pack.files()}
    required = {"LICENSE", "data/LICENSE-awakened-poe-trade.txt", "data/trade_stats.json", "app/trade/trade_window.py"}
    assert required <= relative
    stage, output = tmp_path / "stage", tmp_path / "output"
    monkeypatch.setattr(pack.sys, "argv", ["pack_app.py", str(stage), str(output)])
    assert pack.main() == 0
    manifest = json.loads((output / "manifest.json").read_text())
    assert set(manifest) == {"version", "zip", "sha256", "min_loader"}
    assert manifest["version"] == "1.1.0"
    assert manifest["min_loader"] == 1
    payload = output / manifest["zip"]
    assert hashlib.sha256(payload.read_bytes()).hexdigest() == manifest["sha256"]
    with zipfile.ZipFile(payload) as archive:
        assert required <= set(archive.namelist())
        assert archive.testzip() is None
        for name in required:
            assert archive.read(name) == (ROOT / name).read_bytes()
            assert (stage / name).read_bytes() == (ROOT / name).read_bytes()


def test_release_origin_functions_without_running_script():
    path = str(ROOT / "release.ps1").replace("'", "''")
    script = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile('__PATH__', [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'release parse error' }
$functions = $ast.FindAll({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -in @('Test-ReleaseOrigin', 'Assert-ReleaseOrigin')}, $true)
foreach ($fn in $functions) { Invoke-Expression $fn.Extent.Text }
$cases = @(
 'https://github.com/hsk260214-maker/poe-delta',
 'https://github.com/hsk260214-maker/poe-delta.git',
 'git@github.com:hsk260214-maker/poe-delta.git',
 'HTTPS://GITHUB.COM/HSK260214-MAKER/POE-DELTA.GIT/',
 'https://github.com/hsk260214-maker/poe-delta/',
 'https://github.com/KyungseokKANG/exile-delta.git',
 'git@github.com:someone/another.git'
)
$rows = foreach ($url in $cases) {
 $blocked = $false
 try { Assert-ReleaseOrigin $url } catch { $blocked = $true }
 [pscustomobject]@{allowed=(Test-ReleaseOrigin $url); blocked=$blocked}
}
$rows | ConvertTo-Json -Compress
""".replace("__PATH__", path)
    rows = json.loads(powershell(script))
    assert [row["allowed"] for row in rows] == [True] * 5 + [False] * 2
    assert [row["blocked"] for row in rows] == [False] * 5 + [True] * 2


def test_build_process_filter_keeps_other_folders_running():
    script_path = str(ROOT / "build.ps1").replace("'", "''")
    executable = str(ROOT / "dist" / "PoeDelta.exe").replace("'", "''")
    script = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile('__PATH__', [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'build parse error' }
$fn = $ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-BuildProcesses'}, $true)
Invoke-Expression $fn.Extent.Text
function Get-Process {
 [CmdletBinding()]param([string]$Name)
 @(
  [pscustomobject]@{Id=1;Path='__EXE__'},
  [pscustomobject]@{Id=2;Path='C:\other\PoeDelta.exe'},
  [pscustomobject]@{Id=3;Path='C:\original\ExileDelta.exe'},
  [pscustomobject]@{Id=4;Path=$null}
 )
}
ConvertTo-Json -InputObject @((Get-BuildProcesses '__EXE__') | ForEach-Object { $_.Id }) -Compress
""".replace("__PATH__", script_path).replace("__EXE__", executable)
    assert json.loads(powershell(script)) == [1]
    for name in ("release.ps1", "build.ps1"):
        (ROOT / name).read_bytes().decode("ascii")


@pytest.mark.parametrize("fail_build", [False, True])
def test_build_work_is_cleaned_on_success_and_failure(tmp_path, fail_build):
    sandbox = tmp_path / "build-case"
    sandbox.mkdir()
    script_file = sandbox / "build.ps1"
    script_file.write_bytes((ROOT / "build.ps1").read_bytes())
    data = sandbox / "data"
    data.mkdir()
    for name in ("mods_ko.json", "names_ko.json", "ko_en.json"):
        (data / name).write_text("{}")
    temporary = sandbox / "temp"
    unrelated = temporary / "poedelta_build" / "unrelated"
    unrelated.mkdir(parents=True)
    (unrelated / "keep.txt").write_text("keep")
    script = r"""
$ErrorActionPreference = 'Stop'
$env:TEMP = '__TEMP__'
$global:ObservedWork = $null
$global:FailBuild = __FAIL__
function python {
 $global:LASTEXITCODE = 0
 if ($args[0] -like '*pack_app.py') {
  $stage = [string]$args[1]
  $global:ObservedWork = Split-Path $stage -Parent
  New-Item -ItemType Directory -Path $stage -Force | Out-Null
  [IO.File]::WriteAllText((Join-Path $stage 'fixture.txt'), 'fixture')
 }
 if ($args[0] -eq '-m') {
  if ($global:FailBuild) { $global:LASTEXITCODE = 7; return }
  $dist = [string]$args[[array]::IndexOf($args, '--distpath') + 1]
  New-Item -ItemType Directory -Path $dist -Force | Out-Null
  [IO.File]::WriteAllText((Join-Path $dist 'PoeDelta.exe'), 'not an executable')
 }
}
function Get-Process { [CmdletBinding()]param([string]$Name) @() }
$caught = $false
try { & '__SCRIPT__' -NoRun } catch {
 if ($_.Exception.Message -ne 'PyInstaller build failed') { throw }
 $caught = $true
}
if (-not $global:ObservedWork) { throw 'work was not exercised' }
[pscustomobject]@{
 failed=$caught
 workExists=(Test-Path -LiteralPath $global:ObservedWork)
 unrelated=[string](Get-Content -LiteralPath '__KEEP__' -Raw)
} | ConvertTo-Json -Compress
""".replace("__TEMP__", str(temporary).replace("'", "''")).replace(
        "__SCRIPT__", str(script_file).replace("'", "''")).replace(
        "__KEEP__", str(unrelated / "keep.txt").replace("'", "''")).replace(
        "__FAIL__", "$true" if fail_build else "$false")
    result = json.loads(powershell(script).splitlines()[-1])
    assert result == {"failed": fail_build, "workExists": False, "unrelated": "keep"}
    assert {folder.name for folder in (temporary / "poedelta_build").iterdir()} == {"unrelated"}
