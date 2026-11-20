"""지도 Ctrl+C → 비선호 옵션 경고 창 (커서 근처, 뜰 때 포커스 가져옴 → Esc 로 닫으면 게임으로 돌려줌)."""
from __future__ import annotations

import html

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

import mapcheck
from overlay import DIM
from storage import load_settings

BAD = "#e8604f"
OK = "#7fc27a"
GOLD = "#c8a96a"


def avoid_keys() -> set[str]:
    return set(load_settings().get("map_avoid") or [])


class MapWarn(QWidget):
    settingsRequested = Signal()

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setObjectName("EditorWin")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("#EditorWin { background: #0e0c09; }"
                           "#EditorWin QLabel { font-size: 11.5pt; color: #f1e9d8; }"
                           "#EditorWin QPushButton#OverlayEdit { font-size: 10pt; padding: 4px 10px; }")
        self.setFixedWidth(560)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.box = QFrame()
        self.box.setObjectName("Overlay")
        outer.addWidget(self.box)
        v = QVBoxLayout(self.box)
        v.setContentsMargins(14, 10, 14, 12)
        v.setSpacing(8)
        head = QHBoxLayout()
        self.title = QLabel()
        self.title.setTextFormat(Qt.TextFormat.RichText)
        self.title.setWordWrap(True)
        head.addWidget(self.title, 1)
        x = QPushButton("✕")
        x.setObjectName("EditorClose")
        x.setFixedSize(32, 30)
        x.setToolTip("닫기 (Esc)")
        x.clicked.connect(self.close)
        head.addWidget(x, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(head)
        self.body = QLabel()
        self.body.setTextFormat(Qt.TextFormat.RichText)
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        v.addWidget(self.body)
        # 서식 글자(RichText) 라벨은 마우스 누름을 먹어서 창이 안 끌림 → 글자 상호작용 끔
        for lb in (self.title, self.body):
            lb.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            lb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        row = QHBoxLayout()
        row.addStretch(1)
        self.set_btn = QPushButton("비선호 옵션 고르기")
        self.set_btn.setObjectName("OverlayEdit")
        self.set_btn.setToolTip("메인 창의 '지도 옵션' 탭을 열어요")
        self.set_btn.clicked.connect(lambda: (self.close(), self.settingsRequested.emit()))
        row.addWidget(self.set_btn)
        v.addLayout(row)
        # 이 창이 포커스를 쥔 채로 게임 아이템/지도에 Ctrl+C → 게임으로 넘겨서 새 것이 바로 뜨게
        QShortcut(QKeySequence.StandardKey.Copy, self, activated=self._forward_copy)
        self._esc_timer = QTimer(self, interval=40, timeout=self._poll_esc)
        self._esc_down = False
        self._prev_fg = 0
        self._drag = None
        self._placed = False

    # ---------------------------------------------------------------- 내용
    def show_map(self, text: str) -> bool:
        info = mapcheck.parse_map(text)
        if info is None:
            return False
        avoid = avoid_keys()
        tier = f" · {info.tier}티어" if info.tier else ""
        nm = info.name if info.name == info.base else f"{info.name} · {info.base}"
        self.title.setText(f"<span style='color:{GOLD}; font-weight:bold'>{html.escape(nm)}</span>"
                           f"<span style='color:{DIM}'>{tier}</span>")
        if not mapcheck.catalog():
            self._set("#86704a", f"<span style='color:{DIM}'>지도 옵션 목록 파일이 없어요. 프로그램을 다시 받아 주세요.</span>")
        elif info.unidentified:
            self._set("#86704a", f"<span style='color:{DIM}'>미확인 지도라 옵션을 볼 수 없어요. 감정한 뒤 다시 Ctrl+C 해 주세요.</span>")
        elif not avoid:
            self._set("#86704a", f"<span style='color:{DIM}'>아직 비선호 옵션을 안 골랐어요.<br>"
                                 f"메인 창 캐릭터 화면 → <b>지도 옵션</b> 탭에서 피하고 싶은 옵션을 비선호로 고르면, "
                                 f"지도에 Ctrl+C 할 때 바로 알려 드려요.</span>")
        else:
            hits = mapcheck.check(info, avoid)
            if hits:
                rows = "".join(
                    f"<div style='margin:3px 0'><span style='color:{BAD}'>⚠</span> "
                    f"<span style='color:#ffd9cf; font-weight:bold'>{html.escape(ln)}</span></div>"
                    for _e, ln in hits)
                self._set(BAD, f"<div style='color:{BAD}; font-size:13pt; font-weight:bold'>"
                               f"비선호 옵션 {len(hits)}개 있어요</div>{rows}")
            elif not info.lines:
                self._set(OK, f"<span style='color:{OK}; font-weight:bold'>옵션 없는 지도예요</span>")
            else:
                unknown = [ln for ln in info.lines if mapcheck.entry_for(ln) is None]
                note = ""
                if unknown:
                    note = (f"<div style='color:{DIM}; font-size:10pt; margin-top:4px'>목록에 없는 줄 {len(unknown)}개: "
                            + " · ".join(html.escape(x) for x in unknown[:4]) + ("…" if len(unknown) > 4 else "") + "</div>")
                self._set(OK, f"<span style='color:{OK}; font-size:13pt; font-weight:bold'>✓ 비선호 옵션 없어요</span>"
                              f"<div style='color:{DIM}; font-size:10pt'>옵션 {len(info.lines)}줄 확인함</div>{note}")
        # 줄바꿈 글자는 adjustSize 가 높이를 넉넉히 잡아 빈칸이 생김 → 폭 기준 높이로
        self.layout().activate()
        self.resize(self.width(), max(80, self.heightForWidth(self.width())))
        self._show_near_cursor()
        return True

    def _set(self, border: str, body: str) -> None:
        self.box.setStyleSheet(f"QFrame#Overlay {{ border: 2px solid {border}; }}")
        self.body.setText(body)

    # ---------------------------------------------------------------- 창
    def _show_near_cursor(self) -> None:
        """처음엔 커서 근처, 이후엔 사용자가 끌어다 둔 자리 그대로 (화면 밖이면 안으로)."""
        if self._placed:
            screen = QGuiApplication.screenAt(self.geometry().center()) or QGuiApplication.screenAt(QCursor.pos()) \
                or QGuiApplication.primaryScreen()
            g = screen.availableGeometry()
            x = min(max(g.left(), self.x()), g.right() - self.width())
            y = min(max(g.top(), self.y()), g.bottom() - self.height())
        else:
            self._placed = True
            pos = QCursor.pos()
            screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
            g = screen.availableGeometry()
            x = min(max(g.left(), pos.x() - self.width() // 2), g.right() - self.width())
            y = min(max(g.top(), pos.y() - 40), g.bottom() - self.height() - 40)
        from winutil import foreground_other

        fg = foreground_other()
        if fg:
            self._prev_fg = fg
        elif not (self.isVisible() and self.isActiveWindow()):
            self._prev_fg = 0
        self.move(x, y)
        self.show()
        self._esc_down = True
        self._esc_timer.start()
        QTimer.singleShot(0, self._grab_focus)

    def _grab_focus(self) -> None:
        """뜰 때 포커스를 가져와서 Esc 가 게임으로 안 가고 이 창이 닫히게."""
        from winutil import focus_window

        if not self.isVisible():
            return
        focus_window(int(self.winId()))
        self.raise_()
        self.activateWindow()

    def hideEvent(self, e):
        from winutil import focus_window

        if self.isActiveWindow() and getattr(self, "_prev_fg", 0):
            focus_window(self._prev_fg)  # 닫히면 게임으로 돌려줌
        self._esc_timer.stop()
        super().hideEvent(e)

    def _forward_copy(self) -> None:
        from winutil import press_ctrl_c, send_copy_to

        if self.frameGeometry().contains(QCursor.pos()):
            return  # 커서가 이 창 위 → 복사할 게임 아이템 없음
        if send_copy_to(self._prev_fg):
            QTimer.singleShot(150, press_ctrl_c)

    def _poll_esc(self) -> None:
        from winutil import key_down

        if not self.isVisible():
            return
        down = key_down(0x1B)
        if down and not self._esc_down:
            self.close()
        self._esc_down = down

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            # 옵션 조정 창과 같은 시스템 이동 (배율·다중 모니터에서도 커서와 안 어긋남)
            if self.windowHandle() and self.windowHandle().startSystemMove():
                e.accept()
                return
            self._drag = e.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None
