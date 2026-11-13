import unicodedata

import pytest

from bench.generate import (
    Query,
    Target,
    generate_collisions,
    generate_dev,
    generate_stepped,
    generate_typos,
)
from bench.inventory import App
from bench.normalize import edit_distance, normalize


def _app(name: str, kind: str = "builtin") -> App:
    return App(name, f"/Applications/{name}.app", f"/Applications/{name}.app", name, kind)  # type: ignore[arg-type]


INVENTORY = [
    _app("Calculator"),
    _app("Calendar"),
    _app("Chess"),
    _app("Maps"),
    _app("Mail"),
    _app("Activity Monitor"),
    _app("Photo Booth"),
    _app("Photos"),
    _app("TV"),
    _app("Raycast", "tool_under_test"),
]


def _by(queries: list[Query], app: str, rule: str) -> list[Query]:
    return [q for q in queries if q.intended == Target("app", app) and q.rule == rule]


def _app_target(name: str) -> Target:
    return Target("app", name)


@pytest.fixture(scope="module")
def dev() -> list[Query]:
    return generate_dev(INVENTORY)


def test_prefix_ca_accepts_calendar_and_calculator(dev: list[Query]) -> None:
    (q,) = _by(dev, "Calculator", "prefix2")
    assert q.text == "ca"
    assert q.acceptable == {_app_target("Calculator"), _app_target("Calendar")}
    assert q.ambiguous is True


def test_full_name_accepts_only_intended(dev: list[Query]) -> None:
    (q,) = _by(dev, "Calculator", "full")
    assert q.text == "calculator"
    assert q.acceptable == {_app_target("Calculator")}
    assert q.ambiguous is False


def test_nospace_and_initials_only_for_multi_word_names(dev: list[Query]) -> None:
    assert _by(dev, "Activity Monitor", "nospace")[0].text == "activitymonitor"
    assert _by(dev, "Activity Monitor", "initials")[0].text == "am"
    assert _by(dev, "Calculator", "nospace") == []
    assert _by(dev, "Calculator", "initials") == []


def test_prefix_accepts_apps_with_any_word_starting_with_it(dev: list[Query]) -> None:
    (q,) = _by(dev, "Photos", "prefix4")
    assert q.text == "phot"
    assert q.acceptable == {_app_target("Photos"), _app_target("Photo Booth")}


def test_dedupe_keeps_full_over_prefix(dev: list[Query]) -> None:
    assert [q.rule for q in dev if q.intended == _app_target("Maps")].count("prefix4") == 0
    assert _by(dev, "TV", "full")[0].text == "tv"
    assert _by(dev, "TV", "prefix2") == []


def test_tools_under_test_are_never_intended() -> None:
    queries = generate_dev(INVENTORY)
    assert all(q.intended != _app_target("Raycast") for q in queries)
    assert [q for q in queries if q.text == "raycast"] == []


def test_raycast_counts_in_acceptable_set_of_shared_prefix() -> None:
    inventory = [*INVENTORY, _app("Reminders")]
    (q,) = _by(generate_dev(inventory), "Reminders", "prefix1")
    assert _app_target("Raycast") in q.acceptable


def test_generation_is_deterministic(dev: list[Query]) -> None:
    assert [q.id for q in generate_dev(INVENTORY)] == [q.id for q in dev]
    assert len({q.id for q in dev}) == len(dev)


def test_no_query_contains_format_characters() -> None:
    inventory = [*INVENTORY, _app("\u200eChatterbox")]
    for q in generate_dev(inventory):
        assert not any(unicodedata.category(c) == "Cf" for c in q.text)


def test_typos_are_one_edit_and_not_near_other_apps() -> None:
    typos = generate_typos(INVENTORY, seed=7, exclude=set())
    assert typos
    for q in typos:
        assert q.intended is not None
        source = normalize(q.intended.id)
        assert len(source.replace(" ", "")) >= 5
        assert edit_distance(q.text, source) == 1
        assert not source.startswith(q.text)
        for other in INVENTORY:
            if other.name == q.intended.id:
                continue
            name = normalize(other.name)
            for k in range(1, len(name) + 1):
                assert edit_distance(q.text, name[:k]) > 1


def test_typos_respect_exclusions() -> None:
    first = generate_typos(INVENTORY, seed=7, exclude=set())
    again = generate_typos(INVENTORY, seed=7, exclude={q.text for q in first})
    assert not {q.text for q in first} & {q.text for q in again}


def test_collisions_only_where_two_or_more_apps_are_acceptable() -> None:
    collisions = generate_collisions(INVENTORY)
    assert collisions
    assert all(len(q.acceptable) >= 2 and q.intended is None for q in collisions)
    assert "cal" in {q.text for q in collisions}


def test_stepped_queries_cover_each_app_once_in_stepped_mode() -> None:
    stepped = generate_stepped(INVENTORY)
    assert {q.intended.id for q in stepped if q.intended} == {
        a.name for a in INVENTORY if a.kind != "tool_under_test"
    }
    assert all(q.mode == "stepped" for q in stepped)


def test_queries_round_trip_through_json() -> None:
    from bench.generate import queries_from_json, queries_to_json

    queries = generate_dev(INVENTORY) + generate_collisions(INVENTORY)
    assert queries_from_json(queries_to_json(queries)) == queries


def test_initials_also_accept_apps_with_a_word_starting_with_those_letters() -> None:
    inventory = [_app("AirPort Utility"), _app("Automator"), _app("Chess")]
    (q,) = _by(generate_dev(inventory), "AirPort Utility", "initials")
    assert q.text == "au"
    assert q.acceptable == {_app_target("AirPort Utility"), _app_target("Automator")}
    assert q.ambiguous is True
