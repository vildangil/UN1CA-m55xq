# Galaxy M55 SM7450. Board parameters are intentionally not guessed.
# Measured from ro.board.api_level in Samsung M556BXXS4BYH2 vendor/build.prop.
TARGET_BOARD_API_LEVEL="${M55_BOARD_API_LEVEL:-31}"
TARGET_USE_DYNAMIC_PARTITIONS=true
TARGET_SUPER_GROUP_NAME="qti_dynamic_partitions"
TARGET_OS_SINGLE_SYSTEM_IMAGE="qssi"
TARGET_OS_BUILD_SYSTEM_EXT_PARTITION=false
