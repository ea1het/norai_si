"""Bringing data into the agent's home: a previous publication, or the operator's public key.

  import site URL      rebuilds the home from a site published earlier: identity.json, every signed
                       declaration and the revocation list. It writes only into the home; the operator's
                       key is checked against the DNS but never copied (that is what import gpg is for).
  import gpg           stores the operator's OpenPGP public key, given as text or as a file, in
                       custom_assets/operator/, after checking it against the DNS record.

Both stop unless the DNS record _aid-sysop.<domain> exists and names the operator's key (dns_anchor.py).
"""
import datetime as dt
import json
import shutil
from urllib.parse import urlparse

from . import verify as site_verifier
from . import dns_anchor
from .declaration import annex
from .home import OPERATOR_DIR, HomeError, key_info, operator_key_file
from .keys import NAMES, key_path, read_public

LOST_KEYS_REASON = "Agent keys lost: the agent's data was restored from the published site"


def identity_from_credential(doc: dict, card: dict) -> dict:
    """identity.json as it was when this norai.json was built."""
    operator = {k: v for k, v in doc["operator"].items() if k != "pgp"}
    issued = dt.date.fromisoformat(doc["validity"]["issued"])
    expires = dt.date.fromisoformat(doc["validity"]["expires"])
    a2a = doc["protocols"]["a2a"]
    interface = (card.get("supportedInterfaces") or [{}])[0]
    return {
        "serial": doc["serial"],
        "version": doc["version"],
        "domain": doc["id"].removeprefix("did:web:"),
        "base_url": doc["url"].removesuffix("/norai.json"),
        "valid_days": (expires - issued).days,
        "agent": doc["agent"],
        "operator": operator,
        "accountability": doc["accountability"],
        "runtime": doc["runtime"],
        "models": doc["models"],
        "skills": doc["skills"],
        "a2a": {"status": a2a["status"], "endpoint": a2a["endpoint"],
                "protocol_binding": interface.get("protocolBinding", "JSONRPC"),
                "protocol_version": a2a["protocol_version"]},
    }


def import_site(home, url: str, replace=False, force=False):
    if not url.startswith("https://"):
        raise HomeError("give the public address of the site, starting with https://")
    if (home.file("identity.json").exists() or home.last_signed()) and not replace:
        raise HomeError(f"{home.path} already holds agent data. To overwrite it: import site {url} --replace")

    domain = urlparse(url).hostname
    published_fpr, _ = key_info(site_verifier.fetcher(url)("/pgp/operator.asc"))
    dns_anchor.require(domain, published_fpr)
    local = operator_key_file()
    if local:
        dns_anchor.require(domain, key_info(local.read_bytes())[0])

    print(f"Checking {url} before importing it:\n")
    ok = site_verifier.verify_site(url)
    if not ok and not force:
        raise HomeError("the published site does not verify. Import it anyway only if you know why "
                        "(for example, it has expired): add --force")

    get = site_verifier.fetcher(url)
    doc = json.loads(get("/norai.json"))
    card = json.loads(get("/.well-known/agent-card.json"))
    revoked = json.loads(get("/revocations.json"))["revoked"]
    last = int(annex(get("/declaration.txt").decode("utf-8")).get("declaration", "0"))
    declarations = {n: (get(f"/declarations/{n:04d}.txt"), get(f"/declarations/{n:04d}.txt.asc"))
                    for n in range(1, last + 1)}

    home.path.mkdir(parents=True, exist_ok=True)
    home.write_json("identity.json", identity_from_credential(doc, card))
    shutil.rmtree(home.declarations, ignore_errors=True)
    home.declarations.mkdir()
    for n, (text, signature) in declarations.items():
        home.declaration_path(n).write_bytes(text)
        home.declaration_path(n, signed=True).write_bytes(signature)

    # The published agent keys stay valid only if their private halves are still here.
    published = [doc["keys"]["identity"]["kid"], doc["keys"]["http_signing"]["kid"]]
    local_kids = {read_public(key_path(n, home.keys))['kid'] for n in NAMES if key_path(n, home.keys).exists()}
    listed = {r["kid"] for r in revoked}
    lost = [kid for kid in published if kid not in local_kids and kid not in listed]
    revoked += [{"kid": kid, "revoked_on": dt.date.today().isoformat(), "reason": LOST_KEYS_REASON}
                for kid in lost]
    home.write_json("revocations.json", revoked)

    print(f"\nImported into {home.path}:")
    print(f"  identity.json, revocations.json and {last} signed declaration(s)")
    if not local:
        fpr = " ".join(published_fpr[i:i + 4] for i in range(0, len(published_fpr), 4))
        print(f"  the operator's key is not stored here: ask the operator for it (fingerprint {fpr}),\n"
              "  then: agentid import gpg --stdin (or --file FILE)")
    if lost:
        print("  the published agent keys are not here: they are added to revocations.json")
        print('\nNext: agentid setup (creates new keys), then\n'
              '      agentid build --changes "New agent keys: the agent\'s data was restored"\n'
              "      and send the declaration to the operator to sign.")
    else:
        print("\nNext: agentid status")


def import_gpg(home, armored: bytes, replace=False):
    if b"PRIVATE KEY BLOCK" in armored:
        raise HomeError("this is a PRIVATE key. Do not keep it: tell the operator to send only the PUBLIC key "
                        "and to treat the private one as exposed")
    fpr, uids = key_info(armored)
    dns_anchor.require(home.domain(), fpr)

    current = operator_key_file()
    if current:
        old, old_uids = key_info(current.read_bytes())
        if old == fpr:
            print(f"The operator key in {current} is already this one: nothing to do.")
            return
        if not replace:
            raise HomeError(f"there is already a different operator key in {current}:\n"
                            f"  {old}  {', '.join(old_uids)}\n"
                            f"The new one is:\n  {fpr}  {', '.join(uids)}\n"
                            "Confirm with the operator that they changed their key, then repeat with --replace")
        current.unlink()
        print(f"Replaced the previous operator key ({old}).")
    OPERATOR_DIR.mkdir(parents=True, exist_ok=True)
    (OPERATOR_DIR / "operator.asc").write_bytes(armored)
    print(f"Operator key stored in {OPERATOR_DIR / 'operator.asc'}:")
    print(f"  fingerprint {' '.join(fpr[i:i + 4] for i in range(0, len(fpr), 4))}")
    for uid in uids:
        print(f"  {uid}")
    print("It matches the DNS record. Ask the operator to confirm that this fingerprint is theirs.")
