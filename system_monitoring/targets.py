"""Exact-origin approval and DNS checks applied to every new connection."""

import asyncio
import ipaddress
import socket

from aiohttp.abc import AbstractResolver
from aiohttp.resolver import ResolveResult
from pydantic import HttpUrl, ValidationError


class TargetBlocked(ValueError):
    """The target falls outside the operator's configured network policy."""


def normalize_url(value: str, *, origin_only: bool = False) -> str:
    try:
        url = HttpUrl(value)
    except ValidationError as error:
        raise ValueError("Use a valid absolute HTTP or HTTPS URL") from error
    if url.username is not None or url.password is not None or url.fragment is not None:
        raise ValueError("Target URLs must not contain credentials or fragments")
    if origin_only and (url.path not in (None, "/") or url.query is not None):
        raise ValueError("Approved origins contain only a scheme, hostname and optional port")
    return str(url)


def origin(value: str) -> str:
    url = HttpUrl(value)
    host = url.host
    return f"{url.scheme}://{host}:{url.port}"


class TargetPolicy:
    def __init__(self, approved_origins: list[str], private_origins: list[str]) -> None:
        self.approved = {origin(value) for value in approved_origins}
        self.private = {origin(value) for value in private_origins}

    def validate(self, value: str) -> str:
        value = normalize_url(value)
        if origin(value) not in self.approved:
            raise TargetBlocked("Target origin is not approved by the operator")
        host = HttpUrl(value).host.strip("[]")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            self.validate_address(str(address), value)
        return value

    def validate_address(self, address: str, value: str) -> None:
        ip = ipaddress.ip_address(address)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        # Never permit metadata/link-local, multicast, unspecified or reserved IPs,
        # even for explicitly approved internal origins.
        metadata = ip in {
            ipaddress.ip_address("168.63.129.16"),
            ipaddress.ip_address("fd00:ec2::254"),
        }
        forbidden = (
            metadata or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved
        )
        private_allowed = origin(value) in self.private and (ip.is_private or ip.is_loopback)
        if forbidden or not (ip.is_global or private_allowed):
            raise TargetBlocked("Target resolves to a prohibited network address")


class ApprovedResolver(AbstractResolver):
    """Validate DNS answers and hand those exact numeric IPs to aiohttp.

    The HTTP client retains the original hostname for Host and TLS verification;
    it never resolves the hostname a second time after policy validation.
    """

    def __init__(self, policy: TargetPolicy, url: str) -> None:
        self.policy = policy
        self.url = url

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET):
        records = await asyncio.get_running_loop().getaddrinfo(
            host, port, family=family, type=socket.SOCK_STREAM
        )
        if not records:
            raise OSError("No addresses returned")
        for _, _, _, _, address in records:
            self.policy.validate_address(address[0], self.url)
        return [
            ResolveResult(
                hostname=host,
                host=address[0],
                port=port,
                family=record_family,
                proto=protocol,
                flags=socket.AI_NUMERICHOST,
            )
            for record_family, _, protocol, _, address in records
        ]

    async def close(self) -> None:
        pass
