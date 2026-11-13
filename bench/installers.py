"""Downloads, verifies and unpacks the third-party apps for the benchmark VM (spec §13.17)."""

import hashlib
import json
import plistlib
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

REPO = Path(__file__).resolve().parent.parent
SOURCES = REPO / "data" / "third-party-sources.json"
INSTALLERS = REPO / "installers"  # gitignored; archived privately
APPS_OUT = INSTALLERS / "apps"


@dataclass(frozen=True)
class CodesignInfo:
    identifier: str
    team_id: str
    signer: str


@dataclass(frozen=True)
class AppRecord:
    name: str
    bundle_id: str
    version: str
    source_url: str
    installer_sha256: str
    team_id: str
    signer: str
    notarized: bool
    install_method: str


def parse_codesign(text: str) -> CodesignInfo:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        key, _, value = line.partition("=")
        if key in ("Identifier", "TeamIdentifier") or (
            key == "Authority" and "signer" not in fields
        ):
            fields["signer" if key == "Authority" else key] = value.strip()
    return CodesignInfo(fields["Identifier"], fields["TeamIdentifier"], fields["signer"])


def parse_spctl(text: str) -> bool:
    return ": accepted" in text and "source=Notarized Developer ID" in text


def public_url(url: str) -> str:
    """Drops query strings and fragments (CDN links carry signed, expiring tokens)."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True)


def download(url: str, dest: Path) -> str:
    """Resumable download; returns the final URL after redirects. Reuses a finished file."""
    if dest.exists() and dest.stat().st_size > 0:
        head = _run("curl", "-sIL", "-o", "/dev/null", "-w", "%{url_effective}", url)
        return head.stdout.strip()
    result = _run(
        "curl",
        "-sSL",
        "-C",
        "-",
        "--retry",
        "10",
        "--retry-all-errors",
        "-o",
        str(dest),
        "-w",
        "%{url_effective}",
        url,
    )
    if result.returncode != 0:
        raise RuntimeError(f"download failed for {url}: {result.stderr.strip()}")
    return result.stdout.strip()


def extract_app(installer: Path, out_dir: Path) -> Path:
    """Unpacks the .app keeping its original file name (it may contain invisible characters)."""
    work = out_dir / f".unpack-{installer.stem}"
    _run("rm", "-rf", str(work))
    work.mkdir(parents=True)
    if installer.suffix == ".zip":
        result = _run("ditto", "-x", "-k", str(installer), str(work))
        if result.returncode != 0:
            raise RuntimeError(f"cannot unzip {installer.name}: {result.stderr.strip()}")
    else:
        mount = out_dir / f".mnt-{installer.stem}"
        mount.mkdir(exist_ok=True)
        attach = subprocess.run(
            [
                "hdiutil",
                "attach",
                "-nobrowse",
                "-readonly",
                "-mountpoint",
                str(mount),
                str(installer),
            ],
            input="Y\n",
            capture_output=True,
            text=True,
        )
        if attach.returncode != 0:
            raise RuntimeError(f"cannot mount {installer.name}: {attach.stderr.strip()}")
        try:
            apps = sorted(mount.glob("*.app"))
            if not apps:
                raise RuntimeError(f"no .app inside {installer.name}")
            _run("ditto", str(apps[0]), str(work / apps[0].name))
        finally:
            _run("hdiutil", "detach", "-quiet", str(mount))
            mount.rmdir()
    found = sorted(work.glob("*.app"))
    if len(found) != 1:
        raise RuntimeError(f"expected one .app from {installer.name}, found {found}")
    target = out_dir / found[0].name
    _run("rm", "-rf", str(target))
    found[0].rename(target)
    work.rmdir()
    return target


def verify(app: Path) -> tuple[CodesignInfo, bool, str]:
    # Not --strict: vendor images can carry Finder metadata (Chrome does, straight from Google's
    # DMG) that --strict rejects even though the signature and notarization are valid.
    check = _run("codesign", "--verify", "--deep", str(app))
    if check.returncode != 0:
        raise RuntimeError(f"code signature invalid for {app.name}: {check.stderr.strip()}")
    info = parse_codesign(_run("codesign", "-dv", "--verbose=2", str(app)).stderr)
    notarized = parse_spctl(_run("spctl", "--assess", "--type", "execute", "-vv", str(app)).stderr)
    plist = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    version = str(plist.get("CFBundleShortVersionString", plist.get("CFBundleVersion", "?")))
    return info, notarized, version


def install_commands(installers: list[str], share: str) -> list[str]:
    """Guest commands that unpack each verified installer into /Applications. Nothing is launched.

    Unpacking happens inside the guest because the shared folder breaks bundle symlinks.
    """
    cmds: list[str] = []
    for name in installers:
        src = f"'{share}/{name}'"
        if name.endswith(".zip"):
            cmds.append(f"ditto -x -k {src} /Applications/")
        else:
            mnt = f"/tmp/mnt-{Path(name).stem}"
            cmds.append(
                f"mkdir -p {mnt} && hdiutil attach -nobrowse -readonly -mountpoint {mnt} {src} "
                f"</dev/null >/dev/null && app=$(ls -d {mnt}/*.app | head -1) && "
                f'ditto "$app" "/Applications/$(basename "$app")"; rc=$?; '
                f"hdiutil detach -quiet {mnt}; exit $rc"
            )
    return cmds


def prepare_all() -> list[AppRecord]:
    sources = json.loads(SOURCES.read_text())["apps"]
    INSTALLERS.mkdir(exist_ok=True)
    records: list[AppRecord] = []
    for src in sources:
        installer = INSTALLERS / f"{src['key']}{src['format']}"
        final_url = download(src["url"], installer)
        app = extract_app(installer, APPS_OUT)
        info, notarized, version = verify(app)
        if info.identifier != src["bundle_id"]:
            raise RuntimeError(f"{app.name}: bundle id {info.identifier} != {src['bundle_id']}")
        if not notarized:
            raise RuntimeError(f"{app.name}: not accepted as a notarized Developer ID app")
        records.append(
            AppRecord(
                name=app.stem,
                bundle_id=info.identifier,
                version=version,
                source_url=public_url(final_url),
                installer_sha256=hashlib.sha256(installer.read_bytes()).hexdigest(),
                team_id=info.team_id,
                signer=info.signer,
                notarized=notarized,
                install_method="copied .app into /Applications in the VM; never opened",
            )
        )
        print(f"ok {app.name!r} {version} {info.team_id}", flush=True)
    return records


if __name__ == "__main__":
    out = REPO / "data" / "third-party.json"
    out.write_text(json.dumps([asdict(r) for r in prepare_all()], indent=2) + "\n")
    sys.exit(0)
