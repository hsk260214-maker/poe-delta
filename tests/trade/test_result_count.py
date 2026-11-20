from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractSlider, QApplication
import pytest

from trade import api, config, trade_window
from trade.settings_dialog import SettingsDialog


TEXT = "Item Class: Rings\nRarity: Rare\nGold Ring\n--------\nItem Level: 83"


def entry(i):
    return {"id": i, "item": {"ilvl": 83}, "listing": {
        "account": {"name": i}, **({"price": {"amount": int(i) + 1, "currency": "chaos"}} if int(i) >= 10 else {}),
    }}


@pytest.fixture
def scenario(app, monkeypatch):
    config.save(mode="api", server=config.OFFICIAL, league="Standard")

    class Client:
        ids = [str(i) for i in range(100)]
        total = 120
        wait = 0
        failure = None
        missing = set()
        calls = []

        def leagues(self, *_):
            return ["Standard", "Hardcore"]

        def search(self, *_):
            self.calls.append("search")
            return {"result": self.ids, "total": self.total, "id": "query"}

        def fetch(self, ids, *_):
            self.calls.append(tuple(ids))
            assert len(ids) <= 10
            if ids[0] == self.failure:
                raise api.TradeError("rate_limited" if self.wait else "network", self.wait)
            return {"result": [entry(i) for i in reversed(ids) if i not in self.missing]}

        def remaining(self, *_):
            return self.wait

    pending = []
    client = Client()
    monkeypatch.setattr(api, "TradeClient", lambda: client)
    monkeypatch.setattr(trade_window, "run_async", lambda work, done, fail: pending.append((work, done, fail)))
    window = trade_window.TradeWindow()
    window.load(TEXT)
    yield window, client, pending
    window.close()


def finish(pending):
    while pending:
        work, done, _ = pending.pop(0)
        done(work())


@pytest.mark.parametrize("value", [None, 11, "30", True, 110, 0, 30.0])
def test_invalid_initial_count_defaults_to_twenty(value):
    assert config.result_count(value) == 20


def test_setting_is_saved_and_disabled_in_browser_mode(app):
    config.save(mode="browser", result_count=11)
    dialog = SettingsDialog()
    assert dialog.result_count.currentData() == 20 and not dialog.result_count.isEnabled()
    dialog.mode.setCurrentIndex(dialog.mode.findData("api"))
    assert dialog.result_count.isEnabled()
    dialog.result_count.setCurrentIndex(dialog.result_count.findData(30))
    assert config.settings()["result_count"] == 30
    dialog.close()


def test_initial_snapshot_order_and_frozen_summary(scenario):
    window, client, pending = scenario
    config.save(result_count=30)
    window.search()
    config.save(result_count=10)
    finish(pending)
    assert len(client.calls) == 4 and window.table.rowCount() == 30
    assert [window.table.item(i, 1).text() for i in range(30)] == [str(i) for i in range(30)]
    frozen = window._results.summary
    window._load_more()
    window._load_more()
    assert len(pending) == 1
    finish(pending)
    assert window.table.rowCount() == 40 and window._results.summary == frozen
    assert "표시 40 / 받은 100개" in window.result_summary.text()
    window.search()
    finish(pending)
    assert window.table.rowCount() == 10


def test_successful_initial_batch_pauses_without_finalizing_summary(scenario, monkeypatch):
    window, client, pending = scenario
    now = 100.0
    monkeypatch.setattr(trade_window.time, "monotonic", lambda: now)
    summary_sizes = []
    summarize = trade_window.summary
    monkeypatch.setattr(trade_window, "summary",
                        lambda total, rows: summary_sizes.append(len(rows)) or summarize(total, rows))
    config.save(result_count=30)
    window.search()
    client.wait = 5
    finish(pending)
    assert window.table.rowCount() == window._results.next == 10
    assert window.open_button.isEnabled() and not window._busy
    assert window._results.summary is None and not summary_sizes
    assert "표시 10 / 받은 100개" in window.result_summary.text()
    assert "요청 제한" in window.hint.text()
    window.table.setCurrentCell(9, 0)
    QTest.keyClick(window.table, Qt.Key.Key_End)
    assert len(client.calls) == 2 and not pending

    now += 5
    client.wait = 0
    window._validate()
    assert not pending
    QTest.keyClick(window.table, Qt.Key.Key_End)
    finish(pending)
    assert [batch[0] for batch in client.calls[1:]] == ["0", "10", "20"]
    assert window.table.rowCount() == window._results.next == 30
    assert window._results.summary is not None and summary_sizes == [30]


def test_partial_initial_failure_keeps_rows_link_and_retries_after_wait(scenario):
    window, client, pending = scenario
    client.missing = {"0", "1", "2"}
    window.search()
    work, done, _ = pending.pop(0)
    done(work())
    assert window.open_button.isEnabled()
    work, done, _ = pending.pop(0)
    done(work())
    client.failure, client.wait = "10", 5
    finish(pending)
    assert window.table.rowCount() == 7 and window._results.next == 10
    assert window.open_button.isEnabled() and "요청 제한" in window.hint.text()
    window._load_more()
    assert not pending
    frozen = window._results.summary
    client.failure, client.wait, window._until = None, 0, 0
    window._load_more()
    finish(pending)
    assert client.calls[-1] == client.calls[-2] and window.table.rowCount() == 17
    assert window._results.summary == frozen


