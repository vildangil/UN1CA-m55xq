#!/usr/bin/env python3
"""Offline M55 stock SEC auto-detection and bootstrap regression fixtures."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from m55_derive_features import parse_stock, experimental_placeholder
from m55_bootstrap_config import generate


def make_fixture(p: Path):
    repo = p / "repo"
    fw = p / "stock"
    (repo / "scripts/internal").mkdir(parents=True)
    (repo / "target/m55xq").mkdir(parents=True)
    (repo / "platform/sm7450").mkdir(parents=True)
    (fw / "vendor").mkdir(parents=True)
    (fw / "system/system/etc").mkdir(parents=True)
    (fw / "product/etc").mkdir(parents=True)
    (repo / "scripts/internal/gen_config_file.sh").write_text(
        'GET_BUILD_VAR "TARGET_AUDIO_SUPPORT_DUAL_SPEAKER"\n'
        'GET_BUILD_VAR "TARGET_FINGERPRINT_CONFIG_SENSOR"\n'
        'GET_BUILD_VAR "TARGET_LCD_CONFIG_HFR_MODE"\n'
        'GET_BUILD_VAR "TARGET_COMMON_CONFIG_MDNIE_MODE"\n'
    )
    (repo / "target/m55xq/config.sh").write_text('TARGET_CODENAME="m55xq"\n')
    (repo / "platform/sm7450/config.sh").write_text('TARGET_PLATFORM="sm7450"\n')
    (fw / "vendor/build.prop").write_text(
        "ro.product.vendor.device=m55xq\n"
        "ro.product.first_api_level=34\nro.board.api_level=31\n"
        "ro.vendor.build.version.incremental=M556BXXS4BYH2\n"
    )
    (fw / "system/system/etc/floating_feature.xml").write_text(
        "<SecFloatingFeature>"
        "<SEC_FLOATING_FEATURE_AUDIO_SUPPORT_DUAL_SPEAKER>TRUE</SEC_FLOATING_FEATURE_AUDIO_SUPPORT_DUAL_SPEAKER>"
        "<SEC_FLOATING_FEATURE_FINGERPRINT_CONFIG_SENSOR>google_touch_display_optical,settings=3</SEC_FLOATING_FEATURE_FINGERPRINT_CONFIG_SENSOR>"
        "<SEC_FLOATING_FEATURE_LCD_CONFIG_HFR_MODE>2</SEC_FLOATING_FEATURE_LCD_CONFIG_HFR_MODE>"
        "</SecFloatingFeature>"
    )
    return repo, fw


with tempfile.TemporaryDirectory(prefix="m55-sec-features-") as t:
    repo, fw = make_fixture(Path(t))
    bootstrap = generate(repo)
    assert 'M55_BOOTSTRAP_ONLY=true' in bootstrap
    assert 'TARGET_LCD_CONFIG_HFR_MODE="0"' in bootstrap
    assert 'TARGET_COMMON_CONFIG_MDNIE_MODE="0"' in bootstrap
    assert '__M55_UNVERIFIED__' in bootstrap

    values, report = parse_stock(fw, repo)
    assert values["TARGET_AUDIO_SUPPORT_DUAL_SPEAKER"] == "true"
    assert values["TARGET_FINGERPRINT_CONFIG_SENSOR"] == "google_touch_display_optical,settings=3"
    assert values["TARGET_LCD_CONFIG_HFR_MODE"] == "2"
    assert report["missing_required"] == ["TARGET_COMMON_CONFIG_MDNIE_MODE"]
    assert not report["full_unica_build_unblocked"]
    assert report["verified_values"]["TARGET_AUDIO_SUPPORT_DUAL_SPEAKER"]["method"] == "exact_xml_tag"

    # Strict mode correctly refuses to proceed with missing SEC settings.
    extractor = Path(__file__).resolve().parents[1] / "m55_derive_features.py"
    strict = subprocess.run([sys.executable, str(extractor), str(fw),
        str(repo), str(Path(t)/"strict"), "--fail-on-missing"],
        capture_output=True, text=True)
    assert strict.returncode != 0
    strict_report = json.loads((Path(t)/"strict/m55-feature-evidence.json").read_text())
    assert not strict_report["full_unica_build_unblocked"]

    # Experimental mode must NOT erase missing evidence: it writes a separate
    # placeholder provenance list while reporting safe_to_flash=False.
    experimental = subprocess.run([sys.executable, str(extractor), str(fw),
        str(repo), str(Path(t)/"experimental"),
        "--fail-on-missing", "--experimental-preview"],
        capture_output=True, text=True)
    assert experimental.returncode == 0, experimental.stderr
    exp_report = json.loads((Path(t)/"experimental/m55-feature-evidence.json").read_text())
    assert not exp_report["safe_to_flash"]
    assert not exp_report["full_unica_build_unblocked"]
    assert exp_report["may_build_experimental_target_files"]
    assert "TARGET_COMMON_CONFIG_MDNIE_MODE" in exp_report["original_missing_required"]
    assert exp_report["experimental_placeholders"]["TARGET_COMMON_CONFIG_MDNIE_MODE"]["value"] == "0"
    exp_config = (Path(t)/"experimental/m55-derived-features.sh").read_text()
    assert "M55_EXPERIMENTAL_FEATURES_ACTIVE=true" in exp_config
    assert "TARGET_COMMON_CONFIG_MDNIE_MODE=0" in exp_config

    (fw / "product/etc/floating_feature.xml").write_text(
        "<SecFloatingFeature>"
        "<SEC_FLOATING_FEATURE_LCD_CONFIG_HFR_MODE>0</SEC_FLOATING_FEATURE_LCD_CONFIG_HFR_MODE>"
        "</SecFloatingFeature>"
    )
    values, report = parse_stock(fw, repo)
    assert "TARGET_LCD_CONFIG_HFR_MODE" not in values
    assert "TARGET_LCD_CONFIG_HFR_MODE" in report["missing_required"]
    assert any("Conflicting firmware" in item for item in report["conflicts"])

# Regression: every field absent in the *actual* 2026-10-30 stock audit
# has an explicit typed preview placeholder. No donor values, no accidental
# implicit default. True hardware support remains unknown.
AUDITED_MISSING = """
TARGET_AUDIO_SUPPORT_ACH_RINGTONE
TARGET_AUDIO_SUPPORT_VIRTUAL_VIBRATION_SOUND
TARGET_BLUETOOTH_SUPPORT_A2DPSINK_PROFILE
TARGET_BLUETOOTH_SUPPORT_A2DP_SBM
TARGET_BLUETOOTH_SUPPORT_HEAD_SAR_BACKOFF
TARGET_BLUETOOTH_SUPPORT_XLNA_CONTROL
TARGET_CAMERA_SUPPORT_CAMERAX_EXTENSION
TARGET_CAMERA_SUPPORT_CUTOUT_PROTECTION
TARGET_CAMERA_SUPPORT_MASS_APP_FLAVOR
TARGET_CAMERA_SUPPORT_SDK_SERVICE
TARGET_COMMON_SUPPORT_DYN_RESOLUTION_CONTROL
TARGET_COMMON_SUPPORT_EMBEDDED_SIM
TARGET_DVFSAPP_CONFIG_DVFS_POLICY_FILENAME
TARGET_DVFSAPP_CONFIG_SSRM_POLICY_FILENAME
TARGET_FINGERPRINT_CONFIG_SENSOR
TARGET_LCD_CONFIG_COLOR_WEAKNESS_SOLUTION
TARGET_LCD_CONFIG_HFR_DEFAULT_REFRESH_RATE
TARGET_LCD_CONFIG_HFR_MODE
TARGET_RIL_SIM_CONFIG_MULTISIM_TRAYCOUNT
TARGET_RIL_SUPPORT_WATERPROOF_SIM_TRAY_MSG
TARGET_WLAN_CONFIG_CONNECTION_PERSONALIZATION
TARGET_WLAN_CONFIG_CPU_CSTATE_DISABLE_THRESHOLD
TARGET_WLAN_CONFIG_DATA_ACTIVITY_AFFINITY_BOOSTER_THRESHOLD
TARGET_WLAN_CONFIG_DYNAMIC_SWITCH
TARGET_WLAN_CONFIG_L1SS_DISABLE_THRESHOLD
TARGET_WLAN_SUPPORT_80211AX
TARGET_WLAN_SUPPORT_80211AX_6GHZ
TARGET_WLAN_SUPPORT_APE_SERVICE
TARGET_WLAN_SUPPORT_LOWLATENCY
TARGET_WLAN_SUPPORT_MBO
TARGET_WLAN_SUPPORT_MIMO
TARGET_WLAN_SUPPORT_MOBILEAP_11AX
TARGET_WLAN_SUPPORT_MOBILEAP_5G_BASEDON_COUNTRY
TARGET_WLAN_SUPPORT_MOBILEAP_6G
TARGET_WLAN_SUPPORT_MOBILEAP_DUALAP
TARGET_WLAN_SUPPORT_MOBILEAP_OWE
TARGET_WLAN_SUPPORT_MOBILEAP_POWER_SAVEMODE
TARGET_WLAN_SUPPORT_MOBILEAP_PRIORITIZE_TRAFFIC
TARGET_WLAN_SUPPORT_MOBILEAP_WIFISHARING_LITE
TARGET_WLAN_SUPPORT_MOBILEAP_WIFI_CONCURRENCY
TARGET_WLAN_SUPPORT_SWITCH_FOR_INDIVIDUAL_APPS
TARGET_WLAN_SUPPORT_TWT_CONTROL
TARGET_WLAN_SUPPORT_WIFI_TO_CELLULAR
""".split()
assert len(AUDITED_MISSING) == 43, len(AUDITED_MISSING)
assert experimental_placeholder("TARGET_LCD_CONFIG_HFR_MODE") == "0"
assert experimental_placeholder("TARGET_LCD_CONFIG_HFR_DEFAULT_REFRESH_RATE") == "60"
assert experimental_placeholder("TARGET_FINGERPRINT_CONFIG_SENSOR") == "none"
assert experimental_placeholder("TARGET_WLAN_SUPPORT_MIMO") == "false"
for key in AUDITED_MISSING:
    candidate = experimental_placeholder(key)
    assert candidate in {"false", "0", "1", "60", "none"}, (key, candidate)
    assert candidate != "__M55_UNVERIFIED__"
try:
    experimental_placeholder("TARGET_UNRECOGNIZED_FIELD")
except ValueError:
    pass
else:
    raise AssertionError("Unknown fields must not receive implicit guesses")

print("PASS: M55 bootstrap remains non-final and SEC features are evidenced, never guessed")
