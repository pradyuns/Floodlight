from bench.inventory import App, index_coverage, parse_inventory

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