def test_first_fetch_failure_can_retry_with_wheel_without_scrollbar(scenario):
    window, client, pending = scenario
    client.failure = "0"
    window.search()
    finish(pending)
    assert window.open_button.isEnabled() and window._results.next == 0
    assert window.table.rowCount() == window.table.verticalScrollBar().maximum() == 0
    client.failure = None
    event = QWheelEvent(QPointF(2, 2), QPointF(2, 2), QPoint(), QPoint(0, -120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(window.table.viewport(), event)
    finish(pending)
    assert client.calls[-1] == client.calls[-2]
    assert window.table.rowCount() == 10 and window._results.next == 10


def test_second_batch_prices_contribute_when_first_batch_has_missing_ids(scenario):
    window, client, pending = scenario
    client.missing = {"0", "1", "2"}
    window.search()
    finish(pending)
    assert window.table.rowCount() == 17
    assert "최저가 11 chaos" in window.result_summary.text()
    assert "상위 10개 중간값 12 chaos" in window.result_summary.text()


@pytest.mark.parametrize("success", [True, False])
def test_old_fetch_cannot_change_replacement_search(scenario, success):
    window, _, pending = scenario
    window.search()
    work, done, _ = pending.pop(0)
    done(work())
    stale_work, stale_done, stale_failed = pending.pop(0)
    window.corrupted.click()
    window.search()
    finish(pending)
    assert window.table.rowCount() == 20 and window.open_button.isEnabled()
    session = window._results
    state = (window.result_summary.text(), window._result_link, window._busy, window._until, session.next)
    stale_done(stale_work()) if success else stale_failed("old fetch")
    assert window._results is session
    assert state == (window.result_summary.text(), window._result_link, window._busy, window._until, session.next)
    assert window.table.rowCount() == 20 and not pending


@pytest.mark.parametrize("size,total,notice", [
    (100, 120, "받은 100개 매물 ID를 모두 조회했습니다."),
    (5, 6, "받은 매물 ID를 모두 조회했습니다."),
    (5, 5, None),
])
def test_end_notices_use_ids_even_when_fetch_is_empty(scenario, size, total, notice):
    window, client, pending = scenario
    client.ids, client.total = client.ids[:size], total
    client.missing = set(client.ids)
    config.save(result_count=100)
    window.search()
    finish(pending)
    assert window.open_button.isEnabled()
    assert window.table.rowCount() == 0 and window._results.next == size
    assert f"표시 0 / 받은 {size}개" in window.result_summary.text()
    assert (notice in window.result_summary.text()) if notice else ("모두 조회" not in window.result_summary.text())
    window._load_more()
    assert not pending


@pytest.mark.parametrize("source", ["wheel", "scrollbar", Qt.Key.Key_Down, Qt.Key.Key_PageDown, Qt.Key.Key_End])
def test_only_explicit_bottom_inputs_schedule_more(scenario, source):
    window, client, pending = scenario
    window.show()
    window.search()
    finish(pending)
    table = window.table
    table.setFixedHeight(100)
    QApplication.processEvents()
    bar = table.verticalScrollBar()
    bar.setValue(bar.maximum())
    assert len(client.calls) == 3 and not pending
    if source == "wheel":
        event = QWheelEvent(QPointF(2, 2), QPointF(2, 2), QPoint(), QPoint(0, -120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(table.viewport(), event)
    elif source == "scrollbar":
        bar.triggerAction(QAbstractSlider.SliderAction.SliderToMaximum)
    else:
        table.setCurrentCell(table.rowCount() - 1, 0)
        QTest.keyClick(table, source)
    assert len(pending) == 1
    finish(pending)
    QApplication.processEvents()
    assert len(client.calls) == 4 and table.rowCount() == 30 and not pending


@pytest.mark.parametrize("invalidate", ["condition", "league", "load", "routing", "close"])
@pytest.mark.parametrize("success", [True, False])
def test_stale_callbacks_leave_every_window_field_unchanged(scenario, invalidate, success):
    window, _, pending = scenario
    window.search()
    work, done, failed = pending.pop(0)
    if invalidate == "condition":
        window.corrupted.click()
    elif invalidate == "league":
        window.league.setEditText("Hardcore")
    elif invalidate == "load":
        window.load(TEXT.replace("Gold Ring", "Topaz Ring"))
    elif invalidate == "routing":
        config.save(mode="browser")
        window._validate()
    else:
        window.close()

    def snapshot():
        return (window.table.rowCount(), window._busy, window._until, window.hint.text(),
                window.result_summary.text(), window._result_link, window.open_button.isEnabled(),
                window.search_button.isEnabled(), window.league.currentText(),
                tuple(window.league.itemText(i) for i in range(window.league.count())))

    before = snapshot()
    done(work()) if success else failed("old failure")
    assert snapshot() == before and not pending
