import re
import unicodedata


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s: str) -> str:
    """Minuscules, sans accents, tout ce qui n'est ni lettre ni chiffre devient une espace."""
    return re.sub(r"[^a-z0-9]+", " ", strip_accents(str(s)).lower()).strip()
