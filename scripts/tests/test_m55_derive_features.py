#!/usr/bin/env python3
"""Offline M55 stock SEC auto-detection and bootstrap regression fixtures."""
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from m55_derive_features import parse_stock
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

    (fw / "product/etc/floating_feature.xml").write_text(
        "<SecFloatingFeature>"
        "<SEC_FLOATING_FEATURE_LCD_CONFIG_HFR_MODE>0</SEC_FLOATING_FEATURE_LCD_CONFIG_HFR_MODE>"
        "</SecFloatingFeature>"
    )
    values, report = parse_stock(fw, repo)
    assert "TARGET_LCD_CONFIG_HFR_MODE" not in values
    assert "TARGET_LCD_CONFIG_HFR_MODE" in report["missing_required"]
    assert any("Conflicting firmware" in item for item in report["conflicts"])

print("PASS: M55 bootstrap remains non-final and SEC features are evidenced, never guessed")
