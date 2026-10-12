#!/usr/bin/env python3
"""Generate an SVG cut line for a rounded-rectangle screen protector."""

import argparse
import json
import math
import os
import re
import sys
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

DEFAULT_INSET_MM = 0.5
PRESETS_PATH = Path(__file__).resolve().parent / "presets.json"
# a name becomes part of the output filename, so this must never admit a path separator or a dot
PRESET_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


@dataclass(frozen=True)
class Outline:
    """A rounded rectangle in millimetres."""

    width: float
    height: float
    radius: float


@dataclass(frozen=True)
class Measurements:
    """A screen's measurements and the inset to cut its protector at, in millimetres."""

    width: float
    height: float
    radius: float
    inset: float

    def describe(self) -> str:
        return (
            f"screen {fmt(self.width)} x {fmt(self.height)} mm, corner radius {fmt(self.radius)} mm, "
            f"inset {fmt(self.inset)} mm per side"
        )


PRESET_FIELDS = tuple(field.name for field in fields(Measurements))


def fmt(value: float) -> str:
    """Format a millimetre value for the SVG, rounded to the micron with trailing zeros removed."""
    return f"{value:.3f}".rstrip("0").rstrip(".")


def protector_outline(width: float, height: float, radius: float, inset: float) -> Outline:
    """Return the protector outline for a screen of the given measurements, inset on every side.

    Raises ValueError if the measurements are not a valid rounded rectangle or the inset leaves
    nothing to cut.
    """
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be greater than 0")
    if radius < 0:
        raise ValueError("corner radius must not be negative")
    if inset < 0:
        raise ValueError("inset must not be negative")
    shorter = min(width, height)
    if radius > shorter / 2:
        raise ValueError(
            f"corner radius {fmt(radius)} mm is more than half the shorter side ({fmt(shorter / 2)} mm)"
        )
    if 2 * inset >= shorter:
        raise ValueError(f"an inset of {fmt(inset)} mm per side leaves nothing of a {fmt(shorter)} mm side")
    # concentric with the screen's corner, so the gap is the inset all the way round; keeping the
    # measured radius would leave a gap of about 1.4 times the inset at each corner
    corner = max(radius - inset, 0.0)
    return Outline(width - 2 * inset, height - 2 * inset, corner)


def outline_path(outline: Outline) -> str:
    """Return SVG path data tracing the outline clockwise from the top-left corner."""
    w, h, r = outline.width, outline.height, outline.radius
    if r == 0:
        return f"M0,0 H{fmt(w)} V{fmt(h)} H0 Z"
    arc = f"A{fmt(r)},{fmt(r)} 0 0 1"
    return (
        f"M{fmt(r)},0 H{fmt(w - r)} {arc} {fmt(w)},{fmt(r)} "
        f"V{fmt(h - r)} {arc} {fmt(w - r)},{fmt(h)} "
        f"H{fmt(r)} {arc} 0,{fmt(h - r)} "
        f"V{fmt(r)} {arc} {fmt(r)},0 Z"
    )


def render_svg(outline: Outline, note: str) -> str:
    """Return an SVG document sized in millimetres containing the outline as one filled path."""
    w, h = fmt(outline.width), fmt(outline.height)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}mm" height="{h}mm" viewBox="0 0 {w} {h}">\n'
        f"  <!-- {note} -->\n"
        f'  <path d="{outline_path(outline)}" fill="#000000"/>\n'
        "</svg>\n"
    )


