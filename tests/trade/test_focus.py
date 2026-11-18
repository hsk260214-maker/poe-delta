import ctypes
import json
import os
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QPushButton

import paths
import winutil
from trade import focus_log
from trade.trade_window import TradeWindow


@pytest.fixture
def windows(monkeypatch, tmp_path):
    state = SimpleNamespace(front=1, valid=True, permit=True, calls=[], keys=[], attachments=[])

    def set_foreground(hwnd):
        state.calls.append(hwnd)
        if state.permit:
            state.front = hwnd
        return state.permit

    def thread_id(hwnd, pointer):
        if pointer:
            pointer._obj.value = os.getpid() if hwnd == 2 or hwnd > 100 else 0
        return 1 if hwnd == 101 else 2

    def class_name(hwnd, buffer, size):
        buffer.value = "POEWindowClass" if hwnd == 1 else "PRIVATE-WINDOW-TITLE"

    user32 = SimpleNamespace(
        GetForegroundWindow=lambda: state.front, SetForegroundWindow=set_foreground,
        IsWindow=lambda hwnd: bool(hwnd) and (hwnd != 1 or state.valid),
        GetWindowThreadProcessId=thread_id, BringWindowToTop=lambda hwnd: None,
        AttachThreadInput=lambda *args: state.attachments.append(args) or True,
        GetClassNameW=class_name, keybd_event=lambda key, *args: state.keys.append(key),
    )
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(
        user32=user32, kernel32=SimpleNamespace(GetCurrentThreadId=lambda: 1)))
    monkeypatch.setattr(paths, "LOCAL", tmp_path)
    monkeypatch.setattr(TradeWindow, "winId", lambda self: 101)
    return state


def log_rows():
    return [json.loads(line) for line in (paths.LOCAL / focus_log.LOG_NAME).read_text().splitlines()]


@pytest.mark.parametrize("front,valid,permit,result", [
    (1, True, True, "game_already_foreground"),
    (2, False, True, "invalid_game"),
    (3, True, True, "unrelated_foreground"),
    (2, True, True, "restored"),
    (2, True, False, "denied"),
])
def test_window_close_returns_focus(app, windows, front, valid, permit, result):
    window = TradeWindow()
    window.show_item("PRIVATE-ITEM-TEXT", 1)
    button = next(b for b in window.findChildren(QPushButton) if b.text() == "닫기")
    button.click()
    assert not window.isVisible()
    assert windows.calls == [101]
    windows.front, windows.valid, windows.permit = front, valid, permit
    app.processEvents()
    assert windows.calls == ([101, 1] if result in {"restored", "denied"} else [101])
    assert not windows.keys and not windows.attachments
    rows = log_rows()
    assert [row["event"] for row in rows] == ["open", "close", "after_hide"]
    assert len({row["open_id"] for row in rows}) == 1
    assert all(row["synthetic_alt"] == 0 and row["time"] for row in rows)
    assert rows[0]["activation"] == "success"
    assert rows[1]["source"] == "button" and rows[1]["was_foreground"]
    assert rows[2]["result"] == result
    raw = (paths.LOCAL / focus_log.LOG_NAME).read_text()
    assert "PRIVATE-ITEM-TEXT" not in raw and "PRIVATE-WINDOW-TITLE" not in raw


def test_denied_hint_and_close_intent(app, windows, monkeypatch):
    windows.permit = False
    window = TradeWindow()
    window.show_item(None, 1)
    assert window.isVisible() and not window.focus_hint.isHidden()
    assert windows.calls == [101] and not windows.keys
    assert log_rows()[0]["activation"] == "denied"
    monkeypatch.setattr(window, "isActiveWindow", lambda: False)
    window._close_on_escape()
    assert window.isVisible()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.changeEvent(QEvent(QEvent.Type.ActivationChange))
    assert window.focus_hint.isHidden()
    window._close_on_escape()
    app.processEvents()
    assert log_rows()[-1]["source"] == "esc" and not log_rows()[-1]["was_foreground"]
    windows.permit = True
    window.show_item(None, 1)
    assert window.focus_hint.isHidden()
    window.close()
    windows.front = 2
    app.processEvents()
    assert windows.calls == [101, 101] and not windows.keys
    assert log_rows()[-1]["source"] == "code"
    assert log_rows()[-1]["was_foreground"]
    assert log_rows()[0]["open_id"] != log_rows()[-1]["open_id"]


def test_system_close_is_user_intent(app, windows):
    class SystemClose(QCloseEvent):
        def spontaneous(self):
            return True

    window = TradeWindow()
    window.show_item(None, 1)
    window.closeEvent(SystemClose())
    window.hide()
    windows.front = 2
    app.processEvents()
    assert log_rows()[1]["source"] == "system"
    assert log_rows()[2]["result"] == "restored"
    assert windows.calls == [101, 1] and not windows.keys


def test_legacy_focus_keeps_alt_fallback(windows):
    windows.permit = False
    assert not winutil.focus_window(101)
    assert windows.calls == [101, 101]
    assert windows.keys == [0x12, 0x12]
    assert windows.attachments == [(1, 2, True), (1, 2, False)]


def test_focus_log_is_bounded(windows, monkeypatch):
    monkeypatch.setattr(focus_log, "MAX_BYTES", 512)
    for i in range(30):
        focus_log.record(str(i), "open", "none", activation="denied")
    assert (paths.LOCAL / focus_log.LOG_NAME).stat().st_size <= 512
    assert log_rows()[-1]["open_id"] == "29"
