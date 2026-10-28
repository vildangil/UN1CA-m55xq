#!/usr/bin/env bash
# This module runs during the UN1CA build, after extraction of stock M55 firmware.
# It never flashes partitions and never repacks or re-signs the supplied images.
M55_IMAGE_DIR="${M55_KERNEL_DIR:-$OUT_DIR/m55xq-kernel}"
for M55_IMAGE in boot.img vendor_boot.img dtbo.img vendor_dlkm.img; do
    if [[ ! -s "$M55_IMAGE_DIR/$M55_IMAGE" ]]; then
        ABORT "Missing $M55_IMAGE_DIR/$M55_IMAGE -- M55 boot-chain overlay is required"
    fi
done
mkdir -p "$WORK_DIR/kernel"
for M55_IMAGE in boot.img vendor_boot.img dtbo.img; do
    LOG "- Preserving supplied $M55_IMAGE"
    cp -f "$M55_IMAGE_DIR/$M55_IMAGE" "$WORK_DIR/kernel/$M55_IMAGE" || ABORT "Copy failed: $M55_IMAGE"
done
unset M55_IMAGE_DIR M55_IMAGE
