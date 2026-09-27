import hashlib
import re
from difflib import SequenceMatcher


BOILERPLATE = re.compile(r"\b(posting here too|sharing here too|cross[- ]?posting|please share|shared to another group|boosting this post)\b", re.I)
URLS = re.compile(r"https?://\S+", re.I)


def normalize_post_text(text: str) -> str:
    value = URLS.sub(" ", text or "").lower()
    value = BOILERPLATE.sub(" ", value)
    value = re.sub(r"[^\w\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def text_fingerprint(text: str) -> tuple[str, str]:
    normalized = normalize_post_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest(), normalized


def likely_crosspost(existing_text: str, incoming_text: str) -> bool:
    a, b = normalize_post_text(existing_text), normalize_post_text(incoming_text)
    if len(a) < 35 or len(b) < 35:
        return False
    return SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.86
