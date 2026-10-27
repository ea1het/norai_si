#!/usr/bin/env python3
"""agentid: an AI agent's public identity card, run by the agent and signed by its human operator.

  agentid setup                                       once: create the agent's working folder and keys
  agentid import gpg (--stdin | --file FILE)          store the operator's OpenPGP public key
  agentid import site https://...                     restore the agent's data from its published site
  agentid status                                      where things stand, and what to do next
  agentid build [--changes "what changed"]...         generate the site and the declaration to sign
  agentid attach FILE                                 add the operator's signature ("-" reads stdin)
  agentid verify [SITE_DIR | https://...]             check a site, local or published
  agentid keys show                                   the agent's public key identifiers
  agentid clean                                       empty build_system/ and output_website/
  agentid keys new --replace --reason "..." [--compromised]
                                                      replace lost or leaked keys

The agent's data lives in build_system/, its working folder.
The keys' passphrase is read from AGENT_ID_PASSPHRASE, or asked for.
Instructions for agents: AGENTS.md and skills/agent-identity/SKILL.md.
"""
import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

from . import dns_anchor, verify as site_verifier
from .build import build_site, manifest_files, publish_declarations
from .crypto import human_fingerprint
from .declaration import annex, sha256, verify as verify_signature
from .home import EXAMPLE_IDENTITY, OUTPUT_WEBSITE, Home, HomeError, operator_key_file
from .imports import import_gpg, import_site
from .keys import KeyStoreError, ask_passphrase, create_all, key_path, load_all, missing, read_public, restrict, NAMES


def fmt_fpr(fpr: str) -> str:
    return " ".join(fpr[i:i + 4] for i in range(0, len(fpr), 4))


def show_keys(home: Home):
    for n in NAMES:
        path = key_path(n, home.keys)
        if path.exists():
            kid = read_public(path)["kid"]
            print(f"  {n:<9} {human_fingerprint(kid)}   kid {kid}")
        else:
            print(f"  {n:<9} (missing)")


def to_confirm(home: Home) -> int:
    """Values still marked TO_CONFIRM; help fields (keys starting with "_") are not data and are skipped."""
    def count(v):
        if isinstance(v, dict):
            return sum(count(x) for k, x in v.items() if not k.startswith("_"))
        if isinstance(v, list):
            return sum(count(x) for x in v)
        return str(v).count("TO_CONFIRM")
    return count(home.identity())


# ── Commands ────────────────────────────────────────────────────────────
def cmd_setup(home: Home, a):
    home.path.mkdir(parents=True, exist_ok=True)
    restrict(home.path, 0o700)
    print(f"Agent home: {home.path}")

    if not home.file("identity.json").exists():
        shutil.copyfile(EXAMPLE_IDENTITY, home.file("identity.json"))
        print("  identity.json created from the example: edit it with the agent's real data")

    if missing(home.keys):
        print("  creating the agent's keys (encrypted with a passphrase)")
        create_all(home.keys, ask_passphrase(confirm=True))
    show_keys(home)


    print("\nNext:")
    print(f"  - set your domain in identity.json; the operator must publish their key's full fingerprint in the DNS record "
          f"{dns_anchor.record_name('<domain>')}")
    print("  - ask the operator for their OpenPGP public key, then: agentid import gpg --stdin (or --file FILE)")
    if to_confirm(home):
        print(f"  - complete identity.json: {to_confirm(home)} field(s) marked TO_CONFIRM")
    print("  - agentid build, then give the declaration to the operator to sign")


