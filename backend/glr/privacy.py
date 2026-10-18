"""Data sanitisation: personal data and secrets are redacted before anything leaves the machine.

Applied to everything a researcher types (research idea, chat messages, unpublished hypotheses) before it is stored,
sent to a model on Token Factory, or turned into a scholarly or web search. Only the redacted text is stored; the
original is never persisted (data minimisation, GDPR Art. 5(1)(c) / privacy by design, Art. 25).
Configured API keys are also scrubbed from every log line and error message.
"""

import re
from dataclasses import dataclass, field

from .config import settings

LABELS = {
    "SECRET": "API key or secret",
    "EMAIL": "email address",
    "IBAN": "IBAN",
    "CARD": "payment card number",
    "PHONE": "phone number",
    "IP": "IP address",
    "ADDRESS": "street address",
    "NAME": "personal name",
    "ID": "ID or tax number",
}

SECRET_RES = [
    re.compile(r"\b(?:sk|pk|rk)-(?:live-|test-|proj-)?[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\btvly-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bnvapi-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bxox[abpr]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    re.compile(r"(?i)(?<=bearer )[A-Za-z0-9._\-]{16,}"),
]
# "password: hunter2"-style: keep the label, redact the value (group 2).
LABELLED_SECRET_RE = re.compile(r"(?i)(\b(?:api[_ -]?key|secret|token|password|passwort|passwd|pwd)\s?[:=]\s?)(\S{6,})")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,3})?\b")
CARD_RE = re.compile(r"(?<!\d)(?:\d[ \-]?){12,18}\d(?!\d)")
PHONE_RE = re.compile(r"(?<![\w€$£.,])(?:\+|00)?\(?\d[\d ()./\-]{6,18}\d(?![\w%])")
IP_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
ADDRESS_RE = re.compile(
    r"\b[A-ZÄÖÜ][a-zäöüß\-]+(?:straße|strasse|str\.|weg|allee|platz|gasse|ring|damm|ufer|chaussee)\s+\d{1,4}[a-z]?\b"
    r"|\b\d{1,5}\s+[A-Z][a-z]+(?:\s[A-Z][a-z]+)?\s(?:Street|St\.|Road|Rd\.|Avenue|Ave\.|Lane|Ln\.|Boulevard|Blvd\.)",
)
NAME_RE = re.compile(
    r"(?i:\b(?:my name is|i am|i'm|ich bin|ich heiße|ich heisse|je m'appelle|contact|founder|ceo|co-founder)\s+)"
    r"([A-ZÄÖÜ][a-zäöüß]+(?:\s[A-ZÄÖÜ][a-zäöüß]+){0,2})"
)
ID_RE = re.compile(r"(?i:\b(?:steuer-?id|tax id|ssn|social security(?: number)?|passport(?: number)?|personalausweis|id number))"
                   r"\s*[:#]?\s*([A-Z0-9][A-Z0-9\-]*(?:\s\d[\d\-]*)*)")
# Words NAME_RE must not treat as names ("I am Building", "founder Mode"...).
NOT_NAMES = {"building", "planning", "making", "creating", "working", "looking", "trying", "a", "an", "the", "going",
             "student", "developer", "founder", "startup", "here", "from", "in", "not", "currently", "based"}


@dataclass
class Redaction:
    text: str
    found: dict[str, int] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return sum(self.found.values())

    def summary(self) -> list[dict]:
        return [{"type": k, "label": LABELS[k], "count": v} for k, v in self.found.items()]


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for d in reversed(digits):
        n = int(d)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
        alt = not alt
    return total % 10 == 0


def _iban_ok(s: str) -> bool:
    s = s.replace(" ", "")
    if not 15 <= len(s) <= 34:
        return False
    moved = s[4:] + s[:4]
    num = "".join(str(int(c, 36)) for c in moved)
    return int(num) % 97 == 1


def _phone_ok(s: str) -> bool:
    digits = re.sub(r"\D", "", s)
    if not 8 <= len(digits) <= 15:
        return False
    if re.fullmatch(r"(19|20)\d{2}([ ./\-](19|20)\d{2})*", s.strip()):  # years / year ranges
        return False
    if re.fullmatch(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}", s.strip()):  # dates
        return False
    if re.fullmatch(r"(19|20)\d{2}/\d{1,5}", s.strip()):  # EU act numbers like 2024/1689
        return False
    # Real numbers start with +/00, a 0 trunk prefix, or carry separators; a bare 8-digit run is usually not a phone.
    return s.strip().startswith(("+", "00", "0", "(")) or bool(re.search(r"[ ()./\-]", s))


def redact(text: str) -> Redaction:
    """Replace personal data and secrets with typed placeholders like [EMAIL_1]."""
    if not text:
        return Redaction(text or "")
    found: dict[str, int] = {}
    seen: dict[tuple[str, str], str] = {}

    def sub(kind: str, value: str) -> str:
        key = (kind, value)
        if key not in seen:
            found[kind] = found.get(kind, 0) + 1
            seen[key] = f"[{kind}_{found[kind]}]"
        return seen[key]

    out = scrub_secrets(text, _count=lambda: found.__setitem__("SECRET", found.get("SECRET", 0) + 1))
    for rx in SECRET_RES:
        out = rx.sub(lambda m: sub("SECRET", m.group(0)), out)
    out = LABELLED_SECRET_RE.sub(lambda m: m.group(1) + (m.group(2) if m.group(2).startswith("[") else sub("SECRET", m.group(2))), out)
    out = EMAIL_RE.sub(lambda m: sub("EMAIL", m.group(0)), out)
    out = IBAN_RE.sub(lambda m: sub("IBAN", m.group(0)) if _iban_ok(m.group(0)) else m.group(0), out)
    out = CARD_RE.sub(lambda m: sub("CARD", m.group(0)) if _luhn(re.sub(r"\D", "", m.group(0))) else m.group(0), out)
    out = IP_RE.sub(lambda m: sub("IP", m.group(0)), out)
    out = ID_RE.sub(lambda m: m.group(0).replace(m.group(1), sub("ID", m.group(1)))
                    if len(re.sub(r"\W", "", m.group(1))) >= 6 else m.group(0), out)
    out = PHONE_RE.sub(lambda m: sub("PHONE", m.group(0)) if _phone_ok(m.group(0)) else m.group(0), out)
    out = ADDRESS_RE.sub(lambda m: sub("ADDRESS", m.group(0)), out)

    def name_sub(m: re.Match) -> str:
        name = m.group(1)
        if name.split()[0].lower() in NOT_NAMES:
            return m.group(0)
        return m.group(0).replace(name, sub("NAME", name))

    out = NAME_RE.sub(name_sub, out)
    return Redaction(out, found)


def scrub_secrets(text: str | None, _count=None) -> str:
    """Remove the configured API keys (and anything shaped like a bearer token) from a string."""
    if not text:
        return text or ""
    for key in (settings.nebius_api_key, settings.openrouter_api_key, settings.tavily_api_key,
                settings.openalex_api_key, settings.s2_api_key, settings.hf_token, settings.nvidia_api_key,
                settings.rerank_key):
        if key and len(key) >= 8 and key in text:
            text = text.replace(key, "[SECRET]")
            if _count:
                _count()
    return re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{12,}", r"\1[SECRET]", text)
