from bench.installers import parse_codesign, parse_spctl, public_url

CODESIGN = """Executable=/x/Slack.app/Contents/MacOS/Slack
Identifier=com.tinyspeck.slackmacgap
Format=app bundle with Mach-O universal (x86_64 arm64)
Authority=Developer ID Application: Slack Technologies, Inc. (BQR82RBBHL)
Authority=Developer ID Certification Authority
Authority=Apple Root CA
TeamIdentifier=BQR82RBBHL
"""


def test_parse_codesign_reads_identifier_team_and_signer() -> None:
    info = parse_codesign(CODESIGN)
    assert info.identifier == "com.tinyspeck.slackmacgap"
    assert info.team_id == "BQR82RBBHL"
    assert info.signer == "Developer ID Application: Slack Technologies, Inc. (BQR82RBBHL)"


def test_parse_spctl_accepts_only_notarized_developer_id() -> None:
    ok = "/x/Slack.app: accepted\nsource=Notarized Developer ID\norigin=Developer ID Application"
    assert parse_spctl(ok) is True
    assert parse_spctl("/x/A.app: accepted\nsource=Developer ID\n") is False
    assert parse_spctl("/x/A.app: rejected\nsource=Unnotarized Developer ID\n") is False


def test_public_url_drops_signed_query_strings() -> None:
    url = "https://cdn.example.net/v/t39/x.dmg/WhatsApp-2.26.dmg?oh=SECRET&oe=1"
    assert public_url(url) == "https://cdn.example.net/v/t39/x.dmg/WhatsApp-2.26.dmg"


def test_install_commands_unpack_inside_the_guest_without_opening() -> None:
    from bench.installers import install_commands

    share = "/Volumes/My Shared Files/installers"
    cmds = install_commands(["slack.dmg", "vscode.zip"], share=share)
    assert "hdiutil attach -nobrowse -readonly" in cmds[0]
    assert f"'{share}/slack.dmg'" in cmds[0]
    assert "ditto" in cmds[0] and "/Applications/" in cmds[0]
    assert "hdiutil detach" in cmds[0]
    assert cmds[1] == f"ditto -x -k '{share}/vscode.zip' /Applications/"
    assert not any("open " in c for c in cmds)
