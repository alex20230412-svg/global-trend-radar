"""Conservative, resumable delivery to a single Telegram private chat."""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
import hashlib
import hmac
from html import escape
from html.parser import HTMLParser
import http.client
import json
import math
import re
import time
from urllib.parse import urlsplit


TELEGRAM_LIMIT = 4096
HTML_MAX_BYTES = 32768
MAX_PARTS = 99
MIN_CHAT_GAP = 1.05
INLINE_RETRY_LIMIT = 15
DEFAULT_RETRY_AFTER = 60
MAX_RESPONSE_BYTES = 128 * 1024
TOKEN_PATTERN = re.compile(r"[1-9][0-9]{0,15}:[A-Za-z0-9_-]{20,100}")
DELIVERY_STATES = {"PENDING", "SENDING", "SENT", "UNKNOWN", "RATE_LIMITED", "REJECTED", "CONFIRMED"}
REJECTION_CODES = {400, 401, 403, 404}
LedgerLoad = Callable[[str], dict | None]
LedgerSave = Callable[[str, dict], None]
TelegramRequest = Callable[[str, str, dict], tuple[int, object]]


class DeliveryError(RuntimeError):
    """A safe, fixed error code that can be printed to public logs."""


def _units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


class _MessageParser(HTMLParser):
    """Parse the HTML subset emitted by the report renderer."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.tags: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "b" and not attrs:
            self.tags.append(tag)
            return
        if tag == "a" and len(attrs) == 1 and attrs[0][0] == "href" and "a" not in self.tags:
            href = attrs[0][1]
            if href and len(href) <= 2048 and not any(char.isspace() or ord(char) < 32 for char in href):
                try:
                    url = urlsplit(href)
                    if url.scheme in {"http", "https"} and url.hostname and url.username is None:
                        self.tags.append(tag)
                        return
                except ValueError:
                    pass
        raise DeliveryError("invalid_message_markup")

    def handle_endtag(self, tag):
        if not self.tags or self.tags.pop() != tag:
            raise DeliveryError("invalid_message_markup")

    def handle_data(self, data):
        if any(char in data for char in "<>&"):
            raise DeliveryError("unescaped_message_text")
        self.text.append(data)

    def handle_entityref(self, name):
        names = {"lt": "<", "gt": ">", "amp": "&", "quot": '"'}
        if name not in names:
            raise DeliveryError("invalid_message_entity")
        self.text.append(names[name])

    def handle_charref(self, name):
        try:
            value = int(name[1:], 16) if name.lower().startswith("x") else int(name, 10)
            self.text.append(chr(value))
        except ValueError:
            raise DeliveryError("invalid_message_entity") from None

    def handle_startendtag(self, tag, attrs):
        raise DeliveryError("invalid_message_markup")

    def handle_comment(self, data):
        raise DeliveryError("invalid_message_markup")

    handle_decl = handle_comment
    handle_pi = handle_comment
    unknown_decl = handle_comment


def _message_text(markup: str) -> str:
    parser = _MessageParser()
    try:
        if len(markup.encode("utf-8")) > HTML_MAX_BYTES:
            raise DeliveryError("invalid_message_markup")
        parser.feed(markup)
        parser.close()
        if parser.tags:
            raise DeliveryError("invalid_message_markup")
        text = "".join(parser.text)
        if not text.strip() or _units(text) > TELEGRAM_LIMIT:
            raise DeliveryError("invalid_message_length")
        if any(ord(char) < 32 and char not in "\n\t" for char in text):
            raise DeliveryError("invalid_message_text")
        return text
    except UnicodeError:
        raise DeliveryError("invalid_message_text") from None


def split_parts(blocks: Iterable[tuple[str, str]], *, label: str = "") -> list[str]:
    """Pack complete HTML blocks. An optional stable label identifies every part."""
    if len(label) > 80 or any(ord(char) < 32 for char in label):
        raise DeliveryError("invalid_message_label")
    # Reserve room for the longest part marker.
    marker = f"{label} · 分段 99/99\n\n" if label else "分段 99/99\n\n"
    units_budget = TELEGRAM_LIMIT - _units(marker)
    bytes_budget = HTML_MAX_BYTES - len(escape(marker).encode("utf-8"))
    groups = []
    current = []
    units_used = 0
    bytes_used = 0
    for markup, plain in blocks:
        if _message_text(markup) != plain:
            raise DeliveryError("message_text_mismatch")
        size = _units(plain)
        raw_size = len(markup.encode("utf-8"))
        if size > units_budget or raw_size > bytes_budget:
            raise DeliveryError("message_block_too_long")
        if current and (units_used + 2 + size > units_budget or bytes_used + 2 + raw_size > bytes_budget):
            groups.append("\n\n".join(current))
            current = []
            units_used = 0
            bytes_used = 0
        gap = 2 if current else 0
        current.append(markup)
        units_used += gap + size
        bytes_used += gap + raw_size
    if current:
        groups.append("\n\n".join(current))
    if not groups or len(groups) > MAX_PARTS:
        raise DeliveryError("invalid_message_part_count")
    if label:
        return [f"{escape(label)} · 分段 {number}/{len(groups)}\n\n{markup}"
                for number, markup in enumerate(groups, 1)]
    if len(groups) == 1:
        return groups
    return [f"分段 {number}/{len(groups)}\n\n{markup}" for number, markup in enumerate(groups, 1)]


def valid_chat_id(value: object) -> bool:
    return type(value) is int and 0 < value < 2 ** 52


def telegram_request(token: str, method: str, payload: dict) -> tuple[int, object]:
    """POST to Telegram directly. Never propagate raw bodies, URLs or exceptions."""
    if not TOKEN_PATTERN.fullmatch(token) or method not in {"getChat", "sendMessage", "getUpdates"}:
        raise DeliveryError("invalid_telegram_request")
    connection = http.client.HTTPSConnection("api.telegram.org", timeout=8)
    try:
        connection.request(
            "POST", f"/bot{token}/{method}", json.dumps(payload).encode("utf-8"),
            {"Content-Type": "application/json", "Accept-Encoding": "identity",
             "User-Agent": "GlobalTrendRadar/1.0"},
        )
        with connection.getresponse() as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                return response.status, None
            return response.status, json.loads(body)
    except (OSError, http.client.HTTPException, ValueError, RecursionError):
        return 0, None
    finally:
        connection.close()


@dataclass(frozen=True, slots=True)
class _Result:
    state: str
    failure_code: str | None = None
    message_id: int | None = None
    retry_after: int | None = None


def _retry_result(status: int, body: object) -> _Result | None:
    if status != 429 or not isinstance(body, dict) or body.get("ok") is not False or body.get("error_code") != 429:
        return None
    parameters = body.get("parameters")
    delay = parameters.get("retry_after") if isinstance(parameters, dict) else None
    if type(delay) is not int or not 0 < delay < 2 ** 31:
        delay = DEFAULT_RETRY_AFTER
    return _Result("RATE_LIMITED", "telegram_429", retry_after=delay)


class TelegramClient:
    def __init__(self, token: str, chat_id: str, *, request: TelegramRequest = telegram_request):
        if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
            raise DeliveryError("invalid_telegram_token")
        if not isinstance(chat_id, str) or not re.fullmatch(r"[1-9][0-9]{0,15}", chat_id):
            raise DeliveryError("invalid_private_chat_id")
        self._chat_id = int(chat_id)
        if not valid_chat_id(self._chat_id):
            raise DeliveryError("invalid_private_chat_id")
        self._token = token
        self._request = request
        self._verified = False
        self.destination_fingerprint = hmac.digest(
            token.encode("ascii"), f"radar-telegram-private:{chat_id}".encode("ascii"), "sha256",
        ).hex()

    def _call(self, method: str, payload: dict):
        try:
            return self._request(self._token, method, payload)
        except (OSError, http.client.HTTPException, ValueError, RecursionError):
            return 0, None

    def _is_private_chat(self, chat: object) -> bool:
        return (isinstance(chat, dict) and chat.get("type") == "private"
                and valid_chat_id(chat.get("id")) and chat["id"] == self._chat_id)

    def verify_private_chat(self) -> _Result:
        if self._verified:
            return _Result("READY")
        status, body = self._call("getChat", {"chat_id": self._chat_id})
        limited = _retry_result(status, body)
        if limited:
            return limited
        if status == 200 and isinstance(body, dict) and body.get("ok") is True:
            if self._is_private_chat(body.get("result")):
                self._verified = True
                return _Result("READY")
            return _Result("REJECTED", "telegram_destination_mismatch")
        code = f"telegram_{status}" if status in REJECTION_CODES else "telegram_preflight_failed"
        return _Result("REJECTED", code)

    def send(self, markup: str) -> _Result:
        _message_text(markup)
        verified = self.verify_private_chat()
        if verified.state != "READY":
            return verified
        status, body = self._call("sendMessage", {
            "chat_id": self._chat_id,
            "text": markup,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
            "allow_paid_broadcast": False,
        })
        limited = _retry_result(status, body)
        if limited:
            return limited
        if isinstance(body, dict):
            if status == 200 and body.get("ok") is True:
                result = body.get("result")
                if isinstance(result, dict) and self._is_private_chat(result.get("chat")):
                    message_id = result.get("message_id")
                    if type(message_id) is int and message_id > 0:
                        return _Result("SENT", message_id=message_id)
            if status in REJECTION_CODES and body.get("ok") is False and body.get("error_code") == status:
                return _Result("REJECTED", f"telegram_{status}")
        # A response might have been lost after Telegram accepted the message.
        return _Result("UNKNOWN", "telegram_outcome_unconfirmed")


def _payload_hash(markup: str) -> str:
    return hashlib.sha256(markup.encode("utf-8")).hexdigest()


def _check_report_id(report_id: str) -> None:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,95}", report_id):
        raise DeliveryError("invalid_report_id")


def _new_ledger(report_id: str, hashes: list[str], fingerprint: str, now: float) -> dict:
    return {
        "version": 1,
        "report_id": report_id,
        "destination_fingerprint": fingerprint,
        "parts": [
            {"part_no": number, "payload_hash": digest, "delivery_state": "PENDING",
             "message_id": None, "attempts": 0, "retry_at": None, "failure_code": None,
             "updated_at": now}
            for number, digest in enumerate(hashes, 1)
        ],
    }


def _finite_timestamp(value: object) -> bool:
    return type(value) in {int, float} and 0 <= value <= 10 ** 15 and math.isfinite(value)


def _validate_ledger(ledger: dict, report_id: str) -> list[dict]:
    if not isinstance(ledger, dict) or ledger.get("version") != 1 or ledger.get("report_id") != report_id:
        raise DeliveryError("invalid_delivery_ledger")
    rows = ledger.get("parts")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_PARTS:
        raise DeliveryError("invalid_delivery_ledger")
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict) or row.get("part_no") != number:
            raise DeliveryError("invalid_delivery_ledger")
        digest = row.get("payload_hash")
        state = row.get("delivery_state")
        attempts = row.get("attempts")
        message_id = row.get("message_id")
        retry_at = row.get("retry_at")
        if (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not isinstance(state, str) or state not in DELIVERY_STATES
            or type(attempts) is not int or attempts < 0
            or not _finite_timestamp(row.get("updated_at"))
            or (message_id is not None and (type(message_id) is not int or message_id <= 0))
            or (state == "SENT" and message_id is None)
            or (state not in {"SENT", "CONFIRMED"} and message_id is not None)
            or (state == "RATE_LIMITED" and not _finite_timestamp(retry_at))
            or (state != "RATE_LIMITED" and retry_at is not None)):
            raise DeliveryError("invalid_delivery_ledger")
    return rows


def _update_row(row: dict, state: str, now: float, *, message_id: int | None = None,
                failure_code: str | None = None, retry_at: float | None = None):
    row.update(delivery_state=state, updated_at=now, message_id=message_id,
               failure_code=failure_code, retry_at=retry_at)


def send_parts(
    report_id: str,
    parts: Sequence[str],
    telegram: TelegramClient,
    load: LedgerLoad,
    save: LedgerSave,
    *,
    retry_rate_limit: bool = True,
    now: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Deliver frozen parts under the caller's exclusive write lock.

    Save must durably publish the full ledger before returning. A successful
    API response is the only path to SENT. A lost response or SENDING left by
    an interrupted process blocks automatic resend and later parts.
    """
    _check_report_id(report_id)
    if not 1 <= len(parts) <= MAX_PARTS:
        raise DeliveryError("invalid_message_part_count")
    for part in parts:
        _message_text(part)
    hashes = [_payload_hash(part) for part in parts]
    fingerprint = telegram.destination_fingerprint
    previous = load(report_id)
    ledger = previous if previous is not None else _new_ledger(report_id, hashes, fingerprint, now())
    rows = _validate_ledger(ledger, report_id)
    if ledger.get("destination_fingerprint") != fingerprint:
        raise DeliveryError("delivery_destination_changed")
    if [row["payload_hash"] for row in rows] != hashes:
        raise DeliveryError("delivery_payload_changed")

    interrupted = [row for row in rows if row["delivery_state"] == "SENDING"]
    if interrupted:
        for row in interrupted:
            _update_row(row, "UNKNOWN", now(), failure_code="interrupted_send")
        save(report_id, ledger)
    if any(row["delivery_state"] == "UNKNOWN" for row in rows):
        return "UNKNOWN"

    last_sent = None
    inline_retry_used = False
    for markup, row in zip(parts, rows, strict=True):
        if row["delivery_state"] in {"SENT", "CONFIRMED"}:
            if row["delivery_state"] == "SENT":
                last_sent = row["updated_at"]
            continue
        if row["delivery_state"] == "RATE_LIMITED" and row["retry_at"] > now():
            return "RATE_LIMITED"
        if last_sent is not None:
            delay = min(MIN_CHAT_GAP, last_sent + MIN_CHAT_GAP - now())
            if delay > 0:
                sleep(delay)

        while True:
            result = telegram.verify_private_chat()
            if result.state == "READY":
                _update_row(row, "SENDING", now())
                row["attempts"] += 1
                save(report_id, ledger)
                result = telegram.send(markup)

            timestamp = now()
            delay = result.retry_after
            _update_row(
                row, result.state, timestamp, message_id=result.message_id,
                failure_code=result.failure_code,
                retry_at=timestamp + delay if delay is not None else None,
            )
            # A failed first preflight sends nothing. Retain no binding to malformed
            # credentials that an Owner may need to fix before the first message.
            if previous is not None or row["attempts"] or result.state == "RATE_LIMITED":
                save(report_id, ledger)
                previous = ledger
            if result.state == "SENT":
                last_sent = timestamp
                break
            if (result.state != "RATE_LIMITED" or not retry_rate_limit
                    or inline_retry_used or delay > INLINE_RETRY_LIMIT):
                return result.state
            inline_retry_used = True
            sleep(delay)
            if now() < row["retry_at"]:
                return "RATE_LIMITED"

    return "CONFIRMED" if any(row["delivery_state"] == "CONFIRMED" for row in rows) else "SENT"