def cmd_status(home: Home, _):
    home.require()
    src = home.identity()
    site = OUTPUT_WEBSITE
    print(f"Agent      : {src['agent']['name']} ({src['base_url']})")
    print(f"Home       : {home.path}")
    print(f"Site folder: {site}")
    try:
        fpr = home.operator_fingerprint()
        print(f"Operator   : {fmt_fpr(fpr)}")
        print(f"DNS        : {dns_anchor.check(src['domain'], fpr)[1]}")
    except HomeError as e:
        print(f"Operator   : {e}")
    print("Keys:")
    show_keys(home)
    if to_confirm(home):
        print(f"identity.json still has {to_confirm(home)} field(s) marked TO_CONFIRM")

    last, pending = home.last_signed(), home.pending()
    print(f"Signed declarations: {last}")
    manifest = site / "manifest.json"
    if pending:
        print(f"Waiting for the operator to sign declaration no. {pending}: {home.declaration_path(pending)}")
        print("Next: send it to the operator; when the signature comes back, run agentid attach FILE")
    elif not operator_key_file():
        print("Next: ask the operator for their OpenPGP public key, then: agentid import gpg --stdin (or --file FILE)")
    elif not last:
        print("Next: agentid build")
    elif (manifest.exists()
          and annex(home.declaration_path(last).read_text(encoding="utf-8")).get(
              "site-manifest-sha256") == sha256(manifest.read_bytes())
          and json.loads(manifest.read_text(encoding="utf-8"))["files"] == manifest_files(site)):
        print("The site folder matches the last signed declaration: it can be published as it is.")
    else:
        print("The site folder does not match the last signed declaration. Next: agentid build")


def cmd_build(home: Home, a):
    home.require()
    home.operator_key()   # fails early, before asking for the passphrase
    number = build_site(home, load_all(home.keys), changes=a.changes or [], issued=a.issued)
    path = home.declaration_path(number)
    print(path.read_text(encoding="utf-8"))
    print(f"Declaration no. {number} written to {path}")
    if to_confirm(home):
        print(f"warning: identity.json has {to_confirm(home)} field(s) marked TO_CONFIRM; "
              "the operator will be signing them as they are")
    print("\nNext: give this declaration to the operator. They read it, sign it with their OpenPGP key\n"
          "(a signed text or a separate signature file) and send the result back.\n"
          "Then: agentid attach <the file they sent>. Do not publish the site before that.")


def cmd_attach(home: Home, a):
    home.require()
    number = home.pending()
    if not number:
        raise HomeError("there is no declaration waiting for a signature. Run agentid build first")
    signature = sys.stdin.buffer.read() if a.file == "-" else Path(a.file).read_bytes()
    draft = home.declaration_path(number)
    try:
        fpr, text, armored = verify_signature(signature, draft, home.operator_key())
    except ValueError as e:
        raise HomeError(f"signature rejected: {e}") from None
    expected = home.operator_fingerprint()
    dns_anchor.require(home.domain(), expected)
    if fpr != expected:
        raise HomeError(f"signature rejected: made by {fmt_fpr(fpr)}, not by the operator ({fmt_fpr(expected)})")
    site = OUTPUT_WEBSITE
    manifest = site / "manifest.json"
    if not manifest.exists() or annex(text).get("site-manifest-sha256") != sha256(manifest.read_bytes()):
        raise HomeError("the site folder changed after this declaration was written. "
                        "Run agentid build again and ask the operator to sign the new declaration")
    home.declaration_path(number, signed=True).write_text(armored, encoding="utf-8", newline="\n")
    publish_declarations(home, site)
    print(f"Declaration no. {number} signed by the operator ({fmt_fpr(fpr)}) and added to the site.")
    print(f"Next: publish the site folder ({site}) with the method set up for this agent, "
          "then run agentid verify <public URL>.")


def cmd_verify(home: Home, a):
    target = a.target or str(OUTPUT_WEBSITE)
    ok = site_verifier.verify_site(target)
    sys.exit(0 if ok else 1)


