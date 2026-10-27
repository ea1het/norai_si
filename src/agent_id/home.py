"""The agent's working folder, build_system/: everything that belongs to one agent.

Git ignores everything in build_system/ except identity.example.json. It can be lost
at any time: `agentid import site <URL>` rebuilds it from the published site, and
`agentid clean` empties it, together with output_website/, on purpose.

The operator's OpenPGP public key is not in the home: it lives in custom_assets/operator/, which the
operator customises and git ignores. Any one key file is accepted there (.asc, .gpg, .pub, .key).

  build_system/
    identity.json              public data about the agent and its operator
    revocations.json           keys withdrawn before expiry (written by agentid keys)
    keys/                      the agent's private keys, encrypted
    declarations/0001.txt      each declaration given to the operator to sign...
    declarations/0001.txt.asc  ...and the signature the operator sent back
    out/                       DNS records and a preview of the page
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # the tool's repository
BUILD_SYSTEM = ROOT / "build_system"
EXAMPLE_IDENTITY = BUILD_SYSTEM / "identity.example.json"
CUSTOM_ASSETS = ROOT / "custom_assets"         # html/, images/, styles/: the look of the website
TEMPLATE = CUSTOM_ASSETS / "html" / "template.html"
OUTPUT_WEBSITE = ROOT / "output_website"       # where every build writes the website
OPERATOR_DIR = CUSTOM_ASSETS / "operator"      # the operator's OpenPGP public key: one file, any name
KEY_SUFFIXES = {".asc", ".gpg", ".pub", ".key"}


class HomeError(Exception):
    pass


def gpg(args, home=None, check=True, **kw):
    env = dict(os.environ)
    if home:
        env["GNUPGHOME"] = str(home)
    try:
        return subprocess.run(["gpg", "--batch", *args], env=env, check=check, capture_output=True, **kw)
    except FileNotFoundError:
        raise HomeError("GnuPG (gpg) is not installed: it is needed to read the operator's key") from None


def key_info(armored: bytes) -> tuple:
    """(primary-key fingerprint, user IDs) of an OpenPGP public key, without importing it anywhere."""
    with tempfile.TemporaryDirectory() as tmp:
        out = gpg(["--with-colons", "--import-options", "show-only", "--import"], tmp, input=armored,
                  check=False).stdout.decode()
    lines = [line.split(":") for line in out.splitlines()]
    fprs = [f[9] for f in lines if f[0] == "fpr"]
    if not fprs:
        raise HomeError("this is not an OpenPGP public key")
    return fprs[0].upper(), [f[9] for f in lines if f[0] == "uid"]


def key_fingerprint(armored: bytes) -> str:
    return key_info(armored)[0]


def operator_key_file():
    """The operator's key file in custom_assets/operator/, or None. Raises if there is more than one."""
    files = sorted(p for p in OPERATOR_DIR.glob("*") if p.is_file() and p.suffix.lower() in KEY_SUFFIXES) \
        if OPERATOR_DIR.exists() else []
    if len(files) > 1:
        raise HomeError(f"{OPERATOR_DIR} holds {len(files)} key files ({', '.join(p.name for p in files)}). "
                        "Leave only the operator's key")
    return files[0] if files else None


class Home:
    def __init__(self, path: Path = BUILD_SYSTEM):
        self.path = Path(path).resolve()
        self.keys = self.path / "keys"
        self.declarations = self.path / "declarations"
        self.out = self.path / "out"

    def file(self, name: str) -> Path:
        return self.path / name

    def require(self):
        if not self.file("identity.json").exists():
            raise HomeError(f"no agent data in {self.path}. New agent: agentid setup. "
                            "Agent already published: agentid import site <URL>")

    def identity(self) -> dict:
        self.require()
        return json.loads(self.file("identity.json").read_text(encoding="utf-8"))

    def revocations(self) -> list:
        path = self.file("revocations.json")
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def domain(self) -> str:
        return self.identity()["domain"]

    def operator_key(self) -> bytes:
        path = operator_key_file()
        if not path:
            raise HomeError(f"the operator's OpenPGP public key is missing from {OPERATOR_DIR}. Ask the operator "
                            "for it, then: agentid import gpg --stdin (or --file FILE)")
        return path.read_bytes()

    def operator_fingerprint(self) -> str:
        return key_fingerprint(self.operator_key())

    def write_json(self, name: str, data):
        self.path.mkdir(parents=True, exist_ok=True)
        self.file(name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8", newline="\n")

    def clean(self) -> list:
        """Empties build_system/ (all but identity.example.json) and output_website/ (all but .gitkeep).
        Returns the paths removed, relative to the repository."""
        keep = {self.path: EXAMPLE_IDENTITY.name, OUTPUT_WEBSITE: ".gitkeep"}
        targets = [p for folder, kept in keep.items() if folder.exists()
                   for p in sorted(folder.iterdir()) if p.name != kept]
        for p in targets:
            if p.is_dir() and not p.is_symlink():
                shutil.rmtree(p)
            else:
                p.unlink()
        return [str(p.relative_to(ROOT)) for p in targets]

    # ── Declarations ────────────────────────────────────────────────────
    def declaration_path(self, number: int, signed: bool = False) -> Path:
        return self.declarations / f"{number:04d}.txt{'.asc' if signed else ''}"

    def last_signed(self) -> int:
        signed = sorted(self.declarations.glob("*.txt.asc")) if self.declarations.exists() else []
        return int(signed[-1].name.split(".")[0]) if signed else 0

    def pending(self):
        """Number of the declaration waiting for the operator's signature, or None."""
        n = self.last_signed() + 1
        return n if self.declaration_path(n).exists() else None
