"""Bounded HTTP probes; no environment proxies, redirects, credentials or body reads."""

import asyncio
import ssl
from time import perf_counter

import aiohttp

from system_monitoring import __version__
from system_monitoring.models import ProbeResult
from system_monitoring.targets import ApprovedResolver, TargetPolicy


class HttpChecker:
    def __init__(self, policy: TargetPolicy) -> None:
        self.policy = policy
        self.ssl_context = ssl.create_default_context()

    async def probe(self, service: dict) -> ProbeResult:
        started = perf_counter()
        status = None
        try:
            url = self.policy.validate(service["url"])
            # The total deadline includes DNS resolution, connect, TLS and headers.
            async with asyncio.timeout(service["timeout_seconds"]):
                resolver = ApprovedResolver(self.policy, url)
                connector = aiohttp.TCPConnector(
                    resolver=resolver,
                    use_dns_cache=False,
                    force_close=True,
                    ssl=self.ssl_context,
                    limit=1,
                )
                async with aiohttp.ClientSession(
                    connector=connector,
                    trust_env=False,
                    auto_decompress=False,
                    skip_auto_headers={"Accept-Encoding"},
                    timeout=aiohttp.ClientTimeout(total=service["timeout_seconds"]),
                    read_bufsize=1024,
                    max_line_size=4096,
                    max_field_size=4096,
                    headers={"User-Agent": f"SystemMonitoring/{__version__}"},
                    cookie_jar=aiohttp.DummyCookieJar(),
                ) as session:
                    async with session.get(url, allow_redirects=False) as response:
                        status = response.status
                        response.close()
            outcome = "success" if status == service["expected_status"] else "failure"
            reason = None if outcome == "success" else f"Unexpected HTTP status {status}"
        except ValueError:
            outcome, reason = "blocked", "Target blocked by operator network policy"
        except TimeoutError:
            outcome, reason = "failure", "Request timed out"
        except (aiohttp.ClientConnectorCertificateError, ssl.SSLError):
            outcome, reason = "failure", "TLS verification failed"
        except (aiohttp.ClientError, OSError):
            outcome, reason = "failure", "Connection or DNS lookup failed"
        return ProbeResult(outcome, round(perf_counter() - started, 6), status, reason)
