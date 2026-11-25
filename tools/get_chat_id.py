"""Read a new dedicated bot's private Chat ID locally after Owner approval."""

from getpass import GetPassWarning, getpass
from secrets import token_hex
import sys
import warnings

from radar.delivery import TOKEN_PATTERN, telegram_request, valid_chat_id


def private_probe_ids(updates: object, probe: str) -> set[int]:
    ids = set()
    if not isinstance(updates, list):
        return ids
    for update in updates:
        message = update.get("message") if isinstance(update, dict) else None
        if not isinstance(message, dict) or message.get("text") != probe:
            continue
        chat = message.get("chat")
        sender = message.get("from")
        if not isinstance(chat, dict) or not isinstance(sender, dict):
            continue
        chat_id = chat.get("id")
        if (chat.get("type") == "private" and valid_chat_id(chat_id)
            and valid_chat_id(sender.get("id")) and sender["id"] == chat_id
            and sender.get("is_bot") is False):
            ids.add(chat_id)
    return ids


def main() -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty() or not sys.stderr.isatty():
        print("Open an interactive private terminal to run this helper.", file=sys.stderr)
        return 1
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            token = getpass("Token from BotFather for this project's new bot (hidden): ").strip()
        if not TOKEN_PATTERN.fullmatch(token):
            print("Token format is invalid.", file=sys.stderr)
            return 1

        probe = f"GTR-PROBE-{token_hex(12)}"
        print("Open your private chat with the new bot and send /start, then send this as a separate message:")
        print(probe)
        input("Press Enter after sending the probe. ")
        status, response = telegram_request(token, "getUpdates", {
            "timeout": 0, "limit": 100, "allowed_updates": ["message"],
        })
        if status != 200 or not isinstance(response, dict) or response.get("ok") is not True:
            print("Telegram did not return updates. Check the dedicated bot and network.", file=sys.stderr)
            return 1
        ids = private_probe_ids(response.get("result"), probe)
        if len(ids) != 1:
            print("No unique private chat matched the probe. Verify the message and try again.", file=sys.stderr)
            return 1
        print(f"TELEGRAM_CHAT_ID for your GitHub Secret: {ids.pop()}")
        return 0
    except (EOFError, KeyboardInterrupt, GetPassWarning):
        print("Chat ID setup stopped.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
