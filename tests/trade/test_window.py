import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from itemmodel import parse
from trade import config


def test_browser_full_flow_without_api(tmp_path, fixtures):
    script = r"""
import sys, socket, json
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QDesktopServices
sys.path.insert(0, str(Path('app').resolve()))
from trade import config
from trade.trade_window import TradeWindow
def denied(*a,**k): raise AssertionError('HTTP is forbidden')
app=QApplication([])
config.save(mode='browser',league='Standard')
calls=[]
with patch('requests.Session.request', denied), patch.object(socket.socket,'connect',denied), patch.object(QDesktopServices,'openUrl',lambda url: calls.append(bytes(url.toEncoded()).decode('ascii')) or True):
    window=TradeWindow()
    window.load(Path('tests/trade/fixtures/rare_en.txt').read_text())
    assert window.search_button.isEnabled()
    assert window.table.isHidden()
    window.search()
    assert len(calls)==1 and 'securable' in calls[0]
    expected=json.loads(Path('tests/trade/fixtures/browser_links.json').read_text(encoding='utf-8'))
    assert calls[0]==expected['rare_en_official']
    assert 'trade.api' not in sys.modules
    window.league.setEditText('')
    assert not window.search_button.isEnabled()
    assert '리그 이름' in window.hint.text()
    window.search()
    assert len(calls)==1
print('browser flow: HTTP=0, trade.api not loaded')
"""
    env = {**os.environ, "APPDATA": str(tmp_path / "roaming"), "LOCALAPPDATA": str(tmp_path / "local")}
    result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_api_window_lazy_and_search_counts(app, fixtures, monkeypatch):
    from ratelimit import RateLimiter
    from trade import api, secret
    from trade import trade_window

    monkeypatch.setattr(api, "_LEAGUES", None)
    monkeypatch.setattr(api, "_POLICIES", {})
    monkeypatch.setattr(api, "_LIMITS", RateLimiter())
    monkeypatch.setattr(secret, "load_session", lambda: "")
    config.save(mode="api", api_ack_at=1, league="invalid")
    calls = []
    ids = [str(i) for i in range(21)]

    def transport(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if "/data/leagues" in url:
            data = {"result": [{"id": "Standard"}, {"id": "Hardcore"}]}
        elif "/search/" in url:
            assert kwargs["json"]["query"]["status"] == {"option": "securable"}
            data = {"id": "query-id", "result": ids, "total": 100}
        else:
            chunk = url.rsplit("/", 1)[1].split(",")
            assert len(chunk) <= 10
            data = {"result": [{"id": i, "listing": {"price": {"amount": int(i) + 1, "currency": "chaos"},
                                                     "account": {"name": f"seller{i}"}, "indexed": "2026-01-01T00:00:00Z"},
                                "item": {"ilvl": 86}} for i in chunk]}
        return SimpleNamespace(status_code=200, headers={}, json=lambda: data)

    monkeypatch.setattr(requests, "request", transport)
    monkeypatch.setattr(trade_window, "run_async", lambda fn, done, failed: done(fn()))
    window = trade_window.TradeWindow()
    window.load((fixtures / "rare_en.txt").read_text())
    assert not calls
    window.search()
    assert len(calls) == 4
    assert window.table.rowCount() == 20
    assert window.table.item(0, 0).text() == "1 chaos"
    assert "전체 100개" in window.result_summary.text()
    assert "리그를 Standard" in window.result_summary.text()
    assert window._result_link.endswith("/Standard/query-id")
    window.search()
    assert len(calls) == 7
    assert sum("/data/leagues" in url for _, url, _ in calls) == 1
    assert not any("/data/stats" in url for _, url, _ in calls)


def test_api_window_limit_and_unsupported_ui(app, fixtures, monkeypatch):
    from trade import trade_window

    config.save(mode="browser", league="Standard")
    window = trade_window.TradeWindow()
    for filename in ("magic_en.txt", "currency_ko.txt"):
        window.load((fixtures / filename).read_text(encoding="utf-8"))
        assert window.search_button.isHidden()
        assert "지원하지 않습니다" in window.hint.text()
    text = (fixtures / "rare_en.txt").read_text()
    window.load(text)
    from trade import browser
    monkeypatch.setattr(browser, "MAX_URL_LEN", 100)
    window._validate()
    assert not window.search_button.isEnabled()
    assert "검색 조건이 너무 깁니다" in window.hint.text()
    monkeypatch.setattr(browser, "MAX_URL_LEN", 2000)
    window._until = __import__("time").monotonic() + 3
    window._validate()
    assert not window.search_button.isEnabled()
    assert "초 뒤" in window.hint.text()
    window.load(text + "\n10% chance to Avoid being Chilled during Effect\n+1 Unknown Modifier")
    unsupported = [(condition, widgets) for condition, widgets in zip(window.stats, window.inputs) if not condition.match.id]
    assert unsupported
    assert all(not widgets[0].isEnabled() and widgets[0].toolTip() for _, widgets in unsupported)


@pytest.mark.parametrize("data,expected", [
    ({}, "browser"), ({"mode": "other", "api_ack_at": 1}, "browser"),
    ({"mode": "api"}, "browser"), ({"mode": "api", "api_ack_at": 1}, "api"),
])
def test_effective_mode(data, expected):
    config.save(**data)
    assert config.mode() == expected


def test_risk_accept_cancel_every_transition(app, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from trade.settings_dialog import SettingsDialog

    accept = False
    seen = []

    def exec_box(box):
        buttons = {button.text(): button for button in box.buttons()}
        assert box.defaultButton() is buttons["취소"]
        assert box.escapeButton() is buttons["취소"]
        assert "계정 정지" in box.text()
        box.chosen = buttons["위험을 이해하고 사용" if accept else "취소"]
        seen.append(box.text())
        return 0

    monkeypatch.setattr(QMessageBox, "exec", exec_box)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box.chosen)
    dialog = SettingsDialog()
    assert config.mode() == "browser"
    assert not dialog.cookie.isEnabled()
    dialog.mode.setCurrentIndex(1)
    assert config.mode() == "browser"
    assert dialog.mode.currentData() == "browser"
    accept = True
    dialog.mode.setCurrentIndex(1)
    assert config.mode() == "api"
    assert config.settings()["api_ack_at"] > 0
    assert dialog.cookie.isEnabled()
    dialog.mode.setCurrentIndex(0)
    dialog.mode.setCurrentIndex(1)
    assert len(seen) == 3


def test_window_close_returns_focus(app, fixtures, monkeypatch):
    import winutil
    from trade.trade_window import TradeWindow

    calls = []
    monkeypatch.setattr(winutil, "focus_window", lambda hwnd: calls.append(hwnd))
    window = TradeWindow()
    window.load((fixtures / "rare_en.txt").read_text(), 12345)
    window.close()
    assert calls == [12345]


def test_settings_lists_kakao_without_any_item(app):
    import storage
    from trade.settings_dialog import SettingsDialog

    assert not storage.SETTINGS_FILE.exists()
    dialog = SettingsDialog()
    assert [dialog.server.itemText(i) for i in range(dialog.server.count())] == [
        "공식", "카카오 (한글 클라이언트 전용)"]
    assert [dialog.server.itemData(i) for i in range(dialog.server.count())] == [config.OFFICIAL, config.KAKAO]
    dialog.show()
    app.processEvents()
    dialog.close()
    app.processEvents()
    assert not storage.SETTINGS_FILE.exists()


@pytest.mark.parametrize("case", ["kakao", "unknown", "missing", "disabled_kakao"])
def test_settings_server_selection_matches_saved_value(app, monkeypatch, case):
    import storage
    from trade.settings_dialog import SettingsDialog

    trade = {"league": "Standard"}
    if case in ("kakao", "disabled_kakao"):
        trade["server"] = config.KAKAO
    elif case == "unknown":
        trade["server"] = "https://unknown.invalid"
    if case == "disabled_kakao":
        monkeypatch.setattr(config, "KAKAO_ENABLED", False)
    storage.save_settings({"trade": trade, "untouched": "keep"})
    before = storage.SETTINGS_FILE.read_bytes()
    before_mtime = storage.SETTINGS_FILE.stat().st_mtime_ns
    dialog = SettingsDialog()
    expected = config.KAKAO if case == "kakao" else config.OFFICIAL
    assert dialog.server.currentData() == expected
    assert config.settings().get("server", config.OFFICIAL) == expected
    dialog.show()
    app.processEvents()
    dialog.close()
    app.processEvents()
    if case in ("missing", "kakao"):
        assert storage.SETTINGS_FILE.read_bytes() == before
        assert storage.SETTINGS_FILE.stat().st_mtime_ns == before_mtime
    if case == "missing":
        assert "server" not in config.settings()
    else:
        assert config.settings()["server"] == expected
    assert storage.load_settings()["untouched"] == "keep"


def test_kakao_blocks_english_with_action_and_keeps_korean_search(app, fixtures, monkeypatch):
    from trade import browser
    from trade.trade_window import TradeWindow

    config.save(mode="browser", league="Standard", server=config.KAKAO)
    opened = []
    monkeypatch.setattr(browser, "open_url", lambda url: opened.append(url))
    window = TradeWindow()
    window.load((fixtures / "rare_en.txt").read_text())
    assert not window.search_button.isEnabled()
    assert window.hint.text() == "카카오 서버는 한글 클라이언트에서만 지원합니다. 거래소 설정에서 서버를 '공식'으로 바꾸세요"
    window.search()
    assert not opened
    window.load((fixtures / "rare_ko.txt").read_text(encoding="utf-8"))
    assert window.search_button.isEnabled()
    window.search()
    expected = json.loads((fixtures / "browser_links.json").read_text(encoding="utf-8"))
    assert opened == [expected["rare_ko_kakao"]]
    window.close()


def test_korean_official_window_does_not_warn_about_different_market(app, fixtures):
    from PySide6.QtWidgets import QLabel
    from trade.trade_window import TradeWindow

    config.save(mode="browser", league="Standard", server=config.OFFICIAL)
    window = TradeWindow()
    window.load((fixtures / "rare_ko.txt").read_text(encoding="utf-8"))
    assert window.search_button.isEnabled()
    assert not any("매물·시세가 다를 수 있습니다" in label.text() for label in window.findChildren(QLabel))
    window.close()


def test_editor_trade_button_uses_copied_original(app, fixtures, monkeypatch):
    from PySide6.QtWidgets import QPushButton
    from item_editor import ItemEditor
    from itemmodel import Mod
    from trade.query import build_query, conditions, item_info

    copied = parse((fixtures / "rare_en.txt").read_text())
    editor = ItemEditor(None, SimpleNamespace(_cur=lambda: None))
    monkeypatch.setattr(editor, "_compute_original", lambda: None)
    monkeypatch.setattr(editor, "_recompute", lambda: None)
    editor.load(copied, None)
    editor.model.mods[1].enabled = False
    editor.model.mods[2].text = "+999 to maximum Life"
    editor.model.mods.append(Mod("+900 to Armour", added=True))
    captured = []
    editor.tradeRequested.connect(lambda model, hwnd: captured.append(model))
    button = next(button for button in editor.findChildren(QPushButton) if button.text() == "거래소 검색")
    button.click()
    assert captured == [editor.original]
    info = item_info(captured[0])
    actual = build_query(info, conditions(info))
    assert actual == json.loads((fixtures / "rare_expected.json").read_text())
    editor._timer.stop()
    editor.close()


def test_only_user_window_moves_are_saved(app, fixtures, monkeypatch):
    from PySide6.QtCore import QCoreApplication, QPoint
    from PySide6.QtGui import QMoveEvent
    from PySide6.QtTest import QTest
    import winutil
    from trade.trade_window import TradeWindow

    class UserMove(QMoveEvent):
        def spontaneous(self):
            return True

    monkeypatch.setattr(winutil, "focus_window", lambda hwnd: True)
    saved = []
    original_save = config.save

    def record(**changes):
        if "window" in changes:
            saved.append(changes["window"])
        original_save(**changes)

    monkeypatch.setattr(config, "save", record)
    config.save(mode="browser", league="Standard")
    window = TradeWindow()
    item = (fixtures / "rare_en.txt").read_text()
    window.show_item(item)
    app.processEvents()
    QTest.qWait(window._position_timer.interval() + 50)
    assert "window" not in config.settings()
    assert not saved
    window.move(window.pos() + QPoint(10, 10))
    app.processEvents()
    assert not window._position_timer.isActive()
    for step in range(3):
        window.move(window.pos() + QPoint(1, 1))
        QCoreApplication.sendEvent(window, UserMove(window.pos(), window.pos() - QPoint(1, 1)))
    assert not saved
    QTest.qWait(window._position_timer.interval() + 50)
    assert saved == [{"x": window.x(), "y": window.y()}]
    assert config.settings()["window"] == saved[0]
    window.close()
    window.show_item(item)
    app.processEvents()
    QTest.qWait(window._position_timer.interval() + 50)
    assert len(saved) == 1
    window.close()
