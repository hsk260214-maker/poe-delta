import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(folder):
    return {path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in folder.rglob("*") if path.is_file()}


@pytest.fixture
def roots(tmp_path, monkeypatch):
    roaming, local = tmp_path / "roaming", tmp_path / "local"
    roaming.mkdir()
    local.mkdir()
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    return roaming, local


@pytest.fixture
def exited_process():
    with subprocess.Popen([sys.executable, "-c", "pass"], stdout=subprocess.DEVNULL) as child:
        assert child.wait(timeout=5) == 0
        yield child.pid


def original(roaming):
    folder = roaming / "ExileDelta"
    (folder / "data").mkdir(parents=True)
    (folder / "settings.json").write_text(json.dumps({
        "watch_clipboard": False, "trade": {"mode": "browser", "league": "Standard"},
        "app_update_seen": True, "app_update_skip": "1.0.99", "app_updated": {"to": "1.0.99"}}), encoding="utf-8")
    (folder / "characters.json").write_text('{"characters":["fixture"]}', encoding="utf-8")
    (folder / "profiles.json").write_text('{"tabs":["fixture"]}', encoding="utf-8")
    (folder / "data" / "names_ko.json").write_text('{"names":{}}', encoding="utf-8")
    return folder


def paths():
    return load_module("isolated_paths", ROOT / "app" / "paths.py")


def test_first_copy_preserves_original_and_never_reads_old_local(roots, monkeypatch):
    roaming, local = roots
    old = original(roaming)
    before = snapshot(old)
    old_local = local / "ExileDelta"
    (old_local / "app").mkdir(parents=True)
    (old_local / "app" / "state.json").write_text('{"current":"untrusted-old-code"}')
    local_before = snapshot(old_local)
    real_exists = Path.exists
    with monkeypatch.context() as context:
        def forbid_old_local(path):
            assert not path.is_relative_to(old_local), "원본 LOCAL을 읽으면 안 됩니다"
            return real_exists(path)

        context.setattr(Path, "exists", forbid_old_local)
        module = paths()
    assert module.ROAMING == roaming / "PoeDelta"
    assert module.LOCAL == local / "PoeDelta"
    assert module.APP_NAME == "POE Delta"
    assert not module.MIGRATION_FAILED
    copied = json.loads((module.ROAMING / "settings.json").read_text(encoding="utf-8"))
    assert copied == {"watch_clipboard": False, "trade": {"mode": "browser", "league": "Standard"}}
    for name in ("characters.json", "profiles.json", "data/names_ko.json"):
        assert (module.ROAMING / name).read_bytes() == (old / name).read_bytes()
    assert snapshot(old) == before
    assert snapshot(old_local) == local_before
    assert not module.LOCAL.exists()
    assert not list(roaming.glob("PoeDelta.partial-*"))


def test_existing_custom_data_is_not_copied_again(roots, monkeypatch):
    roaming, _ = roots
    old = original(roaming)
    new = roaming / "PoeDelta"
    new.mkdir()
    (new / "settings.json").write_text('{"own":true}')
    before = snapshot(old)

    def forbidden(*args, **kwargs):
        pytest.fail("완료된 커스텀 폴더가 있으면 다시 복사하면 안 됩니다")

    monkeypatch.setattr(shutil, "copytree", forbidden)
    module = paths()
    assert module.ROAMING == new
    assert (new / "settings.json").read_text() == '{"own":true}'
    assert snapshot(old) == before


