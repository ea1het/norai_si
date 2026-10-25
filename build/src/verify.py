#!/usr/bin/env python3
"""Verifies an agent's published identity site, or a local site folder. Anyone can run it.

  python3 build/src/verify.py https://norai.si
  python3 build/src/verify.py <site folder>

Exit code 0 only if every required check passes.
"""
import datetime as dt
import json
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from declaration import annex, sha256, text_hash, verify as verify_signature  # noqa: E402
from norai_crypto import verify_document  # noqa: E402
from norai_home import HomeError  # noqa: E402


def fetcher(root: str):
    if root.startswith("https://"):
        base = root.rstrip("/")

        def get(path):
            with urllib.request.urlopen(base + path, timeout=15) as r:
                return r.read()
    else:
        base = Path(root)

        def get(path):
            return (base / path.lstrip("/")).read_bytes()
    return get


def check_declaration(asc: bytes, text: bytes, operator_key: bytes):
    """Verifies one signed declaration. Returns (primary fingerprint, signed text)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "declaration.txt"
        path.write_bytes(text)
        return verify_signature(asc, path, operator_key)[:2]


def verify_site(target: str) -> bool:
    get = fetcher(target)
    ok_all = True

    def report(name, ok, detail="", required=True):
        nonlocal ok_all
        mark = "OK  " if ok else ("FAIL" if required else "WARN")
        print(f"[{mark}] {name}{' — ' + detail if detail else ''}")
        if required and not ok:
            ok_all = False

    raw = get("/norai.json")
    doc = json.loads(raw)
    jwks = json.loads(get("/.well-known/jwks.json"))
    kid = doc["keys"]["identity"]["kid"]
    http_kid = doc["keys"]["http_signing"]["kid"]

    # 1. The agent's own signatures
    for name, d in [("norai.json", doc),
                    ("agent-card.json", json.loads(get("/.well-known/agent-card.json"))),
                    ("revocations.json", json.loads(get("/revocations.json")))]:
        res = verify_document(d, jwks)
        good = bool(res) and all(r[1] for r in res) and all(r[0] == kid for r in res)
        report(f"Agent signature on {name}", good, "; ".join(f"{r[0][:12]}…: {r[2]}" for r in res))

    did = json.loads(get("/.well-known/did.json"))
    did_keys = {m["publicKeyJwk"]["kid"]: m["publicKeyJwk"]["x"] for m in did["verificationMethod"]}
    report("did.json and jwks.json publish the same keys", did_keys == {k["kid"]: k["x"] for k in jwks["keys"]})
    wba = json.loads(get("/.well-known/http-message-signatures-directory"))
    report("Web Bot Auth key matches the credential", [k["kid"] for k in wba["keys"]] == [http_kid])

    today = dt.datetime.now(dt.timezone.utc).date()
    exp = dt.date.fromisoformat(doc["validity"]["expires"])
    report("Validity", exp > today, f"expires {exp}")
    revoked = {r["kid"] for r in json.loads(get("/revocations.json"))["revoked"]}
    report("Agent keys not revoked", kid not in revoked and http_kid not in revoked)

    # 2. Every published file is the one listed in the manifest
    manifest_raw = get("/manifest.json")
    manifest = json.loads(manifest_raw)
    bad = []
    for path, digest in manifest["files"].items():
        try:
            if sha256(get("/" + path)) != digest:
                bad.append(path)
        except (OSError, urllib.error.URLError):
            bad.append(path + " (missing)")
    report("Every file matches manifest.json", not bad and "norai.json" in manifest["files"],
           ", ".join(bad) or f"{len(manifest['files'])} files")

    # 3. The operator's declaration covers this manifest and these keys
    operator_fpr = doc["operator"]["pgp"]["fingerprint"].upper()
    operator_key = get("/pgp/operator.asc")
    try:
        text = get("/declaration.txt")
        fpr, signed = check_declaration(get("/declaration.txt.asc"), text, operator_key)
    except (OSError, urllib.error.URLError):
        report("Operator's signed declaration", False, "declaration.txt(.asc) not found: not signed yet")
        print("\nRESULT: INVALID")
        return False
    except ValueError as e:
        report("Operator's signed declaration", False, str(e))
        print("\nRESULT: INVALID")
        return False
    except HomeError as e:
        report("Operator's signed declaration", False, str(e), required=False)
        print("\nRESULT:", "VALID (without the operator check)" if ok_all else "INVALID")
        return ok_all
    facts = annex(signed)
    report("Declaration signed by the operator named in norai.json", fpr == operator_fpr, fpr)
    report("Declaration covers this manifest", facts.get("site-manifest-sha256") == sha256(manifest_raw))
    report("Declaration names the agent keys in use",
           facts.get("identity-key") == kid and facts.get("http-key") == http_kid)

    # 4. The chain of earlier declarations
    number = int(facts.get("declaration", "0"))
    expected_prev = facts.get("previous-declaration-sha256")
    chain_ok, detail = True, f"{number} declaration(s)"
    for n in range(number - 1, 0, -1):
        try:
            prev_text = get(f"/declarations/{n:04d}.txt")
            pfpr, psigned = check_declaration(get(f"/declarations/{n:04d}.txt.asc"), prev_text, operator_key)
        except (OSError, urllib.error.URLError, ValueError) as e:
            chain_ok, detail = False, f"declaration {n}: {e}"
            break
        if text_hash(psigned) != expected_prev or pfpr != operator_fpr:
            chain_ok, detail = False, f"declaration {n} does not match the hash in declaration {n + 1}"
            break
        expected_prev = annex(psigned).get("previous-declaration-sha256")
    if chain_ok and expected_prev not in (None, "none") and number:
        chain_ok, detail = False, "the first declaration points to an earlier one"
    report("Chain of declarations", chain_ok, detail)

    domain = doc["protocols"]["did"]["id"].split(":")[-1]
    print(f"\nAlso check the DNS anchor by hand: dig TXT _norai-id.{domain} must show pgp={operator_fpr}.")
    print("Before trusting a counterpart, ask for a liveness proof (a fresh challenge signed with its key).")
    print("\nRESULT:", "VALID" if ok_all else "INVALID")
    return ok_all


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(0 if verify_site(sys.argv[1]) else 1)


if __name__ == "__main__":
    main()
