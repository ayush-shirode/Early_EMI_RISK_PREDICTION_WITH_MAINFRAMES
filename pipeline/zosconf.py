"""Where the mainframe is and who we are on it: host, ports, user ID, password.

Non-secret settings live in ~/.config/ews/zos.json. The password lives in the OS
keyring (Secret Service on Linux, Keychain on macOS) under the service "ews-zos".
Environment variables override both, which is handy for CI:
EWS_ZOS_HOST, EWS_ZOS_PORT, EWS_ZOS_USER, EWS_ZOS_PASSWORD, EWS_SSH_PORT, EWS_ZOS_VERIFY.

    python -m pipeline.zosconf login               # prompt, test and save
    python -m pipeline.zosconf login --from-zowe   # copy an existing Zowe setup once
    python -m pipeline.zosconf show
    python -m pipeline.zosconf logout
"""
from __future__ import annotations

import base64
import getpass
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("EWS_CONFIG_DIR", Path.home() / ".config" / "ews"))
CONFIG_FILE = CONFIG_DIR / "zos.json"
KNOWN_HOSTS = CONFIG_DIR / "known_hosts"     # SSH host keys we have accepted
KEYRING_SERVICE = "ews-zos"

_generation = 0  # bumped on login/logout so open sessions in this process re-authenticate


class NotConfigured(RuntimeError):
    pass


@dataclass
class Settings:
    host: str
    port: int = 10443
    user: str = ""
    ssh_port: int = 22
    verify: bool = True      # verify the z/OSMF TLS certificate (Z Xplore uses a self-signed one)

    @property
    def base_url(self) -> str:
        return f"https://{self.host}:{self.port}"


def generation() -> int:
    return _generation


def load() -> Settings:
    data: dict = {}
    if CONFIG_FILE.exists():
        data = json.loads(CONFIG_FILE.read_text())
    env = {
        "host": os.environ.get("EWS_ZOS_HOST"), "port": os.environ.get("EWS_ZOS_PORT"),
        "user": os.environ.get("EWS_ZOS_USER"), "ssh_port": os.environ.get("EWS_SSH_PORT"),
        "verify": os.environ.get("EWS_ZOS_VERIFY"),
    }
    data.update({k: v for k, v in env.items() if v})
    if not data.get("host") or not data.get("user"):
        raise NotConfigured("Mainframe connection not configured. Log on first: make login (or LOGON in the TUI).")
    verify = data.get("verify", True)
    if isinstance(verify, str):
        verify = verify.lower() not in ("0", "false", "no")
    return Settings(host=data["host"], port=int(data.get("port", 10443)), user=str(data["user"]).upper(),
                    ssh_port=int(data.get("ssh_port", 22)), verify=bool(verify))


def is_configured() -> bool:
    try:
        s = load()
    except NotConfigured:
        return False
    return bool(password(s))


def password(s: Settings) -> str | None:
    if os.environ.get("EWS_ZOS_PASSWORD"):
        return os.environ["EWS_ZOS_PASSWORD"]
    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, s.user)
    except Exception:  # no keyring backend available
        return None


def save(s: Settings, pw: str | None) -> None:
    global _generation
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    s.user = s.user.upper()
    CONFIG_FILE.write_text(json.dumps(asdict(s), indent=2) + "\n")
    if pw:
        import keyring
        keyring.set_password(KEYRING_SERVICE, s.user, pw)
    _generation += 1


def logout() -> None:
    global _generation
    try:
        s = load()
        import keyring
        keyring.delete_password(KEYRING_SERVICE, s.user)
    except Exception:
        pass
    _generation += 1


def from_zowe() -> tuple[Settings, str]:
    """Read host/ports from ~/.zowe/zowe.config.json and user/password from Zowe's secure store.

    Only used once, to migrate an existing Zowe setup; nothing calls Zowe afterwards.
    """
    cfg = json.loads((Path.home() / ".zowe" / "zowe.config.json").read_text())
    profiles = cfg.get("profiles", {})
    props = {}
    for p in profiles.values():
        props.setdefault(p.get("type"), p.get("properties", {}))
    base, zosmf, ssh = props.get("base", {}), props.get("zosmf", {}), props.get("ssh", {})

    import secretstorage
    con = secretstorage.dbus_init()
    coll = secretstorage.get_default_collection(con)
    item = next(coll.search_items({"service": "Zowe", "account": "secure_config_props"}), None)
    if item is None:
        raise RuntimeError("No Zowe credentials found in the keyring")
    raw = item.get_secret().decode()
    try:
        secure = json.loads(raw)
    except json.JSONDecodeError:
        secure = json.loads(base64.b64decode(raw))
    user = pw = None
    for values in secure.values():
        for k, v in values.items():
            if k.endswith(".user"):
                user = user or v
            elif k.endswith(".password"):
                pw = pw or v
    if not (user and pw):
        raise RuntimeError("Zowe secure store has no user/password")
    s = Settings(host=zosmf.get("host") or base.get("host"), port=int(zosmf.get("port", 10443)), user=user,
                 ssh_port=int(ssh.get("port", 22)),
                 verify=bool(zosmf.get("rejectUnauthorized", base.get("rejectUnauthorized", True))))
    return s, pw


def _cli() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "show":
        try:
            s = load()
        except NotConfigured as e:
            print(e)
            sys.exit(1)
        print(json.dumps(asdict(s), indent=2))
        print("password:", "stored" if password(s) else "MISSING")
        return
    if cmd == "logout":
        logout()
        print("Password removed from the keyring.")
        return
    if cmd != "login":
        print(__doc__)
        sys.exit(2)
    if "--from-zowe" in sys.argv:
        s, pw = from_zowe()
        print(f"Imported {s.user}@{s.host}:{s.port} (ssh {s.ssh_port}, verify TLS {s.verify}) from Zowe")
    else:
        try:
            cur = load()
        except NotConfigured:
            cur = Settings(host="")
        host = input(f"z/OSMF host [{cur.host}]: ").strip() or cur.host
        port = int(input(f"z/OSMF port [{cur.port}]: ").strip() or cur.port)
        ssh_port = int(input(f"SSH port [{cur.ssh_port}]: ").strip() or cur.ssh_port)
        user = (input(f"User ID [{cur.user}]: ").strip() or cur.user).upper()
        verify = input(f"Verify TLS certificate? (n for self-signed) [{'Y' if cur.verify else 'N'}]: ").strip().lower()
        pw = getpass.getpass("Password: ")
        s = Settings(host=host, port=port, user=user, ssh_port=ssh_port,
                     verify=cur.verify if not verify else verify.startswith("y"))
    save(s, pw)
    from pipeline import zos
    info = zos.check_status()
    print(f"Logged on: {info['user']} at {info['system']} (z/OS {info['zos_version']}, z/OSMF {info['zosmf_version']})")


if __name__ == "__main__":
    _cli()
