"""Shared Telegram tables and expandable detail blocks."""

from html import escape
import unicodedata

from .delivery import HTML_MAX_BYTES, TELEGRAM_LIMIT, _units
from .scoring import trend_key
from .sources import clean_url


TABLE_LIMIT = 28
APP_WIDTH = 12


def entry_key(title, url=None, *, section=None, artist=None):
    """Canonical topic or work identity, before translation and display truncation."""
    normalized = trend_key(title or "")
    if not normalized:
        return f"link:{link}" if (link := clean_url(url)) else ""
    if section == "music":
        return f"music:{normalized}|{trend_key(artist or '')}"
    if section == "apps":
        return f"apps:{normalized}"
    return f"topic:{normalized}"


def _clean_line(text, *, collapse_space=True):
    text = str(text or "")
    text = " ".join(text.split()) if collapse_space else text.replace("\n", " ").replace("\r", " ")
    return "".join(char for char in text if unicodedata.category(char) not in {"Cc", "Cs", "Cf"}
                   or char in "\u200c\u200d")


def _width(char):
    if unicodedata.category(char) in {"Cc", "Cf", "Mn", "Me"}:
        return 0
    return 2 if unicodedata.east_asian_width(char) in {"W", "F"} or ord(char) >= 0x1F300 else 1


def table_width(text):
    return sum(_width(char) for char in text)


def _truncate(text, limit, width):
    if sum(width(char) for char in text) <= limit:
        return text
    if limit < 1:
        return ""
    size = 0
    for index, char in enumerate(text):
        size += width(char)
        if size >= limit:
            return text[:index].rstrip() + "…"
    return text


def table_row(rank, metric, title, *, metric_width=7, marker=False, app_name=None, suffix=""):
    """Keep all numeric columns before the text, reserving room for suffixes."""
    prefix = f"{rank:>2}  "
    if app_name is not None:
        ascii_name = _clean_line(unicodedata.normalize("NFKD", app_name).encode("ascii", "ignore").decode())
        prefix += f"{(ascii_name or 'App')[:APP_WIDTH]:<{APP_WIDTH}} "
    elif metric is not None:
        value = _truncate(_clean_line(metric), metric_width, _width)
        prefix += " " * (metric_width - table_width(value)) + value + "  "
    end = _truncate(_clean_line(suffix), 10, _width)
    if marker:
        end += " 🆕"
    return prefix + _truncate(_clean_line(title), max(0, TABLE_LIMIT - table_width(prefix + end)), _width) + end


def table_header(metric="", title="话题", *, metric_width=7, app=False):
    if app:
        return " #  NAME         " + _clean_line(title)
    return table_row("#", metric or None, title, metric_width=metric_width)


def table_block(tables):
    """Return an indivisible <pre> block and its visible text."""
    sections = ["\n".join((_truncate(_clean_line(heading), TABLE_LIMIT, _width), header, *rows))
                for heading, header, rows in tables]
    plain = "\n\n".join(sections)
    return f"<pre>{escape(plain)}</pre>", plain


def quote_block(heading, rows, *, row_units=90, preserve_spaces=False):
    """Return an indivisible expandable quote. Links are never part of a table."""
    heading = _clean_line(heading)
    html, plain = [f"<b>{escape(heading, quote=False)}</b>"], [heading]
    for text, url in rows:
        text = _clean_line(text, collapse_space=not preserve_spaces)
        if row_units is not None:
            text = _truncate(text, row_units, _units)
        link = clean_url(url)
        markup = escape(text)
        if link:
            markup += f' <a href="{escape(link, quote=True)}">🔗</a>'
            text += " 🔗"
        html.append(markup)
        plain.append(text)
    return "<blockquote expandable>" + "\n".join(html) + "</blockquote>", "\n".join(plain)


def quote_blocks(heading, rows):
    """Keep link-heavy details within both message limits before packing parts."""
    current = []
    for row in rows:
        markup, plain = quote_block(heading, [*current, row])
        # Reserve space for a part marker even when every possible label character is wide.
        if current and (_units(plain) > TELEGRAM_LIMIT - 180
                        or len(markup.encode("utf-8")) > HTML_MAX_BYTES - 500):
            yield quote_block(heading, current)
            current = []
        current.append(row)
    if current:
        yield quote_block(heading, current)
