"""Builds the agent's website from the data in build_system/, its working folder (see home.py).

Called by agentid. It writes, into output_website/:
  - the credential, Agent Card, keys, DID and revocations, signed with the agent's key;
  - manifest.json: the SHA-256 of every published file;
and, into the agent's home, the declaration the operator has to sign (declarations/NNNN.txt).
Nothing here needs the operator's private key: the operator signs the declaration separately.
"""
import datetime as dt
import html
import json
import shutil
from pathlib import Path

from . import dns_anchor
from .crypto import human_fingerprint, public_jwk, sign_document
from .declaration import render, sha256, text_hash
from .home import CUSTOM_ASSETS, OUTPUT_WEBSITE, TEMPLATE, HomeError

# Everything build.py writes into the site folder. Only these are removed before a build:
# anything else in the folder (CNAME, .gitkeep, .git...) is left alone.
GENERATED = ["index.html", "norai.json", "revocations.json", "llms.txt", "_headers", ".well-known", "pgp",
             "images", "styles", "scripts", "manifest.json", "declaration.txt", "declaration.txt.asc", "declarations"]
# Files that the operator's declaration cannot cover, because they are the declaration itself.
NOT_IN_MANIFEST = {"manifest.json", "declaration.txt", "declaration.txt.asc", "declarations"}
E = html.escape


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def write_text(path: Path, text: str):
    # Always LF: on Windows the default would be CRLF, and the hashes in manifest.json
    # cover the exact bytes of each file.
    path.write_text(text, encoding="utf-8", newline="\n")


def check_revocations(entries, current_kids):
    for r in entries:
        if (not {"kid", "revoked_on", "reason"} <= r.keys() or not str(r["reason"]).strip()
                or not isinstance(r.get("compromised", False), bool)):
            raise HomeError(f"bad entry in revocations.json: {r}")
        if r["kid"] in current_kids:
            raise HomeError(f"the key in use ({r['kid']}) is in revocations.json")
    return entries


def asset_url(path: str) -> str:
    """Link to a file from custom_assets/ with a version taken from its content, so that browsers
    fetch it again whenever it changes instead of reusing a cached copy with new HTML."""
    return f"{path}?v={sha256((CUSTOM_ASSETS / path).read_bytes())[:12]}"


def manifest_files(site: Path) -> dict:
    paths = []
    for name in GENERATED:
        path = site / name
        if name in NOT_IN_MANIFEST:
            continue
        if path.is_dir():
            paths += [p for p in sorted(path.rglob("*")) if p.is_file() and p.name != ".DS_Store"]
        elif path.exists():
            paths.append(path)
    return {p.relative_to(site).as_posix(): sha256(p.read_bytes()) for p in paths}


def publish_declarations(home, site: Path):
    """Copies every signed declaration into the site, and the latest one to /declaration.txt(.asc)."""
    last = home.last_signed()
    for n in range(1, last + 1):
        for signed in (False, True):
            dest = site / "declarations" / home.declaration_path(n, signed).name
            dest.parent.mkdir(exist_ok=True)
            shutil.copyfile(home.declaration_path(n, signed), dest)
    if last:
        shutil.copyfile(home.declaration_path(last), site / "declaration.txt")
        shutil.copyfile(home.declaration_path(last, True), site / "declaration.txt.asc")


MRZ_WIDTH = 44   # the line length of a passport's machine-readable zone (ICAO 9303, TD3)


def mrz(src, issued, expires, kid):
    def line(s):
        s = "".join(c if c.isalnum() else "<" for c in s.upper())
        return (s + "<" * MRZ_WIDTH)[:MRZ_WIDTH]
    d = lambda x: x.strftime("%Y%m%d")  # noqa: E731
    serial = src["serial"].replace("-", "")
    return "\n".join([
        line(f"AI<{src['agent']['handle']}<<{src['domain'].replace('.', '<')}"),
        line(f"{serial}<{d(issued)}<{d(expires)}"),
        # The key appears as the start of its hex fingerprint, as on the card and in the QR code: hex has
        # no case and no symbols, so it survives the MRZ alphabet (A-Z, 0-9, <) unchanged.
        line(f"{src['agent']['name']}<<{src['operator']['display_name']}<<{human_fingerprint(kid).replace(' ', '')[:10]}"),
    ])


