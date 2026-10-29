# Galaxy M55 (m55xq) UN1CA 8 port — work in progress

**Base layout:** UN1CA `sixteen` (One UI 8 / Android 16) `system` and `product`; Samsung SM-M556B **One UI 7 / Android 15** `vendor`, `odm`, and hardware configs. Proven working patched boot-chain supplied separately.

This fork intentionally has **one device target only**: `target/m55xq`. Upstream targets remain available at https://github.com/salvogiangri/UN1CA/tree/sixteen/target.

## Current status
- Port skeleton and boot-chain overlay added; **not boot tested**. The original upstream UN1CA build pipeline now lives in manual-only `.github/workflows/ci.yml`, with M55-specific safeguards.
- Existing local images: `boot.img`, `dtbo.img`, `vendor_boot.img`, `vendor_dlkm.img`.
- The AnyKernel3 archive contains an Image that differs from the supplied boot image; user confirmed the boot image simply has an older kernel build. **No auto replacement** is performed.
- Stock M55 `vbmeta.img` and `vbmeta_system.img` were recovered and audited (AVB flags=0). They are **not compatible by assumption** with modified boot images; this port does **not** flash them automatically.
- Device reportedly unlocked; current bootloader/AVB state must be checked independently.
- DSU support is **not implemented** here. DSU cannot test a custom boot image and is not equivalent to full ROM installation.

## Original UN1CA CI (manual for M55)

The active build workflow is [UN1CA CI (Galaxy M55)](https://github.com/vildangil/UN1CA-m55xq/actions/workflows/ci.yml), based on upstream `salvogiangri/UN1CA` branch `sixteen` original `.github/workflows/ci.yml`.

It preserves the upstream sequence:

1. `Shellcheck` and Python preflight;
2. generate the target matrix (restricted to `m55xq`);
3. free GitHub runner disk, install build dependencies and JDK 17;
4. generate upstream `buildenv.sh m55xq` configuration;
5. run upstream `scripts/build_dependencies.sh`;
6. obtain exact S22 One UI 8 donor and historical M55 One UI 7 from Samsung via native Bifrost without a target IMEI, preserving upstream `out/odin/SM-..._CSC` cache layout;
7. unpack using upstream `scripts/extract_fw.sh --ignore-target` (S22) and `--ignore-source` (M55);
8. verify the previously provided custom kernel quartet, run upstream `scripts/make_rom.sh` (target-files only; not flashable).

**Manual-only**: `workflow_dispatch` offers `preflight` (default; runs shellcheck, generates matrix and reports missing config options) and `build` (full upstream-style compilation). No `push`, PR or scheduled trigger is enabled. The full build is strictly gated on these GitHub Actions secrets:

- `M55_DEVICE_CONFIG_B64`: Base64 of a source-able shell config containing verified M55-specific `TARGET_*` SEC feature settings. The previous preflight found 47 missing hardware variables, and we must not fill them with unrelated S22 values.
- `M55_KERNEL_ARCHIVE_URL`: downloadable ZIP containing *exactly* the owner-supplied `boot.img`, `dtbo.img`, `vendor_boot.img`, `vendor_dlkm.img`; all four are checksum-verified before the build.

The `SM-M556B/INS/CACHE` token is a **local-only sentinel** allowing the upstream UN1CA source/extractor to reference a pinned M55 archive from Bifrost without leaking or inventing an IMEI. It is never passed to Samloader; the real exact firmware string is stored in `.downloaded` by `scripts/m55_prepare_odin_cache.py`.

The full `build` mode will fail early if hardware secrets are not configured. Even after compilation, a target-files ZIP is **not boot-tested or flashable by assumption**. Kernel/AVB chain, SELinux and VINTF compatibility require separate device validation. The original upstream `blobs.yml` (prebuilt update scheduler for other devices) is not applicable to M55 and has not been imported.

Older successful Stage 0 manifests are still available through [historical run #40922752695](https://github.com/vildangil/UN1CA-m55xq/actions/runs/40922752695), though the experimental workflows themselves have been consolidated into `ci.yml`.

## Read-only checks
```bash
bash scripts/m55xq_preflight.sh
mkdir -p out/m55xq-kernel
# Copy the four user-provided .img files to out/m55xq-kernel/ (never commit them)
bash scripts/m55xq_preflight.sh --images
```

## Required One UI 7 stock metadata (do not guess)
- `M55_ONEUI7_FIRMWARE`: the original build uses the local-only `SM-M556B/INS/CACHE` sentinel with native Bifrost and verified historical build `M556BXXS4BYH2`. No personal identifier is required or stored.
- `M55_BOARD_API_LEVEL`: now defaults to measured `31` (`ro.board.api_level` from stock M556BXXS4BYH2).
- `M55_SUPER_PARTITION_SIZE` defaults to measured `13631488000`; `M55_QTI_DYNAMIC_PARTITIONS_SIZE` defaults to measured `13627293696`.
- `M55_DEVICE_CONFIG`: local source-able file with verified M55 SEC feature values from extracted One UI 7 firmware. Never borrow A73/M52 features without verification.
- `TARGET_PRODUCT_SHIPPING_API_LEVEL=34` is now confirmed by stock vendor `ro.product.first_api_level=34`.

Preliminary collection on the device, read only:
```sh
adb shell getprop ro.board.api_level
adb shell getprop ro.product.first_api_level
adb shell getprop ro.boot.bootloader
adb shell getprop ro.product.vendor.device
adb shell lpdump
```

## Boot-chain staging
Set `M55_KERNEL_DIR` to a folder containing the four previously boot-tested images, or use `out/m55xq-kernel/`. The target patch overlays boot/vendor_boot/dtbo **without repacking**. The target-files generator replaces its newly built `vendor_dlkm.img` with the supplied EROFS image to keep the corresponding modules.

No firmware is flashed by these scripts. **Do not flash generated target-files/ROM packages yet**: device-specific feature flags, stock partition layout, VINTF/SELinux, recovery fstab and verified installation assertions are not complete. Full boot and DSU tests are pending.
