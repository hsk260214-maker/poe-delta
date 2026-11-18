from types import SimpleNamespace

import pytest
import requests

import app_update
from version import VERSION


def response(status, data=None):
    def raise_for_status():
        if status >= 400:
            raise requests.HTTPError(str(status))
    return SimpleNamespace(status_code=status, json=lambda: data, raise_for_status=raise_for_status)


@pytest.fixture(autouse=True)
def no_manifest_override(monkeypatch):
    monkeypatch.delenv("EXILEDELTA_UPDATE_MANIFEST", raising=False)


def test_private_or_missing_release_returns_empty(monkeypatch):
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return response(404)

    monkeypatch.setattr(requests, "get", get)
    assert app_update.latest() is None
    assert app_update.history() == []
    assert [url for url, _ in calls] == [
        "https://api.github.com/repos/hsk260214-maker/poe-delta/releases/latest",
        "https://api.github.com/repos/hsk260214-maker/poe-delta/releases?per_page=50"]
    assert all(kwargs["headers"]["User-Agent"] == "PoeDelta-updater" for _, kwargs in calls)


def test_public_release_uses_same_repo_without_code_change(monkeypatch):
    calls = []
    page = "https://github.com/hsk260214-maker/poe-delta/releases/tag/v1.2.0"
    manifest = "https://example.invalid/manifest.json"
    payload = "https://example.invalid/app-1.2.0.zip"

    def get(url, **kwargs):
        calls.append(url)
        if url == manifest:
            return response(200, {"version": "1.2.0", "zip": "app-1.2.0.zip", "sha256": "fixture", "min_loader": 1})
        return response(200, {"body": "notes", "html_url": page, "assets": [
            {"name": "manifest.json", "browser_download_url": manifest},
            {"name": "app-1.2.0.zip", "browser_download_url": payload}]})

    monkeypatch.setattr(requests, "get", get)
    result = app_update.latest()
    assert result == {"version": "1.2.0", "zip_url": payload, "sha256": "fixture", "min_loader": 1,
                      "notes": "notes", "page": page}
    assert calls == ["https://api.github.com/repos/hsk260214-maker/poe-delta/releases/latest", manifest]


@pytest.mark.parametrize("manual", [False, True])
def test_missing_release_manual_notice_and_silent_auto(monkeypatch, manual):
    import asyncjob

    notices, finished = [], []
    monkeypatch.setattr(app_update, "enabled", lambda: True)
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: response(404))
    monkeypatch.setattr(asyncjob, "run_async", lambda job, done, fail: done(job()))
    updater = app_update.StartupUpdater(None, lambda: finished.append(True), manual=manual)
    monkeypatch.setattr(updater, "_info", lambda title, text: notices.append((title, text)))
    updater.start()
    assert finished == [True]
    assert notices == ([("프로그램 업데이트", f"확인할 수 있는 릴리스가 없습니다 (지금 v{VERSION}). 저장소가 비공개이거나 아직 릴리스가 없습니다.")] if manual else [])


def test_new_loader_page_uses_custom_repo(monkeypatch):
    import dialogs
    import webbrowser

    pages, finished = [], []
    monkeypatch.setattr(app_update, "loader_version", lambda: 1)
    monkeypatch.setattr(dialogs, "confirm", lambda *args: True)
    monkeypatch.setattr(webbrowser, "open", pages.append)
    updater = app_update.StartupUpdater(None, lambda: finished.append(True), manual=True)
    updater._got({"version": "9.0.0", "min_loader": 2, "page": ""})
    assert pages == ["https://github.com/hsk260214-maker/poe-delta/releases/latest"]
    assert finished == [True]
