"""Which recorded attempt stands for each scheduled slot (analysis plan, "Pilot-derived settings"):
the first attempt that is neither errored nor in a flagged block; if every clean attempt was
flagged, the last clean one, labelled flagged. A slot with no clean attempt is a kept error."""

from typing import Any

Slot = tuple[str, str, int, str]


def select_samples(
    raw: list[dict[str, Any]], flagged: dict[tuple[int, int], bool]
) -> tuple[dict[Slot, dict[str, Any]], list[Slot]]:
    attempts: dict[Slot, list[dict[str, Any]]] = {}
    for rec in raw:
        key = (rec["query_id"], rec["tool"], rec["run"], rec["condition"])
        attempts.setdefault(key, []).append(rec)
    picked: dict[Slot, dict[str, Any]] = {}
    kept_errors: list[Slot] = []
    for key, recs in attempts.items():
        clean = [r for r in recs if r.get("error") is None]
        if not clean:
            kept_errors.append(key)
            continue
        unflagged = [r for r in clean if not flagged[(r["block"], r["attempt"])]]
        chosen = unflagged[0] if unflagged else clean[-1]
        picked[key] = {**chosen, "flagged": not unflagged}
    return picked, sorted(kept_errors)
