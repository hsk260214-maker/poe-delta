"""Exile Delta — PoE1 아이템을 끼웠을 때 DPS/EHP 가 얼마나 바뀌는지(PoB 엔진) 보여 주는 도구."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from paths import APP_NAME, DIR_NAME, MIGRATION_FAILED, MIGRATION_WARNING
EDGE = 6
SECTIONS = ["캐릭터"]
# 아이템 필터(O/△/X) 화면은 숨김. 다시 켜려면 SHOW_FILTER = True (코드·저장된 탭은 그대로 유지)
SHOW_FILTER = False
if SHOW_FILTER:
    SECTIONS.append("아이템 필터")


def single_instance_key() -> str:
    import hashlib
    import os

    return f"{DIR_NAME}-" + hashlib.md5(os.environ.get("APPDATA", "").lower().encode()).hexdigest()[:12]


def _worker_main() -> int:
    """`--pob-worker <port> <logpath>` 로 실행된 PoB 계산 워커."""
    i = sys.argv.index("--pob-worker")
    from pob.worker import run

    return run(int(sys.argv[i + 1]), Path(sys.argv[i + 2]))


def main() -> int:
    from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer
    from PySide6.QtGui import QCursor, QGuiApplication, QKeySequence, QShortcut
    from PySide6.QtWidgets import (QAbstractScrollArea, QAbstractSpinBox, QApplication, QComboBox, QFrame, QHBoxLayout,
                               QLabel, QMenu, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

    from character_page import CharacterPage
    from data import ModDB
    from filter_page import FilterPage
    from icon import app_icon
    from itemcheck import check_item, parse_item
    from item_editor import ItemEditor
    from itemmodel import compose_en
    from itemmodel import parse as parse_model
    from overlay import Overlay
    from pob.client import PobClient
    from storage import load_settings, save_settings
    from theme import build_qss
    from titlebar import TitleBar
    from trade.hotkey import TradeHotkey
    from trade.trade_window import TradeWindow

    class MainWindow(QWidget):
        def __init__(self, db: ModDB):
            super().__init__()
            self.db = db
            self.settings = load_settings()
            self._cursor_shape = None

            self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
            from version import VERSION

            self.setWindowTitle(f"{APP_NAME} v{VERSION} — PoE 장비 교체 DPS · EHP 비교")
            self.setWindowIcon(app_icon())
            self.setMinimumSize(900, 600)

            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            self.frame = QFrame()
            self.frame.setObjectName("WindowFrame")
            outer.addWidget(self.frame)
            v = QVBoxLayout(self.frame)
            v.setContentsMargins(1, 1, 1, 1)
            v.setSpacing(0)

            self.titlebar = TitleBar(self, SECTIONS)
            v.addWidget(self.titlebar)
            self.pages = QStackedWidget()
            v.addWidget(self.pages, 1)

            status = QFrame()
            status.setObjectName("StatusBar")
            sh = QHBoxLayout(status)
            sh.setContentsMargins(14, 5, 14, 5)
            self.status_left = QLabel("준비됨")
            self.status_left.setObjectName("StatusText")
            self.engine_label = QLabel("PoB 엔진: —")
            self.engine_label.setObjectName("StatusText")
            right = QLabel(f"옵션 데이터 {db.built}  ·  {db.total:,}개")
            right.setObjectName("StatusText")
            from version import VERSION as _ver

            self.app_label = QLabel(f"{APP_NAME} v{_ver}")
            self.app_label.setObjectName("StatusText")
            self.app_label.setToolTip("프로그램 버전 · 누르면 업데이트 내역")
            self.app_label.setCursor(Qt.CursorShape.PointingHandCursor)
            self.app_label.mousePressEvent = lambda e: self._show_history()
            sh.addWidget(self.status_left)
            sh.addStretch(1)
            sh.addWidget(self.app_label)
            # 새 버전이 있으면 나타나는 버튼 (10분마다 조용히 확인)
            self.app_up_btn = QPushButton("")
            self.app_up_btn.setObjectName("Primary")
            self.app_up_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.app_up_btn.setStyleSheet("padding: 1px 10px; font-size: 9.5pt;")
            self.app_up_btn.clicked.connect(self._check_app_update)
            self.app_up_btn.hide()
            sh.addSpacing(6)
            sh.addWidget(self.app_up_btn)
            sh.addSpacing(16)
            sh.addWidget(self.engine_label)
            sh.addSpacing(16)
            sh.addWidget(right)
            v.addWidget(status)

            # PoB 엔진 (별도 프로세스)
            self.client = PobClient(self)
            self.client.stateChanged.connect(self._on_engine_state)

            self.char_page = CharacterPage(self.client, self.flash)
            self.filter_page = FilterPage(db, self.flash)
            for page in (self.char_page, self.filter_page) if SHOW_FILTER else (self.char_page,):
                self.pages.addWidget(page)
                self.titlebar.add_strip(page.strip)
            if not SHOW_FILTER:
                self.filter_page.hide()
            self.titlebar.sectionChanged.connect(self.set_section)

            self.menu = QMenu(self)
            self.menu.aboutToShow.connect(self._fill_menu)
            self.titlebar.menu_btn.setMenu(self.menu)

            QShortcut(QKeySequence("Ctrl+T"), self, activated=lambda: self._page().strip.addRequested.emit())
            QShortcut(QKeySequence("Ctrl+W"), self, activated=self._close_current_tab)
            QShortcut(QKeySequence("Ctrl+Shift+D"), self, activated=lambda: self.filter_page.duplicate_tab(
                self.filter_page.strip.tabs.currentIndex()) if self._page() is self.filter_page else None)
            QShortcut(QKeySequence("Ctrl+S"), self, activated=self.filter_page.save_now)
            QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self._page() is self.filter_page and self.filter_page.editor.open_search())
            QShortcut(QKeySequence("Ctrl+Tab"), self, activated=self._next_tab)
            QShortcut(QKeySequence("Ctrl+1"), self, activated=lambda: self.set_section(0))
            QShortcut(QKeySequence("Ctrl+2"), self, activated=lambda: self.set_section(1))

            # 클립보드 감지 → 오버레이 (게임에서 Ctrl+C)
            self.overlay = Overlay(db)
            self.overlay.editRequested.connect(self._open_editor)
            self.editor_win: ItemEditor | None = None
            self._last_model = None
            self.trade_win = TradeWindow(lambda: (self.char_page._cur() or {}).get("source"))
            self.trade_hotkey = TradeHotkey(self, self.flash)
            self.watch_clipboard = bool(self.settings.get("watch_clipboard", True))
            QApplication.clipboard().dataChanged.connect(self._on_clipboard)
            # 한글→영문 사전(약 1초)을 미리 백그라운드로 읽어 첫 Ctrl+C 지연 방지
            import threading

            import ko2en
            threading.Thread(target=ko2en.preload, daemon=True).start()
            # 옵션 조정 창도 미리 만들어 둠 (첫 Ctrl+C 때 창 생성 지연 방지)
            QTimer.singleShot(3000, self._ensure_editor)

            self.set_section(int(self.settings.get("section", 0)))
            self._cursor_timer = QTimer(self, interval=50, timeout=self._poll_edge_cursor)
            self._cursor_timer.start()
            QApplication.instance().installEventFilter(self)
            self._restore_geometry()
            QTimer.singleShot(0, self.client.start)
            # 자동 업데이트 (PoB 엔진: 점검 후 전환 / 번역 사전) — 시작 직후 부담을 피해 잠시 뒤에
            from updater import Updater

            self.updater = Updater(self.client, self.char_page, self)
            self.updater.message.connect(self.flash)
            self.char_page.updater = self.updater
            QTimer.singleShot(20000, self.updater.auto)
            # 프로그램 업데이트(내 GitHub 릴리스) 확인 → 끝나면 PoB 엔진이 없을 때 자동 설치
            import app_update

            self._app_update = app_update
            # (객체를 self 에 붙잡아 둬야 결과 신호를 받기 전에 사라지지 않음)
            self._app_up = app_update.StartupUpdater(self, self._after_app_update)
            QTimer.singleShot(1200, self._app_up.start)
            self._app_poll = QTimer(self, interval=10 * 60 * 1000, timeout=self._poll_app_update)
            self._app_poll.start()
            QTimer.singleShot(6000, app_update.mark_ok)  # 창이 뜨고 잘 돌면 '정상 시작' 표시 (로더의 되돌리기 판단용)

        def _poll_app_update(self) -> None:
            """10분마다: GitHub 에 새 버전이 있으면 아래쪽에 업데이트 버튼만 띄움 (게임 중 방해 안 되게 창은 안 띄움)."""
            app_update = self._app_update
            if not app_update.enabled():
                return
            from asyncjob import run_async

            def got(inf):
                what = app_update.decide(inf)
                if what in ("update", "exe"):
                    self.app_up_btn.setText(f"v{inf['version']} 업데이트 있어요")
                    self.app_up_btn.setToolTip("누르면 바뀐 내용 보고 바로 업데이트할 수 있어요")
                    self.app_up_btn.show()
                else:
                    self.app_up_btn.hide()

            run_async(app_update.latest, got, lambda m: None)

        def _after_app_update(self) -> None:
            self._poll_app_update()  # 시작할 때 '나중에'를 눌렀어도 버튼은 보이게
            if self.client.state == "missing" and not getattr(self.char_page, "_installing", False):
                self.char_page.install_engine()  # 처음 실행: 버튼 누를 필요 없이 바로 PoB 엔진 받기

        # ---------- 섹션 ----------
        def _page(self):
            return self.pages.currentWidget()

        def set_section(self, i: int) -> None:
            i = max(0, min(i, self.pages.count() - 1))
            self.pages.setCurrentIndex(i)
            self.titlebar.set_section(i)
            self.settings["section"] = i

        def _fill_menu(self) -> None:
            self.menu.clear()
            self._page().fill_menu(self.menu)
            self.menu.addSeparator()
            act = self.menu.addAction("게임 Ctrl+C 감지 (장착 비교 창)")
            act.setCheckable(True)
            act.setChecked(self.watch_clipboard)
            act.toggled.connect(self._set_watch)
            self.menu.addAction("거래소 설정", self._trade_settings)
            self.menu.addSeparator()
            from version import VERSION

            self.menu.addAction(f"프로그램 업데이트 확인 (지금 v{VERSION})", self._check_app_update)
            self.menu.addAction("업데이트 내역 보기", self._show_history)

        def _show_history(self) -> None:
            self._app_update.show_history(self)

        def _check_app_update(self) -> None:
            self._app_up_manual = self._app_update.StartupUpdater(self, lambda: None, manual=True)
            self._app_up_manual.start()

        def _set_watch(self, on: bool) -> None:
            self.watch_clipboard = on
            self.settings["watch_clipboard"] = on
            self.flash("Ctrl+C 감지 켜짐" if on else "Ctrl+C 감지 꺼짐")
            if not on:
                self.overlay.hide()
                if self.editor_win is not None:
                    self.editor_win.hide()
                if getattr(self, "map_warn", None) is not None:
                    self.map_warn.hide()

        def _ensure_editor(self) -> None:
            if self.editor_win is None:
                self.editor_win = ItemEditor(self.db, self.char_page)
                self.editor_win.tradeRequested.connect(self._show_trade)

        def _show_trade(self, item, hwnd=0) -> None:
            self.trade_win.show_item(item, hwnd)

        def _trade_settings(self) -> None:
            from trade.settings_dialog import SettingsDialog

            model = self.trade_win.model or (self._last_model[0] if self._last_model else None)
            SettingsDialog(self, model.lang if model else "en").exec()
            self.trade_hotkey.poll()
            if self.trade_win.model is not None:
                self.trade_win.load(self.trade_win.model, self.trade_win._prev_fg)

        def _open_editor(self) -> None:
            if not self._last_model or self._last_model[0] is None:
                return
            model, slot = self._last_model
            self.overlay.hide()
            self._ensure_editor()
            try:
                self.editor_win.load(model, slot)
            except Exception as ex:  # noqa: BLE001
                self.flash(f"아이템 표시 실패: {ex}")
                return
            self.editor_win.show_near_cursor()

        def _map_warn_win(self):
            if getattr(self, "map_warn", None) is None:
                from map_warn import MapWarn

                self.map_warn = MapWarn()
                self.map_warn.settingsRequested.connect(self._open_map_settings)
            return self.map_warn

        def _open_map_settings(self) -> None:
            self.showNormal() if self.isMinimized() else self.show()
            self.raise_()
            self.activateWindow()
            self.set_section(0)
            self.char_page._set_sub(3)

        def _show_map(self, text: str) -> bool:
            """지도면 비선호 옵션 경고 창 (옵션 조정 창은 닫음)."""
            import mapcheck

            if not mapcheck.is_map(text):
                return False
            if self.editor_win is not None:
                self.editor_win.hide()
            if self._map_warn_win().show_map(text):
                self.flash("지도 감지 — 비선호 옵션 확인")
            return True

        def open_item_text(self, text: str) -> bool:
            """아이템 텍스트(한글·영문)로 옵션 조정·비교 창을 연다. 아이템이 아니면 False."""
            if self._show_map(text or ""):
                return True
            item = parse_item(text or "")
            model = parse_model(text or "") if item is not None else None
            if model is None:
                return False
            self._last_model = (model, item.slot)
            if getattr(self, "map_warn", None) is not None:
                self.map_warn.hide()
            self._open_editor()
            return True

        # ---------- 클립보드 → 옵션 조정 창 ----------
        def _on_clipboard(self, attempt: int = 0, destination=None) -> None:
            """게임에서 Ctrl+C → 옵션 조정 창(장착 시 DPS/EHP 변화)을 바로 띄운다."""
            if attempt == 0:
                live, hwnd = self.trade_hotkey.pending.consume()
                destination = ("trade", hwnd) if live else ("existing", 0)
                if not live and not self.watch_clipboard:
                    return
            text = QApplication.clipboard().text()
            if not text.strip() and attempt < 5:
                # 게임이 아직 클립보드를 잡고 있으면 빈 값이 옴 → 조금 뒤 다시 읽기 (첫 Ctrl+C 가 씹히던 문제)
                QTimer.singleShot((60, 120, 250, 400, 700)[attempt], lambda: self._on_clipboard(attempt + 1, destination))
                return
            if destination[0] == "trade":
                if text.strip():
                    self._show_trade(text, destination[1])
                return
            if self._show_map(text):
                return
            item = parse_item(text)
            if item is None:
                return
            model = parse_model(text)
            if model is None:
                return
            self._last_model = (model, item.slot)
            if getattr(self, "map_warn", None) is not None:
                self.map_warn.hide()
            try:  # 해석 문제 진단용: 마지막 Ctrl+C 원문 (이 PC 에만 저장)
                from paths import LOCAL as d
                d.mkdir(parents=True, exist_ok=True)
                (d / "last_item.txt").write_text(text, encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
            if SHOW_FILTER:  # (숨김 기능) 필터 판정 오버레이
                results = check_item(self.db, self.filter_page.tabs_data, item)
                self.overlay.show_item(item, results, None)
                return
            self._open_editor()
            self.flash(f"아이템 감지 — {item.name}")

        def _close_current_tab(self) -> None:
            p = self._page()
            i = p.strip.tabs.currentIndex()
            if i >= 0:
                p.strip.closeTabRequested.emit(i)

        def _next_tab(self) -> None:
            tb = self._page().strip.tabs
            if tb.count():
                tb.setCurrentIndex((tb.currentIndex() + 1) % tb.count())

        def flash(self, msg: str) -> None:
            self.status_left.setText(f"{msg}  ·  {datetime.now():%H:%M:%S}")

        def _on_engine_state(self, st: str, msg: str) -> None:
            label = {"ready": f"PoB {self.client.version} ●", "starting": "PoB 시작 중…", "missing": "PoB 미설치",
                     "error": "PoB 오류", "stopped": "PoB 중지"}.get(st, st)
            self.engine_label.setText(label)
            self.engine_label.setToolTip(msg)
            if msg and st in ("error",):
                self.flash(msg)

        # ---------- 창 ----------
        def _restore_geometry(self) -> None:
            w = self.settings.get("window") or {}
            rect = QRect(w.get("x", 0), w.get("y", 0), w.get("w", 1180), w.get("h", 780))
            screen = QGuiApplication.screenAt(rect.center()) if w else None
            if screen is None:
                avail = QGuiApplication.primaryScreen().availableGeometry()
                rect = QRect(0, 0, min(1180, avail.width() - 80), min(780, avail.height() - 80))
                rect.moveCenter(avail.center())
            self.setGeometry(rect)
            self.start_max = bool(w.get("max"))

        def closeEvent(self, e):
            g = self.normalGeometry() if self.isMaximized() else self.geometry()
            self.settings["window"] = {"x": g.x(), "y": g.y(), "w": g.width(), "h": g.height(), "max": self.isMaximized()}
            try:
                # 시작할 때 읽은 설정을 통째로 쓰면 그 사이 다른 곳에서 저장한 값(자동 갱신 등)이 지워짐 → 최신에 합침
                s = load_settings()
                for k in ("window", "section", "watch_clipboard"):
                    if k in self.settings:
                        s[k] = self.settings[k]
                save_settings(s)
            except OSError:
                pass
            self.filter_page.save_now()
            self.trade_hotkey.stop()
            self.trade_win.close()
            self.overlay.close()
            if self.editor_win is not None:
                self.editor_win.close()
            if getattr(self, "map_warn", None) is not None:
                self.map_warn.close()
            self.client.stop()
            super().closeEvent(e)

        def changeEvent(self, e):
            if e.type() == QEvent.Type.WindowStateChange:
                self.titlebar.update_max_glyph()
                self.frame.setProperty("maximized", self.isMaximized())
                self.frame.style().unpolish(self.frame)
                self.frame.style().polish(self.frame)
                m = 0 if self.isMaximized() else 1
                self.frame.layout().setContentsMargins(m, m, m, m)
            super().changeEvent(e)

        # ---------- 프레임리스 리사이즈 ----------
        def _edges_at(self, gp: QPoint):
            edges = Qt.Edge(0)
            if self.isMaximized() or self.isMinimized():
                return edges
            r = self.frameGeometry()
            if not r.contains(gp):
                return edges
            if gp.x() - r.left() < EDGE:
                edges |= Qt.Edge.LeftEdge
            if r.right() - gp.x() < EDGE:
                edges |= Qt.Edge.RightEdge
            if gp.y() - r.top() < EDGE:
                edges |= Qt.Edge.TopEdge
            if r.bottom() - gp.y() < EDGE:
                edges |= Qt.Edge.BottomEdge
            return edges

        def _poll_edge_cursor(self) -> None:
            gp = QCursor.pos()
            edges = Qt.Edge(0)
            if (QApplication.mouseButtons() == Qt.MouseButton.NoButton and QApplication.activePopupWidget() is None
                    and QApplication.activeModalWidget() is None):
                w = QApplication.widgetAt(gp)
                if w is not None and w.window() is self:
                    edges = self._edges_at(gp)
            L, R, T, B = Qt.Edge.LeftEdge, Qt.Edge.RightEdge, Qt.Edge.TopEdge, Qt.Edge.BottomEdge
            shape = None
            if edges in (L | T, R | B):
                shape = Qt.CursorShape.SizeFDiagCursor
            elif edges in (R | T, L | B):
                shape = Qt.CursorShape.SizeBDiagCursor
            elif edges in (L, R):
                shape = Qt.CursorShape.SizeHorCursor
            elif edges in (T, B):
                shape = Qt.CursorShape.SizeVerCursor
            if shape != self._cursor_shape:
                if self._cursor_shape is not None:
                    QApplication.restoreOverrideCursor()
                if shape is not None:
                    QApplication.setOverrideCursor(shape)
                self._cursor_shape = shape

        def eventFilter(self, obj, ev):
            if (ev.type() == QEvent.Type.MouseButtonPress and isinstance(obj, QWidget) and obj.window() is self
                    and ev.button() == Qt.MouseButton.LeftButton):
                edges = self._edges_at(QCursor.pos())
                if edges != Qt.Edge(0) and self.windowHandle():
                    self.windowHandle().startSystemResize(edges)
                    return True
            if ev.type() == QEvent.Type.Wheel and isinstance(obj, (QComboBox, QAbstractSpinBox)):
                # 목록 상자 위를 지나며 스크롤해도 값이 바뀌지 않게: 휠은 바깥 스크롤 영역으로 넘김
                p = obj.parentWidget()
                while p is not None and not isinstance(p, QAbstractScrollArea):
                    p = p.parentWidget()
                if p is not None:
                    QApplication.sendEvent(p.verticalScrollBar(), ev)
                return True
            return super().eventFilter(obj, ev)

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    app.setStyleSheet(build_qss())

    # 단일 실행: 이미 켜져 있으면 그 창을 앞으로 띄우고 종료 (두 개가 켜지면 Ctrl+C 창도 두 개 뜸)
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    key = single_instance_key()
    sock = QLocalSocket()
    sock.connectToServer(key)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return 0
    QLocalServer.removeServer(key)
    server = QLocalServer(app)
    server.listen(key)

    win = MainWindow(ModDB())

    def _activate() -> None:
        while server.hasPendingConnections():
            server.nextPendingConnection().deleteLater()
        if win.isMinimized():
            win.showNormal()
        win.show()
        win.raise_()
        win.activateWindow()
        win.flash("이미 실행 중이라 이 창을 띄웠습니다")
    server.newConnection.connect(_activate)

    win._single_server = server
    win.showMaximized() if win.start_max else win.show()
    if MIGRATION_FAILED:
        QTimer.singleShot(0, lambda: win.flash(MIGRATION_WARNING))
    import app_update

    # 업데이트로 다시 켜진 경우: 이전 프로그램에 '창 떴음' 알림(이걸 보고 이전 창이 닫힘) + 업데이트됐다고 표시
    QTimer.singleShot(150, app_update.mark_ready)

    def _updated_note() -> None:
        from storage import load_settings, save_settings
        from version import VERSION

        s = load_settings()
        up = s.pop("app_updated", None)
        if up:
            save_settings(s)
            if up.get("to") == VERSION:
                win.flash(f"v{up.get('from')} → v{VERSION} 업데이트 완료! 바뀐 내용은 아래 버전 글씨를 누르면 볼 수 있어요")
    QTimer.singleShot(400, _updated_note)
    code = app.exec()
    if app_update.RESTART["want"] and not app_update.RESTART.get("spawned"):
        server.close()  # 새 프로세스가 '이미 실행 중' 으로 착각하지 않게
        win.client.stop()
        app_update.relaunch()
    return code


if __name__ == "__main__":
    if "--pob-worker" in sys.argv:
        sys.exit(_worker_main())
    sys.exit(main())