def reconcile_delivery(
    report_id: str,
    part_no: int,
    payload_hash: str,
    load: LedgerLoad,
    save: LedgerSave,
    *,
    confirmed_sent: bool = False,
    confirmed_unsent: bool = False,
    message_id: int | None = None,
    now: Callable[[], float] = time.time,
) -> None:
    """Resolve a specific UNKNOWN/SENDING after an Owner verifies the chat."""
    _check_report_id(report_id)
    if confirmed_sent == confirmed_unsent or (message_id is not None and (
        not confirmed_sent or type(message_id) is not int or message_id <= 0
    )):
        raise DeliveryError("invalid_delivery_confirmation")
    ledger = load(report_id)
    rows = _validate_ledger(ledger, report_id)
    if type(part_no) is not int or not 1 <= part_no <= len(rows):
        raise DeliveryError("invalid_delivery_part")
    row = rows[part_no - 1]
    if row["payload_hash"] != payload_hash or row["delivery_state"] not in {"UNKNOWN", "SENDING"}:
        raise DeliveryError("delivery_confirmation_mismatch")
    state = "CONFIRMED" if confirmed_sent else "PENDING"
    _update_row(row, state, now(), message_id=message_id)
    row["owner_confirmation"] = "received" if confirmed_sent else "not_received"
    row["owner_confirmed_at"] = row["updated_at"]
    save(report_id, ledger)
