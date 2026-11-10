# ThinkBook native HiDPI: observed result and next display checkpoint

Status: read-only observations on 2026-11-10 (ThinkBook 14+ Ryzen 7 8845H / Radeon 780M `1002:1900`, macOS 26.7.2 build 25G332). The user confirmed that HiDPI is working. This is a hardware-specific result, **not** a promise of mode availability on every panel or a validation of other scaling ratios.

## Provenance and result

- The installed and loaded PhxAccel is the separately built/ad-hoc-signed test candidate from commit `1a3623c6b6f9ba729dd5f19d6e1a442c54e77fcc`: its executable SHA256 is `1cb7abab99f7b25c7a4d0110149f1bb4ed2c82b29d4f774ddce03242451e517f`. Its *installed* bundle version is 0.1.2. This source branch subsequently restored `Info.plist` to the upstream version; rebuilding this branch is **not** the already installed binary. The running PhxBringup remains 1.0.0; no EFI/override/Metal plugin/RADV change was part of the candidate.
- The active `NSScreen` has logical size **1536×960**, backing **3072×1920**, and `backingScaleFactor=2`. Public CoreGraphics enumeration contains both a 3072×1920 1× mode and a **usable** 1536×960 2× mode with 3072×1920 pixels; the latter is current. Both share native mode ID 1. The framebuffer still describes a 3072×1920 scan-out with 3232×2000 H/V totals. This validates native backing geometry without introducing a second physical timing.
- Public flags are `0x00900007` (native logical 1×) and `0x00900003` (current 2×). The existing Television bit and `IOFBtv=Yes` **remain**; they did not prevent this tested 2× mode. The candidate's only experimental mode capability bit is `kDisplayModeValidForHiResFlag=0x00800000` in `getInformationForDisplayMode`. This result supports the flag as sufficient **in this configuration**, not a universal explanation of CoreDisplay's internal validation.
- Direct kernel EDID is still absent. CoreDisplay still reads the existing 384-byte real panel EDID and two scale-resolution entries from the user override. Thus no newly fabricated driver DDC/EDID path was required for this result.
- Read-only/offscreen Metal checks passed for private and IOSurface-backed textures at 3072×1920 and 3840×2400. Display-copy successful transactions increased from 1969 to 2068 over 3 seconds, while `debug.nvaccel_iop_fail` remained zero. This is a brief smoke test, not a sleep/wake or long-duration stability result.

## Open issue before claiming the original 60 Hz target

At this boot `PhxFBRefreshMilliHz=54985` and public CoreGraphics refresh is **55.0000 Hz**, whereas the pre-candidate baseline reported 60 Hz. H/V totals still read 3232×2000. The current driver samples the OTG frame counter over roughly 200 ms and derives a VBL timer rate; a count/scheduling error is plausible, but **actual physical panel refresh/pixel clock was not independently measured**. Do not claim this boot met 60 Hz, and do not change clock registers, EDID timing or scan-out dimensions based on this one result. Preserve current working HiDPI and investigate refresh separately.

The legacy `scripts/hidpi-monitor.sh --check` stopped at its AppleDisplay identity guard (`Cannot parse a NULL or zero-length data`, `Display vendor changed`) after the new boot; independent CoreGraphics and CoreDisplay probes succeeded and still reported vendor `0x756e6b6e` / product `0x717`. Do not weaken the install/remove safety guard to make a read-only report pass; use the independent probes until a separate read-only monitor adaptation is justified.

## Maintainer roadmap alignment / selected next need

[`docs/roadmap.md`](roadmap.md) specifies an evidence-first progression: Stage 0 verifies the hardware and safe recovery channel; Stage 1 isolates host-testable logic; Stage 5 validates DCN scan-out and timings before depending on the Stage 6 user graphics stack. The reference machine's `README.md` status has advanced beyond the roadmap's initial phases, so this is an **adaptation of the method to this ThinkBook**, not a claim that the maintainer has assigned a new HiDPI or 55 Hz milestone.

**Next bounded checkpoint: verify and, only if needed, correct the framebuffer's refresh measurement/reporting.** First collect repeated non-invasive OTG frame-counter samples over a longer interval and compare them with reported `PhxFBRefreshMilliHz`, CoreGraphics refresh, physical H/V totals and display-copy errors across a stable boot. Distinguish a coarse 200 ms measurement artefact from an actual timing change. Only then propose a small timing-reporting fix with a host-testable estimator and a controlled x86_64 build; leave panel PLL/PHY programming, 120 Hz, arbitrary downscaling and backlight untouched. Acceptance is a consistent ~60 Hz report corroborated by independent observations, while 1536×960@2×/3072×1920 backing and zero copy errors remain intact.

No installation, AuxKC update, mode switch, NVRAM/EFI edit or reboot is performed by this record.
