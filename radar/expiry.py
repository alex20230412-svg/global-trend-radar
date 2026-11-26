"""Optional expiry reminder from the dedicated private repository's metadata response."""

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from math import ceil
import re

import httpx

from .storage import DATA_REPO, GITHUB_API_ROOT


EXPIRATION_HEADER = "GitHub-Authentication-Token-Expiration"
# GitHub documents the header but not its exact format; accept "UTC" and "+0000" styles.
OFFSET = re.compile(r"\s*([+-])([0-9]{2}):?([0-9]{2})$")
MYT = timezone(timedelta(hours=8))


def token_expiry_notice(token, now, *, client=None):
    if not token:
        return "no_token", None
    try:
        connection = nullcontext(client) if client is not None else httpx.Client(trust_env=False)
        with connection as http:
            with http.stream(
                "GET",
                f"{GITHUB_API_ROOT}/repos/{DATA_REPO}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                timeout=5,
                follow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    return f"http_{response.status_code}", None
                raw = response.headers.get(EXPIRATION_HEADER)
    except (httpx.HTTPError, ValueError):
        return "request_failed", None
    if not raw:
        return "missing_header", None
    try:
        timestamp = raw.strip()
        if timestamp.endswith(" UTC"):
            timestamp = timestamp.removesuffix(" UTC") + "+00:00"
        elif OFFSET.search(timestamp):
            timestamp = OFFSET.sub(lambda match: f"{match[1]}{match[2]}:{match[3]}", timestamp)
        expiry = datetime.fromisoformat(timestamp)
        if expiry.tzinfo is None:
            return "invalid_header", None
    except ValueError:
        return "invalid_header", None
    days = max(0, ceil((expiry - now).total_seconds() / 86400))
    if days > 14:
        return "ok", None
    date = expiry.astimezone(MYT).date().isoformat()
    return "expiring", f"⚠️ 私库钥匙 {days} 天后到期（{date}），请到 GitHub 更新 DATA_REPO_TOKEN"
