"""The DNS anchor: the operator's OpenPGP fingerprint, published by the operator in a TXT record.

  _aid-sysop.<domain>  TXT  "0x<fingerprint>"

It is the root of trust. Nothing that involves the operator's key goes ahead unless the record
exists and names that key:
  - no record: nothing can be checked, so nothing proceeds;
  - the key does not match the record: stop, a site that contradicts the DNS must not exist;
  - the key matches: proceed.

The record must hold the full 40-character fingerprint ("0x" and spaces are ignored). Shorter key
IDs are rejected: they can be forged by generating another key whose fingerprint ends the same way.
"""
import re

import dns.exception
import dns.resolver

from .home import HomeError

RECORD = "_aid-sysop"


def record_name(domain: str) -> str:
    return f"{RECORD}.{domain}"


def normalize(value: str) -> str:
    # Any whitespace goes, including the non-breaking spaces that copying a formatted fingerprint adds.
    value = "".join(value.strip().strip('"').split()).upper()
    return value[2:] if value.startswith("0X") else value


def published_values(domain: str) -> list:
    """The raw TXT values of the record; an empty list when there is no record."""
    try:
        answer = dns.resolver.resolve(record_name(domain), "TXT")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []
    except dns.exception.DNSException as e:
        raise HomeError(f"could not query the DNS for {record_name(domain)}: {e}") from None
    return [b"".join(r.strings).decode("utf-8", "replace") for r in answer]


def published_ids(domain: str) -> list:
    """The full fingerprints in the record (40 hex characters, optionally with 0x and spaces)."""
    ids = [normalize(v) for v in published_values(domain)]
    return [v for v in ids if re.fullmatch(r"[0-9A-F]{40}", v)]


# The records shown on the page: who may issue the site's HTTPS certificate, and the anchor.
SITE_RECORDS = (("", "CAA"), (RECORD, "TXT"))


def site_zone(domain: str) -> str:
    """The records above as they are published right now, in zone-file form. The TTL is left out:
    a resolver reports the time left in its cache, which would change the page on every build."""
    rows = []
    for prefix, rtype in SITE_RECORDS:
        name = f"{prefix}.{domain}." if prefix else f"{domain}."
        try:
            answer = dns.resolver.resolve(name, rtype)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            continue
        except dns.exception.DNSException as e:
            raise HomeError(f"could not query the DNS for {name} {rtype}: {e}") from None
        rows += [(name, rtype, r.to_text()) for r in sorted(answer, key=lambda r: r.to_text())]
    widths = [max(len(r[i]) for r in rows) for i in range(2)] if rows else [0, 0]
    return "\n".join(f"{n.ljust(widths[0])}  IN  {k.ljust(widths[1])}  {v}" for n, k, v in rows)


def check(domain: str, fingerprint: str) -> tuple:
    """(ok, message) comparing a key fingerprint with the DNS record. Never raises on a mismatch."""
    ids = published_ids(domain)
    name = record_name(domain)
    if not ids:
        raw = published_values(domain)
        if raw:
            return False, (f"the {name} TXT record does not hold a full fingerprint ({', '.join(map(repr, raw))}). "
                           "It must be the operator's complete 40-character fingerprint, for example \"0x"
                           + fingerprint.upper() + "\": short key IDs can be forged")
        return False, (f"there is no {name} TXT record. The operator must publish their key's full fingerprint there first: "
                       "without it neither the agent nor the operator can be verified")
    fingerprint = fingerprint.upper()
    if fingerprint not in ids:
        return False, (f"the operator key {fingerprint} does not match the fingerprint published in {name} "
                       f"({', '.join('0x' + i for i in ids)})")
    return True, f"matches {name}"


def require(domain: str, fingerprint: str):
    """Raises HomeError unless the DNS record names this key."""
    ok, message = check(domain, fingerprint)
    if not ok:
        raise HomeError(f"stopped: {message}")
