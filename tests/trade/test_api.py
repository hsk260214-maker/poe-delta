import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
import requests

from ratelimit import RateLimiter, parse_headers
from trade import config, secret


@pytest.fixture
def api(monkeypatch):
    from trade import api

    monkeypatch.setattr(api, "_LIMITS", RateLimiter(clock=lambda: 100))
    monkeypatch.setattr(api, "_POLICIES", {})
    monkeypatch.setattr(api, "_LEAGUES", None)
    monkeypatch.setattr(secret, "load_session", lambda: "")
    config.save(mode="api", api_ack_at=1)
    return api


def response(data=None, status=200, headers=None):
    return SimpleNamespace(status_code=status, headers=headers or {}, json=lambda: data or {})


@pytest.mark.parametrize("index", range(4))
def test_rate_samples(fixtures, index):
    sample = json.loads((fixtures / "rate_headers.json").read_text())[index]
    note = parse_headers(sample["headers"], sample["status"], now=100)
    assert max(0, note.next_at - 100) == sample["wait"]
    limiter = RateLimiter(clock=lambda: 100)
    policy = limiter.note(sample["headers"], sample["status"])
    assert limiter.remaining(policy) == sample["wait"]
    assert limiter.remaining("other-policy") == 0


def test_importer_legacy_rate_state(monkeypatch):
    import time
    from pob import importers

    monkeypatch.setattr(time, "time", lambda: 100)
    monkeypatch.setattr(importers, "RL", {})
    monkeypatch.setattr(importers, "PAUSE_UNTIL", 0)
    headers = {"X-Rate-Limit-Policy": "character", "X-Rate-Limit-Rules": "ip",
               "X-Rate-Limit-Ip": "10:60:20,100:1800:3600",
               "X-Rate-Limit-Ip-State": "3:60:8,85:1800:0"}
    importers._note_rate(response(status=200, headers=headers))
    assert importers.RL == {"character": (100, [(3, 10, 60), (85, 100, 1800)])}
    assert importers.PAUSE_UNTIL == 108
    assert "요청 한도 초과" in importers.budget_note()
    importers._note_rate(response(status=429, headers={"Retry-After": "17"}))
    assert importers.PAUSE_UNTIL == 117


def test_policy_gate_no_extra_request(api, monkeypatch):
    calls = []

    def transport(*args, **kwargs):
        calls.append(args)
        return response({"id": "sample", "result": []}, headers={
            "X-Rate-Limit-Policy": "trade-search", "X-Rate-Limit-Rules": "ip",
            "X-Rate-Limit-Ip": "1:10:20", "X-Rate-Limit-Ip-State": "1:10:0"})

    monkeypatch.setattr(requests, "request", transport)
    client = api.TradeClient()
    query = {"query": {"status": {"option": "securable"}}}
    client.search("Standard", query)
    with pytest.raises(api.TradeError) as problem:
        client.search("Standard", query)
    assert problem.value.kind == "rate_limited"
    assert problem.value.retry_after == 10
    assert len(calls) == 1
    assert client.remaining(endpoint="fetch") == 0


@pytest.mark.parametrize("status,kind", [(401, "login_required"), (403, "login_required"),
                                        (404, "bad_league"), (500, "server"), (429, "rate_limited")])
def test_safe_errors(api, monkeypatch, status, kind):
    value = "FAKE-COOKIE-DO-NOT-LEAK"
    monkeypatch.setattr(secret, "load_session", lambda: value)
    monkeypatch.setattr(requests, "request", lambda *a, **k: response(
        {"error": {"message": value}}, status, {"Retry-After": "5", "Sensitive": value}))
    with pytest.raises(api.TradeError) as problem:
        api.TradeClient().search("Standard", {"query": {"status": {"option": "securable"}}})
    assert problem.value.kind == kind
    assert value not in str(problem.value)
    assert problem.value.__cause__ is None


def test_mode_guard_and_network_error(api, monkeypatch):
    calls = []

    def broken(*args, **kwargs):
        calls.append(args)
        raise requests.ConnectionError("FAKE-COOKIE-DO-NOT-LEAK")

    monkeypatch.setattr(requests, "request", broken)
    client = api.TradeClient()
    config.save(mode="browser")
    with pytest.raises(api.TradeError) as problem:
        client.search("Standard", {"query": {"status": {"option": "securable"}}})
    assert problem.value.kind == "mode_disabled"
    assert not calls
    config.save(mode="api", api_ack_at=None)
    with pytest.raises(api.TradeError):
        client.search("Standard", {"query": {"status": {"option": "securable"}}})
    assert not calls
    config.save(mode="api", api_ack_at=1)
    with pytest.raises(api.TradeError) as problem:
        client.search("Standard", {"query": {"status": {"option": "securable"}}})
    assert problem.value.kind == "network"
    assert "FAKE-COOKIE" not in str(problem.value)


def test_cookie_host_redirect_and_user_agent(api, monkeypatch):
    captured = []
    monkeypatch.setattr(secret, "load_session", lambda: "FAKE-COOKIE-DO-NOT-LEAK")

    def transport(*args, **kwargs):
        captured.append(kwargs)
        return response({"id": "sample", "result": []})

    monkeypatch.setattr(requests, "request", transport)
    query = {"query": {"status": {"option": "securable"}}}
    client = api.TradeClient()
    client.search("Standard", query)
    client.search("Standard", query, config.KAKAO, "ko")
    assert captured[0]["headers"]["Cookie"] == "POESESSID=FAKE-COOKIE-DO-NOT-LEAK"
    assert "Cookie" not in captured[1]["headers"]
    assert "contact:" not in captured[0]["headers"]["User-Agent"]
    assert "Mozilla" not in captured[0]["headers"]["User-Agent"]
    assert captured[0]["allow_redirects"] is False
    config.save(contact="owner@example.invalid")
    client.search("Standard", query)
    assert captured[2]["headers"]["User-Agent"].endswith("(contact: owner@example.invalid)")


def test_serialized_requests(api, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    active, maximum = 0, 0
    state_lock = threading.Lock()

    def transport(*args, **kwargs):
        nonlocal active, maximum
        with state_lock:
            active += 1
            maximum = max(maximum, active)
        entered.set()
        assert release.wait(5)
        with state_lock:
            active -= 1
        return response({"id": "sample", "result": []})

    monkeypatch.setattr(requests, "request", transport)
    query = {"query": {"status": {"option": "securable"}}}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(api.TradeClient().search, "Standard", query) for _ in range(2)]
        assert entered.wait(5)
        release.set()
        for future in futures:
            assert future.result()["id"] == "sample"
    assert maximum == 1


def test_dpapi_and_plaintext_absence(tmp_path, monkeypatch, fixtures):
    import storage
    from paths import LOCAL
    from trade import browser
    from trade.query import build_query, conditions, item_info
    from itemmodel import parse

    value = "FAKE-COOKIE-DO-NOT-LEAK"
    path = tmp_path / "trade_session.bin"
    monkeypatch.setattr(secret, "SESSION_FILE", path)
    config.save(mode="api", api_ack_at=1)
    secret.save_session(value)
    assert value.encode() not in path.read_bytes()
    assert secret.load_session() == value
    model = parse((fixtures / "rare_en.txt").read_text())
    info = item_info(model)
    link = browser.build_url("Standard", build_query(info, conditions(info)))
    assert value not in link
    assert value not in storage.SETTINGS_FILE.read_text()
    for filename in LOCAL.rglob("*"):
        if filename.is_file():
            assert value.encode() not in filename.read_bytes()
    secret.delete_session()
    assert not path.exists()
