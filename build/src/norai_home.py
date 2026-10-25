"""The agent's own folder ("home"): everything that belongs to one agent, outside the tool.

The tool (this repository) holds no data about any agent. Each agent keeps its data in a
folder of its persistent storage, given by --home or by the AGENT_ID_HOME variable:

  <home>/
    identity.json              public data about the agent and its operator
    operator.asc               the operator's OpenPGP public key
    settings.json              local settings, not published: {"site_dir": "..."}
    site/                      the website, unless settings.json points elsewhere
    revocations.json           keys withdrawn before expiry (written by agentid.py keys)
    keys/                      the agent's private keys, encrypted
    declarations/0001.txt      each declaration given to the operator to sign...
    declarations/0001.txt.asc  ...and the signature the operator sent back
    out/                       DNS records and a preview of the page
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # the tool's repository
BUILD = ROOT / "build"
EXAMPLE_IDENTITY = BUILD / "identity.example.json"
DEMO_HOME = BUILD / "demo"
HOME_ENV = "AGENT_ID_HOME"
DEFAULT_HOME = Path.home() / ".agent-id"


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


def key_fingerprint(armored: bytes) -> str:
    """Primary-key fingerprint of an OpenPGP public key, without importing it anywhere."""
    with tempfile.TemporaryDirectory() as tmp:
        out = gpg(["--with-colons", "--import-options", "show-only", "--import"], tmp, input=armored,
                  check=False).stdout.decode()
    fprs = [line.split(":")[9] for line in out.splitlines() if line.startswith("fpr:")]
    if not fprs:
        raise HomeError("the operator key file does not contain an OpenPGP public key")
    return fprs[0].upper()


class Home:
    def __init__(self, path: Path):
        self.path = Path(path).expanduser().resolve()
        self.keys = self.path / "keys"
        self.declarations = self.path / "declarations"
        self.out = self.path / "out"

    @classmethod
    def resolve(cls, arg=None) -> "Home":
        return cls(arg or os.environ.get(HOME_ENV) or DEFAULT_HOME)

    def file(self, name: str) -> Path:
        return self.path / name

    def require(self):
        if not self.file("identity.json").exists():
            raise HomeError(f"no agent data in {self.path}. Run: python3 build/src/agentid.py setup")

    def identity(self) -> dict:
        self.require()
        return json.loads(self.file("identity.json").read_text(encoding="utf-8"))

    def settings(self) -> dict:
        path = self.file("settings.json")
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def site_dir(self) -> Path:
        return Path(self.settings().get("site_dir") or self.path / "site").expanduser().resolve()

    def revocations(self) -> list:
        path = self.file("revocations.json")
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def operator_key(self) -> bytes:
        path = self.file("operator.asc")
        if not path.exists():
            raise HomeError(f"missing {path}: the operator's OpenPGP public key")
        return path.read_bytes()

    def operator_fingerprint(self) -> str:
        return key_fingerprint(self.operator_key())

    def write_json(self, name: str, data):
        self.path.mkdir(parents=True, exist_ok=True)
        self.file(name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8", newline="\n")

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
