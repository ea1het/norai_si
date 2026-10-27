"""The operator's declaration: the one document a human reads and signs.

The agent writes it; the operator reads it, signs it with their OpenPGP key and sends the
signature back. The top part states, in plain language, what the website says about the
agent. The technical annex binds that text to the exact published files:

  site-manifest-sha256          SHA-256 of manifest.json, which lists the SHA-256 of every file
  previous-declaration-sha256   SHA-256 of the previous declaration, so they form a chain

Both a clearsigned text and a detached signature (armored .asc or binary .sig) are accepted.
"""
import base64
import hashlib
import re
import tempfile
from pathlib import Path

from .home import gpg

ANNEX_RULE = "──────────────"
CLEARSIGN_HEADER = "-----BEGIN PGP SIGNED MESSAGE-----"
ANNEX_LINE = re.compile(r"^([a-z0-9-]+): (.+)$")

MONTHS = {
    "en": "January February March April May June July August September October November December".split(),
    "es": "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(),
}
LABELS = {
    "en": {
        "title": "OPERATOR DECLARATION · {name} · no. {n} · {date}",
        "intro": "I, {operator}, am the person responsible for the AI agent {name}.\n"
                 "I declare that the information published at {url} is correct:",
        "what": "What it is", "email": "Email", "for": "On whose behalf", "tech": "Technology", "models": "Models",
        "never": "It never", "asks": "It asks first", "valid": "Valid until",
        "tech_line": "{arch}: ~{local}% local models, ~{frontier}% cloud ({providers})",
        "ai": "an artificial intelligence system, not a person",
        "changes": "Changes since declaration no. {prev}:", "first": "This is the first declaration.",
        "annex": "Technical annex (checked by machines)", "none": "none",
    },
    "es": {
        "title": "DECLARACIÓN DEL OPERADOR · {name} · nº {n} · {date}",
        "intro": "Yo, {operator}, soy la persona responsable del agente de IA {name}.\n"
                 "Declaro que la información publicada en {url} es correcta:",
        "what": "Qué es", "email": "Correo", "for": "En nombre de", "tech": "Tecnología", "models": "Modelos",
        "never": "Nunca", "asks": "Pide permiso", "valid": "Válida hasta",
        "tech_line": "{arch}: ~{local} % modelos locales, ~{frontier} % en la nube ({providers})",
        "ai": "un sistema de inteligencia artificial, no una persona",
        "changes": "Cambios desde la declaración nº {prev}:", "first": "Es la primera declaración.",
        "annex": "Anexo técnico (lo comprueban las máquinas)", "none": "ninguna",
    },
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize(text: str) -> str:
    """The form both sides compare: LF line endings, no trailing spaces, one final newline.
    OpenPGP clearsigning drops trailing spaces, so the comparison must ignore them."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip("\n") + "\n"


def text_hash(text: str) -> str:
    return sha256(normalize(text).encode("utf-8"))


def long_date(iso: str, lang: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    month = MONTHS[lang][m - 1]
    return f"{d} de {month} de {y}" if lang == "es" else f"{d} {month} {y}"


def render(src: dict, *, number: int, issued: str, expires: str, kids: dict, fingerprints: dict,
           manifest_sha: str, previous_sha: str, changes: list) -> str:
    lang = src["operator"].get("language", "en")
    if lang not in LABELS:
        lang = "en"
    t = LABELS[lang]
    ag, op, rt, acc = src["agent"], src["operator"], src["runtime"], src["accountability"]
    providers = sorted({p for m in src["models"] for p in m.get("provider", [])})
    width = max(len(t[k]) for k in ("what", "email", "for", "tech", "models", "never", "asks", "valid")) + 2

    def field(label, value):
        return f"  {(t[label] + ':').ljust(width)} {value}"

    def bullets(label, items):
        pad = " " * (width + 3)
        return [field(label, f"- {items[0]}")] + [f"{pad}- {x}" for x in items[1:]]

    lines = [t["title"].format(name=ag["name"], n=number, date=long_date(issued, lang)), "",
             t["intro"].format(operator=op["display_name"], name=ag["name"], url=src["base_url"].rstrip("/") + "/"), "",
             field("what", f"{ag['kind']}: {t['ai']}."),
             *([field("email", ag["email"])] if ag.get("email") else []),
             field("for", acc["acts_on_behalf_of"]),
             field("tech", t["tech_line"].format(arch=rt["architecture"], local=rt["target_mix"]["local_percent"],
                                                 frontier=rt["target_mix"]["frontier_percent"],
                                                 providers=", ".join(providers) or "-"))]
    lines += bullets("models", [f"{m['role']} — {m['id']} ({m['location']})" for m in src["models"]])
    lines += bullets("never", acc["will_not"])
    lines += bullets("asks", acc["requires_human_confirmation_for"])
    lines += [field("valid", expires), ""]
    if number == 1:
        lines.append(t["first"])
    else:
        lines.append(t["changes"].format(prev=number - 1))
        lines += [f"  - {c}" for c in changes]
    lines += ["", f"{ANNEX_RULE} {t['annex']} {ANNEX_RULE}",
              f"agent: {ag['name']}",
              f"domain: {src['domain']}",
              f"declaration: {number}",
              f"issued: {issued}",
              f"expires: {expires}",
              f"identity-key: {kids['identity']}",
              f"identity-key-fingerprint: {fingerprints['identity']}",
              f"http-key: {kids['http']}",
              f"http-key-fingerprint: {fingerprints['http']}",
              f"site-manifest-sha256: {manifest_sha}",
              f"previous-declaration-sha256: {previous_sha or 'none'}"]
    return normalize("\n".join(lines))


def annex(text: str) -> dict:
    after = normalize(text).split(ANNEX_RULE, 2)[-1]
    return {m.group(1): m.group(2).strip() for m in map(ANNEX_LINE.match, after.splitlines()) if m}


def armor_signature(binary: bytes) -> str:
    """ASCII armor (RFC 9580 §6) for a binary detached signature (.sig)."""
    crc = 0xB704CE
    for byte in binary:
        crc ^= byte << 16
        for _ in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= 0x1864CFB
    body = base64.b64encode(binary).decode("ascii")
    lines = [body[i:i + 64] for i in range(0, len(body), 64)]
    checksum = base64.b64encode((crc & 0xFFFFFF).to_bytes(3, "big")).decode("ascii")
    return "-----BEGIN PGP SIGNATURE-----\n\n" + "\n".join(lines) + f"\n={checksum}\n-----END PGP SIGNATURE-----\n"


def verify(signature: bytes, text_file: Path, operator_key: bytes) -> tuple:
    """Checks an operator signature over a declaration.

    Returns (primary_fingerprint, signed_text, armored_signature). Raises ValueError if the
    signature is not valid, was not made by operator_key, or covers a different text."""
    sig_text = signature.decode("utf-8", "replace").lstrip("﻿")
    clearsigned = sig_text.lstrip().startswith(CLEARSIGN_HEADER)
    with tempfile.TemporaryDirectory() as tmp:
        gpg(["--import"], tmp, input=operator_key)
        sig_path = Path(tmp) / "signature"
        sig_path.write_bytes(signature)
        if clearsigned:
            plain = Path(tmp) / "plain.txt"
            out = gpg(["--status-fd", "1", "--output", str(plain), "--decrypt", str(sig_path)], tmp, check=False)
            signed_text = plain.read_text(encoding="utf-8") if plain.exists() else ""
        else:
            out = gpg(["--status-fd", "1", "--verify", str(sig_path), str(text_file)], tmp, check=False)
            signed_text = text_file.read_text(encoding="utf-8")
    valid = [line.split() for line in out.stdout.decode().splitlines() if line.startswith("[GNUPG:] VALIDSIG")]
    if not valid:
        raise ValueError("the signature is not valid, or it was not made with the operator's key")
    if normalize(signed_text) != normalize(text_file.read_text(encoding="utf-8")):
        raise ValueError("the signature is valid but covers a different text from this declaration")
    if clearsigned:
        armored = sig_text.strip() + "\n"
    elif sig_text.lstrip().startswith("-----BEGIN PGP SIGNATURE-----"):
        armored = sig_text.strip() + "\n"
    else:
        armored = armor_signature(signature)
    return valid[0][-1].upper(), signed_text, armored
