"""POE Delta 로더 (exe 의 시작점).

exe 안에는 Python · Qt 같은 실행 환경과 '기본 앱 코드' 한 벌(appsrc)이 들어 있다.
실제로 실행하는 앱 코드는 다음 중 하나:
  1) %LOCALAPPDATA%\\PoeDelta\\app\\<버전>\\   — GitHub 릴리스에서 받은 최신 코드 (exe 안 코드보다 새 버전일 때)
  2) exe 안의 기본 코드 (처음 실행 · 인터넷 없음 · 받은 버전이 고장났을 때)

받은 버전이 정상 시작(.ok 표시)을 못 하고 3번 연속 실패하면 고장으로 표시하고 이전 버전/기본 코드로 돌아간다.
앱 코드는 이 파일을 import 하지 않는다. 앱이 쓰는 라이브러리는 아래 _deps() 에 적어 둬야 exe 에 들어간다
(앱 코드는 exe 안의 모듈 묶음에 넣지 않고 파일로 읽어야 받은 새 코드가 쓰이기 때문).
"""
from __future__ import annotations

import json
import os
import re
import runpy
import sys
import traceback
from pathlib import Path

LOADER_VERSION = 1  # exe(로더 · 실행 환경)가 바뀌면 올림 → 릴리스 manifest 의 min_loader 와 비교
DIR_NAME = "PoeDelta"
MAX_TRIES = 3


def _deps() -> None:  # pragma: no cover - 호출하지 않음. PyInstaller 가 의존성을 찾도록 import 만 적어 둔다
    import argparse, base64, bisect, calendar, codecs, collections, concurrent.futures, contextlib, copy, csv  # noqa: E401,F401
    import ctypes, ctypes.wintypes, dataclasses, datetime, decimal, difflib, email, enum, fnmatch, fractions  # noqa: E401,F401
    import functools, glob, gzip, hashlib, heapq, html, html.parser, http.client, importlib, inspect, io  # noqa: E401,F401
    import itertools, json, locale, logging, lzma, math, operator, platform, pprint, queue, random, re  # noqa: E401,F401
    import secrets, shutil, signal, socket, ssl, statistics, string, struct, subprocess, tempfile, textwrap  # noqa: E401,F401
    import threading, time, traceback, typing, unicodedata, urllib.parse, urllib.request, uuid, weakref  # noqa: E401,F401
    import webbrowser, xml.etree.ElementTree, zipfile, zlib  # noqa: E401,F401
    import requests  # noqa: F401
    import lupa.luajit21  # noqa: F401
    import PySide6.QtCore, PySide6.QtGui, PySide6.QtWidgets, PySide6.QtNetwork  # noqa: E401,F401


def _local_dir() -> Path:
    """app/paths.py 와 같은 독립 LOCAL 경로. 원본은 복사하거나 옮기지 않는다."""
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    return base / DIR_NAME


def _vt(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.strip().lstrip("v").split("."))
    except (ValueError, AttributeError):
        return (0,)


def _code_version(root: Path) -> str:
    try:
        m = re.search(r'VERSION\s*=\s*"([^"]+)"', (root / "app" / "version.py").read_text(encoding="utf-8"))
        return m.group(1) if m else "0"
    except OSError:
        return "0"


def _valid(root: Path) -> bool:
    return (root / ".complete").exists() and (root / "app" / "main.py").exists()


class State:
    """%LOCALAPPDATA%\\PoeDelta\\app\\state.json — {current, previous, bad: [..], tries: {ver: n}}"""

    def __init__(self, root: Path):
        self.path = root / "state.json"
        try:
            self.d = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.d = {}
        self.d.setdefault("bad", [])
        self.d.setdefault("tries", {})

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.d, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    def mark_bad(self, ver: str) -> None:
        if ver and ver not in self.d["bad"]:
            self.d["bad"].append(ver)
        if self.d.get("current") == ver:
            self.d["current"] = self.d.get("previous") if self.d.get("previous") != ver else None
        self.save()


def _bundled() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "appsrc"


def choose() -> tuple[Path, bool]:
    """(실행할 코드 폴더, 받은 버전인지)."""
    forced = os.environ.get("EXILEDELTA_APP_ROOT")
    if forced and Path(forced, "app", "main.py").exists():
        return Path(forced), False  # PoB 워커 등 하위 프로세스: 부모와 같은 코드
    bundled = _bundled()
    bver = _code_version(bundled)
    apps = _local_dir() / "app"
    st = State(apps)
    for _ in range(3):
        cur = st.d.get("current")
        if not cur or cur in st.d["bad"]:
            break
        d = apps / cur
        if not _valid(d) or _vt(cur) <= _vt(bver):
            break  # exe 안 코드가 같거나 더 새것 (새 exe 를 받은 경우) → exe 안 코드
        if (d / ".ok").exists():
            return d, True
        n = int(st.d["tries"].get(cur, 0))
        if n >= MAX_TRIES:
            st.mark_bad(cur)  # 정상 시작 표시 없이 연속 실패 → 이전 버전으로
            continue
        st.d["tries"][cur] = n + 1
        st.save()
        return d, True
    return bundled, False


def _restart_without(root: Path) -> None:
    import subprocess

    env = dict(os.environ)
    env.pop("EXILEDELTA_APP_ROOT", None)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"  # 별개 실행 (부모 exe 의 임시 폴더를 같이 쓰지 않게)
    subprocess.Popen([sys.executable] + sys.argv[1:], env=env, close_fds=True,
                     creationflags=0x00000008 | 0x00000200)  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def _error_box(text: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text[:3000], "POE Delta 실행 오류", 0x10)
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    worker = "--pob-worker" in sys.argv
    root, downloaded = choose()
    os.environ["EXILEDELTA_APP_ROOT"] = str(root)
    os.environ["EXILEDELTA_LOADER"] = str(LOADER_VERSION)
    os.environ["EXILEDELTA_BUNDLED"] = _code_version(_bundled())
    sys.path.insert(0, str(root / "app"))
    try:
        runpy.run_path(str(root / "app" / "main.py"), run_name="__main__")
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001
        tb = traceback.format_exc()
        try:
            log = _local_dir() / "launcher.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"--- {root}\n{tb}\n")
        except OSError:
            pass
        if worker:
            raise
        if downloaded and not (root / ".ok").exists():
            # 받은 새 버전이 시작조차 못 함 → 고장 표시하고 이전 코드로 다시 실행
            State(_local_dir() / "app").mark_bad(root.name)
            _restart_without(root)
            return
        _error_box(f"프로그램을 시작하지 못했습니다.\n\n{tb[-2000:]}")
        raise


if __name__ == "__main__":
    main()
