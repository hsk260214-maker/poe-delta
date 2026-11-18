"""커스텀판 데이터 경로. 원본 ROAMING은 최초 한 번 복사하며 LOCAL은 공유하지 않는다."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

APP_NAME = "POE Delta"
DIR_NAME = "PoeDelta"
MIGRATION_WARNING = "원본 설정을 가져오지 못했습니다. 다음 실행 때 다시 시도합니다"


def _root(env: str) -> Path:
    return Path(os.environ.get(env) or Path.home())


def _discard_partial(path: Path) -> None:
    try:
        shutil.rmtree(path)
    except OSError:
        pass


def _process_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            # 접근 거부 등 확인 불가는 살아 있는 쪽으로 취급해 복사본을 보호한다.
            return ctypes.get_last_error() != 87
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _roaming() -> tuple[Path, bool]:
    base = _root("APPDATA")
    new = base / DIR_NAME
    for partial in base.glob(f"{DIR_NAME}.partial-*"):
        suffix = partial.name.removeprefix(f"{DIR_NAME}.partial-")
        if suffix.isdecimal():
            pid = int(suffix)
            if pid != os.getpid() and not _process_alive(pid):
                _discard_partial(partial)
    old = base / "ExileDelta"
    if new.exists() or not old.exists():
        return new, False
    partial = base / f"{DIR_NAME}.partial-{os.getpid()}"
    try:
        shutil.copytree(old, partial)
        settings = partial / "settings.json"
        if settings.exists():
            data = json.loads(settings.read_text(encoding="utf-8"))
            for key in ("app_update_seen", "app_update_skip", "app_updated"):
                data.pop(key, None)
            settings.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        try:
            os.rename(partial, new)
        except OSError:
            if not new.is_dir():
                raise
            # 다른 프로세스가 먼저 복사를 완료했다. 그 완성본을 쓰고 자기 사본만 버린다.
            _discard_partial(partial)
        return new, False
    except (OSError, ValueError, TypeError, AttributeError):
        _discard_partial(partial)
        session = Path(tempfile.mkdtemp(prefix=f"{DIR_NAME}-session-{os.getpid()}-"))
        return session, True


ROAMING, MIGRATION_FAILED = _roaming()
LOCAL = _root("LOCALAPPDATA") / DIR_NAME
