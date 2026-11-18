"""프로그램(앱 코드) 자동 업데이트 — GitHub 릴리스.

릴리스 (github.com/hsk260214-maker/poe-delta/releases) 에는 release.ps1 이 아래 파일을 올린다:
  manifest.json      {"version", "zip", "sha256", "min_loader", "notes"}
  app-<버전>.zip     앱 코드 (app/, data/) — 1~2MB
  PoeDelta-<버전>.zip  처음 설치용 exe

걸러 내는 규칙:
  - '최신 릴리스'만 본다 (GitHub 가 시험판 Pre-release · 초안은 빼고 알려 줌)
  - 지금 버전보다 높은 버전만 · 이 PC 에서 시작에 실패했던 버전(state.json bad)은 건너뜀
  - min_loader 가 지금 exe 보다 높으면 코드만으로는 안 됨 → 새 exe 를 받으라고 안내
  - 받은 zip 은 SHA-256 이 manifest 와 같아야 설치
설치: %LOCALAPPDATA%\\PoeDelta\\app\\<버전>\\ 에 풀고 state.json 의 current 를 바꾼 뒤 재시작 (실제 전환은 로더가 함).
로더 없이(개발 모드 python app\\main.py) 실행하면 동작하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

import requests

from paths import LOCAL
from version import VERSION

REPO = "hsk260214-maker/poe-delta"
UA = {"User-Agent": "PoeDelta-updater", "Accept": "application/vnd.github+json"}
APPS = LOCAL / "app"
RESTART = {"want": False}


def enabled() -> bool:
    return bool(os.environ.get("EXILEDELTA_LOADER"))


def loader_version() -> int:
    try:
        return int(os.environ.get("EXILEDELTA_LOADER") or 0)
    except ValueError:
        return 0


def vt(v: str) -> tuple:
    try:
        return tuple(int(x) for x in str(v).strip().lstrip("v").split("."))
    except ValueError:
        return (0,)


# ---------------------------------------------------------------- 상태 (로더와 같은 파일)
def _state() -> dict:
    try:
        d = json.loads((APPS / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    d.setdefault("bad", [])
    d.setdefault("tries", {})
    return d


def _save_state(d: dict) -> None:
    APPS.mkdir(parents=True, exist_ok=True)
    tmp = APPS / "state.tmp"
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, APPS / "state.json")


def mark_ok() -> None:
    """정상 시작 표시 (로더가 '고장난 버전' 판단에 씀). 창이 뜨고 잠시 뒤 호출."""
    root = os.environ.get("EXILEDELTA_APP_ROOT")
    if not root:
        return
    try:
        p = Path(root) / ".ok"
        if not p.exists():
            p.write_text(VERSION, encoding="utf-8")
        st = _state()
        if st["tries"].pop(Path(root).name, None) is not None:
            _save_state(st)
    except OSError:
        pass


# ---------------------------------------------------------------- 확인
def latest() -> dict | None:
    """최신 릴리스 정보 {version, zip_url, sha256, min_loader, notes, page} 또는 None (릴리스 없음).
    시험용: 환경 변수 EXILEDELTA_UPDATE_MANIFEST 에 로컬 manifest.json 경로를 주면 그걸 씀."""
    test = os.environ.get("EXILEDELTA_UPDATE_MANIFEST")
    if test:
        m = json.loads(Path(test).read_text(encoding="utf-8"))
        z = Path(test).with_name(m["zip"])
        return {"version": m["version"], "zip_url": z.as_uri(), "sha256": m["sha256"],
                "min_loader": int(m.get("min_loader", 1)), "notes": m.get("notes", ""), "page": ""}
    r = requests.get(f"https://api.github.com/repos/{REPO}/releases/latest", headers=UA, timeout=15)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    rel = r.json()
    assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
    if "manifest.json" not in assets:
        return None
    m = requests.get(assets["manifest.json"], headers=UA, timeout=15).json()
    if m.get("zip") not in assets:
        return None
    return {"version": m["version"], "zip_url": assets[m["zip"]], "sha256": m["sha256"],
            "min_loader": int(m.get("min_loader", 1)), "notes": rel.get("body") or m.get("notes", ""),
            "page": rel.get("html_url", "")}


def history(newer_than: str | None = None, upto: str | None = None) -> list[dict]:
    """릴리스 내역 [{version, title, date, notes}] 최신 순. 시험판 · 초안은 뺌.
    newer_than 을 주면 그보다 높은 버전만 (예: 지금 1.0.0, 최신 1.0.3 → 1.0.3 · 1.0.2 · 1.0.1)."""
    test = os.environ.get("EXILEDELTA_UPDATE_MANIFEST")
    if test:
        m = json.loads(Path(test).read_text(encoding="utf-8"))
        rels = m.get("history") or [{"version": m["version"], "title": f"v{m['version']}", "date": "",
                                      "notes": m.get("notes", "")}]
    else:
        r = requests.get(f"https://api.github.com/repos/{REPO}/releases?per_page=50", headers=UA, timeout=15)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        rels = [{"version": x["tag_name"].lstrip("v"), "title": x.get("name") or x["tag_name"],
                 "date": (x.get("published_at") or "")[:10], "notes": x.get("body") or ""}
                for x in r.json() if not x.get("draft") and not x.get("prerelease")]
    out = [x for x in rels
           if (newer_than is None or vt(x["version"]) > vt(newer_than)) and (upto is None or vt(x["version"]) <= vt(upto))]
    return sorted(out, key=lambda x: vt(x["version"]), reverse=True)


def history_markdown(rels: list[dict], current: str | None = None) -> str:
    """내역 → 화면용 마크다운. 릴리스 글의 '설치' 안내처럼 업데이트와 상관없는 부분은 줄임."""
    import re

    parts = []
    for x in rels:
        body = (x.get("notes") or "").strip()
        body = re.sub(r"(?ms)^#+\s*설치.*?(?=^#+\s|\Z)", "", body)  # '### 설치' 절은 빼기
        body = re.sub(r"(?m)^`app-.*manifest\.json`.*$", "", body)  # 업데이트용 파일 안내 줄
        body = re.sub(r"(?m)^\*.*Grinding Gear Games.*$", "", body)  # 고지 문구 줄
        body = re.sub(r"(?m)^#{1,2}\s+.*$", "", body, count=1)  # 맨 위 제목은 아래 머리로 대신
        body = re.sub(r"(?m)^#+\s*(이번 버전|변경 내용|바뀐 점)\s*$", "", body)  # 버전마다 반복되는 소제목
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        mark = "  ← 지금 버전" if current and x["version"] == current else ""
        date = f" · {x['date']}" if x.get("date") else ""
        parts.append(f"## v{x['version']}{date}{mark}\n\n{body or '(내용 없음)'}")
    return "\n\n---\n\n".join(parts)


def decide(info: dict | None) -> str:
    """'none'(최신) / 'bad'(실패했던 버전) / 'exe'(새 exe 필요) / 'update'."""
    if not info or vt(info["version"]) <= vt(VERSION):
        return "none"
    if info["version"] in _state()["bad"]:
        return "bad"
    if info["min_loader"] > loader_version():
        return "exe"
    return "update"


# ---------------------------------------------------------------- 설치
def _download(url: str, dest: Path, progress) -> None:
    if url.startswith("file:"):
        from urllib.parse import unquote, urlparse

        src = Path(unquote(urlparse(url).path.lstrip("/")))
        shutil.copyfile(src, dest)
        return
    with requests.get(url, headers={"User-Agent": UA["User-Agent"]}, timeout=60, stream=True) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(64 * 1024):
                f.write(chunk)
                done += len(chunk)
                progress(done, max(total, done), f"받는 중… {done // 1024:,} KB")


def install(info: dict, progress=lambda *a: None) -> str:
    ver = info["version"]
    APPS.mkdir(parents=True, exist_ok=True)
    part = APPS / f"{ver}.zip.part"
    _download(info["zip_url"], part, progress)
    sha = hashlib.sha256(part.read_bytes()).hexdigest()
    if sha.lower() != str(info["sha256"]).lower():
        part.unlink(missing_ok=True)
        raise RuntimeError("받은 파일이 손상되었습니다 (SHA-256 불일치). 잠시 후 다시 시도해 주세요.")
    progress(1, 1, "설치 중…")
    tmp = APPS / f"{ver}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(part) as z:
        for n in z.namelist():  # 폴더 밖으로 나가는 경로 거부
            if n.startswith(("/", "\\")) or ".." in Path(n).parts:
                raise RuntimeError(f"잘못된 파일 경로: {n}")
        z.extractall(tmp)
    part.unlink(missing_ok=True)
    if not (tmp / "app" / "main.py").exists():
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError("업데이트 파일에 앱 코드가 없습니다.")
    (tmp / ".complete").write_text(ver, encoding="utf-8")
    dest = APPS / ver
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(tmp, dest)
    st = _state()
    cur = st.get("current")
    if cur and cur != ver:
        st["previous"] = cur
    st["current"] = ver
    st["tries"].pop(ver, None)
    _save_state(st)
    # 지금 · 이전 · 실행 중 버전만 남기고 정리
    keep = {ver, st.get("previous"), Path(os.environ.get("EXILEDELTA_APP_ROOT", "")).name}
    for d in APPS.iterdir():
        if d.is_dir() and d.name not in keep and (d / ".complete").exists():
            shutil.rmtree(d, ignore_errors=True)
    return ver


def relaunch() -> None:
    """app.exec() 가 끝난 뒤 main.py 가 부름: 새 프로세스로 다시 실행 (로더가 새 버전을 고름)."""
    import subprocess

    env = dict(os.environ)
    env.pop("EXILEDELTA_APP_ROOT", None)
    # 단일 exe(PyInstaller onefile)는 자식 프로세스가 부모의 임시 폴더를 같이 씀 → 부모가 끝나며 지우면 깨짐.
    # 새로 실행하는 것은 완전히 별개 실행으로 (PoB 워커는 부모와 같이 쓰는 게 맞으므로 거기엔 안 씀)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen([sys.executable] + sys.argv[1:], env=env, close_fds=True,
                     creationflags=0x00000008 | 0x00000200)


READY_FILE = APPS / "ready.txt"


def mark_ready() -> None:
    """새로 켜진 프로그램이 창을 띄웠다고 알림 → 이전 프로그램이 그걸 보고 닫힘 (빈틈 없이 넘겨받기)."""
    import time

    try:
        APPS.mkdir(parents=True, exist_ok=True)
        READY_FILE.write_text(f"{time.time()} {os.getpid()}", encoding="utf-8")
    except OSError:
        pass


def hand_over(win, dlg=None, timeout: float = 40.0) -> None:
    """새 버전을 바로 띄우고, 그 창이 뜰 때까지 지금 창은 '다시 켜는 중' 으로 남겨 둠.
    (예전엔 먼저 닫고 새로 켜서 단일 exe 가 풀리는 몇 초 동안 아무것도 안 보였음)"""
    import time

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    RESTART["want"] = True
    RESTART["spawned"] = True
    srv = getattr(win, "_single_server", None)
    if srv is not None:
        srv.close()  # 새 프로그램이 '이미 실행 중' 으로 보고 꺼지지 않게
    try:
        win.client.stop()
    except Exception:  # noqa: BLE001
        pass
    t0 = time.time()
    relaunch()

    def quit_now():
        timer.stop()
        if dlg is not None:
            dlg.close()
        win.close()
        QApplication.instance().quit()

    def poll():
        try:
            ts = float(READY_FILE.read_text(encoding="utf-8").split()[0])
        except (OSError, ValueError, IndexError):
            ts = 0.0
        if ts >= t0 or time.time() - t0 > timeout:
            quit_now()

    timer = QTimer(win)
    timer.setInterval(250)
    timer.timeout.connect(poll)
    timer.start()
    win._handover_timer = timer


# ---------------------------------------------------------------- 화면
class StartupUpdater:
    """시작할 때 한 번: 업데이트 확인 → (처음 실행이면 바로, 아니면 물어보고) 설치 → 재시작.
    끝나면(업데이트 없음 · 나중에 · 실패) after() 호출 — 이어서 PoB 엔진 설치 등."""

    def __init__(self, win, after, manual: bool = False, direct: bool = False):
        self.win = win
        self.after = after
        self.manual = manual
        self.direct = direct  # 이미 내역 창에서 '지금 업데이트'를 누름 → 다시 묻지 않음

    def start(self) -> None:
        from asyncjob import run_async

        if not enabled():
            if self.manual:
                self._info("프로그램 업데이트", "개발 모드로 실행 중이라 업데이트를 확인하지 않습니다.")
            return self.after()
        def job():
            inf = latest()
            if inf and vt(inf["version"]) > vt(VERSION):
                try:  # 지금 버전 다음부터 최신까지 모든 버전의 내역
                    inf["history"] = history(VERSION, inf["version"])
                except Exception:  # noqa: BLE001 - 내역을 못 받아도 업데이트는 가능
                    inf["history"] = []
            return inf

        run_async(job, self._got, self._fail)

    def _info(self, title: str, text: str) -> None:
        from dialogs import info

        info(self.win, title, text)

    def _fail(self, msg: str) -> None:
        if self.manual:
            self._info("업데이트 확인 실패", f"GitHub 에 연결하지 못했습니다.\n{msg}")
        self.after()

    def _got(self, inf) -> None:
        from storage import load_settings, save_settings

        what = decide(inf)
        s = load_settings()
        first = not s.get("app_update_seen")
        if not first and not self.manual and s.get("app_update_skip") == (inf or {}).get("version"):
            what = "none"  # '이 버전 건너뛰기'
        if what == "none":
            if self.manual:
                text = (f"확인할 수 있는 릴리스가 없습니다 (지금 v{VERSION}). 저장소가 비공개이거나 아직 릴리스가 없습니다."
                        if inf is None else f"최신 버전입니다 (v{VERSION}).")
                self._info("프로그램 업데이트", text)
            return self._done()
        if what == "bad":
            if self.manual:
                self._info("프로그램 업데이트", f"v{inf['version']} 은 이 PC 에서 시작에 실패해서 건너뜁니다.")
            return self._done()
        if what == "exe":
            from dialogs import confirm

            if confirm(self.win, "새 설치 파일 필요",
                       f"새 버전 v{inf['version']} 은 프로그램(exe)을 새로 받아야 합니다.\n"
                       f"다운로드 페이지를 열까요?", "페이지 열기"):
                import webbrowser

                webbrowser.open(inf.get("page") or f"https://github.com/{REPO}/releases/latest")
            return self._done()
        if (first and not self.manual) or self.direct:
            return self._install(inf)  # 처음 실행: 묻지 않고 최신으로
        if self._ask(inf):
            return self._install(inf)
        return self._done()

    def _ask(self, inf: dict) -> bool:
        rels = inf.get("history") or [{"version": inf["version"], "date": "", "notes": inf.get("notes", "")}]
        dlg = HistoryDialog(self.win, "프로그램 업데이트",
                            f"새 버전이 있습니다: <b>v{VERSION} → v{inf['version']}</b>"
                            + (f" &nbsp;<span style='color:#968b7a'>({len(rels)}개 버전의 변경 내용)</span>" if len(rels) > 1 else ""),
                            history_markdown(rels), update=True)
        dlg.exec()
        if dlg.choice == "skip":
            from storage import load_settings, save_settings

            s = load_settings()
            s["app_update_skip"] = inf["version"]
            save_settings(s)
        return dlg.choice == "update"

    def _install(self, inf: dict) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QProgressDialog

        from asyncjob import run_async

        head = f"최신 버전(v{inf['version']})으로 맞추는 중이에요.\n끝나면 프로그램이 알아서 다시 켜져요."
        dlg = QProgressDialog(head, "", 0, 0, self.win)
        dlg.setWindowTitle("프로그램 업데이트")
        dlg.setCancelButton(None)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setMinimumWidth(380)
        dlg.show()

        def prog(d, t, m):
            dlg.setRange(0, max(1, t))
            dlg.setValue(d)
            dlg.setLabelText(f"{head}\n\n{m}")

        def ok(ver):
            from storage import load_settings, save_settings

            s = load_settings()
            s["app_update_seen"] = True
            s["app_updated"] = {"from": VERSION, "to": ver}  # 새로 켜진 쪽에서 '업데이트됐어요' 표시
            save_settings(s)
            dlg.setRange(0, 0)
            dlg.setLabelText(f"v{ver} 받기 완료.\n새 버전으로 다시 켜는 중이에요… (몇 초 걸려요)")
            hand_over(self.win, dlg)

        def fail(msg):
            dlg.close()
            self._info("업데이트 실패", f"업데이트를 설치하지 못했습니다. 지금 버전으로 계속합니다.\n{msg}")
            self._done()

        run_async(lambda p: install(inf, p), ok, fail, prog, with_progress=True)

    def _done(self) -> None:
        from storage import load_settings, save_settings

        s = load_settings()
        if not s.get("app_update_seen"):
            s["app_update_seen"] = True
            save_settings(s)
        self.after()


# ---------------------------------------------------------------- 업데이트 내역 창
def _dialog_base():
    from dialogs import FramelessDialog

    return FramelessDialog


class HistoryDialog(_dialog_base()):
    """버전별 변경 내용. update=True 면 [지금 업데이트] [나중에] [이 버전 건너뛰기], 아니면 [닫기]."""

    def __init__(self, parent, title: str, head_html: str, markdown: str, update: bool = False):
        super().__init__(parent)
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout

        self.choice = "later"
        self.setMinimumSize(560, 460)
        v = QVBoxLayout(self.frame)
        v.setContentsMargins(22, 18, 22, 16)
        v.setSpacing(10)
        t = QLabel(title)
        t.setObjectName("DialogTitle")
        v.addWidget(t)
        h = QLabel(head_html)
        h.setObjectName("DialogText")
        h.setWordWrap(True)
        v.addWidget(h)
        body = QTextBrowser()
        body.setOpenExternalLinks(True)
        body.setMarkdown(markdown or "(변경 내용 없음)")
        body.setStyleSheet("QTextBrowser { background: #100e0b; border: 1px solid #3a3226; border-radius: 6px;"
                           " padding: 8px; color: #e6dcc8; font-size: 10.5pt; }")
        v.addWidget(body, 1)
        row = QHBoxLayout()
        if update:
            note = QLabel("몇 초 뒤 다시 시작")
            note.setStyleSheet("color: #968b7a; font-size: 9.5pt;")
            row.addWidget(note)
        row.addStretch(1)

        def pick(c):
            self.choice = c
            self.accept() if c == "update" else self.reject()

        if update:
            skip = QPushButton("이 버전 건너뛰기")
            skip.clicked.connect(lambda: pick("skip"))
            row.addWidget(skip)
            later = QPushButton("나중에")
            later.clicked.connect(lambda: pick("later"))
            row.addWidget(later)
            ok = QPushButton("지금 업데이트")
            ok.setObjectName("Primary")
            ok.setDefault(True)
            ok.clicked.connect(lambda: pick("update"))
            row.addWidget(ok)
        else:
            close = QPushButton("닫기")
            close.setObjectName("Primary")
            close.setDefault(True)
            close.clicked.connect(self.accept)
            row.addWidget(close)
        v.addLayout(row)


def show_history(win) -> None:
    """메뉴 · 상태 표시줄 버전 클릭: 지금까지의 모든 릴리스 내역."""
    from asyncjob import run_async

    def got(rels):
        if not rels:
            from dialogs import info

            info(win, "업데이트 내역", "아직 올라온 릴리스가 없습니다.")
            return
        newest = rels[0]["version"]
        newer = vt(newest) > vt(VERSION) and enabled()
        head = (f"지금 버전 <b>v{VERSION}</b> · 최신 <b>v{newest}</b>"
                + (" &nbsp;<span style='color:#e8c15a'>새 버전이 있어요. 아래 '지금 업데이트'로 바로 받을 수 있어요</span>"
                   if newer else " &nbsp;<span style='color:#7fc46a'>최신 버전입니다</span>"))
        dlg = HistoryDialog(win, "업데이트 내역", head, history_markdown(rels, VERSION), update=newer)
        dlg.exec()
        if newer and dlg.choice == "skip":
            from storage import load_settings, save_settings

            s = load_settings()
            s["app_update_skip"] = newest
            save_settings(s)
        elif newer and dlg.choice == "update":
            # (win 에 붙잡아 둬야 결과 신호를 받기 전에 사라지지 않음)
            win._app_up_manual = StartupUpdater(win, lambda: None, manual=True, direct=True)
            win._app_up_manual.start()

    def fail(msg):
        from dialogs import info

        info(win, "업데이트 내역", f"GitHub 에서 내역을 받지 못했습니다.\n{msg}")

    win._history_job = run_async(lambda: history(), got, fail)
