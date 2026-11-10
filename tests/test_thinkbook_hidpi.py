"""Filesystem lifecycle checks for the root-only display override helper.

All writes use temporary directories; root and hardware checks are mocked.
No kext compilation or display configuration calls occur.
"""
import dataclasses
import hashlib
import importlib.util
from pathlib import Path
import plistlib
import struct
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("thinkbook_hidpi", ROOT / "tools/thinkbook-hidpi/hidpi.py")
hidpi = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hidpi)


class OverrideLifecycle(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="thinkbook-hidpi-test-")
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name).resolve()
        target = base / "Overrides/DisplayVendorID-756e6b6e/DisplayProductID-717"
        target.parent.mkdir(parents=True)
        state_parent = base / "State"
        state_parent.mkdir()
        candidate = hidpi.CONFIG.payload.read_bytes()
        before = plistlib.loads(candidate)
        before["scale-resolutions"].append(struct.pack(">IIII", 3072, 1920, 1, 0x00200000))
        self.original = plistlib.dumps(before, sort_keys=True)
        target.write_bytes(self.original)
        self.config = dataclasses.replace(hidpi.CONFIG, target=target, state=state_parent / "tahoe12",
                                          base_sha=hashlib.sha256(self.original).hexdigest())
        for name in ("require_root", "verify_display"):
            patcher = mock.patch.object(hidpi, name)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_install_is_idempotent_and_rollback_is_exact(self):
        hidpi.install(self.config)
        state_files = {p.name: p.read_bytes() for p in self.config.state.iterdir()}
        hidpi.install(self.config)
        self.assertEqual(state_files, {p.name: p.read_bytes() for p in self.config.state.iterdir()})
        self.assertEqual(self.config.target.read_bytes(), self.config.payload.read_bytes())
        hidpi.remove(self.config)
        self.assertEqual(self.config.target.read_bytes(), self.original)
        self.assertFalse(self.config.state.exists())
        hidpi.remove(self.config)

    def test_install_refuses_unrecognized_existing_profile(self):
        self.config.target.write_bytes(b"user's unrelated override")
        with self.assertRaisesRegex(RuntimeError, "differs"):
            hidpi.install(self.config)
        self.assertEqual(self.config.target.read_bytes(), b"user's unrelated override")
        self.assertFalse(self.config.state.exists())

    def test_rollback_refuses_newer_external_change(self):
        hidpi.install(self.config)
        self.config.target.write_bytes(b"another experiment")
        with self.assertRaisesRegex(RuntimeError, "changed after"):
            hidpi.remove(self.config)
        self.assertEqual(self.config.target.read_bytes(), b"another experiment")
        self.assertTrue(self.config.state.exists())

    def test_interrupted_state_keeps_original_file(self):
        self.config.state.mkdir(mode=0o700)
        (self.config.state / "previous-override").write_bytes(self.original)
        with self.assertRaisesRegex(RuntimeError, "Incomplete"):
            hidpi.install(self.config)
        self.assertEqual(self.config.target.read_bytes(), self.original)

    def test_tampered_rollback_is_rejected(self):
        hidpi.install(self.config)
        (self.config.state / "previous-override").write_bytes(b"corrupt backup")
        with self.assertRaisesRegex(RuntimeError, "damaged"):
            hidpi.remove(self.config)
        self.assertEqual(self.config.target.read_bytes(), self.config.payload.read_bytes())

    def test_symlink_parent_is_rejected(self):
        directory = self.config.target.parent
        saved = directory.with_name("real-vendor-directory")
        directory.rename(saved)
        directory.symlink_to(saved, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            hidpi.install(self.config)
        self.assertEqual(self.config.target.read_bytes(), self.original)

    def test_damaged_payload_never_creates_state(self):
        payload = self.config.state.parent / "broken-payload"
        payload.write_bytes(self.config.payload.read_bytes() + b" ")
        config = dataclasses.replace(self.config, payload=payload)
        with self.assertRaisesRegex(RuntimeError, "Payload hash"):
            hidpi.install(config)
        self.assertFalse(config.state.exists())
        self.assertEqual(config.target.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
