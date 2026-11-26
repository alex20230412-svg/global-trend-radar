"""Bounded, credential-free HTTP for approved source endpoints."""

import re
import ipaddress
import os
import socket
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from threading import Lock

import httpx
from protego import Protego


USER_AGENT = "GlobalTrendRadar/1.0 (+https://github.com/alex20230412-svg/global-trend-radar)"
MAX_BODY = 2 * 1024 * 1024
RETRY_SECONDS = 10
MIN_INTERVAL = 0.5
GDELT_HOST = "api.gdeltproject.org"
ORIGIN_MIN_INTERVALS = {GDELT_HOST: 5.0}
ORIGIN_READ_TIMEOUTS = {GDELT_HOST: 20.0}
# Malaysian origins answered within 4 s most hours, but GitHub runners saw sporadic ConnectTimeouts.
CONNECT_TIMEOUT = 8.0
GITHUB_ARCHIVE_HOST = "api.github.com"
WEIBO_ARCHIVE_PATH = "/repos/justjavac/weibo-trending-hot-search/contents/raw"
WEIBO_ARCHIVE_FILE = re.compile(re.escape(WEIBO_ARCHIVE_PATH) + r"/[0-9]{4}-[0-9]{2}-[0-9]{2}\.json")
SINGLE_READ_ORIGINS = {GITHUB_ARCHIVE_HOST, "wikimedia.org", "www.chinanews.com.cn"}
ARCHIVE_TOKEN = re.compile(r"[!-~]{20,512}")
DETAIL = re.compile(r"[A-Z][A-Za-z0-9_]{0,39}(?::[0-9]{1,7}:[0-9]{1,7})?")
HOSTS = frozenset({
    "trends.google.com",
    "www.malaysiakini.com",
    "www.malaymail.com",
    "cms.freemalaysiatoday.com",
    "www.bernama.com",
    "hacker-news.firebaseio.com",
    "public.api.bsky.app",
    "mastodon.social",
    "api.data.gov.my",
    "rss.marketingtools.apple.com",
    *SINGLE_READ_ORIGINS,
    GDELT_HOST,
})


class SourceError(Exception):
    """An error that can be recorded without disclosing upstream text."""

    def __init__(self, code, retry_after=None, *, http_status=None, skipped=0, detail=None):
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after
        self.http_status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None
        self.skipped = skipped
        # Only an exception class name and an optional line:column position, never upstream text.
        self.detail = detail if isinstance(detail, str) and DETAIL.fullmatch(detail) else None


@dataclass
class OriginGate:
    lock: object = field(default_factory=Lock)
    robots: Protego | None = None
    last_request: float = 0
    stopped: bool = False


# These gates cover concurrent geographic feeds within one workflow process.
ORIGINS = {host: OriginGate() for host in HOSTS}


def public_address(host):
    try:
        candidates = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise SourceError("dns_error") from None
    if not candidates:
        raise SourceError("dns_error")
    addresses = [ipaddress.ip_address(candidate[4][0]) for candidate in candidates]
    if any(
        not address.is_global or address.is_multicast or address.is_reserved
        for address in addresses
    ):
        raise SourceError("private_address_blocked")
    # Standard hosted runners are IPv4-capable. Fall back to IPv6 for IPv6-only hosts.
    return str(min(addresses, key=lambda address: address.version))


def _retry_after(raw):
    raw = raw.strip()
    if raw.isascii() and raw.isdigit() and len(raw) <= 8:
        return int(raw)
    try:
        value = parsedate_to_datetime(raw)
        if value is not None and value.tzinfo is not None:
            return max(0, (value - datetime.now(UTC)).total_seconds())
    except (ValueError, TypeError, OverflowError):
        pass
    return None


