from bench.normalize import edit_distance, normalize


def test_normalize_strips_invisible_left_to_right_mark() -> None:
    assert normalize("\u200eWhatsApp") == "whatsapp"


def test_normalize_strips_accents_and_casefolds() -> None:
    assert normalize("Café Ünïcode") == "cafe unicode"


def test_normalize_collapses_whitespace_including_nbsp() -> None:
    assert normalize("  Photo\u00a0  Booth ") == "photo booth"


def test_edit_distance_counts_adjacent_transposition_as_one() -> None:
    assert edit_distance("calcualtor", "calculator") == 1


def test_edit_distance_basic_cases() -> None:
    assert edit_distance("maps", "mail") == 2
    assert edit_distance("", "abc") == 3
