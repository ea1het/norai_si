"""Primitives shared by build.py and verify.py.

Signature scheme (the one A2A v1.0 uses to sign Agent Cards):
  payload    = JCS(document without the "signatures" field)   (RFC 8785)
  protected  = base64url(JSON header {alg, kid, jku, typ})
  signature  = Ed25519( ASCII(protected) + "." + base64url(payload) )   (RFC 7515/8037)
  document["signatures"] = [{"protected": ..., "signature": ...}]
"""
import base64
import hashlib
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def jcs(obj) -> bytes:
    """JSON canonicalisation (RFC 8785) for documents without decimal numbers.

    With ASCII keys, integers and strings, sorting keys by code point and the
    compact json.dumps serialisation match JCS. If decimal numbers are ever
    added, use a full JCS library.
    """
    def check(value):
        if isinstance(value, float):
            raise ValueError("simplified JCS: floats are not supported; use integers or strings")
        if isinstance(value, dict):
            for v in value.values():
                check(v)
        if isinstance(value, list):
            for v in value:
                check(v)
    check(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def raw_public(pub: Ed25519PublicKey) -> bytes:
    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def jwk_thumbprint(x: str) -> str:
    """RFC 7638 / RFC 8037: SHA-256 of {"crv","kty","x"} in lexicographic order."""
    canonical = json.dumps({"crv": "Ed25519", "kty": "OKP", "x": x}, separators=(",", ":"), sort_keys=True)
    return b64u(hashlib.sha256(canonical.encode("ascii")).digest())


def public_jwk(pub: Ed25519PublicKey, use: str = "sig") -> dict:
    x = b64u(raw_public(pub))
    return {"kty": "OKP", "crv": "Ed25519", "x": x, "kid": jwk_thumbprint(x), "use": use, "alg": "EdDSA"}


def human_fingerprint(kid: str) -> str:
    """Short human-readable fingerprint: first 10 bytes of the thumbprint in hex, groups of 4."""
    h = b64u_decode(kid)[:10].hex().upper()
    return " ".join(h[i:i + 4] for i in range(0, len(h), 4))


def sign_document(doc: dict, key: Ed25519PrivateKey, kid: str, jku: str) -> dict:
    body = {k: v for k, v in doc.items() if k != "signatures"}
    header = {"alg": "EdDSA", "kid": kid, "jku": jku, "typ": "JOSE+JSON"}
    protected = b64u(json.dumps(header, separators=(",", ":")).encode("ascii"))
    signing_input = protected.encode("ascii") + b"." + b64u(jcs(body)).encode("ascii")
    signature = b64u(key.sign(signing_input))
    signed = dict(body)
    signed["signatures"] = [{"protected": protected, "signature": signature}]
    return signed


def verify_document(doc: dict, jwks: dict) -> list:
    """Returns a list of (kid, ok, reason) for each signature on the document."""
    results = []
    body = {k: v for k, v in doc.items() if k != "signatures"}
    payload = b64u(jcs(body)).encode("ascii")
    keys = {k["kid"]: k for k in jwks.get("keys", [])}
    for sig in doc.get("signatures", []):
        header = json.loads(b64u_decode(sig["protected"]))
        kid = header.get("kid")
        if header.get("alg") != "EdDSA":
            results.append((kid, False, "algorithm not supported"))
            continue
        jwk = keys.get(kid)
        if jwk is None:
            results.append((kid, False, "kid not published in the JWKS"))
            continue
        if jwk_thumbprint(jwk["x"]) != kid:
            results.append((kid, False, "kid does not match the key thumbprint"))
            continue
        pub = Ed25519PublicKey.from_public_bytes(b64u_decode(jwk["x"]))
        try:
            pub.verify(b64u_decode(sig["signature"]), sig["protected"].encode("ascii") + b"." + payload)
            results.append((kid, True, "valid signature"))
        except Exception:
            results.append((kid, False, "INVALID signature"))
    return results