class SourceHttp:
    """Use a separate client for each source to isolate cookies and TLS connections."""

    def __init__(self, client, resolver=public_address, sleep=time.sleep, origins=None, clock=time.monotonic):
        self.client = client
        self.resolve = resolver
        self.sleep = sleep
        self.clock = clock
        self.addresses = {}
        self.origins = ORIGINS if origins is None else origins
        self.last_modified = None

    def load(self, url):
        try:
            target = httpx.URL(url)
        except (httpx.InvalidURL, ValueError):
            raise SourceError("url_blocked") from None
        if (
            target.scheme != "https" or target.port not in (None, 443)
            or target.userinfo or target.host not in HOSTS or target.fragment
        ):
            raise SourceError("url_blocked")
        if target.host == GITHUB_ARCHIVE_HOST and not _archive_request(target):
            raise SourceError("url_blocked")
        self.last_modified = None
        gate = self.origins[target.host]
        with gate.lock:
            if gate.stopped:
                raise SourceError("host_backoff")
            if target.host not in self.addresses:
                self.addresses[target.host] = self.resolve(target.host)
            try:
                return self._load(target, gate)
            except SourceError as error:
                if error.code in {"http_401", "http_403", "http_429"}:
                    gate.stopped = True
                raise

    def _load(self, target, gate):
        interval = ORIGIN_MIN_INTERVALS.get(target.host, MIN_INTERVAL)
        if gate.robots is None:
            robots_url = target.copy_with(path="/robots.txt", query=None)
            try:
                robots = self._request(robots_url, gate, interval)
            except SourceError as error:
                if error.code not in {"http_404", "http_410"}:
                    raise
                robots = b""
            if robots.lstrip().startswith(b"<"):
                raise SourceError("robots_invalid")
            try:
                gate.robots = Protego.parse(robots.decode("utf-8-sig"))
            except UnicodeError:
                raise SourceError("robots_invalid") from None
        robots = gate.robots
        if not robots.can_fetch(str(target), USER_AGENT):
            raise SourceError("robots_denied")
        rate = robots.request_rate(USER_AGENT)
        wait = max(
            interval,
            robots.crawl_delay(USER_AGENT) or 0,
            rate.seconds / rate.requests if rate is not None and rate.requests > 0 else 0,
        )
        if wait > RETRY_SECONDS or robots.visit_time(USER_AGENT) is not None:
            raise SourceError("robots_rate_unsupported")
        return self._request(target, gate, wait)

    def _request(self, target, gate, interval):
        for attempt in range(2):
            delay = gate.last_request + interval - self.clock()
            if delay > 0:
                self.sleep(delay)
            gate.last_request = self.clock()
            try:
                return self._read(target)
            except SourceError as error:
                if attempt or target.host in SINGLE_READ_ORIGINS or error.code not in {
                    "network_error", "http_429", "http_500", "http_502", "http_503", "http_504",
                }:
                    raise
                wait = error.retry_after
                # If no wait was advertised, defer a 429 retry to a subsequent run.
                if (error.code == "http_429" and wait is None) or (
                    wait is not None and wait > RETRY_SECONDS
                ):
                    raise
                self.sleep(max(1, wait or 0))
        raise AssertionError("unreachable")

    def _read(self, target):
        # Pin the validated IP for the actual socket connection, with TLS SNI and cert
        # verification against the named origin. Payload URLs never enter this path.
        address = self.addresses[target.host]
        url = target.copy_with(host=address)
        read_timeout = ORIGIN_READ_TIMEOUTS.get(target.host)
        options = {"timeout": httpx.Timeout(read_timeout, connect=CONNECT_TIMEOUT)} if read_timeout else {}
        deadline = self.clock() + max(12, (read_timeout or 0) + 5)
        try:
            headers = {"User-Agent": USER_AGENT, "Host": target.host, "Accept-Encoding": "identity"}
            if _archive_request(target):
                headers["Accept"] = "application/vnd.github.raw+json"
                token = os.environ.get("RUN_METADATA_TOKEN", "")
                if ARCHIVE_TOKEN.fullmatch(token):
                    headers["Authorization"] = f"Bearer {token}"
            with self.client.stream(
                "GET", url,
                headers=headers,
                extensions={"sni_hostname": target.host},
                follow_redirects=False,
                **options,
            ) as response:
                if response.status_code != 200:
                    raise SourceError(
                        f"http_{response.status_code}",
                        _retry_after(response.headers.get("Retry-After", "")),
                        http_status=response.status_code,
                    )
                encoding = response.headers.get("Content-Encoding", "identity")
                if encoding.lower() != "identity":
                    raise SourceError("response_encoding")
                body = bytearray()
                for chunk in response.iter_raw():
                    if self.clock() > deadline:
                        raise SourceError("network_error")
                    if len(body) + len(chunk) > MAX_BODY:
                        raise SourceError("response_too_large")
                    body.extend(chunk)
                self.last_modified = response.headers.get("Last-Modified")
                return bytes(body)
        except httpx.HTTPError as error:
            raise SourceError("network_error", detail=type(error).__name__) from None


def _archive_request(target):
    # This is the only source request that may receive the Actions read token.
    return (
        target.host == GITHUB_ARCHIVE_HOST
        and WEIBO_ARCHIVE_FILE.fullmatch(target.path) is not None
        and target.query == b"ref=master"
    )
