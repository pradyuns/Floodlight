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
