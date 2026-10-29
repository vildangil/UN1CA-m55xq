# Samsung Galaxy M55 / m55xq — stock One UI 7 baseline

Source: Samsung FUS SmartDownload, Bifrost 2.x, firmware
`M556BXXS4BYH2/M556BODM4BYH2/M556BXXS4BYH2/M556BXXS4BYH2` (INS, Android 15).

Verified GitHub Actions run: https://github.com/vildangil/UN1CA-m55xq/actions/runs/40835409448

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

## Remaining check

The manual-only workflow [M55 One UI 7 stock image inspection](https://github.com/vildangil/UN1CA-m55xq/actions/workflows/m55-stock-inspect.yml)
now includes streamed extraction of `vendor`, `odm`, and `vendor_dlkm`, filesystem inspection, VINTF/HAL and kernel module inventory, and a separate AVB descriptor report. This second-stage analysis is **not yet verified** by a completed run.

No scripts in this workflow flash images, unlock devices, or overwrite the user's patched images.
