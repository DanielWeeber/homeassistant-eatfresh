"""The README quotes the panel and the cards word for word."""

from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "eatfresh"


def _ui_texts() -> str:
    """Return all texts the panel, the cards and Home Assistant show."""
    parts = [
        (ROOT / "frontend" / "src" / "i18n.ts").read_text(encoding="utf-8"),
        (ROOT / "frontend" / "src" / "eatfresh-cards.ts").read_text(encoding="utf-8"),
        (COMPONENT / "strings.json").read_text(encoding="utf-8"),
    ]
    parts += [
        path.read_text(encoding="utf-8")
        for path in sorted((COMPONENT / "translations").glob("*.json"))
    ]
    return "\n".join(parts)


def test_quoted_labels_exist_in_the_ui() -> None:
    """Every „…“ (German) and "…" (English) label in the README is a UI text."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    texts = _ui_texts()
    quoted = re.findall(r"„([^“]+)“", readme) + re.findall(r'"([^"]+)"', readme)
    assert quoted
    missing = [label for label in quoted if label not in texts]
    assert not missing, f"README labels not found in the UI: {missing}"


def test_card_yaml_titles_are_the_defaults() -> None:
    """The card examples show the default titles of the cards."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    cards = (ROOT / "frontend" / "src" / "eatfresh-cards.ts").read_text(encoding="utf-8")
    defaults = set(re.findall(r'(?:week|today)_title: "([^"]+)"', cards))
    titles = re.findall(r"^title: (.+)$", readme, flags=re.MULTILINE)
    assert len(titles) == 4
    assert set(titles) == defaults