def load_presets(path: Path) -> dict[str, Measurements]:
    """Return the presets saved at path, or none if the file does not exist.

    Raises ValueError if the file is not a valid presets file.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{path} is not valid JSON: {error}") from None
    if not isinstance(data, dict):
        raise ValueError(f"{path} must hold a JSON object of presets")

    presets = {}
    for name, entry in data.items():
        if not PRESET_NAME.fullmatch(name):
            raise ValueError(f"{path}: {name!r} is not a valid preset name")
        # an unknown key is an error rather than ignored, because the next save would drop it
        if not isinstance(entry, dict) or set(entry) != set(PRESET_FIELDS):
            raise ValueError(f"{path}: preset {name!r} must have exactly {', '.join(PRESET_FIELDS)}")
        values = [entry[key] for key in PRESET_FIELDS]
        if not all(is_finite_number(value) for value in values):
            raise ValueError(f"{path}: preset {name!r} has a value that is not a finite number")
        presets[name] = Measurements(*map(float, values))
    return presets


def save_presets(path: Path, presets: dict[str, Measurements]) -> None:
    """Write the presets to path, one per line in name order.

    The file is replaced in one step, so an interrupted save cannot lose the presets already saved.
    """
    lines = []
    for name, preset in sorted(presets.items()):
        values = {key: json_number(value) for key, value in asdict(preset).items()}
        lines.append(f"  {json.dumps(name)}: {json.dumps(values)}")
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")
    os.replace(temporary, path)


def is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def json_number(value: float) -> float | int:
    rounded = round(value, 3)
    return int(rounded) if rounded.is_integer() else rounded


def millimetres(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError(f"not a finite number: {text!r}")
    return value


def preset_name(text: str) -> str:
    if not PRESET_NAME.fullmatch(text):
        raise argparse.ArgumentTypeError(
            f"{text!r} is not a valid preset name: use lowercase letters, digits and single hyphens"
        )
    return text


def main(argv: list[str] | None = None, presets_path: Path = PRESETS_PATH) -> int:
    parser = argparse.ArgumentParser(
        description="Generate an SVG cut line for a screen protector from the screen's measurements."
    )
    parser.add_argument("width", nargs="?", type=millimetres, help="screen width in mm")
    parser.add_argument("height", nargs="?", type=millimetres, help="screen height in mm")
    parser.add_argument("radius", nargs="?", type=millimetres, help="screen corner radius in mm")
    parser.add_argument(
        "--inset",
        type=millimetres,
        help="gap between the screen edge and the protector edge on each side, in mm "
        f"(default: the preset's, or {fmt(DEFAULT_INSET_MM)})",
    )
    parser.add_argument(
        "--preset", type=preset_name, metavar="NAME", help="cut from a saved preset instead of measurements"
    )
    parser.add_argument(
        "--save",
        type=preset_name,
        metavar="NAME",
        help="save the measurements and inset as a preset, replacing any preset of the same name",
    )
    parser.add_argument("--list", action="store_true", help="list the saved presets")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="SVG file to write (default: named after the preset or measurements)",
    )
    args = parser.parse_args(argv)

    measured = (args.width, args.height, args.radius)
    others = (*measured, args.preset, args.save, args.inset, args.output)
    if args.list and any(value is not None for value in others):
        parser.error("--list takes no other arguments")
    if args.preset and any(value is not None for value in measured):
        parser.error("give either --preset or width, height and radius, not both")
    if not args.list and not args.preset and None in measured:
        parser.error("give width, height and radius, or --preset NAME")

    # read only when needed, so a broken presets file never blocks a cut from measurements
    presets = {}
    if args.list or args.preset or args.save:
        try:
            presets = load_presets(presets_path)
        except ValueError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1

    if args.list:
        for name, preset in sorted(presets.items()):
            print(f"{name}: {preset.describe()}")
        if not presets:
            print("No presets saved")
        return 0

    if args.preset:
        if args.preset not in presets:
            saved = ", ".join(sorted(presets)) or "none"
            parser.error(f"no preset named {args.preset!r} (saved presets: {saved})")
        measurements = presets[args.preset]
        if args.inset is not None:
            measurements = replace(measurements, inset=args.inset)
    else:
        inset = DEFAULT_INSET_MM if args.inset is None else args.inset
        measurements = Measurements(*measured, inset)

    try:
        outline = protector_outline(**asdict(measurements))
    except ValueError as error:
        parser.error(str(error))

    name = args.save or args.preset
    stem = name or f"{fmt(measurements.width)}x{fmt(measurements.height)}-r{fmt(measurements.radius)}"
    output = args.output or Path(f"screen-protector-{stem}-inset{fmt(measurements.inset)}.svg")
    note = f"{name}: {measurements.describe()}" if name else measurements.describe()
    try:
        output.write_text(render_svg(outline, note), encoding="utf-8")
    except OSError as error:
        print(f"error: could not write {output}: {error}", file=sys.stderr)
        return 1
    print(
        f"Wrote {output}: {fmt(outline.width)} x {fmt(outline.height)} mm, "
        f"corner radius {fmt(outline.radius)} mm"
    )

    if args.save:
        previous = presets.get(args.save)
        presets[args.save] = measurements
        try:
            save_presets(presets_path, presets)
        except OSError as error:
            print(f"error: could not save preset {args.save!r} to {presets_path}: {error}", file=sys.stderr)
            return 1
        if previous is not None and previous != measurements:
            print(f"Replaced preset {args.save}, which was {previous.describe()}")
        else:
            print(f"Saved preset {args.save}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
