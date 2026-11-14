import re
import struct
import xml.etree.ElementTree as ET
import zlib

import pytest

from fixtures.make_files import content_for


def _png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    chunks, pos = [], 8
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        ctype = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        (crc,) = struct.unpack(">I", data[pos + 8 + length : pos + 12 + length])
        assert crc == zlib.crc32(ctype + body), f"bad CRC in {ctype!r}"
        chunks.append((ctype, body))
        pos += 12 + length
    return chunks


def test_png_is_valid_with_correct_crcs_and_pixel_data() -> None:
    chunks = _png_chunks(content_for("icon.png", seed=1))
    types = [t for t, _ in chunks]
    assert types[0] == b"IHDR" and types[-1] == b"IEND" and b"IDAT" in types
    width, height, depth, color = struct.unpack(">IIBB", chunks[0][1][:10])
    pixels = zlib.decompress(b"".join(b for t, b in chunks if t == b"IDAT"))
    assert depth == 8 and color == 2
    assert len(pixels) == height * (1 + 3 * width)


def test_pdf_xref_offsets_point_at_their_objects() -> None:
    pdf = content_for("report.pdf", seed=1)
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    startxref = int(re.search(rb"startxref\s+(\d+)", pdf).group(1))  # type: ignore[union-attr]
    assert pdf[startxref:].startswith(b"xref")
    entries = re.findall(rb"(\d{10}) 00000 n", pdf[startxref:])
    assert len(entries) >= 4
    for number, offset in enumerate(entries, start=1):
        assert pdf[int(offset) :].startswith(f"{number} 0 obj".encode())


def test_svg_parses_as_svg_xml() -> None:
    root = ET.fromstring(content_for("logo.svg", seed=1))
    assert root.tag == "{http://www.w3.org/2000/svg}svg"


@pytest.mark.parametrize("name", ["notes.txt", "readme.md", "test.py", "main.swift", "app.js"])
def test_text_and_code_files_are_nonempty_utf8(name: str) -> None:
    assert content_for(name, seed=1).decode("utf-8").strip()


def test_python_fixture_compiles() -> None:
    compile(content_for("test.py", seed=3).decode(), "test.py", "exec")


def test_json_and_csv_fixtures_parse() -> None:
    import csv
    import io
    import json

    json.loads(content_for("data.json", seed=2))
    rows = list(csv.reader(io.StringIO(content_for("data.csv", seed=2).decode())))
    assert len(rows) > 1 and len({len(r) for r in rows}) == 1


def test_content_is_deterministic_per_seed() -> None:
    assert content_for("a.pdf", seed=5) == content_for("a.pdf", seed=5)
    assert content_for("a.txt", seed=5) != content_for("a.txt", seed=6)


def test_unknown_extension_is_rejected() -> None:
    with pytest.raises(ValueError, match="no generator"):
        content_for("x.exe", seed=1)


# --- Fixture layout (planted apps, stress, folders, cross-kind) ---

from pathlib import Path  # noqa: E402

from bench.inventory import App  # noqa: E402
from bench.normalize import normalize  # noqa: E402
from fixtures.plan import HOME, LRM, build_layout, corpus_forbid  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DICT = Path("/usr/share/dict/words")


def _inventory() -> list[App]:
    import json

    raw = json.loads((REPO / "data/inventory-macos-26.4.1.json").read_text())["apps"]
    return [App(**a) for a in raw]


@pytest.fixture(scope="module")
def layout():  # type: ignore[no-untyped-def]
    if not DICT.exists():
        pytest.skip("needs the macOS dictionary")
    return build_layout(_inventory(), DICT)


def test_layout_is_deterministic(layout) -> None:  # type: ignore[no-untyped-def]
    assert build_layout(_inventory(), DICT) == layout


def test_stress_2x2_marks_and_decoys_only_their_cells(layout) -> None:  # type: ignore[no-untyped-def]
    fam = layout.families["stress-2x2"]
    cells: dict[str, list[str]] = {}
    for q in fam.queries:
        assert q.stratum is not None
        cells.setdefault(q.stratum, []).append(q.intended.id)
    assert sorted(cells) == ["lrm=no,svg=no", "lrm=no,svg=yes", "lrm=yes,svg=no", "lrm=yes,svg=yes"]
    for stratum, names in cells.items():
        for name in set(names):
            marked = LRM + name in fam.apps
            assert marked == ("lrm=yes" in stratum) and (marked or name in fam.apps)
            decoys = [f for f in fam.files if f.endswith(".svg") and name.lower() in f.lower()]
            assert bool(decoys) == ("svg=yes" in stratum)


def test_test_py_is_unique_and_queried_by_filename(layout) -> None:  # type: ignore[no-untyped-def]
    fam = layout.families["stress-test-py"]
    assert [f for f in fam.files if f.rsplit("/", 1)[-1] == "test.py"] == [
        q.intended.id.removeprefix(HOME + "/") for q in fam.queries
    ]
    assert {q.text for q in fam.queries} == {"test.py"}
    assert len(fam.files) > 3  # decoys present


def test_cross_kind_targets_are_exact_matches_with_a_weaker_app(layout) -> None:  # type: ignore[no-untyped-def]
    apps = [normalize(a.name).split() for a in _inventory()]
    for q in layout.families["cross-kind"].queries:
        assert q.intended is not None and q.intended.kind in ("file", "settings_pane")
        assert q.acceptable == frozenset({q.intended})
        first = q.text.split(".")[0].split()[0]
        assert any(w.startswith(first) for words in apps for w in words), q.text
        assert all(" ".join(words) != q.text for words in apps), q.text


def test_folder_targets_have_names_unique_among_fixtures(layout) -> None:  # type: ignore[no-untyped-def]
    names = [q.intended.id.rsplit("/", 1)[-1] for q in layout.families["folders"].queries]
    assert all(q.intended.kind == "folder" for q in layout.families["folders"].queries)
    all_parts = [p for fam in layout.families.values() for f in fam.files for p in f.split("/")]
    for name in set(names):
        assert all_parts.count(name) >= 1
        assert (
            sum(
                1
                for p in set(
                    f.rsplit("/", 1)[0] for fam in layout.families.values() for f in fam.files
                )
                if p.endswith("/" + name)
            )
            == 1
        )


def test_planted_dev_apps_have_all_rules(layout) -> None:  # type: ignore[no-untyped-def]
    fam = layout.families["planted-dev"]
    assert len(fam.apps) == 10
    rules = {q.rule for q in fam.queries}
    assert {"full", "nospace", "initials", "prefix1", "typo"} <= rules


def test_corpus_forbid_covers_every_targeted_string(layout) -> None:  # type: ignore[no-untyped-def]
    forbid = corpus_forbid(layout)
    for fam in layout.families.values():
        for q in fam.queries:
            if q.rule in ("full", "nospace", "punct_removed", "stem"):
                assert q.text in forbid
        for app in fam.apps:
            assert app.replace(LRM, "").lower() in forbid


def test_hyphenless_folder_queries_are_labelled_and_keep_an_exact_name_control(layout) -> None:  # type: ignore[no-untyped-def]
    queries = layout.families["folders"].queries
    removed = [q for q in queries if q.rule == "punct_removed"]
    assert removed and all("-" not in q.text for q in removed)
    assert not any(q.rule == "nospace" for q in queries)
    exact = {q.intended: q.text for q in queries if q.rule == "full"}
    for q in removed:
        assert exact[q.intended].replace("-", "") == q.text
