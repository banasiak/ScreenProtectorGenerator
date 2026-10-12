# Screen Protector Generator

Generates an SVG cut line for a screen protector from three measurements of the screen: its width,
its height and its corner radius. Import the SVG into Cricut Design Space to cut hydrogel film to
fit.

The outline is a rounded rectangle. Cutouts for cameras or sensors, continuous ("squircle") corners
and curved screen edges are not supported.

## Requirements

Python 3.11 or later. The script uses only the standard library, so there is nothing to install.

## Measuring

- **Width and height:** measure the screen with calipers.
- **Corner radius:** find the radius gauge that sits flush against a corner of the screen.

Enter all three in millimetres, exactly as measured. The script makes the protector smaller itself.

## Usage

```bash
python3 screen_protector.py 71.5 152.8 8
```

The arguments are width, height and corner radius, in that order. The command prints the size of
the protector it wrote:

```
Wrote screen-protector-71.5x152.8-r8-inset0.5.svg: 70.5 x 151.8 mm, corner radius 7.5 mm
```

| Option | Meaning |
| --- | --- |
| `--inset MM` | Gap between the screen edge and the protector edge on each side. Defaults to the preset's inset, or 0.5 mm. |
| `--save NAME` | Also save the measurements and inset as a preset. |
| `--preset NAME` | Cut from a saved preset instead of measurements. |
| `--list` | List the saved presets. |
| `-o`, `--output PATH` | Where to write the SVG. Defaults to a name built from the preset or measurements and the inset, in the current directory. |

The inset keeps the protector's edge off the edge of the screen, where it would catch and lift. The
corner radius shrinks by the inset too, so the gap is the same all the way round. With an inset
larger than the corner radius, the protector's corners come out square.

The SVG also records the measurements it was made from, in a comment.

## Presets

Save a phone's measurements the first time you cut for it:

```bash
python3 screen_protector.py 71.5 152.8 8 --save pixel9
```

After that, the name is enough:

```bash
python3 screen_protector.py --preset pixel9
```

- Presets are kept in `presets.json`, next to the script, so `--preset` works from any directory.
  Commit it to keep a history of each phone's measurements.
- A preset records its inset as well. `--inset` with `--preset` changes it for that cut only. To
  keep the new inset, save over the preset: `--preset pixel9 --inset 0.75 --save pixel9`.
- Saving under an existing name replaces that preset, and the script prints the values it replaced.
- Names may use lowercase letters, digits and single hyphens, because they become part of the SVG's
  filename.
- `presets.json` can be edited by hand. Each preset needs exactly `width`, `height`, `radius` and
  `inset`. The script refuses a file with anything else, rather than drop it on the next save.

## Cutting

1. Upload the SVG to Design Space.
2. Check the width and height that Design Space shows for the shape against the size the script
   printed. The SVG is sized in millimetres, and this is the check that Design Space kept that size.
3. Cut the first one from paper or cardstock and lay it on the screen. If the gap looks wrong, rerun
   the script with a different `--inset`.
4. Cut the hydrogel film.

## Tests

```bash
python3 -m unittest
```

## License

Released into the public domain under the [Unlicense](LICENSE).
