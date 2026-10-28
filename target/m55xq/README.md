# Galaxy M55 (m55xq) UN1CA 8 port — work in progress

**Base layout:** UN1CA `sixteen` (One UI 8 / Android 16) `system` and `product`; Samsung SM-M556B **One UI 7 / Android 15** `vendor`, `odm`, and hardware configs. Proven working patched boot-chain supplied separately.

This fork intentionally has **one device target only**: `target/m55xq`. Upstream targets remain available at https://github.com/salvogiangri/UN1CA/tree/sixteen/target.

## Current status
- Port skeleton and boot-chain overlay added; **not boot tested**.
- Existing local images: `boot.img`, `dtbo.img`, `vendor_boot.img`, `vendor_dlkm.img`.
- The AnyKernel3 archive contains an Image that differs from the supplied boot image; user confirmed the boot image simply has an older kernel build. **No auto replacement** is performed.
- No original M55 vbmeta is available. This port **does not copy, create, flash or patch vbmeta**.
- Device reportedly unlocked; current bootloader/AVB state must be checked independently.
- DSU support is **not implemented** here. DSU cannot test a custom boot image and is not equivalent to full ROM installation.

## Read-only checks
```bash
bash scripts/m55xq_preflight.sh
mkdir -p out/m55xq-kernel
# Copy the four user-provided .img files to out/m55xq-kernel/ (never commit them)
bash scripts/m55xq_preflight.sh --images
```

## Required One UI 7 stock metadata (do not guess)
- `M55_ONEUI7_FIRMWARE`: exact FUS model/CSC/serial source in `SM-M556B/CSC/ID` format. Keep ID in local environment; **do not commit personal identifiers**.
- `M55_BOARD_API_LEVEL`: `ro.board.api_level` of the selected One UI 7 base.
- `M55_SUPER_PARTITION_SIZE` and `M55_QTI_DYNAMIC_PARTITIONS_SIZE`: exact physical super / logical group sizes from `lpdump`.
- `M55_DEVICE_CONFIG`: local source-able file with verified M55 SEC feature values from extracted One UI 7 firmware. Never borrow A73/M52 features without verification.
- `TARGET_PRODUCT_SHIPPING_API_LEVEL=34` is a provisional M55 launch-level assumption. Check against `ro.product.first_api_level` before a full build.

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