def cmd_keys(home: Home, a):
    if a.action == "show":
        show_keys(home)
        return
    current = [key_path(n, home.keys) for n in NAMES if key_path(n, home.keys).exists()]
    if current and not a.replace:
        raise HomeError("the agent already has keys. To replace them: keys new --replace --reason \"...\"")
    if a.replace and not (a.reason or "").strip():
        raise HomeError("--replace needs --reason: why the keys are being replaced, in your own words")
    if current:
        revocations = home.revocations()
        retired = home.keys / "retired"
        retired.mkdir(exist_ok=True)
        for path in current:
            kid = read_public(path)["kid"]
            entry = {"kid": kid, "revoked_on": dt.date.today().isoformat(), "reason": a.reason.strip()}
            if a.compromised:
                entry["compromised"] = True
            revocations.append(entry)
            shutil.move(str(path), retired / f"{path.name.split('.')[0]}-{kid[:12]}.key.json")
        home.write_json("revocations.json", revocations)
    create_all(home.keys, ask_passphrase(confirm=True))
    print("New keys:")
    show_keys(home)
    if current:
        print("The old keys are listed in revocations.json.")
    print(f'Next: agentid build --changes "New agent keys: {a.reason or "first keys"}", '
          "and ask the operator to sign the declaration.")


def cmd_clean(home: Home, _):
    removed = home.clean()
    print("Cleaned build_system/ and output_website/: " + (", ".join(removed) if removed else "they were already empty"))
    if removed:
        print("Next: agentid import site <URL> to restore the agent's data from its published site, "
              "or agentid setup to start a new one.")


def cmd_import(home: Home, a):
    if a.what == "site":
        import_site(home, a.url, replace=a.replace, force=a.force)
    else:
        armored = sys.stdin.buffer.read() if a.stdin else Path(a.file).read_bytes()
        import_gpg(home, armored, replace=a.replace)


def main():
    ap = argparse.ArgumentParser(prog="agentid", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="create the agent's working folder and keys")
    sub.add_parser("status", help="where things stand, and what to do next")
    b = sub.add_parser("build", help="generate the site and the declaration for the operator")
    b.add_argument("--changes", action="append", help="one change since the last declaration (repeatable)")
    b.add_argument("--issued", help=argparse.SUPPRESS)
    t = sub.add_parser("attach", help="add the operator's signature to the pending declaration")
    t.add_argument("file", help='file with the signature, or "-" to read it from standard input')
    v = sub.add_parser("verify", help="check a site, local or published")
    v.add_argument("target", nargs="?", help="site folder or https:// URL (default: the site folder)")
    sub.add_parser("clean", help="empty build_system/ and output_website/; the agent's keys are lost")
    k = sub.add_parser("keys", help="show or replace the agent's keys")
    k.add_argument("action", choices=["show", "new"])
    k.add_argument("--replace", action="store_true", help="replace existing keys")
    k.add_argument("--reason", help="why the keys are replaced, in your own words")
    k.add_argument("--compromised", action="store_true", help="the old keys leaked or may have leaked")
    i = sub.add_parser("import", help="bring data into the agent's home")
    isub = i.add_subparsers(dest="what", required=True)
    isite = isub.add_parser("site", help="restore the agent's data from its published site")
    isite.add_argument("url", help="public address of the site, for example https://norai.si")
    isite.add_argument("--replace", action="store_true", help="overwrite the agent data already in the home")
    isite.add_argument("--force", action="store_true", help="import even if the published site does not verify")
    igpg = isub.add_parser("gpg", help="store the operator's OpenPGP public key")
    source = igpg.add_mutually_exclusive_group(required=True)
    source.add_argument("--stdin", action="store_true", help="read the key as text from standard input")
    source.add_argument("--file", help="read the key from this file")
    igpg.add_argument("--replace", action="store_true", help="the operator has changed their key")
    a = ap.parse_args()
    home = Home()
    try:
        {"setup": cmd_setup, "status": cmd_status, "build": cmd_build, "attach": cmd_attach,
         "verify": cmd_verify, "keys": cmd_keys, "import": cmd_import, "clean": cmd_clean}[a.cmd](home, a)
    except (HomeError, KeyStoreError) as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
