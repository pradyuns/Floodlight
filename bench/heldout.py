"""Held-out set from the user's secret seed (spec §3, §9): stratum (a) typos of built-in and
third-party apps that reuse no public query string; stratum (b) every §4 rule applied to 40
secret planted apps. Only the digest and counts are ever printed."""

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

from bench.generate import Query, generate_dev, generate_typos, queries_to_json
from bench.inventory import App
from bench.names import make_planted_names
from bench.normalize import normalize

N_SECRET_APPS = 40


def _seed_int(seed: bytes) -> int:
    return int.from_bytes(hashlib.sha256(seed).digest()[:8], "big")


def _plain(queries: list[Query]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = json.loads(queries_to_json(queries))
    return rows


def build_heldout(
    seed: bytes,
    inventory: list[App],
    dictionary: Path,
    public_strings: set[str],
    public_names: set[str],
) -> dict[str, Any]:
    base = [a for a in inventory if a.kind != "planted"]
    s = _seed_int(seed)
    typos = generate_typos(base, s, exclude=public_strings, suite="heldout", stratum="a")
    forbid = {w for a in base for w in normalize(a.name).split()}
    forbid |= {w for n in public_names for w in normalize(n).split()}
    names = make_planted_names(s, N_SECRET_APPS, dictionary, forbid)
    planted = [App(n, f"/Applications/{n}.app", "", "", "planted") for n in names]
    b = [
        Query(**{**q.__dict__, "stratum": "b"})
        for q in generate_dev(base + planted, frozenset({"planted"}), "heldout")
    ]
    b_texts = {q.text for q in b}
    return {
        "version": 1,
        "planted_names": names,
        "strata": {"a": _plain(typos), "b": _plain(b)},
        "overlap_b_with_dev": len(b_texts & public_strings),
    }


def canonical_bytes(heldout: dict[str, Any]) -> bytes:
    return json.dumps(heldout, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def commitment(nonce: bytes, file_bytes: bytes) -> str:
    return hashlib.sha256(nonce + file_bytes).hexdigest()


def verify_commitment(digest: str, nonce: bytes, file_bytes: bytes) -> bool:
    return hmac.compare_digest(digest, commitment(nonce, file_bytes))
