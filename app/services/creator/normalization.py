import re
import unicodedata


def normalize_title(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value).strip()).casefold()


def normalize_tag(value: str) -> str:
    return normalize_title(value)[:30]
