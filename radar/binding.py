"""Pair a dedicated Telegram bot with a manually confirmed private chat."""

from hashlib import sha256
import hmac
import math
import re
from secrets import token_hex
import time

from .delivery import (
    DeliveryError, TOKEN_PATTERN, TelegramClient, send_parts, split_parts, telegram_request, valid_chat_id,
)
from .storage import json_bytes, read_json


BINDING_KEY = "deliveries/telegram-binding.json"
MAX_UPDATES = 100
START_MAX_AGE = 15 * 60
BINDING_MAX_AGE = 30 * 60
ACKNOWLEDGEMENT = (
    "Global Trend Radar 绑定确认。请确认这是您自己创建的新 Bot 私聊，"
    "然后在本项目 GitHub Actions 选择 confirm_bind。"
)


def _bot_fingerprint(token):
    if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
        raise DeliveryError("invalid_telegram_token")
    # The numeric account prefix stays the same when BotFather rotates this bot's token.
    bot_id = token.partition(":")[0]
    return sha256(f"radar-telegram-binding:{bot_id}".encode("ascii")).hexdigest()


def _binding(store, fingerprint):
    value = read_json(store, BINDING_KEY)
    if value is None:
        return None
    if (
        not isinstance(value, dict)
        or value.get("version") != 1
        or value.get("state") not in ("PENDING", "ACTIVE")
        or not valid_chat_id(value.get("chat_id"))
        or not isinstance(value.get("ack_id"), str)
        or re.fullmatch(r"bind-[0-9a-f]{24}", value["ack_id"]) is None
        or type(value.get("opened_at")) is not int
        or value["opened_at"] < 0
        or (value["state"] == "ACTIVE" and (
            type(value.get("confirmed_at")) is not int
            or not value["opened_at"] <= value["confirmed_at"] < value["opened_at"] + BINDING_MAX_AGE
        ))
    ):
        raise DeliveryError("binding_state_invalid")
    saved_fingerprint = value.get("bot_fingerprint")
    if not isinstance(saved_fingerprint, str) or not hmac.compare_digest(saved_fingerprint, fingerprint):
        raise DeliveryError("binding_bot_changed")
    return value


def _candidate_ids(updates, oldest, newest):
    if not isinstance(updates, list):
        raise DeliveryError("binding_updates_unavailable")
    if len(updates) >= MAX_UPDATES:
        # A full page can conceal another candidate. Never acknowledge or drain it.
        raise DeliveryError("binding_updates_incomplete")
    ids = set()
    for update in updates:
        message = update.get("message") if isinstance(update, dict) else None
        if not isinstance(message, dict) or message.get("text") != "/start":
            continue
        stamp = message.get("date")
        if (type(stamp) is not int or not oldest <= stamp <= newest
                or "forward_origin" in message or "sender_chat" in message):
            continue
        chat, sender = message.get("chat"), message.get("from")
        if not isinstance(chat, dict) or not isinstance(sender, dict):
            continue
        chat_id = chat.get("id")
        if (chat.get("type") == "private" and valid_chat_id(chat_id)
                and valid_chat_id(sender.get("id")) and sender["id"] == chat_id
                and sender.get("is_bot") is False):
            ids.add(chat_id)
    return ids


def _ack_for(value):
    return split_parts([(ACKNOWLEDGEMENT, ACKNOWLEDGEMENT)], label=value["ack_id"])


def _save_binding(store, value):
    store.publish({BINDING_KEY: json_bytes(value)}, "Record private Telegram binding")


def _ack_key(report_id):
    return f"deliveries/{report_id}.json"


def bind_chat(store, token, *, request=telegram_request, now=time.time, sleep=time.sleep):
    """Freeze the unique candidate before sending one generic acknowledgement."""
    fingerprint = _bot_fingerprint(token)
    existing = _binding(store, fingerprint)
    if existing and existing["state"] == "ACTIVE":
        return "ALREADY_BOUND"
    started = int(now())
    if existing and started < existing["opened_at"] + BINDING_MAX_AGE:
        binding = existing
    else:
        status, body = request(token, "getUpdates", {
            "timeout": 0, "limit": MAX_UPDATES, "allowed_updates": ["message"],
        })
        if status != 200 or not isinstance(body, dict) or body.get("ok") is not True:
            raise DeliveryError("binding_updates_unavailable")
        oldest = max(started - START_MAX_AGE, existing["opened_at"] + BINDING_MAX_AGE if existing else 0)
        ids = _candidate_ids(body.get("result"), oldest, started + 5)
        if len(ids) != 1:
            raise DeliveryError("binding_ambiguous_start" if ids else "binding_private_start_required")
        binding = {"version": 1, "state": "PENDING", "bot_fingerprint": fingerprint,
                   "chat_id": ids.pop(), "ack_id": f"bind-{token_hex(12)}", "opened_at": started}
        _save_binding(store, binding)

    client = TelegramClient(token, str(binding["chat_id"]), request=request)
    result = send_parts(
        binding["ack_id"], _ack_for(binding), client,
        lambda report_id: read_json(store, _ack_key(report_id)),
        lambda report_id, ledger: store.publish(
            {_ack_key(report_id): json_bytes(ledger)}, "Record private Telegram binding acknowledgement",
        ),
        now=now,
        sleep=sleep,
    )
    return "ACK_SENT" if result == "SENT" else result


def confirm_bind(store, token, *, requested_at, now=time.time):
    """Activate only the acknowledged candidate the Owner chose to confirm."""
    fingerprint = _bot_fingerprint(token)
    binding = _binding(store, fingerprint)
    if not binding:
        raise DeliveryError("binding_not_requested")
    if binding["state"] == "ACTIVE":
        return "ALREADY_BOUND"
    completed = int(now())
    if completed >= binding["opened_at"] + BINDING_MAX_AGE:
        raise DeliveryError("binding_confirmation_expired")

    ack = read_json(store, _ack_key(binding["ack_id"]))
    client = TelegramClient(token, str(binding["chat_id"]))
    payload_hash = sha256(_ack_for(binding)[0].encode("utf-8")).hexdigest()
    parts = ack.get("parts") if isinstance(ack, dict) else None
    part = parts[0] if isinstance(parts, list) and len(parts) == 1 else None
    if (not isinstance(part, dict) or ack.get("report_id") != binding["ack_id"]
            or ack.get("destination_fingerprint") != client.destination_fingerprint
            or part.get("payload_hash") != payload_hash or part.get("part_no") != 1
            or part.get("delivery_state") != "SENT" or type(part.get("message_id")) is not int
            or part["message_id"] <= 0 or type(part.get("updated_at")) not in (int, float)
            or not math.isfinite(part["updated_at"])
            or type(requested_at) not in (int, float) or not math.isfinite(requested_at)
            or not binding["opened_at"] <= part["updated_at"] <= requested_at <= completed + 1):
        raise DeliveryError("binding_ack_unconfirmed")
    _save_binding(store, {**binding, "state": "ACTIVE", "confirmed_at": completed})
    return "BOUND"


def bound_chat_id(store, token):
    binding = _binding(store, _bot_fingerprint(token))
    if binding and binding["state"] == "ACTIVE":
        return str(binding["chat_id"])
    return None
