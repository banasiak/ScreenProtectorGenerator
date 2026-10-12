# CLAUDE.md

## Project Overview

A command-line script that turns three caliper and radius-gauge measurements of a phone screen into
an SVG cut line for a Cricut. The README is the source of truth for usage. Update it with any change
to arguments, defaults or output.

## Commands

```bash
python3 screen_protector.py WIDTH HEIGHT RADIUS [--inset MM] [--save NAME] [-o PATH]
python3 screen_protector.py --preset NAME [--inset MM] [--save NAME] [-o PATH]
python3 screen_protector.py --list
python3 -m unittest
```

## Architecture

`screen_protector.py` is a pipeline of pure functions that `main` wires to argparse:
`protector_outline` validates the measurements and applies the inset, `outline_path` traces the
rounded rectangle as path data, and `render_svg` wraps it in a document. `load_presets` and
`save_presets` read and write `presets.json` as `Measurements`, the screen measurements plus inset.
`main` takes the presets path as a parameter so the tests can point it at a temporary file.
`test_screen_protector.py` sits at the root so plain `python3 -m unittest` discovers it.

## Constraints

- **Standard library only.** The script has to run on a bare `python3`. A dependency would need a
  reason strong enough to outweigh adding a supply chain to a one-file tool.
- **The SVG is sized in millimetres.** `width` and `height` carry an `mm` suffix, and the `viewBox`
  uses the same numbers, so one user unit is one millimetre. A size in pixels or without units
  leaves the importer to guess the pixels per inch (72 and 96 are both common), and the cut comes
  out the wrong size.
- **One filled path with no stroke.** The cut follows the path geometry. Some importers count a
  stroke in the shape's bounds, which would make the size Design Space reports disagree with the
  size the script printed.
- **Every number goes through `fmt`.** It rounds to 0.001 mm so that float noise such as
  `0.30000000000000004` never reaches the file or the default filename.
- **`presets.json` is the user's data and is committed, never ignored.** It sits next to the script
  and holds measurements taken by hand, and git history is the backup that makes replacing a preset
  on save safe. Running the script with `--save` from the repo writes the real file, so exercise the
  CLI from a copy of the script in a scratch directory, or through `main(presets_path=...)` as the
  tests do.
- **A saved preset always records its inset, even the default.** The right inset for a phone is
  found by test cuts, so changing `DEFAULT_INSET_MM` must not silently change a phone already dialled
  in.
- **One preset per line.** `save_presets` writes its own layout rather than `json.dumps(indent=2)`,
  so that each phone's history is a one-line diff.
- **The default filename always includes the inset**, including for presets, so trying a different
  `--inset` writes a new file rather than overwriting the last cut.

## Verification status

- `rsvg-convert -d 300 -p 300` renders a 70.5 × 151.8 mm outline at 833 × 1793 px, i.e.
  70.53 × 151.81 mm: the millimetre sizing works there, within a pixel of rounding.
- Not yet verified: how Design Space imports the file (its reported size and how it handles the
  `A` arc commands). Once a paper cut has been measured, record the result here. If Design Space
  mishandles arcs, the fallback is one cubic Bézier per corner (control-point factor 0.5523,
  radial error under 0.03 % of the radius).
