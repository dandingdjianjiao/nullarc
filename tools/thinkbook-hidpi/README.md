# ThinkBook 14+ 8845H: 12-byte HiDPI override experiment

This experiment has been prepared and checked, **not installed or proven to enable HiDPI**. The running driver stays at the original PhxAccel 0.1. No driver build is required.

The current macOS Tahoe 26.7.2 / 25G332 observations are:

- CoreDisplay reads the original 384-byte LEN145-3K EDID and `DisplayIsTV=false` from the existing user-installed override.
- Public CoreGraphics exposes only 3072×1920 at 1×, flags `0x00100007`.
- Private CGS enumeration has a 1536×960 density-2 candidate, flags `0x80100000`; this does not prove that the mode can be selected.
- The kernel's `IOFBConfig` still has `IOFBtv=Yes`, despite the user-space DisplayIsTV override.

Thus EDID injection was adopted; failure to obtain a selectable HiDPI mode is a separate step. Repeating the same EDID injection is not an informative next test.

## Single change

The existing `scale-resolutions` array has both 12-byte and 16-byte forms for the same 3072×1920 backing size. The new profile keeps only the 12-byte big-endian `(3072, 1920, 1)` entry. The original EDID, IDs, display name and `DisplayIsTV=false` remain identical after plist parsing. No timings are selected or programmed.

This tests an override-format hypothesis, not a proven root cause. [Reports in the related NVIDIA driver](https://github.com/nullmoth/nvidia-macos-driver/issues/354) describe both successful and unsuccessful 12-byte results on Tahoe. They do not establish that PhxAMDFB will behave the same way. [one-key-hidpi](https://github.com/xzhih/one-key-hidpi/blob/master/hidpi.sh) is the format reference; no online script is executed.

## Check and install

From `/Users/wa/AMDGPU_Hackintosh/nullarc`:

```sh
/usr/bin/python3 tools/thinkbook-hidpi/hidpi.py --check
sudo /usr/bin/python3 tools/thinkbook-hidpi/hidpi.py install
```

Run the sudo command in your own terminal. The helper requires the exact previously measured profile hash and original driver binary. It saves the original file in one rollback location and atomically replaces only:

`/Library/Displays/Contents/Resources/Overrides/DisplayVendorID-756e6b6e/DisplayProductID-717`

It does not change EFI, kexts, AuxKC, preferences, NVRAM, brightness, or hardware timings; it does not select a display mode, restart WindowServer, or reboot. The upstream source update also remains uninstalled.

After a normal reboot at your chosen time, run `--check` again. Success requires a **publicly selectable** mode with logical 1536×960 and pixels 3072×1920. A matching `current` mode means it is active. An on-disk profile or private density-2 candidate alone is insufficient.

## Exact rollback

```sh
sudo /usr/bin/python3 tools/thinkbook-hidpi/hidpi.py remove
```

Then reboot normally when convenient. This restores the preceding EDID+monitor override byte-for-byte. Existing `hidpi-monitor.sh`, `hidpi-edid.sh` and `hidpi-override.sh` recovery records are untouched. Undo this experiment before undoing those older layers.

The helper refuses unknown or externally changed files, symlinked paths and damaged recovery state. Rollback does not require the GUI or live display detection.

## Next decision

If the 12-byte-only profile is read by CoreDisplay but still exposes no public HiDPI mode, retain that result and evaluate PhxAMDFB's mode capability/validation separately. Do not restore the withdrawn driver-level EDID injection. Latest upstream PhxAMDFB also adds PWM backlight handling for a different machine; no full-driver deployment is authorized by this external-override experiment.
