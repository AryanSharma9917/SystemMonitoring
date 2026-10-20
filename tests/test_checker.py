import asyncio
import ssl
from time import perf_counter

from system_monitoring.checker import HttpChecker
from system_monitoring.targets import TargetPolicy


def probe(server, path="/", **changes):
    checker = HttpChecker(TargetPolicy([server.url], [server.url]))
    service = {"url": server.url + path, "timeout_seconds": 1, "expected_status": 200, **changes}
    return asyncio.run(checker.probe(service))


def test_real_http_response_and_status_matching(target_server):
    assert probe(target_server).outcome == "success"
    target_server.status = 503
    result = probe(target_server)
    assert result.outcome == "failure"
    assert result.status_code == 503
    assert result.reason == "Unexpected HTTP status 503"
    assert probe(target_server, expected_status=503).outcome == "success"


def test_redirects_are_not_followed(target_server):
    result = probe(target_server, "/redirect")
    assert result.status_code == 302
    assert target_server.paths == ["/redirect"]


def test_request_deadline_includes_waiting_for_headers(target_server):
    started = perf_counter()
    result = probe(target_server, "/slow")
    assert result.outcome == "failure"
    assert result.reason == "Request timed out"
    assert perf_counter() - started < 1.4


def test_blocked_target_is_not_an_outage(target_server):
    checker = HttpChecker(TargetPolicy([target_server.url], []))
    result = asyncio.run(checker.probe({"url": target_server.url, "timeout_seconds": 1}))
    assert result.outcome == "blocked"
    assert target_server.paths == []


def test_tls_verification_is_enabled():
    checker = HttpChecker(TargetPolicy([], []))
    assert checker.ssl_context.verify_mode == ssl.CERT_REQUIRED
    assert checker.ssl_context.check_hostname


def test_dns_policy_failure_remains_blocked(monkeypatch):
    import socket

    async def scenario():
        async def lookup(*args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", lookup)
        checker = HttpChecker(TargetPolicy(["http://example.com"], []))
        result = await checker.probe(
            {
                "url": "http://example.com",
                "timeout_seconds": 1,
                "expected_status": 200,
            }
        )
        assert result.outcome == "blocked"

    asyncio.run(scenario())


def test_response_body_is_not_required_for_success(target_server):
    started = perf_counter()
    assert probe(target_server, "/stream").outcome == "success"
    assert perf_counter() - started < 0.9
