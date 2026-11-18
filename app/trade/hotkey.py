"""PoE가 앞에 있을 때만 Ctrl+D를 등록한다."""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer
from PySide6.QtWidgets import QApplication

import winutil
from trade.config import settings


class PendingCopy:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.expires = 0.0
        self.hwnd = 0

    def arm(self, hwnd: int) -> None:
        self.hwnd = hwnd
        self.expires = self.clock() + 1.0

    def consume(self) -> tuple[bool, int]:
        live = self.expires > self.clock()
        self.expires = 0
        return live, self.hwnd if live else 0


class TradeHotkey(QAbstractNativeEventFilter):
    ID = 0x504F

    def __init__(self, parent, flash):
        super().__init__()
        self.pending = PendingCopy()
        self.flash = flash
        self.registered = False
        self.warned = False
        self.user32 = ctypes.windll.user32 if sys.platform == "win32" else None
        if self.user32:
            self.user32.GetForegroundWindow.restype = wintypes.HWND
        QApplication.instance().installNativeEventFilter(self)
        self.timer = QTimer(parent, interval=200, timeout=self.poll)
        self.timer.start()

    def poll(self) -> None:
        if not self.user32:
            return
        hwnd = self.user32.GetForegroundWindow()
        active = settings().get("hotkey_enabled", True) and winutil.is_poe_window(hwnd)
        if not active:
            if self.registered:
                self.user32.UnregisterHotKey(None, self.ID)
                self.registered = False
            return
        if not self.registered:
            self.registered = bool(self.user32.RegisterHotKey(None, self.ID, 0x4002, ord("D")))
            if self.registered:
                self.warned = False
            elif not self.warned:
                self.flash("Ctrl+D를 다른 프로그램이 쓰고 있습니다")
                self.warned = True

    def trigger(self) -> None:
        if not self.user32 or not settings().get("hotkey_enabled", True):
            return
        hwnd = self.user32.GetForegroundWindow()
        if winutil.is_poe_window(hwnd):
            self.pending.arm(hwnd)
            winutil.press_ctrl_c()

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam == self.ID:
                self.trigger()
                return True, 0
        return False, 0

    def stop(self) -> None:
        self.timer.stop()
        if self.user32 and self.registered:
            self.user32.UnregisterHotKey(None, self.ID)
        self.registered = False
        QApplication.instance().removeNativeEventFilter(self)
