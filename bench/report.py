"""Markdown report: verdict first, and where Floodlight loses always shown (project rules)."""

from dataclasses import dataclass

from bench.stats import verdict

VERDICT_TEXT = {
    "better": "Meaningfully better",
    "worse": "Meaningfully worse",
    "similar": "Practically similar (within ±5 points)",
    "inconclusive": "Inconclusive",
}


@dataclass(frozen=True)
class Comparison:
    name: str
    diff: float
    lo: float
    hi: float

    def line(self) -> str:
        v = VERDICT_TEXT[verdict(self.lo, self.hi)]
        return (
            f"{v}: {self.name}: {self.diff:+.1f} points (95% CI {self.lo:+.1f} to {self.hi:+.1f})"
        )


def render_report(
    primary: Comparison,
    secondary: list[Comparison],
    losses: list[str],
    failure_types: dict[str, int],
) -> str:
    lines = [f"Verdict: {primary.line()}", "", "## Secondary comparisons (descriptive)", ""]
    lines += [f"- {c.line()}" for c in secondary] or ["- None."]
    lines += ["", "## Where Floodlight loses", ""]
    lines += [f"- {loss}" for loss in losses] or ["- None found in this run."]
    lines += ["", "## Failure types", ""]
    lines += [f"- {name}: {count}" for name, count in sorted(failure_types.items())] or ["- None."]
    return "\n".join(lines) + "\n"
