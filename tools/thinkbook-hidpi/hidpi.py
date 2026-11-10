#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""One-display, reversible 12-byte scale-resolutions experiment; default is read-only."""

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import struct
import subprocess
import sys
import tempfile


PANEL_SHA = "5fbe2ea1d53fc96a951f4317ada295b327b77b76f7d9a9a5830f3b98e0625e74"
DRIVER_SHA = "5ca915cbb5dbd0e6a86f68264e26b49451e407eaf38b17ce549054cde81a2cf8"
SCALE = struct.pack(">III", 3072, 1920, 1)


@dataclasses.dataclass(frozen=True)
class Config:
    target: Path
    state: Path
    payload: Path
    base_sha: str
    payload_sha: str


CONFIG = Config(
    Path("/Library/Displays/Contents/Resources/Overrides/DisplayVendorID-756e6b6e/DisplayProductID-717"),
    Path("/Library/Application Support/ThinkBookHiDPI/tahoe12-756e6b6e-717"),
    Path(__file__).resolve().parent / "profiles/DisplayProductID-717",
    "d04f680cfa3079cc75923d3038bb9c3a5eaab505f6663482e8bffa567f44f876",
    "c630ed20084c61e115d3db95cdf8878ee6b002a1973f182d7aa5a6453245528c",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    return digest(path.read_bytes())


def fail(message):
    raise RuntimeError(message)


def require_root():
    if os.geteuid() != 0:
        fail("Run install/remove with sudo in your own terminal; no changes made.")


def check_paths(config):
    for leaf in (config.target, config.state / "previous-override", config.state / "state.json"):
        for path in (leaf, *leaf.parents):
            if path.is_symlink():
                fail("Refusing symlink: " + str(path))
    if not config.target.parent.is_dir() or not config.state.parent.is_dir():
        fail("Existing override and ThinkBookHiDPI state directories are required.")


def verify_payload(config):
    if config.payload.is_symlink() or not config.payload.is_file():
        fail("Payload is missing or symlinked.")
    data = config.payload.read_bytes()
    if digest(data) != config.payload_sha:
        fail("Payload hash mismatch.")
    profile = plistlib.loads(data)
    if (profile.get("DisplayVendorID"), profile.get("DisplayProductID")) != (0x756E6B6E, 0x717):
        fail("Unexpected display identity in payload.")
    edid = profile.get("IODisplayEDID", b"")
    if digest(edid) != PANEL_SHA or len(edid) != 384:
        fail("Payload does not contain the original panel EDID.")
    if profile.get("DisplayIsTV") is not False or profile.get("scale-resolutions") != [SCALE]:
        fail("Expected DisplayIsTV=false and one 3072x1920x1 12-byte scale entry.")
    return data


def registry(service):
    result = subprocess.run(
        ["/usr/sbin/ioreg", "-r", "-c", service, "-d", "1", "-a", "-l", "-w0"],
        check=True, stdout=subprocess.PIPE,
    )
    return plistlib.loads(result.stdout)


def verify_display():
    if platform.system() != "Darwin" or platform.machine() != "x86_64":
        fail("This experiment targets only the x86_64 ThinkBook test machine.")
    displays, framebuffers = registry("AppleDisplay"), registry("PhxAMDFB")
    if len(displays) != 1 or len(framebuffers) != 1:
        fail("Expected exactly one AppleDisplay and one PhxAMDFB.")
    if (displays[0].get("DisplayVendorID"), displays[0].get("DisplayProductID")) != (0x756E6B6E, 0x717):
        fail("Runtime display identity changed.")
    fb = framebuffers[0]
    if (fb.get("PhxFBWidth"), fb.get("PhxFBHeight")) != (3072, 1920) or not fb.get("built-in"):
        fail("Expected the built-in 3072x1920 framebuffer.")
    driver = Path("/Library/Extensions/PhxAccel.kext/Contents/MacOS/PhxAccel")
    if file_sha(driver) != DRIVER_SHA:
        fail("Installed PhxAccel differs from the original 0.1 test baseline.")


def state_record(config):
    return {"format": 1, "target": str(config.target), "previous_sha256": config.base_sha,
            "installed_sha256": config.payload_sha}


def verify_state(config):
    if not config.state.is_dir() or config.state.stat().st_mode & 0o077:
        fail("Missing or unsafe rollback state directory.")
    previous, meta = config.state / "previous-override", config.state / "state.json"
    if not previous.is_file() or not meta.is_file():
        fail("Incomplete rollback state; original override has not been overwritten by this run.")
    if file_sha(previous) != config.base_sha or json.loads(meta.read_text()) != state_record(config):
        fail("Rollback state is damaged or belongs to a different experiment.")
    return previous.read_bytes()


def exclusive_file(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def replace_override(config, data, expected_sha):
    fd, temporary = tempfile.mkstemp(prefix=".thinkbook-tahoe12-", dir=str(config.target.parent))
    temporary = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            os.fsync(stream.fileno())
        check_paths(config)
        actual = file_sha(config.target) if config.target.is_file() else None
        if actual != expected_sha:
            fail("Override changed during preparation; not replaced.")
        os.replace(temporary, config.target)
        if config.target.read_bytes() != data:
            fail("Readback mismatch; keep the rollback state and inspect before continuing.")
    finally:
        if temporary.exists():
            temporary.unlink()


def install(config=CONFIG):
    require_root()
    check_paths(config)
    payload = verify_payload(config)
    verify_display()
    current = file_sha(config.target)
    if current == config.payload_sha:
        verify_state(config)
        print("12-byte-only profile already installed; no changes.")
        return
    if current != config.base_sha:
        fail("Current override differs from the known EDID+monitor profile; not overwritten.")
    # Confirm that scale-resolutions is the only effective plist difference.
    before, after = plistlib.loads(config.target.read_bytes()), plistlib.loads(payload)
    changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    if changed != {"scale-resolutions"}:
        fail("Unexpected profile differences; nothing changed.")
    if config.state.exists():
        verify_state(config)
    else:
        config.state.mkdir(mode=0o700)
        exclusive_file(config.state / "previous-override", config.target.read_bytes())
        exclusive_file(config.state / "state.json", (json.dumps(state_record(config), sort_keys=True) + "\n").encode())
        verify_state(config)
    replace_override(config, payload, config.base_sha)
    print("12-byte-only profile installed and read back. HiDPI is NOT yet verified.")
    print("Reboot normally when convenient, then run --check as your normal user.")


def remove(config=CONFIG):
    require_root()
    check_paths(config)
    current = file_sha(config.target) if config.target.is_file() else None
    if not config.state.exists():
        if current == config.base_sha:
            print("Already on the previous EDID+monitor profile; no changes.")
            return
        fail("No rollback state; nothing changed.")
    previous = verify_state(config)
    if current not in (config.base_sha, config.payload_sha, None):
        fail("Override changed after installation; not overwritten.")
    replace_override(config, previous, current)
    (config.state / "previous-override").unlink()
    (config.state / "state.json").unlink()
    config.state.rmdir()
    print("Previous EDID+monitor profile restored byte-for-byte. Reboot normally when convenient.")


def check(config=CONFIG):
    check_paths(config)
    verify_payload(config)
    verify_display()
    current = file_sha(config.target)
    status = {config.base_sha: "previous EDID+monitor profile; 12-byte test NOT installed",
              config.payload_sha: "12-byte test file installed; live mode still requires verification"}
    print("On-disk profile: " + status.get(current, "unknown; automatic replacement will be refused"))
    print("On-disk SHA256: " + current)
    profile = plistlib.loads(config.target.read_bytes())
    print("scale-resolutions lengths: " + str([len(entry) for entry in profile.get("scale-resolutions", [])]))
    probe = Path("/Users/wa/nullarc-probe-20261109/display-override-probe")
    if os.geteuid() != 0 and probe.is_file() and os.access(probe, os.X_OK):
        sys.stdout.flush()
        subprocess.run([str(probe)], check=True)
    print("Read-only check; no files, display modes or settings changed.")


def main():
    actions = {"--check": check, "install": install, "remove": remove}
    mode = sys.argv[1] if len(sys.argv) == 2 else "--check"
    if len(sys.argv) > 2 or mode not in actions:
        print("Usage: python3 hidpi.py [--check|install|remove]", file=sys.stderr)
        return 2
    try:
        actions[mode]()
    except (RuntimeError, OSError, ValueError, plistlib.InvalidFileException, subprocess.SubprocessError) as error:
        print("Stopped: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
