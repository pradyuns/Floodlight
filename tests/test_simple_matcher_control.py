from scripts.simple_matcher_control import osa, simple_match

NAMES = ["Activity Monitor", "Audio MIDI Setup", "Calculator", "Calendar", "Ropuvaf Lab"]


def test_osa_counts_one_edit_of_each_kind_and_two_for_a_rotation() -> None:
    assert [osa("abc", x) for x in ("abc", "axc", "ac", "abbc", "acb", "bca", "")] == [
        0,
        1,
        1,
        1,
        1,
        2,
        3,
    ]


def test_exact_prefix_word_prefix_and_initials_without_typo_matching() -> None:
    assert simple_match("calculator", NAMES, one_edit=False) == "Calculator"
    assert simple_match("cal", NAMES, one_edit=False) == "Calculator"  # alphabetical tie-break
    assert simple_match("monitor", NAMES, one_edit=False) == "Activity Monitor"
    assert simple_match("am", NAMES, one_edit=False) == "Activity Monitor"
    assert simple_match("ropuvaflab", NAMES, one_edit=False) == "Ropuvaf Lab"


def test_one_edit_typos_only_match_when_enabled() -> None:
    assert simple_match("ropuvfa lab", NAMES, one_edit=False) is None
    assert simple_match("ropuvfa lab", NAMES, one_edit=True) == "Ropuvaf Lab"
    assert simple_match("calculatr", NAMES, one_edit=True) == "Calculator"
    assert simple_match("zzz", NAMES, one_edit=True) is None
