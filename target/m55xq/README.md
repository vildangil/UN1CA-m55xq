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
8. derive M55 SEC settings from verified unpacked Samsung stock, regenerate the final build config and refuse unknown/mismatched settings;
9. by default, patch the three **stock M55** boot-chain images with the user's original `samsung_custom_binary.py`, preserving the original stock files and original `vendor_dlkm.img`; optionally use the pre-tested patched quartet;
10. run upstream `scripts/make_rom.sh` (target-files only; not flashable) and, if it succeeds, upload the checked artifact `M55-UN1CA-OneUI8-UNTESTED-target-files` with its SHA-256 for three days.

**Manual-only**: `workflow_dispatch` has these modes:

- `preflight` (default): shellcheck, Python syntax and target config readiness.
- `stock_custom_images`: **requires NO secrets**. Downloads only the small M55 image artifact from verified stock run `40908265068`, uses the exact, unmodified user-supplied `samsung_custom_binary.py` on `boot.img`, `vendor_boot.img` and `dtbo.img`, checks both original and output SHA-256 against known-good values, and uploads patched copies with a `DO_NOT_FLASH` notice.
- `build`: original upstream UN1CA full build flow. Default `kernel_source=stock_custom` processes the downloaded historical M55 stock kernel images with the user's patcher and stages **unchanged stock `vendor_dlkm`** for the target-files generator. Alternatively `kernel_source=owner_tested` imports and SHA-verifies the four previously provided custom images.

The original stock-only SEC verification run [#41001233459](https://github.com/vildangil/UN1CA-m55xq/actions/runs/41001233459) downloaded and extracted both firmwares, but proved only **4 of 47** required target features. It also found differing system/vendor LCD HFR flags (120/60 Hz and mode 2/0). They must not be silently treated as equivalent. To investigate later UN1CA build stages despite these incomplete features, `build` has a visible `feature_policy` input:

- **`experimental` (default)** — generates fully audited, neutral placeholders only for unsupported M55 settings, records each in `m55-feature-evidence.json`, and builds **uninstallable/UNFLASHABLE target-files for analysis**. The original Samsung feature evidence is preserved; these values are **not verified** and must never be treated as hardware compatibility.
- **`strict`** — stops on unverified/conflicting features as before.

`scripts/make_rom.sh --build-rom-zip` is explicitly blocked whenever the experimental feature policy is active. No automatic flashing, vbmeta bypass or recovery installation is enabled.

For `build` mode, **`M55_DEVICE_CONFIG_B64` is no longer required**. The original UN1CA build is bootstrapped *only for host tools/firmware extraction*, then `scripts/m55_derive_features.py` reads the **actual unpacked M556BXXS4BYH2 stock filesystem**, checks the vendor identity/API/PDA, and maps exact `SEC_FLOATING_FEATURE_*` tags or unique device policy filenames to `TARGET_*` variables. It produces `m55-derived-features.sh` and `m55-feature-evidence.json`, then regenerates the **real** UN1CA config. Any required setting without unambiguous stock evidence stops the ROM build; the report is uploaded even on failure. **`M55_KERNEL_ARCHIVE_URL` is needed only for `kernel_source=owner_tested`** and is not needed in the default `stock_custom` mode.

The user's original custom binary patcher is stored **byte-for-byte** in `scripts/m55/samsung_custom_binary.py`, Git blob SHA-1 `e66c804b184ae17b8e03aa4c9ff3cf0a012ea4ae`. The patch was tested on stock `M556BXXS4BYH2` M55 images on 2026-10-29, generating these SHA-256 digests:

| Output image | SHA-256 |
| --- | --- |
| `boot.img` | `6924a9cc6e5732aab897e46e6af8133edbe95fcf01de659e2d8318e62d456729` |
| `vendor_boot.img` | `9a9344bccf712e5a6605085388f0ebd470a3953b75ef70e9087a695e403f9c41` |
| `dtbo.img` | `f0c1e70c7b3eb0db054bd6cd96a26226f8274cdb17989d9d0b5f20316ea7387e` |

It removes `SignerVer02`, preserves the embedded vbmeta blob for boot/vendor_boot (with an updated footer), and retains the DTBO payload byte-for-byte. It does **not** alter or unlock the device bootloader, change its rollback fuses, or prove that the complete AVB chain is accepted. The tool should only run on **pinned** images for which the original hashes match; it is not used on previously patched images.

The `SM-M556B/INS/CACHE` token is a **local-only sentinel** allowing the upstream UN1CA source/extractor to reference a pinned M55 archive from Bifrost without leaking or inventing an IMEI. It is never passed to Samloader; the real exact firmware string is stored in `.downloaded` by `scripts/m55_prepare_odin_cache.py`.

The full `build` mode will fail after M55 stock extraction if required hardware-feature values remain unverified; inspect `M55-OneUI7-real-hardware-feature-evidence` artifact. Even after compilation, a target-files ZIP is **not boot-tested or flashable by assumption**. Kernel/AVB chain, SELinux and VINTF compatibility require separate device validation. The original upstream `blobs.yml` (prebuilt update scheduler for other devices) is not applicable to M55 and has not been imported.

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
