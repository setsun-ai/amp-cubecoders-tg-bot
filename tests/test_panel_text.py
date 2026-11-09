"""Every text the panel shows - its own and the server's error codes - exists in all four bot languages."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
PAGE = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
SERVER = (ROOT / "miniapp.py").read_text(encoding="utf-8")
LANGS = 4  # pl, en, ru, uk - the order of bot.LANG_ORDER


def strings():
    block = re.search(r"const STRINGS = (\{.*?\n\});", APP, re.S)
    assert block, "app.js keeps its texts in one JSON block: const STRINGS = {...};"
    return json.loads(block.group(1))


def test_every_text_has_all_four_languages():
    for key, texts in strings().items():
        assert isinstance(texts, list) and len(texts) == LANGS and all(x.strip() for x in texts), key


def test_every_text_the_page_asks_for_exists():
    used = set(re.findall(r"\bt\('([a-z0-9_]+)'", APP)) | set(re.findall(r'data-t="([a-z0-9_]+)"', PAGE))
    assert used and not used - set(strings())


def test_every_server_error_is_a_code_the_page_can_translate():
    codes = set(re.findall(r'APIError\(\d+, "([^"]*)"\)', SERVER)) | set(re.findall(r'\{"error": "([^"]*)"\}', SERVER))
    assert codes
    assert all(re.fullmatch(r"[a-z_]+", c) for c in codes), sorted(c for c in codes if not re.fullmatch(r"[a-z_]+", c))
    assert not {f"err_{c}" for c in codes} - set(strings())


def test_no_polish_text_is_left_outside_the_translations():
    code = re.sub(r"const STRINGS = \{.*?\n\};", "", APP, flags=re.S)
    assert not re.findall(r"[^\n]*[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ][^\n]*", code)