@pytest.mark.parametrize("phase", ["copy", "settings", "rename"])
def test_failed_copy_is_temporary_and_next_import_retries(roots, monkeypatch, phase):
    roaming, _ = roots
    old = original(roaming)
    before = snapshot(old)
    partial = roaming / f"PoeDelta.partial-{os.getpid()}"
    real_write = Path.write_text
    with monkeypatch.context() as context:
        if phase == "copy":
            def fail_copy(source, destination):
                destination.mkdir()
                (destination / "incomplete").write_text("partial")
                raise OSError("injected copy failure")
            context.setattr(shutil, "copytree", fail_copy)
        elif phase == "settings":
            def fail_write(path, *args, **kwargs):
                if path == partial / "settings.json":
                    raise OSError("injected settings write failure")
                return real_write(path, *args, **kwargs)
            context.setattr(Path, "write_text", fail_write)
        else:
            def fail_rename(*args):
                raise OSError("injected rename failure")
            context.setattr(os, "rename", fail_rename)
        failed = paths()
    assert failed.MIGRATION_FAILED
    assert failed.ROAMING.is_dir()
    assert failed.ROAMING.name.startswith(f"PoeDelta-session-{os.getpid()}-")
    assert not (roaming / "PoeDelta").exists()
    assert not partial.exists()
    assert snapshot(old) == before
    retried = paths()
    assert not retried.MIGRATION_FAILED
    assert retried.ROAMING == roaming / "PoeDelta"
    assert (retried.ROAMING / "characters.json").read_bytes() == (old / "characters.json").read_bytes()
    assert snapshot(old) == before


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_stale_partial_is_never_used(roots, monkeypatch, cleanup_fails, exited_process):
    roaming, _ = roots
    stale = roaming / f"PoeDelta.partial-{exited_process}"
    stale.mkdir()
    (stale / "settings.json").write_text('{"incomplete":true}')
    if cleanup_fails:
        def locked(path):
            raise OSError("injected locked folder")
        monkeypatch.setattr(shutil, "rmtree", locked)
    module = paths()
    assert module.ROAMING == roaming / "PoeDelta"
    assert not module.MIGRATION_FAILED
    assert stale.exists() == cleanup_fails


def test_live_and_own_partials_survive_only_dead_partial_is_cleaned(roots, exited_process):
    roaming, _ = roots
    child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.buffer.read(1)"],
                             stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
    try:
        live = roaming / f"PoeDelta.partial-{child.pid}"
        own = roaming / f"PoeDelta.partial-{os.getpid()}"
        dead = roaming / f"PoeDelta.partial-{exited_process}"
        for folder in (live, own, dead):
            folder.mkdir()
            (folder / "settings.json").write_text('{"copying":true}')
        module = paths()
        assert not module.MIGRATION_FAILED
        assert (live / "settings.json").read_text() == '{"copying":true}'
        assert (own / "settings.json").read_text() == '{"copying":true}'
        assert not dead.exists()
        assert not module.ROAMING.exists()
    finally:
        child.stdin.close()
        assert child.wait(timeout=5) == 0
def test_rename_race_uses_completed_winner(roots, monkeypatch):
    roaming, _ = roots
    old = original(roaming)
    before = snapshot(old)

    def winner_finished(source, destination):
        destination.mkdir()
        (destination / "settings.json").write_text('{"winner":true}')
        raise FileExistsError("another process already completed migration")

    monkeypatch.setattr(os, "rename", winner_finished)
    module = paths()
    assert not module.MIGRATION_FAILED
    assert module.ROAMING == roaming / "PoeDelta"
    assert json.loads((module.ROAMING / "settings.json").read_text()) == {"winner": True}
    assert not list(roaming.glob("PoeDelta.partial-*"))
    assert snapshot(old) == before


def test_launcher_and_legacy_names_stay_separate(roots):
    roaming, local = roots
    for base in roots:
        legacy = base / "ExileSieve"
        legacy.mkdir()
        (legacy / "keep.txt").write_text("keep")
    module = paths()
    launcher = load_module("isolated_launcher", ROOT / "launcher" / "launcher.py")
    assert launcher._local_dir() == module.LOCAL == local / "PoeDelta"
    assert module.ROAMING == roaming / "PoeDelta"
    assert not module.ROAMING.exists()
    assert not module.LOCAL.exists()
    for base in roots:
        assert (base / "ExileSieve" / "keep.txt").read_text() == "keep"


def test_single_instance_key_is_custom_and_user_specific(roots, monkeypatch):
    import main

    first = main.single_instance_key()
    assert first.startswith("PoeDelta-")
    assert first != "ExileDelta-" + first.split("-", 1)[1]
    monkeypatch.setenv("APPDATA", os.environ["APPDATA"].upper())
    assert main.single_instance_key() == first
    monkeypatch.setenv("APPDATA", str(roots[0] / "another-user"))
    assert main.single_instance_key() != first
