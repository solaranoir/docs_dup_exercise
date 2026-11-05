"""Built-in document templates (DOC-023..027, ADR-011).

A template is a recipe for the *initial content* of an ordinary document: once created, the
document has no link back to its template, so changing a template never touches existing
documents. Each section is a level-2 heading, bold "Label:" lines to fill in and an optional
italic hint, all within the node types the editor and ``validate_content`` already accept.

Bump ``version`` whenever a template's content changes; ``tests/test_templates.py`` pins a
fingerprint per version so an unversioned change fails CI.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Section:
    heading: str
    fields: tuple[str, ...] = ()
    hint: str | None = None
    bullets: bool = False  # end with an empty bullet list for free-form notes


@dataclass(frozen=True)
class Template:
    id: str
    version: int
    name: str
    description: str
    sections: tuple[Section, ...] = field(default_factory=tuple)

    def content(self) -> dict[str, Any]:
        blocks: list[dict[str, Any]] = []
        for section in self.sections:
            blocks.append(_heading(section.heading))
            blocks.extend(_label_line(label) for label in section.fields)
            if section.hint:
                blocks.append(
                    _paragraph({"type": "text", "text": section.hint, "marks": [_ITALIC]})
                )
            if section.bullets:
                blocks.append(
                    {
                        "type": "bulletList",
                        "content": [{"type": "listItem", "content": [_paragraph()]}],
                    }
                )
        return {"type": "doc", "content": blocks}


_BOLD = {"type": "bold"}
_ITALIC = {"type": "italic"}


def _paragraph(*inline: dict[str, Any]) -> dict[str, Any]:
    return {"type": "paragraph", "content": list(inline)} if inline else {"type": "paragraph"}


def _heading(text: str) -> dict[str, Any]:
    return {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": text}]}


def _label_line(label: str) -> dict[str, Any]:
    # The unmarked trailing space means text typed at the end of the line is not bold.
    return _paragraph(
        {"type": "text", "text": f"{label}:", "marks": [_BOLD]}, {"type": "text", "text": " "}
    )


TEMPLATES: tuple[Template, ...] = (
    Template(
        id="pota-activation-plan",
        version=1,
        name="POTA Activation Plan",
        description="Plan a Parks on the Air activation: park, schedule, station, bands and "
        "conditions, with room for notes on the day.",
        sections=(
            Section("Park", ("Park reference", "Park name", "Access and parking")),
            Section("Schedule", ("Date", "Start (UTC)", "End (UTC)", "Spotting")),
            Section(
                "Equipment",
                ("Radio", "Power", "Logging"),
                hint="Include spares: fuses, coax adapters, a backup battery.",
            ),
            Section("Antenna", ("Type", "Support and height", "Feedline and tuner")),
            Section("Bands and modes", ("Bands", "Modes", "Frequencies to try")),
            Section(
                "Weather",
                ("Forecast", "Space weather (SFI, K-index)"),
                hint="Check again the morning of the activation.",
            ),
            Section("Operating notes", bullets=True),
        ),
    ),
    Template(
        id="satellite-observation-log",
        version=1,
        name="Satellite Observation Log",
        description="Record a satellite pass: timing, frequencies, elevation, your station and "
        "how well it was received.",
        sections=(
            Section("Satellite", ("Satellite", "Mode", "Grid square")),
            Section("Pass", ("Date", "AOS (UTC)", "LOS (UTC)", "Maximum elevation")),
            Section("Frequencies", ("Uplink", "Downlink", "CTCSS / PL tone", "Doppler notes")),
            Section("Equipment", ("Radio", "Antenna", "Preamp / filters", "Recording")),
            Section(
                "Reception",
                ("Signal quality", "Contacts"),
                hint="Note fades, pass direction and any interference.",
            ),
            Section("Observations", bullets=True),
        ),
    ),
    Template(
        id="antenna-experiment",
        version=1,
        name="Antenna Experiment",
        description="Test an antenna idea: what you expect, how it is set up, what you measured "
        "and what to try next.",
        sections=(
            Section(
                "Hypothesis",
                hint="What do you expect to happen, and why?",
                bullets=True,
            ),
            Section(
                "Setup", ("Antenna", "Dimensions", "Height and orientation", "Feedline", "Location")
            ),
            Section(
                "Measurements",
                ("Instrument", "SWR / impedance", "Signal reports or RBN spots"),
                hint="Record frequencies and readings, with times.",
            ),
            Section("Conditions", ("Date and time (UTC)", "Weather", "Band conditions")),
            Section("Results", bullets=True),
            Section("Next steps", bullets=True),
        ),
    ),
    Template(
        id="research-notes",
        version=1,
        name="Research / Engineering Notes",
        description="Work through a technical question: the problem, your assumptions and "
        "method, the evidence and what you found.",
        sections=(
            Section("Problem", hint="State the question in one or two sentences.", bullets=True),
            Section("Assumptions", bullets=True),
            Section("Method", bullets=True),
            Section("Evidence", hint="Link sources, data and attachments.", bullets=True),
            Section("Findings", bullets=True),
            Section("Follow-ups", bullets=True),
        ),
    ),
)

BY_ID: dict[str, Template] = {t.id: t for t in TEMPLATES}
