# Galaxy M55 (m55xq) UN1CA 8 port — work in progress

**Base layout:** UN1CA `sixteen` (One UI 8 / Android 16) `system` and `product`; Samsung SM-M556B **One UI 7 / Android 15** `vendor`, `odm`, and hardware configs. Proven working patched boot-chain supplied separately.

This fork intentionally has **one device target only**: `target/m55xq`. Upstream targets remain available at https://github.com/salvogiangri/UN1CA/tree/sixteen/target.

## Current status
- Port skeleton and boot-chain overlay added; **not boot tested**. A manual-only stock staging build now exists at `.github/workflows/m55-build.yml`; it validates real EROFS input images but is **not a complete ROM**.
- Existing local images: `boot.img`, `dtbo.img`, `vendor_boot.img`, `vendor_dlkm.img`.
- The AnyKernel3 archive contains an Image that differs from the supplied boot image; user confirmed the boot image simply has an older kernel build. **No auto replacement** is performed.
- Stock M55 `vbmeta.img` and `vbmeta_system.img` were recovered and audited (AVB flags=0). They are **not compatible by assumption** with modified boot images; this port does **not** flash them automatically.
- Device reportedly unlocked; current bootloader/AVB state must be checked independently.
- DSU support is **not implemented** here. DSU cannot test a custom boot image and is not equivalent to full ROM installation.

## Stage-0 assembly (manual GitHub Actions)

The [M55 UN1CA prototype build](https://github.com/vildangil/UN1CA-m55xq/actions/workflows/m55-build.yml) downloads verified stock `vendor`, `odm` and `vendor_dlkm` from successful [stock inspection run #40908265068](https://github.com/vildangil/UN1CA-m55xq/actions/runs/40908265068), checks size, SHA-256, EROFS magic, fstab, AVB metadata, board API and super group capacity, then emits a small **NON-FLASHABLE** staging manifest and a list of still-missing hardware configuration fields.

It does **not** build One UI 8 system/product or combine patched boot images with the stock AVB chain. The four user-supplied modified images are not stored in this repo and are not part of the staging artifact. A full custom ROM build would require verified target-specific SEC feature values, S22 donor integration, original file contexts/ownership metadata for any regenerated partitions, kernel/module ABI and VINTF compatibility, and a safely configured AVB chain. Never flash the stage-0 output.

## Donor One UI 8 integration experiment (manual)

[M55 UN1CA 8 donor integration experiment](https://github.com/vildangil/UN1CA-m55xq/actions/workflows/m55-donor-mix.yml) is a separate *manual* workflow. It uses the original Bifrost SmartDownload to request the **exact** S22 One UI 8 firmware `SM-S901E/TUR/S901EXXSEGZH4`, streams `system`, `product` and `system_ext` out of its dynamic `super`, and checks them against the already verified M55 `vendor`, `odm` and `vendor_dlkm` from [stock extraction #40908265068](https://github.com/vildangil/UN1CA-m55xq/actions/runs/40908265068).

It stops if the donor version does not match, any partition is not EROFS, the vendor hashes have changed, or the combined images cannot fit `qti_dynamic_partitions` (13,627,293,696 bytes). The artifact contains a partition layout, checksums, and an optional `lpmake` recipe. **It does not create a flashable ROM, modify AVB, or replace the user's patched boot-chain.** Successful staging does *not* demonstrate compatibility between Samsung Android 16 framework and the Galaxy M55 Android 15 vendor. The input stock artifact expires on GitHub's retention schedule.

There are still 47 unspecified device-specific feature settings in UN1CA's target configuration. We need measured settings (not borrowed from S22) before safely running the normal `unica make_rom` path. A first experiment may identify additional VINTF/ABI work, but it must not be flashed or presented as a DSU-compatible image.

## Read-only checks
```bash
bash scripts/m55xq_preflight.sh
mkdir -p out/m55xq-kernel
# Copy the four user-provided .img files to out/m55xq-kernel/ (never commit them)
bash scripts/m55xq_preflight.sh --images
```

## Required One UI 7 stock metadata (do not guess)
- `M55_ONEUI7_FIRMWARE`: exact FUS model/CSC/serial source in `SM-M556B/CSC/ID` format. Keep ID in local environment; **do not commit personal identifiers**.
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
