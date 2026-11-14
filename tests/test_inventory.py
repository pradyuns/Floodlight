import pytest

from bench.inventory import App, index_coverage, manifest_kinds, parse_inventory

LISTING = "\n".join(
    [
        "/System/Applications/Chess.app\t/System/Applications/Chess.app\tChess\tcom.apple.Chess",
        "/Applications/Safari.app\t/System/Cryptexes/App/Safari.app\tSafari\tcom.apple.Safari",
        "/Applications/Foo.app\t/Applications/Foo.app\tFoo\tcom.example.foo1",
        "/Applications/Utilities/Foo.app\t/Applications/Utilities/Foo.app\tFoo\tcom.example.foo2",
        "/Applications/\u200eChat.app\t/Applications/\u200eChat.app\t\u200eChat\tcom.example.chat",
        "/Applications/Raycast.app\t/Applications/Raycast.app\tRaycast\tcom.raycast.macos",
    ]
)


def test_parse_keeps_unique_plain_names() -> None:
    apps, _ = parse_inventory(LISTING, tools_under_test={"com.raycast.macos"})
    names = [a.name for a in apps]
    assert "Chess" in names
    assert "Safari" in names


def test_parse_excludes_duplicate_names_and_reports_them() -> None:
    apps, excluded = parse_inventory(LISTING, tools_under_test=set())
    assert "Foo" not in [a.name for a in apps]
    assert excluded["Foo"] == "duplicate name"


def test_parse_excludes_names_with_format_characters() -> None:
    apps, excluded = parse_inventory(LISTING, tools_under_test=set())
    assert all("\u200e" not in a.name for a in apps)
    assert excluded["\u200eChat"] == "format character in name"


def test_parse_assigns_kinds_from_bundle_ids() -> None:
    apps, _ = parse_inventory(
        LISTING, tools_under_test={"com.raycast.macos"}, third_party={"com.example.foo1"}
    )
    kinds = {a.name: a.kind for a in apps}
    assert kinds["Chess"] == "builtin"
    assert kinds["Raycast"] == "tool_under_test"


def test_coverage_accepts_real_path_of_symlinked_app() -> None:
    safari = App(
        "Safari",
        "/Applications/Safari.app",
        "/System/Cryptexes/App/Safari.app",
        "com.apple.Safari",
        "builtin",
    )
    chess = App(
        "Chess",
        "/System/Applications/Chess.app",
        "/System/Applications/Chess.app",
        "com.apple.Chess",
        "builtin",
    )
    indexed = {"/System/Cryptexes/App/Safari.app"}
    assert index_coverage([safari, chess], indexed) == {"Safari": True, "Chess": False}


def test_manifest_marks_raycast_as_tool_under_test_and_the_rest_third_party() -> None:
    manifest = (
        '[{"name": "Slack", "bundle_id": "com.tinyspeck.slackmacgap"},'
        ' {"name": "Raycast", "bundle_id": "com.raycast.macos"}]'
    )
    tools_under_test, third_party = manifest_kinds(manifest)
    assert tools_under_test == {"com.raycast.macos"}
    assert third_party == {"com.tinyspeck.slackmacgap"}


def test_listing_labels_manifest_apps_by_kind() -> None:
    listing = "\n".join(
        [
            "/Applications/Slack.app\t/Applications/Slack.app\tSlack\tcom.tinyspeck.slackmacgap",
            "/Applications/Raycast.app\t/Applications/Raycast.app\tRaycast\tcom.raycast.macos",
            "/System/Applications/Chess.app\t/System/Applications/Chess.app\tChess\tcom.apple.Chess",
        ]
    )
    tools_under_test, third_party = manifest_kinds(
        '[{"bundle_id": "com.tinyspeck.slackmacgap"}, {"bundle_id": "com.raycast.macos"}]'
    )
    apps, _ = parse_inventory(listing, tools_under_test, third_party)
    assert {a.name: a.kind for a in apps} == {
        "Chess": "builtin",
        "Raycast": "tool_under_test",
        "Slack": "third_party",
    }


def test_manifest_without_bundle_id_fails_loudly() -> None:
    with pytest.raises(ValueError, match="bundle_id"):
        manifest_kinds('[{"name": "Slack"}]')