def build_site(home, keys: dict, *, changes=(), issued=None) -> int:
    """Builds the site and writes the declaration to sign. Returns the declaration's number."""
    src = home.identity()
    SITE, OUT = OUTPUT_WEBSITE, home.out
    number = home.last_signed() + 1
    if number > 1 and not changes:
        raise HomeError("describe what changed since the last declaration (--changes), "
                        "so the operator knows what they are signing")
    base, domain = src["base_url"].rstrip("/"), src["domain"]
    issued = dt.date.fromisoformat(issued) if issued else dt.datetime.now(dt.timezone.utc).date()
    expires = issued + dt.timedelta(days=int(src["valid_days"]))
    did = "did:web:" + domain

    for name in GENERATED:
        path = SITE / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / ".well-known").mkdir()
    (SITE / "pgp").mkdir()
    OUT.mkdir(parents=True, exist_ok=True)
    for folder in ("images", "styles", "scripts"):   # the customisable look of the site, published as it is
        shutil.copytree(CUSTOM_ASSETS / folder, SITE / folder,
                        ignore=shutil.ignore_patterns(".gitkeep", ".DS_Store"))

    id_key = keys["identity"]    # signs documents
    http_key = keys["http"]      # signs HTTP requests (Web Bot Auth)
    id_jwk, http_jwk = public_jwk(id_key.public_key()), public_jwk(http_key.public_key())
    kid, http_kid = id_jwk["kid"], http_jwk["kid"]
    jku = f"{base}/.well-known/jwks.json"
    fp = human_fingerprint(kid)

    pgp_fpr = home.operator_fingerprint()
    dns_anchor.require(domain, pgp_fpr)
    (SITE / "pgp" / "operator.asc").write_bytes(home.operator_key())

    # ── norai.json: the credential ─────────────────────────────────────────
    clean = lambda d: {k: v for k, v in d.items() if not k.startswith("_")}  # noqa: E731
    op = dict(src["operator"])
    op["pgp"] = {"fingerprint": pgp_fpr,
                 "public_key": f"{base}/pgp/operator.asc",
                 "declaration": f"{base}/declaration.txt.asc"}
    credential = {
        "type": "AgentIdentityCredential",
        "spec": "norai-identity/1",
        "id": did,
        "serial": src["serial"],
        "version": src["version"],
        "url": f"{base}/norai.json",
        "human_page": f"{base}/",
        "agent": src["agent"],
        "operator": op,
        "accountability": src["accountability"],
        "runtime": src["runtime"],
        "models": src["models"],
        "skills": src["skills"],
        "protocols": {
            "a2a": {"status": src["a2a"]["status"], "agent_card": f"{base}/.well-known/agent-card.json",
                    "endpoint": src["a2a"]["endpoint"], "protocol_version": src["a2a"]["protocol_version"]},
            "web_bot_auth": {"directory": f"{base}/.well-known/http-message-signatures-directory", "kid": http_kid,
                             "note": "NorAI's HTTP requests carry an RFC 9421 signature made with this key."},
            "did": {"id": did, "document": f"{base}/.well-known/did.json"},
        },
        "keys": {
            "identity": {"kid": kid, "alg": "EdDSA", "crv": "Ed25519", "fingerprint": fp,
                         "purpose": "Signs this credential, the Agent Card and identity challenges"},
            "http_signing": {"kid": http_kid, "alg": "EdDSA", "crv": "Ed25519",
                             "purpose": "Signs outgoing HTTP requests (Web Bot Auth)"},
            "jwks": jku,
        },
        "verification": {
            "method": "JWS EdDSA over the JCS (RFC 8785) form of the document without 'signatures'; same scheme as A2A v1.0 signed Agent Cards",
            "dns_txt": dns_anchor.record_name(domain),
            "revocations": f"{base}/revocations.json",
            "manifest": f"{base}/manifest.json",
            "operator_declaration": f"{base}/declaration.txt.asc",
            "liveness": "A copy of these files proves nothing on its own: ask NorAI to sign a fresh challenge or an HTTP request with the keys above.",
        },
        "validity": {"issued": issued.isoformat(), "expires": expires.isoformat()},
    }
    credential = sign_document(clean(credential), id_key, kid, jku)
    write_json(SITE / "norai.json", credential)

    # ── A2A Agent Card v1.0 ───────────────────────────────────────────────
    card = {
        "name": src["agent"]["name"],
        "description": src["agent"]["self_introduction"],
        "supportedInterfaces": [{"url": src["a2a"]["endpoint"], "protocolBinding": src["a2a"]["protocol_binding"],
                                 "protocolVersion": src["a2a"]["protocol_version"]}],
        "provider": {"organization": f"NorAI (operator: {src['operator']['display_name']})", "url": base},
        "version": src["version"],
        "documentationUrl": f"{base}/",
        "iconUrl": f"{base}/images/logo.png",
        "capabilities": {"streaming": False, "pushNotifications": False, "extensions": [{
            "uri": f"{base}/ext/identity/v1",
            "description": "Signed identity credential of the agent and its human operator",
            "required": False,
            "params": {"credential": f"{base}/norai.json", "did": did, "aiSystem": True}}]},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [{"id": s["id"], "name": s["name"], "description": s["description"], "tags": s["tags"]}
                   for s in src["skills"]],
    }
    write_json(SITE / ".well-known" / "agent-card.json", sign_document(card, id_key, kid, jku))

    # ── Public keys: JWKS, Web Bot Auth, DID ─────────────────────────
    write_json(SITE / ".well-known" / "jwks.json", {"keys": [id_jwk, http_jwk]})
    write_json(SITE / ".well-known" / "http-message-signatures-directory", {"keys": [http_jwk]})
    vm = lambda j, frag: {"id": f"{did}#{frag}", "type": "JsonWebKey2020", "controller": did,  # noqa: E731
                          "publicKeyJwk": j}
    write_json(SITE / ".well-known" / "did.json", {
        "@context": ["https://www.w3.org/ns/did/v1", "https://w3id.org/security/suites/jws-2020/v1"],
        "id": did, "controller": did,
        "verificationMethod": [vm(id_jwk, kid), vm(http_jwk, http_kid)],
        "authentication": [f"{did}#{kid}", f"{did}#{http_kid}"],
        "assertionMethod": [f"{did}#{kid}"],
        "service": [
            {"id": f"{did}#credential", "type": "AgentIdentityCredential", "serviceEndpoint": f"{base}/norai.json"},
            {"id": f"{did}#a2a", "type": "A2AAgentCard", "serviceEndpoint": f"{base}/.well-known/agent-card.json"},
            {"id": f"{did}#web", "type": "LinkedDomains", "serviceEndpoint": f"{base}/"},
        ]})
    write_json(SITE / "revocations.json", sign_document(
        {"type": "NorAIRevocationList", "updated": issued.isoformat(),
         "revoked": check_revocations(home.revocations(), {kid, http_kid})}, id_key, kid, jku))

    # ── LLM text, security.txt, headers ──────────────────────────
    ag, rt = src["agent"], src["runtime"]
    models_txt = "\n".join(f"- {m['role']}: {m['id']} ({m['location']})" for m in src["models"])
    write_text(SITE / "llms.txt", f"""# {ag['name']}

> {ag['self_introduction']}

{ag['ai_disclosure']['statement']} Operator: {src['operator']['display_name']} ({src['operator']['website']}).

## Machine-readable identity
- [Signed credential]({base}/norai.json): JWS EdDSA over JCS, kid {kid}
- [A2A Agent Card]({base}/.well-known/agent-card.json) (signed, A2A v1.0; endpoint status: {src['a2a']['status']})
- [JWKS]({base}/.well-known/jwks.json), [DID document]({base}/.well-known/did.json) ({did})
- [Web Bot Auth key directory]({base}/.well-known/http-message-signatures-directory)
- [Revocations]({base}/revocations.json); DNS anchor: TXT {dns_anchor.record_name(domain)}
- [Operator's signed declaration]({base}/declaration.txt.asc): covers every file listed in [manifest.json]({base}/manifest.json)

## Runtime
{rt['architecture']}; ~{rt['target_mix']['local_percent']}% local / {rt['target_mix']['frontier_percent']}% frontier. Gateway: {rt['gateway']}. Inference: {rt['inference_server']}.

## Models
{models_txt}

## Verification rule
A copy of these files proves nothing on its own. Ask NorAI to sign a fresh challenge or an HTTP request with the keys above.
""")
    write_text(SITE / ".well-known" / "security.txt",
               f"Contact: mailto:{src['operator']['contact']}\nExpires: {expires.isoformat()}T00:00:00Z\n"
               f"Preferred-Languages: es, en\nCanonical: {base}/.well-known/security.txt\n")
    write_text(SITE / "_headers", """/*
  Access-Control-Allow-Origin: *
  X-Content-Type-Options: nosniff
  Referrer-Policy: no-referrer
/.well-known/http-message-signatures-directory
  Content-Type: application/http-message-signatures-directory+json
/.well-known/did.json
  Content-Type: application/did+json
/declaration.txt.asc
  Content-Type: text/plain; charset=utf-8
/declarations/*
  Content-Type: text/plain; charset=utf-8
/pgp/operator.asc
  Content-Type: application/pgp-keys
""")
    if not (SITE / ".nojekyll").exists():  # GitHub Pages: serve .well-known/ instead of skipping dot folders
        write_text(SITE / ".nojekyll", "")

    # The DNS record names the operator, not the agent's keys: the operator publishes it once and
    # it only changes if they change their OpenPGP key. The full fingerprint cannot be forged.
    dns = (f"; Records for the {domain} zone (enable DNSSEC at the registrar)\n"
           f'{dns_anchor.record_name(domain)}.  3600 IN TXT "0x{pgp_fpr}"\n'
           f'{domain}.            3600 IN CAA 0 issue "letsencrypt.org"\n')
    write_text(OUT / "dns.txt", dns)

    # ── QR and page ──────────────────────────────────────────────────────
    import segno
    qr_url = f"{base}/?fp={fp.replace(' ', '')}"
    qr_svg = segno.make(qr_url, error="m").svg_inline(scale=1, border=1, dark="#0B1B33", omitsize=True)
    qr_svg = qr_svg.replace("<svg ", '<svg role="img" aria-label="QR: ' + E(qr_url) + '" ', 1)

    loc_tag = lambda loc: '<span class="tag">local</span>' if loc == "local" else f'<span class="tag">{E(loc)}</span>'  # noqa: E731
    def model_id(m):
        if m["id"] == "TO_CONFIRM":
            return '<span class="tag todo">to confirm</span>'
        prof = "".join(f'<span class="tag">{E(p)}</span>' for p in m.get("profiles", []))
        return f"<code>{E(m['id'])}</code><br><small style=\"color:var(--muted)\">{E(m['family'])}</small>" + (f"<br>{prof}" if prof else "")
    models_rows = "".join(f"<tr><td>{E(m['role'])}</td><td>{model_id(m)}</td><td>{loc_tag(m['location'])}</td></tr>"
                          for m in src["models"])
    skills = "".join(f'<span class="tag" title="{E(s["description"])}">{E(s["name"])}</span>' for s in src["skills"])

    def val(v):
        return '<span class="tag todo">to confirm</span>' if "TO_CONFIRM" in v else E(v)
    o = src["operator"]
    op_kv = (f"<dt>Role</dt><dd>{E(o['role'])}</dd>"
             f"<dt>Type</dt><dd>{E(o['type'])}</dd>"
             f"<dt>Jurisdiction</dt><dd>{val(o['jurisdiction'])}</dd>"
             f"<dt>Web</dt><dd><a href=\"{E(o['website'])}\">{E(o['website'].split('//')[-1])}</a></dd>"
             f"<dt>Contact</dt><dd><span class=\"mono\">{E(o['contact'])}</span><button class=\"copy\" type=\"button\" data-copy=\"{E(o['contact'])}\">copy</button></dd>"
             f"<dt>OpenPGP</dt><dd class=\"mono fpr\">{E(' '.join(pgp_fpr[i:i+4] for i in range(0, len(pgp_fpr), 4)))}</dd>")
    endpoints = [
        ("/norai.json", "Signed JSON (JWS EdDSA)", "Full credential: identity, operator, technology, limits, keys and validity."),
        ("/declaration.txt.asc", "OpenPGP-signed text", "The operator's declaration: plain-language statement, signed by the human operator."),
        ("/manifest.json", "JSON", "SHA-256 of every published file. The operator's declaration covers it."),
        ("/declarations/0001.txt.asc", "OpenPGP-signed text", "The first declaration. Every later one (0002, 0003…) is kept too, chained by hash."),
        ("/.well-known/agent-card.json", "A2A Agent Card v1.0, signed", f"Agent-to-agent discovery. A2A endpoint: {src['a2a']['status']}."),
        ("/.well-known/jwks.json", "JWK Set", "Ed25519 public keys (identity and HTTP requests)."),
        ("/.well-known/did.json", "DID Document (did:web)", f"Decentralised identifier {did} for verifiable credentials."),
        ("/.well-known/http-message-signatures-directory", "Web Bot Auth directory", "The key I sign my HTTP requests with (RFC 9421)."),
        ("/revocations.json", "Signed JSON", "Keys withdrawn before expiry."),
        ("/llms.txt", "Markdown", "Summary for language models."),
        ("/pgp/operator.asc", "OpenPGP public key", "The operator's key."),
    ]
    endpoints_rows = "".join(f'<tr><td><a href="{E(p.lstrip("/"))}"><code>{E(p)}</code></a></td><td>{E(f)}</td><td>{E(d)}</td></tr>'
                             for p, f, d in endpoints)
    http_example = E(f"""# Illustrative example (signature shortened)
GET /api/resource HTTP/1.1
Host: example.org
Signature-Agent: sig1="{base}/.well-known/http-message-signatures-directory"
Signature-Input: sig1=("@authority" "signature-agent");
  created=1761235200;expires=1761238800;
  keyid="{http_kid}";
  alg="ed25519";tag="web-bot-auth";nonce="…"
Signature: sig1=:jR0x…Q==:""")
    jsonld = json.dumps({
        "@context": "https://schema.org", "@type": "SoftwareApplication", "@id": did,
        "name": ag["name"], "description": ag["self_introduction"], "applicationCategory": "AI agent",
        "url": f"{base}/", "image": f"{base}/images/logo.png", "softwareVersion": src["version"],
        "author": {"@type": "Person", "name": o["display_name"], "url": o["website"]},
        "sameAs": [f"{base}/norai.json", f"{base}/.well-known/agent-card.json"],
    }, ensure_ascii=False).replace("</", "<\\/")

    repl = {
        "FAVICON": asset_url("images/favicon.png"),
        "LOGO_MARK": asset_url("images/mark.png"),
        "STYLESHEET": asset_url("styles/credential.css"),
        "SCRIPT": asset_url("scripts/credential.js"),
        "JSONLD": jsonld, "VERSION": E(src["version"]), "DOMAIN": E(domain),
        "NAME": E(ag["name"]), "KIND": E(ag["kind"]), "OPERATOR_NAME": E(o["display_name"]),
        "SERIAL": E(src["serial"]), "ISSUED": issued.isoformat(), "EXPIRES": expires.isoformat(), "FP": E(fp),
        "QR_SVG": qr_svg, "MRZ": E(mrz(src, issued, expires, kid)),
        "DISCLOSURE": E(ag["ai_disclosure"]["statement"]),
        "LEAD": E(ag["self_introduction"].removeprefix(f"Hi, I am {ag['name']}. ")),
        "AGENT_EMAIL": (f'<p class="agent-mail"><span class="eyebrow">Email</span>'
                        f'<a class="mono" href="mailto:{E(ag["email"])}">{E(ag["email"])}</a>'
                        f'<button class="copy" type="button" data-copy="{E(ag["email"])}">copy</button></p>'
                        if ag.get("email") else ""),
        "ARCH": E(rt["architecture"]), "INTERFACES": E(" · ".join(rt["interfaces"])),
        "A2A_STATUS": E(src["a2a"]["status"]), "HARNESSES": E(" · ".join(rt["harnesses"])),
        "MEMORY": E(rt["memory"]), "INFERENCE": E(rt["inference_server"]), "HARDWARE": E(rt["hardware"]),
        "MODELS_ROWS": models_rows, "SKILLS": skills, "OPERATOR_BIO": E(o["bio"]), "OPERATOR_KV": op_kv,
        "CONFIRM_LIST": "".join(f"<li>{E(x)}</li>" for x in src["accountability"]["requires_human_confirmation_for"]),
        "WILLNOT_LIST": "".join(f"<li>{E(x)}</li>" for x in src["accountability"]["will_not"]),
        "ENDPOINTS_ROWS": endpoints_rows, "HTTP_EXAMPLE": http_example, "DNS_RECORD": E(f"; Published in the {domain} zone when this page was built ({issued.isoformat()})\n"
                         + dns_anchor.site_zone(domain)),
        "DOMAIN_JSON": json.dumps(domain), "FP_JSON": json.dumps(fp),
    }
    page = TEMPLATE.read_text(encoding="utf-8")
    for k, v in repl.items():
        page = page.replace("{{" + k + "}}", v)
    leftover = [p for p in page.split("{{")[1:] if "}}" in p[:40]]
    if leftover:
        raise HomeError(f"unfilled placeholders in template.html: {[p.split('}}')[0] for p in leftover]}")
    write_text(OUT / "artifact.html", page)
    head = ('<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n')
    write_text(SITE / "index.html", head + page)

    # ── Manifest and the declaration for the operator ─────────────────────
    publish_declarations(home, SITE)
    manifest = {"type": "AgentSiteManifest", "algorithm": "sha256", "site": f"{base}/",
                "files": manifest_files(SITE)}
    write_json(SITE / "manifest.json", manifest)
    previous = home.declaration_path(number - 1)
    text = render(src, number=number, issued=issued.isoformat(), expires=expires.isoformat(),
                  kids={"identity": kid, "http": http_kid},
                  fingerprints={"identity": fp, "http": human_fingerprint(http_kid)},
                  manifest_sha=sha256((SITE / "manifest.json").read_bytes()),
                  previous_sha=text_hash(previous.read_text(encoding="utf-8")) if number > 1 else None,
                  changes=list(changes))
    home.declarations.mkdir(parents=True, exist_ok=True)
    write_text(home.declaration_path(number), text)
    return number
