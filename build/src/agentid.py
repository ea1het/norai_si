#!/usr/bin/env python3
"""agentid: an AI agent's public identity card, run by the agent and signed by its human operator.

  agentid.py setup --operator-key FILE [--site DIR]   once: create the agent's home, keys and settings
  agentid.py status                                   where things stand, and what to do next
  agentid.py build [--changes "what changed"]...      generate the site and the declaration to sign
  agentid.py attach FILE                              add the operator's signature ("-" reads stdin)
  agentid.py verify [SITE_DIR | https://...]          check a site, local or published
  agentid.py keys show                                the agent's public key identifiers
  agentid.py keys new --replace --reason "..." [--compromised]
                                                      replace lost or leaked keys
  agentid.py demo                                     a complete example with throwaway keys

The agent's data lives in its home folder: --home, or the AGENT_ID_HOME variable, or ~/.agent-id.
The keys' passphrase is read from AGENT_ID_PASSPHRASE, or asked for.
Instructions for agents: AGENTS.md and skills/agent-identity/SKILL.md.
"""
import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import build_site, manifest_files, publish_declarations  # noqa: E402
from declaration import annex, sha256, verify as verify_signature  # noqa: E402
from norai_crypto import human_fingerprint  # noqa: E402
from norai_home import DEMO_HOME, EXAMPLE_IDENTITY, Home, HomeError, gpg, key_fingerprint  # noqa: E402
from norai_keys import (KeyStoreError, ask_passphrase, create_all, key_path, load_all, load_or_create_demo,  # noqa: E402
                        missing, read_public, restrict, NAMES)
import verify as site_verifier  # noqa: E402


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
    return home.file("identity.json").read_text(encoding="utf-8").count("TO_CONFIRM")


# ── Commands ────────────────────────────────────────────────────────────
def cmd_setup(home: Home, a):
    home.path.mkdir(parents=True, exist_ok=True)
    restrict(home.path, 0o700)
    print(f"Agent home: {home.path}")

    if not home.file("identity.json").exists():
        shutil.copyfile(a.identity or EXAMPLE_IDENTITY, home.file("identity.json"))
        print("  identity.json created from", a.identity or "the example: edit it with the agent's real data")

    if a.operator_key:
        armored = Path(a.operator_key).read_bytes()
        fpr = key_fingerprint(armored)
        old = home.file("operator.asc")
        if old.exists() and key_fingerprint(old.read_bytes()) != fpr and home.last_signed():
            print("  warning: the operator key changes. Earlier declarations stay signed by the old key.")
        old.write_bytes(armored)
        print(f"  operator key: {fmt_fpr(fpr)}")
    elif not home.file("operator.asc").exists():
        raise HomeError("pass --operator-key FILE: the operator's OpenPGP public key")

    if missing(home.keys):
        print("  creating the agent's keys (encrypted with a passphrase)")
        create_all(home.keys, ask_passphrase(confirm=True))
    show_keys(home)

    settings = home.settings()
    if a.site or "site_dir" not in settings:
        settings["site_dir"] = str(Path(a.site).expanduser().resolve() if a.site else home.path / "site")
        home.write_json("settings.json", settings)
    print(f"  site folder: {settings['site_dir']}")

    print("\nNext:")
    if to_confirm(home):
        print(f"  - complete identity.json: {to_confirm(home)} field(s) marked TO_CONFIRM")
    print("  - agentid.py build, then give the declaration to the operator to sign")


def cmd_status(home: Home, _):
    home.require()
    src = home.identity()
    site = home.site_dir()
    print(f"Agent      : {src['agent']['name']} ({src['base_url']})")
    print(f"Home       : {home.path}")
    print(f"Site folder: {site}")
    try:
        print(f"Operator   : {fmt_fpr(home.operator_fingerprint())}")
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
        print("Next: send it to the operator; when the signature comes back, run agentid.py attach FILE")
    elif not last:
        print("Next: agentid.py build")
    elif (manifest.exists()
          and annex(home.declaration_path(last).read_text(encoding="utf-8")).get(
              "site-manifest-sha256") == sha256(manifest.read_bytes())
          and json.loads(manifest.read_text(encoding="utf-8"))["files"] == manifest_files(site)):
        print("The site folder matches the last signed declaration: it can be published as it is.")
    else:
        print("The site folder does not match the last signed declaration. Next: agentid.py build")


def cmd_build(home: Home, a, demo=False, keys=None):
    home.require()
    keys = keys or load_all(home.keys)
    number = build_site(home, keys, changes=a.changes or [], demo=demo, issued=getattr(a, "issued", None))
    path = home.declaration_path(number)
    if not demo:
        print(path.read_text(encoding="utf-8"))
        print(f"Declaration no. {number} written to {path}")
        if to_confirm(home):
            print(f"warning: identity.json has {to_confirm(home)} field(s) marked TO_CONFIRM; "
                  "the operator will be signing them as they are")
        print("\nNext: give this declaration to the operator. They read it, sign it with their OpenPGP key\n"
              "(a signed text or a separate signature file) and send the result back.\n"
              "Then: agentid.py attach <the file they sent>. Do not publish the site before that.")
    return number


