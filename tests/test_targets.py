import asyncio
import socket

import pytest
from pydantic import ValidationError

from system_monitoring.config import Settings
from system_monitoring.targets import ApprovedResolver, TargetBlocked, TargetPolicy, normalize_url


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com",
        "https://user:password@example.com",
        "https://example.com/#fragment",
    ],
)
def test_target_urls_reject_unsupported_inputs(url):
    with pytest.raises(ValueError):
        normalize_url(url)


def test_origin_approval_is_exact():
    policy = TargetPolicy(["https://example.com"], [])
    assert policy.validate("https://example.com/health") == "https://example.com/health"
    for url in ["http://example.com", "https://example.com:444", "https://sub.example.com"]:
        with pytest.raises(TargetBlocked):
            policy.validate(url)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "0.0.0.0",
        "224.0.0.1",
        "100.100.100.200",
        "::1",
        "fe80::1",
        "::ffff:127.0.0.1",
    ],
)
def test_public_origins_cannot_resolve_to_internal_addresses(address):
    policy = TargetPolicy(["https://example.com"], [])
    with pytest.raises(TargetBlocked):
        policy.validate_address(address, "https://example.com")


def test_internal_exceptions_never_allow_metadata_addresses():
    policy = TargetPolicy(["http://demo:8080"], ["http://demo:8080"])
    policy.validate_address("172.18.0.10", "http://demo:8080")
    for address in [
        "169.254.169.254",
        "fe80::1",
        "100.100.100.200",
        "224.0.0.1",
        "168.63.129.16",
        "fd00:ec2::254",
    ]:
        with pytest.raises(TargetBlocked):
            policy.validate_address(address, "http://demo:8080")


def test_literal_addresses_are_checked_before_connecting():
    policy = TargetPolicy(["http://127.0.0.1"], [])
    with pytest.raises(TargetBlocked):
        policy.validate("http://127.0.0.1/health")


def test_private_origins_must_be_a_subset_of_approved_origins():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, private_origins=["http://demo:8080"])
    with pytest.raises(ValidationError):
        Settings(_env_file=None, approved_origins=["https://example.com/path"])


def test_resolver_checks_every_answer_and_returns_numeric_addresses(monkeypatch):
    async def scenario():
        answers = ["93.184.216.34"]

        async def lookup(*args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in answers]

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", lookup)
        resolver = ApprovedResolver(
            TargetPolicy(["https://example.com"], []), "https://example.com"
        )
        result = await resolver.resolve("example.com", 443)
        assert result[0]["host"] == "93.184.216.34"
        assert result[0]["hostname"] == "example.com"
        assert result[0]["flags"] == socket.AI_NUMERICHOST
        answers.append("127.0.0.1")
        with pytest.raises(TargetBlocked):
            await resolver.resolve("example.com", 443)

    asyncio.run(scenario())
