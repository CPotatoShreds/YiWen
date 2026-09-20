import re
import unicodedata

from pypinyin import lazy_pinyin


def normalize_title(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value).strip()).casefold()


def slugify_title(value: str) -> str:
    value = "-".join(lazy_pinyin(unicodedata.normalize("NFKC", value).casefold()))
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:80]
