# Galaxy M55 (m55xq) -- One UI 7 vendor base for UN1CA One UI 8
# Values that cannot be derived safely must be supplied from the actual M55 firmware.
TARGET_NAME="Galaxy M55 5G"
TARGET_CODENAME="m55xq"
TARGET_PLATFORM="sm7450"
TARGET_FIRMWARE="${M55_ONEUI7_FIRMWARE:-}"
TARGET_EXTRA_FIRMWARES=()
TARGET_PLATFORM_SDK_VERSION=35
TARGET_PRODUCT_SHIPPING_API_LEVEL=34
TARGET_BOARD_API_LEVEL="${M55_BOARD_API_LEVEL:-}"
TARGET_ASSERT_MODEL=("SM-M556B")

# Verified lengths of the supplied, full-size boot-chain images.
# Re-check physical partition sizes before flashing.
TARGET_BOOT_PARTITION_SIZE=100663296
TARGET_DTBO_PARTITION_SIZE=8388608
TARGET_VENDOR_BOOT_PARTITION_SIZE=100663296

TARGET_USE_DYNAMIC_PARTITIONS=true
TARGET_SUPER_GROUP_NAME="qti_dynamic_partitions"
# Verified against One UI 7 M556BXXS4BYH2 super LP metadata (2026-10-29).
TARGET_SUPER_PARTITION_SIZE="${M55_SUPER_PARTITION_SIZE:-13631488000}"
TARGET_QTI_DYNAMIC_PARTITIONS_SIZE="${M55_QTI_DYNAMIC_PARTITIONS_SIZE:-13627293696}"

TARGET_OS_SINGLE_SYSTEM_IMAGE="qssi"
TARGET_OS_BUILD_SYSTEM_EXT_PARTITION=false
TARGET_OS_FILE_SYSTEM_TYPE="erofs"

# Preserve the uploaded boot-chain bytes; never synthesize vbmeta.
TARGET_KEEP_ORIGINAL_SIGN=true
TARGET_DISABLE_AVB_SIGNING=true
TARGET_INCLUDE_PATCHED_VBMETA=false

# Required SEC feature values must be measured from stock M55 One UI 7,
# not copied from A73/M52. Supply a local file, excluded from the repo.
if [[ -n "${M55_DEVICE_CONFIG:-}" ]]; then
    if [[ ! -r "$M55_DEVICE_CONFIG" ]]; then
        echo "Cannot read M55_DEVICE_CONFIG=$M55_DEVICE_CONFIG" >&2
        return 1
    fi
    # shellcheck disable=SC1090
    source "$M55_DEVICE_CONFIG"
fi
