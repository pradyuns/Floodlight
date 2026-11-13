from scripts.precommit_scan import local_only_files, scan


def test_scan_flags_personal_home_path() -> None:
    findings = scan("see /Users/someone/Desktop/notes.txt", ["/Users/someone"])
    assert findings == ["personal pattern: /Users/someone"]


def test_scan_personal_patterns_are_case_insensitive() -> None:
    assert scan("Host: MY-LAPTOP.local", ["my-laptop"]) == ["personal pattern: my-laptop"]


def test_scan_flags_private_key_block() -> None:
    fake_header = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"
    assert scan(fake_header, []) == ["key-like: private key block"]


def test_scan_flags_github_token() -> None:
    assert scan("token=ghp_" + "a" * 36, []) == ["key-like: GitHub token"]


def test_scan_flags_aws_access_key() -> None:
    assert scan("AKIA" + "ABCDEFGHIJKLMNOP", []) == ["key-like: AWS access key"]


def test_scan_flags_api_secret_key() -> None:
    assert scan("sk-" + "x" * 40, []) == ["key-like: API secret key"]


def test_mentioning_local_file_pattern_in_text_is_allowed() -> None:
    assert scan("*.local.* files stay gitignored", []) == []


def test_staging_a_local_only_file_is_flagged() -> None:
    assert local_only_files(["README.md", "docs/DECISIONS.local.md"]) == [
        "local-only file staged: docs/DECISIONS.local.md"
    ]


def test_scan_clean_text_passes() -> None:
    assert scan("def normalize(s: str) -> str: ...", ["/Users/someone"]) == []