def cmd_attach(home: Home, a):
    home.require()
    number = home.pending()
    if not number:
        raise HomeError("there is no declaration waiting for a signature. Run agentid.py build first")
    signature = sys.stdin.buffer.read() if a.file == "-" else Path(a.file).read_bytes()
    draft = home.declaration_path(number)
    try:
        fpr, text, armored = verify_signature(signature, draft, home.operator_key())
    except ValueError as e:
        raise HomeError(f"signature rejected: {e}") from None
    expected = home.operator_fingerprint()
    if fpr != expected:
        raise HomeError(f"signature rejected: made by {fmt_fpr(fpr)}, not by the operator ({fmt_fpr(expected)})")
    site = home.site_dir()
    manifest = site / "manifest.json"
    if not manifest.exists() or annex(text).get("site-manifest-sha256") != sha256(manifest.read_bytes()):
        raise HomeError("the site folder changed after this declaration was written. "
                        "Run agentid.py build again and ask the operator to sign the new declaration")
    home.declaration_path(number, signed=True).write_text(armored, encoding="utf-8", newline="\n")
    publish_declarations(home, site)
    print(f"Declaration no. {number} signed by the operator ({fmt_fpr(fpr)}) and added to the site.")
    print(f"Next: publish the site folder ({site}) with the method set up for this agent, "
          "then run agentid.py verify <public URL>.")


def cmd_verify(home: Home, a):
    target = a.target or str(home.site_dir())
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
    print(f'Next: agentid.py build --changes "New agent keys: {a.reason or "first keys"}", '
          "and ask the operator to sign the declaration.")


def cmd_demo(_, a):
    """A complete run with throwaway keys and a demo operator, signed automatically."""
    home = Home(DEMO_HOME)
    home.path.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(home.declarations, ignore_errors=True)
    shutil.copyfile(EXAMPLE_IDENTITY, home.file("identity.json"))
    gnupg = home.path / "gnupg"
    gnupg.mkdir(exist_ok=True)
    restrict(gnupg, 0o700)
    if "fpr:" not in gpg(["--with-colons", "--list-secret-keys"], gnupg).stdout.decode():
        gpg(["--passphrase", "", "--quick-gen-key", "Demo operator <demo@example.invalid>", "ed25519", "sign", "2y"], gnupg)
    home.file("operator.asc").write_bytes(gpg(["--armor", "--export"], gnupg).stdout)
    home.write_json("settings.json", {"site_dir": str(Path(a.site).expanduser().resolve() if a.site else home.path / "site")})
    a.changes = []
    number = cmd_build(home, a, demo=True, keys=load_or_create_demo(home.keys))
    signed = gpg(["--clearsign", "--output", "-", str(home.declaration_path(number))], gnupg).stdout
    fpr, _, armored = verify_signature(signed, home.declaration_path(number), home.operator_key())
    home.declaration_path(number, signed=True).write_text(armored, encoding="utf-8", newline="\n")
    publish_declarations(home, home.site_dir())
    print(f"Demo site written to {home.site_dir()} (demo keys, demo operator {fmt_fpr(fpr)}).")
    print("Do not publish it. Check it with: agentid.py verify")
    a.target = str(home.site_dir())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home", help="the agent's home folder (default: $AGENT_ID_HOME or ~/.agent-id)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup", help="create the agent's home, keys and settings")
    s.add_argument("--operator-key", help="file with the operator's OpenPGP public key")
    s.add_argument("--site", help="folder where the website is written, for example a checkout of the "
                   "branch that is published (default: <home>/site)")
    s.add_argument("--identity", help="start identity.json from this file instead of the example")
    sub.add_parser("status", help="where things stand, and what to do next")
    b = sub.add_parser("build", help="generate the site and the declaration for the operator")
    b.add_argument("--changes", action="append", help="one change since the last declaration (repeatable)")
    b.add_argument("--issued", help=argparse.SUPPRESS)
    t = sub.add_parser("attach", help="add the operator's signature to the pending declaration")
    t.add_argument("file", help='file with the signature, or "-" to read it from standard input')
    v = sub.add_parser("verify", help="check a site, local or published")
    v.add_argument("target", nargs="?", help="site folder or https:// URL (default: the site folder)")
    k = sub.add_parser("keys", help="show or replace the agent's keys")
    k.add_argument("action", choices=["show", "new"])
    k.add_argument("--replace", action="store_true", help="replace existing keys")
    k.add_argument("--reason", help="why the keys are replaced, in your own words")
    k.add_argument("--compromised", action="store_true", help="the old keys leaked or may have leaked")
    d = sub.add_parser("demo", help="a complete example with throwaway keys")
    d.add_argument("--site", help="folder for the demo site (default: build/demo/site)")
    a = ap.parse_args()
    home = Home.resolve(a.home)
    try:
        if a.cmd == "demo":
            cmd_demo(home, a)
            ok = site_verifier.verify_site(a.target)
            sys.exit(0 if ok else 1)
        {"setup": cmd_setup, "status": cmd_status, "build": cmd_build, "attach": cmd_attach,
         "verify": cmd_verify, "keys": cmd_keys}[a.cmd](home, a)
    except (HomeError, KeyStoreError) as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
