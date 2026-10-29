# Samsung Galaxy M55 / m55xq — stock One UI 7 baseline

Source: Samsung FUS SmartDownload, Bifrost 2.x, firmware
`M556BXXS4BYH2/M556BODM4BYH2/M556BXXS4BYH2/M556BXXS4BYH2` (INS, Android 15).

Verified GitHub Actions runs:\n- 2026-10-29 base partition/AVB metadata: https://github.com/vildangil/UN1CA-m55xq/actions/runs/40835409448\n- 2026-10-29 vendor/ODM/kernel module extraction and VINTF audit: https://github.com/vildangil/UN1CA-m55xq/actions/runs/40908265068

## Super / liblp verified from stock super.img

| Setting | Value |
| --- | ---: |
| `super` block device bytes | `13631488000` |
| `qti_dynamic_partitions` maximum bytes | `13627293696` |
| Metadata slots | 2 |
| LP logical block bytes | 4096 |
| LP metadata major/minor | 10/0 |

| Logical partition | LP allocated bytes |
| --- | ---: |
| `system` | 6131326976 |
| `product` | 2054823936 |
| `system_ext` | 345051136 |
| `vendor` | 2008227840 |
| `odm` | 1699840 |
| `vendor_dlkm` | 126201856 |

These are sizes in **stock One UI 7**. Actual ROM port output must fit the dynamic group. The measured values have been installed as overridable defaults in `target/m55xq/config.sh`.

## Stock AVB and boot-chain

| Stock image | Size (bytes) | SHA-256 |
| --- | ---: | --- |
| `boot.img` | 100663296 | `e84ccd196731d16eb745619bd8ecd4ae2d37e644cdd8822855b36577d4c1e979` |
| `vendor_boot.img` | 100663296 | `04871187eaf09053cabe1486c1838ef2f4cd34a41f4283400224d5a35ae65126` |
| `dtbo.img` | 8388608 | `5086afb98fdc592e8e248ee51842590e7ead5e3fbb9c12e58e9132eee632add2` |
| `vbmeta.img` | 8448 | `be1071bbb832e61382dd4800c61f48d1692440fb7adf43dcb7e7ce4d8a6df58b` |
| `vbmeta_system.img` | 3904 | `89425da54d104be5d8bc8812533683bce355793d5f98fa0749c477999d8ec79d` |

Both stock vbmeta images contain AVB0 headers, AVB flags **0**, and algorithm identifier **2**. The main vbmeta has hash descriptors for `boot`, `recovery`, `vendor_boot`, in addition to other descriptors. AVB0 and a recognized descriptor layout **do not prove** that Samsung will accept a modified boot-chain.

## Previously supplied custom images — hashes, no image replacements

| Local modified image | Bytes | SHA-256 |
| --- | ---: | --- |
| `boot.img` | 100663296 | `937a4c973ff7daff7fcc63c6244526be9b11a69b4a7d2729c39661fd9ccf4479` |
| `vendor_boot.img` | 100663296 | `dd0ac56f3d186ce0545f47352ce2db4ff09221c7654bf7236f9c1a1bae5c719c` |
| `dtbo.img` | 8388608 | `b83bb40ac00a9e4e4855a6c47527326a17b681fb5af840153ea69726e2898b2b` |
| `vendor_dlkm.img` | 56664064 | `1fa2a5f271b7f3ac4b9c61631065472015ca507821281dbbaa3f2519d037e37c` |

The custom `boot` and `vendor_boot` differ from the hashes in stock and must **not** be combined with unchanged stock vbmeta as though the images still matched. The `vendor_dlkm` image contains an EROFS magic at offset 1024, but its contents and kernel-module compatibility still need to be checked against stock vendor/ODM.

## Verified vendor, ODM, and kernel-module extraction (2026-10-29)

Manual-only GitHub Actions run [#40908265068](https://github.com/vildangil/UN1CA-m55xq/actions/runs/40908265068) completed successfully. Samsung FUS returned **exactly** `M556BXXS4BYH2`; 8,560,869,744 encrypted bytes were downloaded, decrypted to ZIP, CRC-checked, and its `super.img.lz4` was streamed into separate logical partition images without ever creating a full-size raw super.

| Partition | Size (bytes) | SHA-256 | Files | Other details |
| --- | ---: | --- | ---: | --- |
| `vendor` | 2008227840 | `825c78c6855e837b07d65e6e30d30959ef2caab43bf7eaeb12a305d0f8a34203` | 3731 | 106 HAL shared libraries, 238 extracted configuration files |
| `odm` | 1699840 | `a6520727edcb70a1119368538d9ba566f571d71b300963ffcf819947db075f82` | 12 | 3 configuration files |
| `vendor_dlkm` | 126201856 | `e52e39b4b5443d398528c21a483757c3af673a29d39ba46bd086d17361d92ae4` | 320 | 311 `.ko` kernel modules, 5 configuration files |

All three extracted images have EROFS magic `e2e1f5e0` at byte offset 1024. The `vendor_dlkm/lib/modules/modules.load` has 314 lines, 311 unique module filenames; all 311 unique names exist as stock `.ko` files (three duplicates in the load list).

Stock `vendor/build.prop` confirms `ro.product.vendor.device=m55xq`, `ro.product.vendor.model=SM-M556B`, `ro.product.board=taro`, and `ro.board.platform=taro`. **Important**: while the overall Samsung firmware is One UI 7 (Android 15), vendor reports `ro.vendor.build.version.sdk=32` and an Android 12 vendor fingerprint (`SP2A.220305.013`). This is the stock vendor-side release/API reported in the image, not evidence that the whole firmware was Android 12. Keep its vendor compatibility assumptions separate from the system port.

Stock `vendor/etc/fstab.qcom` defines `system`, `system_ext`, `product`, `vendor`, `odm`, and `vendor_dlkm` as `logical,first_stage_mount` EROFS devices protected by AVB. `system` and `vendor` explicitly reference `vbmeta_system`; do not remove the AVB chain implicitly when mixing custom and stock partitions.

The original stock `vbmeta.img` has 18 descriptors: hashes for `boot`, `recovery`, and `vendor_boot`, six hashtrees, chained descriptors, and properties. Stock `vbmeta_system.img` has six hashtrees. Both are signed and have flags 0. The pre-existing patched `boot`/`vendor_boot` hashes differ from stock. Mixing a modified boot chain with unmodified stock vbmeta has not been validated.

Artifacts from run #40908265068 (temporary, until GitHub's configured expiration):
- [Metadata, vbmeta, extracted configs, full file/HAL inventories](https://github.com/vildangil/UN1CA-m55xq/actions/runs/40908265068/artifacts/12915305501) (about 86 MB)
- [Raw vendor/odm/vendor_dlkm partition images](https://github.com/vildangil/UN1CA-m55xq/actions/runs/40908265068/artifacts/12914676290) (about 2.14 GB)

## Remaining compatibility work

Compare the **contents**, module ABI and load order of the user's patched `vendor_dlkm` against the stock 311 modules, then reconcile vendor VINTF HAL declarations with the One UI 8 framework and the S22 donor. Do not assume kernel/AVB compatibility from a successful extraction job. None of these results constitute a boot test, and no workflow flashed, unlocked, or overwrote the user's patched boot-chain images.
