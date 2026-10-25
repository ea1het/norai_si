"""Storage of the agent's private keys, in the keys/ folder of its home (see norai_home.py).

Each key lives in one JSON file (<home>/keys/<name>-ed25519.key.json) that holds:
  - the public key as a JWK, in clear, so its kid can be read without a passphrase;
  - the 32-byte Ed25519 private key, encrypted with a passphrase:
      key        = scrypt(passphrase, salt, N=2^17, r=8, p=1)     (RFC 7914)
      ciphertext = AES-256-GCM(key, nonce, private, aad=kid)       (NIST SP 800-38D)

Why not encrypted PKCS#8 PEM: the cryptography library writes it with PBKDF2 at
2048 iterations, which is cheap to brute-force. scrypt costs ~128 MB of memory per
guess. The format is plain JSON and works the same on macOS, Linux and Windows.
"""
import getpass
import json
import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from norai_crypto import b64u, b64u_decode, public_jwk

NAMES = ("identity", "http")
FORMAT = "norai-key/1"
PASSPHRASE_ENV = "AGENT_ID_PASSPHRASE"
DEMO_PASSPHRASE = b"demo passphrase, not a secret"
MIN_PASSPHRASE = 12
SCRYPT = {"n": 2 ** 17, "r": 8, "p": 1}


class KeyStoreError(Exception):
    pass


def key_path(name: str, folder: Path) -> Path:
    return folder / f"{name}-ed25519.key.json"


def restrict(path: Path, mode: int):
    """chmod 600/700 on macOS and Linux. On Windows chmod only toggles read-only,
    so the protection there is the encryption plus the user's profile ACLs."""
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def ask_passphrase(confirm: bool = False) -> bytes:
    pw = os.environ.get(PASSPHRASE_ENV)
    interactive = not pw
    if interactive:
        pw = getpass.getpass("Key passphrase: ")
    if confirm:
        if len(pw) < MIN_PASSPHRASE:
            raise KeyStoreError(f"use at least {MIN_PASSPHRASE} characters")
        if interactive and getpass.getpass("Repeat it: ") != pw:
            raise KeyStoreError("the passphrases do not match")
    return pw.encode("utf-8")


def _kdf(salt: bytes, params: dict) -> Scrypt:
    return Scrypt(salt=salt, length=32, n=params["n"], r=params["r"], p=params["p"])


def save(key: Ed25519PrivateKey, path: Path, passphrase: bytes):
    jwk = public_jwk(key.public_key())
    salt, nonce = os.urandom(16), os.urandom(12)
    raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                            serialization.NoEncryption())
    ciphertext = AESGCM(_kdf(salt, SCRYPT).derive(passphrase)).encrypt(nonce, raw, jwk["kid"].encode("ascii"))
    doc = {"format": FORMAT, "public_jwk": jwk,
           "kdf": {"name": "scrypt", **SCRYPT, "salt": b64u(salt)},
           "cipher": {"name": "AES-256-GCM", "nonce": b64u(nonce), "ciphertext": b64u(ciphertext)}}
    path.parent.mkdir(parents=True, exist_ok=True)
    restrict(path.parent, 0o700)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    restrict(path, 0o600)


def read_public(path: Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("format") != FORMAT:
        raise KeyStoreError(f"{path.name}: unknown key format")
    return doc["public_jwk"]


def load(path: Path, passphrase: bytes) -> Ed25519PrivateKey:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("format") != FORMAT:
        raise KeyStoreError(f"{path.name}: unknown key format")
    kdf, c, kid = doc["kdf"], doc["cipher"], doc["public_jwk"]["kid"]
    try:
        raw = AESGCM(_kdf(b64u_decode(kdf["salt"]), kdf).derive(passphrase)).decrypt(
            b64u_decode(c["nonce"]), b64u_decode(c["ciphertext"]), kid.encode("ascii"))
    except InvalidTag:
        raise KeyStoreError(f"{path.name}: wrong passphrase or damaged file") from None
    key = Ed25519PrivateKey.from_private_bytes(raw)
    if public_jwk(key.public_key())["kid"] != kid:
        raise KeyStoreError(f"{path.name}: the private key does not match its public key")
    return key


def missing(folder: Path) -> list:
    return [key_path(n, folder) for n in NAMES if not key_path(n, folder).exists()]


def load_all(folder: Path, passphrase: bytes = None) -> dict:
    if missing(folder):
        raise KeyStoreError("the agent has no keys yet. Run: python3 build/src/agentid.py setup")
    passphrase = passphrase or ask_passphrase()
    return {n: load(key_path(n, folder), passphrase) for n in NAMES}


def create_all(folder: Path, passphrase: bytes):
    for n in NAMES:
        save(Ed25519PrivateKey.generate(), key_path(n, folder), passphrase)


def load_or_create_demo(folder: Path) -> dict:
    if missing(folder):
        create_all(folder, DEMO_PASSPHRASE)
    return load_all(folder, DEMO_PASSPHRASE)
