import ast
from pathlib import Path
from types import SimpleNamespace

from trade import config
from trade.hotkey import PendingCopy, TradeHotkey


def test_hotkey_registration_scope_and_copy(app, monkeypatch):
    import winutil
    from PySide6.QtWidgets import QWidget

    host = QWidget()
    messages, copies = [], []
    hotkey = TradeHotkey(host, messages.append)
    hotkey.timer.stop()
    foreground = [10]
    success = [False]
    registrations, unregistrations = [], []
    hotkey.user32 = SimpleNamespace(
        GetForegroundWindow=lambda: foreground[0],
        RegisterHotKey=lambda *args: registrations.append(args) or success[0],
        UnregisterHotKey=lambda *args: unregistrations.append(args))
    monkeypatch.setattr(winutil, "is_poe_window", lambda hwnd: hwnd == 10)
    monkeypatch.setattr(winutil, "press_ctrl_c", lambda: copies.append(1))
    hotkey.poll()
    hotkey.poll()
    assert len(messages) == 1
    success[0] = True
    hotkey.poll()
    assert hotkey.registered
    hotkey.trigger()
    assert copies == [1]
    assert hotkey.pending.consume() == (True, 10)
    foreground[0] = 20
    hotkey.poll()
    hotkey.trigger()
    assert not hotkey.registered
    assert len(unregistrations) == 1
    assert copies == [1]
    config.save(hotkey_enabled=False)
    foreground[0] = 10
    hotkey.poll()
    assert not hotkey.registered
    hotkey.stop()


def test_pending_expiry():
    clock = [10]
    pending = PendingCopy(lambda: clock[0])
    pending.arm(123)
    clock[0] = 11.1
    assert pending.consume() == (False, 0)
    pending.arm(456)
    assert pending.consume() == (True, 456)
    assert pending.consume() == (False, 0)


def test_clipboard_retry_keeps_destination(monkeypatch):
    # main()의 지역 클래스 전체를 띄우면 업데이트·PoB가 시작되므로 실제 메서드 AST만 실행한다.
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "app" / "main.py").read_text(encoding="utf-8"))
    method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_on_clipboard")
    now = [0]
    pending = PendingCopy(lambda: now[0])
    pending.arm(777)
    clipboard = [""]
    timers, routed = [], []
    qt = SimpleNamespace(singleShot=lambda delay, callback: timers.append((delay, callback)))
    qapp = SimpleNamespace(clipboard=lambda: SimpleNamespace(text=lambda: clipboard[0]))
    namespace = {"QTimer": qt, "QApplication": qapp}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(root / "app" / "main.py"), "exec"), namespace)
    callback = namespace["_on_clipboard"]
    host = SimpleNamespace(watch_clipboard=False, trade_hotkey=SimpleNamespace(pending=pending),
                           _show_trade=lambda text, hwnd: routed.append((text, hwnd)))
    host._on_clipboard = lambda attempt=0, destination=None: callback(host, attempt, destination)
    host._on_clipboard()
    assert not pending.consume()[0]
    for i in range(4):
        now[0] += timers[0][0] / 1000
        timers.pop(0)[1]()
    now[0] += timers[0][0] / 1000
    clipboard[0] = "Item text after 1.53 seconds"
    timers.pop(0)[1]()
    assert now[0] > 1
    assert routed == [("Item text after 1.53 seconds", 777)]
    host._on_clipboard()
    assert len(routed) == 1
    host.watch_clipboard = True
    existing = []
    host._show_map = lambda text: existing.append(text) or True
    host._on_clipboard()
    assert existing == [clipboard[0]]


def test_shared_window_helpers_import_and_behavior(monkeypatch):
    import item_editor
    import map_warn
    import winutil

    names = ("send_copy_to", "foreground_other", "focus_window", "key_down", "press_ctrl_c")
    assert all(getattr(item_editor, name) is getattr(winutil, name) for name in names)
    calls = []
    monkeypatch.setattr(winutil, "focus_window", lambda hwnd: calls.append(hwnd))
    fake = SimpleNamespace(isVisible=lambda: True, winId=lambda: 123,
                           raise_=lambda: None, activateWindow=lambda: None)
    map_warn.MapWarn._grab_focus(fake)
    assert calls == [123]
    monkeypatch.setattr(item_editor, "focus_window", lambda hwnd: calls.append(hwnd))
    item_editor.ItemEditor._grab_focus(fake)
    assert calls == [123, 123]
