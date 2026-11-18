"""앱 import 전에 사용자 데이터와 모든 테스트 출력을 임시 폴더로 격리."""
import os
import socket
import sys
import tempfile
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
TEMP = Path(tempfile.mkdtemp(prefix="poe-tests-"))
os.environ["APPDATA"] = str(TEMP / "roaming")
os.environ["LOCALAPPDATA"] = str(TEMP / "local")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "app"))


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    import dict_builder
    import paths
    import storage

    assert not list((paths.ROAMING / "data").glob("*"))
    monkeypatch.setattr(dict_builder, "CACHE", tmp_path / "apt-cache")
    monkeypatch.setattr(dict_builder, "OUT_DIR", tmp_path / "data-output")
    monkeypatch.setattr(storage, "APP_DIR", tmp_path / "settings")
    monkeypatch.setattr(storage, "SETTINGS_FILE", tmp_path / "settings" / "settings.json")

    def denied(*args, **kwargs):
        pytest.fail("테스트의 실제 네트워크 요청은 금지됩니다")

    monkeypatch.setattr(requests.Session, "request", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


@pytest.fixture(scope="session")
def app():
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance() or QApplication([])
    yield application
    for widget in QApplication.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()
    application.quit()


@pytest.fixture
def fixtures():
    return ROOT / "tests" / "trade" / "fixtures"
