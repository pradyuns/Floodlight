from bench.selection import select_samples


def _rec(q: str, tool: str, block: int, attempt: int, error: str | None = None) -> dict:  # type: ignore[type-arg]
    return {
        "query_id": q,
        "tool": tool,
        "run": 0,
        "condition": "warm",
        "block": block,
        "attempt": attempt,
        "error": error,
    }


def test_first_clean_attempt_in_an_unflagged_block_is_used() -> None:
    raw = [_rec("q", "spotlight", 0, 0), _rec("q", "spotlight", 0, 1)]
    picked, kept_errors = select_samples(raw, flagged={(0, 0): True, (0, 1): False})
    assert picked[("q", "spotlight", 0, "warm")]["attempt"] == 1 and kept_errors == []


def test_errored_attempt_is_replaced_by_its_requeue() -> None:
    raw = [_rec("q", "raycast", 3, 0, "field_never_matched"), _rec("q", "raycast", 3, 1)]
    picked, _ = select_samples(raw, flagged={(3, 0): False, (3, 1): False})
    assert picked[("q", "raycast", 0, "warm")]["attempt"] == 1


def test_when_every_attempt_is_flagged_the_last_is_used_and_labelled() -> None:
    raw = [_rec("q", "raycast", 2, a) for a in range(3)]
    picked, _ = select_samples(raw, flagged={(2, 0): True, (2, 1): True, (2, 2): True})
    chosen = picked[("q", "raycast", 0, "warm")]
    assert chosen["attempt"] == 2 and chosen["flagged"] is True


def test_slot_with_only_errors_is_a_kept_error_not_a_sample() -> None:
    raw = [_rec("q", "raycast", 1, 0, "not_ready"), _rec("q", "raycast", 1, 1, "not_ready")]
    picked, kept_errors = select_samples(raw, flagged={(1, 0): False, (1, 1): False})
    assert ("q", "raycast", 0, "warm") not in picked
    assert kept_errors == [("q", "raycast", 0, "warm")]
