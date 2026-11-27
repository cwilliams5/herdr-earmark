"""Text helpers shared by the popup and the placeholder (no curses here, so
the placeholder doesn't load it)."""
import re
import time
import unicodedata

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def clean(text):
    """Text safe to draw: control characters (tabs, newlines, backspaces,
    escapes that came in through a title or a name) become spaces."""
    return _CONTROL.sub(" ", str(text or ""))


def char_cols(ch):
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def cols(text):
    """How many terminal columns text takes (wide characters such as CJK and
    most emoji take two)."""
    return sum(char_cols(ch) for ch in text)


def fit(text, width):
    """Text cleaned and cut to width columns, ending in … when anything was cut."""
    text = clean(text)
    if width <= 0:
        return ""
    if cols(text) <= width:
        return text
    used, cut = 0, 0
    for i, ch in enumerate(text):
        if used + char_cols(ch) > width - 1:  # leave a column for …
            break
        used += char_cols(ch)
        cut = i + 1
    return text[:cut].rstrip() + "…"


def wrap_cols(para, width):
    """Words wrapped to `width` terminal columns (wide characters take two);
    a word longer than the width is cut."""
    out, line = [], ""
    for word in para.split():
        while cols(word) > width:
            cut, used = 0, 0
            for i, ch in enumerate(word):
                if used + char_cols(ch) > width:
                    break
                used += char_cols(ch)
                cut = i + 1
            if line:
                out.append(line)
                line = ""
            out.append(word[:cut])
            word = word[cut:]
        candidate = f"{line} {word}" if line else word
        if cols(candidate) <= width:
            line = candidate
        else:
            out.append(line)
            line = word
    if line:
        out.append(line)
    return out


def ago(t, now=None):
    seconds = max(0, (now or time.time()) - (t or 0))
    if seconds < 90:
        return "just now"
    minutes = seconds / 60
    if minutes < 60:
        return f"{int(minutes)} min ago"
    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)} hour{'s' if int(hours) != 1 else ''} ago"
    days = hours / 24
    if days < 2:
        return "yesterday"
    return f"{int(days)} days ago"
