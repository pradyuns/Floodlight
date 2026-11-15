import pytest

from bench.inventory import parse_bundle_names

OUT = (
    'LOCALE\ten_US\nLANGS\t("en-US")\n'
    "NAME\t/S/Print Center.app\tInfo.plist\tCFBundleName\tPrint Center\n"
    "NAME\t/S/Print Center.app\tloctable:en_GB\tCFBundleDisplayName\tPrint Centre\n"
    "NAME\t/S/Image Playground.app\tloctable:en\tCFBundleDisplayName\tPlayground\n"
)
APPS = {"/S/Print Center.app": "Print Center", "/S/Image Playground.app": "Image Playground"}


def test_bundle_names_become_aliases_with_their_source() -> None:
    table = parse_bundle_names(OUT, APPS)
    assert table["locale"] == "en_US" and table["languages"] == '("en-US")'
    assert table["aliases"] == {
        "Image Playground": [["Playground", "loctable:en CFBundleDisplayName"]],
        "Print Center": [["Print Centre", "loctable:en_GB CFBundleDisplayName"]],
    }


def test_a_name_shared_by_two_apps_is_refused() -> None:
    shared = OUT + "NAME\t/S/Image Playground.app\tInfo.plist\tCFBundleName\tPrint Centre\n"
    with pytest.raises(ValueError, match="Print Centre"):
        parse_bundle_names(shared, APPS)
