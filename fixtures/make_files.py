"""Small, valid file contents for planted fixtures and the busy corpus, chosen by extension."""

import json
import random
import struct
import zlib
from collections.abc import Callable
from pathlib import PurePosixPath

WORDS = [
    "alpha",
    "beta",
    "gamma",
    "delta",
    "river",
    "stone",
    "cloud",
    "paper",
    "window",
    "garden",
    "orange",
    "silver",
    "north",
    "south",
    "market",
    "planet",
    "signal",
    "module",
    "vector",
    "record",
    "sample",
    "budget",
    "meeting",
    "summary",
    "draft",
    "review",
    "travel",
    "kitchen",
    "recipe",
    "invoice",
    "project",
    "report",
    "schedule",
    "chapter",
    "outline",
    "estimate",
]


def _sentence(rng: random.Random, n: int = 12) -> str:
    return " ".join(rng.choice(WORDS) for _ in range(n)).capitalize() + "."


def _text(rng: random.Random) -> bytes:
    return ("\n".join(_sentence(rng) for _ in range(rng.randint(2, 8))) + "\n").encode()


def _markdown(rng: random.Random) -> bytes:
    return f"# {_sentence(rng, 3)}\n\n{_text(rng).decode()}".encode()


def _python(rng: random.Random) -> bytes:
    a, b = rng.choice(WORDS), rng.choice(WORDS)
    return f"def {a}_{b}(x):\n    return x * {rng.randint(2, 9)}\n\n\nprint({a}_{b}(3))\n".encode()


def _swift(rng: random.Random) -> bytes:
    name, value = rng.choice(WORDS), rng.randint(1, 99)
    return f'let {name} = {value}\nprint("{_sentence(rng, 4)}")\n'.encode()


def _javascript(rng: random.Random) -> bytes:
    return f"export const {rng.choice(WORDS)} = {rng.randint(1, 99)};\n".encode()


def _json(rng: random.Random) -> bytes:
    data = {rng.choice(WORDS): rng.randint(0, 999) for _ in range(rng.randint(2, 6))}
    return (json.dumps(data, indent=1, sort_keys=True) + "\n").encode()


def _csv(rng: random.Random) -> bytes:
    lines = ["name,amount,count"] + [
        f"{rng.choice(WORDS)},{rng.randint(1, 999)}.{rng.randint(0, 99):02d},{rng.randint(1, 9)}"
        for _ in range(rng.randint(2, 10))
    ]
    return ("\n".join(lines) + "\n").encode()


def _svg(rng: random.Random) -> bytes:
    r, g, b = (rng.randint(0, 255) for _ in range(3))
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
        f'<rect width="64" height="64" fill="rgb({r},{g},{b})"/>'
        f'<circle cx="32" cy="32" r="{rng.randint(8, 30)}" fill="white"/></svg>\n'
    ).encode()


def _png_chunk(ctype: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + ctype + body + struct.pack(">I", zlib.crc32(ctype + body))


def _png(rng: random.Random) -> bytes:
    width = height = 8
    pixel = bytes(rng.randint(0, 255) for _ in range(3))
    raw = b"".join(b"\x00" + pixel * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw))
        + _png_chunk(b"IEND", b"")
    )


def _pdf(rng: random.Random) -> bytes:
    text = _sentence(rng, 6).replace("(", "").replace(")", "")
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    out += f"startxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


GENERATORS: dict[str, Callable[[random.Random], bytes]] = {
    ".txt": _text,
    ".md": _markdown,
    ".py": _python,
    ".swift": _swift,
    ".js": _javascript,
    ".json": _json,
    ".csv": _csv,
    ".svg": _svg,
    ".png": _png,
    ".pdf": _pdf,
}


def content_for(name: str, seed: int) -> bytes:
    suffix = PurePosixPath(name).suffix.lower()
    if suffix not in GENERATORS:
        raise ValueError(f"no generator for {suffix or 'files without an extension'}: {name}")
    return GENERATORS[suffix](random.Random(f"{seed}:{name}"))
