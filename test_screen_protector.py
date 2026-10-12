import contextlib
import io
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from screen_protector import (
    Measurements,
    Outline,
    fmt,
    load_presets,
    main,
    outline_path,
    protector_outline,
    render_svg,
    save_presets,
)

SVG_NS = "{http://www.w3.org/2000/svg}"


class FmtTest(unittest.TestCase):
    def test_drops_trailing_zeros(self):
        self.assertEqual(fmt(70.0), "70")
        self.assertEqual(fmt(70.5), "70.5")
        self.assertEqual(fmt(0.0), "0")

    def test_hides_float_noise(self):
        self.assertEqual(fmt(0.1 + 0.2), "0.3")
        self.assertEqual(fmt(152.8 - 2 * 0.5), "151.8")


class ProtectorOutlineTest(unittest.TestCase):
    def test_inset_shrinks_each_side_and_the_corner(self):
        outline = protector_outline(71.5, 152.8, 8.0, 0.5)
        self.assertAlmostEqual(outline.width, 70.5)
        self.assertAlmostEqual(outline.height, 151.8)
        self.assertAlmostEqual(outline.radius, 7.5)

    def test_zero_inset_keeps_the_measurements(self):
        self.assertEqual(protector_outline(70, 150, 8, 0), Outline(70, 150, 8))

    def test_inset_larger_than_radius_gives_square_corners(self):
        self.assertEqual(protector_outline(70, 150, 0.3, 0.5).radius, 0)

    def test_radius_of_half_the_shorter_side_is_allowed(self):
        # a stadium shape: the short sides are fully round
        self.assertAlmostEqual(protector_outline(20, 50, 10, 1).radius, 9)

    def test_rejects_radius_over_half_the_shorter_side(self):
        with self.assertRaisesRegex(ValueError, "more than half the shorter side"):
            protector_outline(20, 50, 10.01, 0)

    def test_rejects_non_positive_size(self):
        for width, height in [(0, 50), (20, 0), (-1, 50)]:
            with self.subTest(width=width, height=height):
                with self.assertRaises(ValueError):
                    protector_outline(width, height, 0, 0)

    def test_rejects_negative_radius_or_inset(self):
        with self.assertRaises(ValueError):
            protector_outline(20, 50, -1, 0)
        with self.assertRaises(ValueError):
            protector_outline(20, 50, 1, -0.5)

    def test_rejects_inset_that_consumes_the_shorter_side(self):
        with self.assertRaisesRegex(ValueError, "leaves nothing"):
            protector_outline(20, 50, 1, 10)


class OutlinePathTest(unittest.TestCase):
    def test_rounded_corners_are_clockwise_quarter_arcs(self):
        self.assertEqual(
            outline_path(Outline(10, 20, 2)),
            "M2,0 H8 A2,2 0 0 1 10,2 V18 A2,2 0 0 1 8,20 H2 A2,2 0 0 1 0,18 V2 A2,2 0 0 1 2,0 Z",
        )

    def test_square_corners_have_no_arcs(self):
        self.assertEqual(outline_path(Outline(10, 20, 0)), "M0,0 H10 V20 H0 Z")


class RenderSvgTest(unittest.TestCase):
    def test_document_is_sized_in_millimetres(self):
        root = ET.fromstring(render_svg(Outline(70.5, 151.8, 7.5), "note"))
        self.assertEqual(root.get("width"), "70.5mm")
        self.assertEqual(root.get("height"), "151.8mm")
        self.assertEqual(root.get("viewBox"), "0 0 70.5 151.8")

    def test_outline_is_a_single_filled_path_without_stroke(self):
        root = ET.fromstring(render_svg(Outline(70.5, 151.8, 7.5), "note"))
        paths = root.findall(f"{SVG_NS}path")
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].get("d"), outline_path(Outline(70.5, 151.8, 7.5)))
        self.assertIsNone(paths[0].get("stroke"))


class PresetsFileTest(unittest.TestCase):
    def setUp(self):
        self.path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "presets.json"

    def write(self, text):
        self.path.write_text(text, encoding="utf-8")

    def test_missing_file_means_no_presets(self):
        self.assertEqual(load_presets(self.path), {})

    def test_saves_one_preset_per_line_in_name_order(self):
        save_presets(
            self.path,
            {
                "pixel9": Measurements(71.5, 152.8, 8.0, 0.5),
                "iphone-15": Measurements(70.6, 147.6, 0.1 + 0.2, 1.0),
            },
        )
        self.assertEqual(
            self.path.read_text(encoding="utf-8"),
            "{\n"
            '  "iphone-15": {"width": 70.6, "height": 147.6, "radius": 0.3, "inset": 1},\n'
            '  "pixel9": {"width": 71.5, "height": 152.8, "radius": 8, "inset": 0.5}\n'
            "}\n",
        )

    def test_save_and_load_round_trip(self):
        presets = {"pixel9": Measurements(71.5, 152.8, 8.0, 0.5), "a1": Measurements(60, 120, 0, 0)}
        save_presets(self.path, presets)
        self.assertEqual(load_presets(self.path), presets)
        self.assertFalse(self.path.with_name("presets.json.tmp").exists())

    def test_rejects_malformed_files(self):
        cases = {
            "not JSON": "{",
            "not an object": "[]",
            "bad name": '{"../x": {"width": 1, "height": 1, "radius": 0, "inset": 0}}',
            "missing key": '{"a": {"width": 1, "height": 1, "radius": 0}}',
            # rejected rather than ignored, since the next save would silently drop it
            "unknown key": '{"a": {"width": 1, "height": 1, "radius": 0, "inset": 0, "note": "x"}}',
            "string value": '{"a": {"width": "1", "height": 1, "radius": 0, "inset": 0}}',
            "boolean value": '{"a": {"width": true, "height": 1, "radius": 0, "inset": 0}}',
            "NaN value": '{"a": {"width": NaN, "height": 1, "radius": 0, "inset": 0}}',
        }
        for case, text in cases.items():
            with self.subTest(case):
                self.write(text)
                with self.assertRaises(ValueError):
                    load_presets(self.path)


class MainTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(contextlib.chdir(directory))
        self.presets_path = Path(directory) / "presets.json"

    def run_main(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = main(list(args), presets_path=self.presets_path)
            except SystemExit as exit_:
                code = exit_.code
        return code, stdout.getvalue(), stderr.getvalue()

    def svg_root(self, filename):
        return ET.fromstring(Path(filename).read_text(encoding="utf-8"))

    def test_writes_the_inset_outline(self):
        code, stdout, _ = self.run_main("71.5", "152.8", "8", "-o", "protector.svg")
        self.assertEqual(code, 0)
        self.assertIn("70.5 x 151.8 mm, corner radius 7.5 mm", stdout)
        self.assertEqual(self.svg_root("protector.svg").get("width"), "70.5mm")

    def test_default_filename_records_the_measurements(self):
        code, _, _ = self.run_main("71.5", "152.8", "8", "--inset", "0.75")
        self.assertEqual(code, 0)
        self.assertTrue(Path("screen-protector-71.5x152.8-r8-inset0.75.svg").is_file())

    def test_rejects_an_impossible_radius_as_a_usage_error(self):
        code, _, stderr = self.run_main("20", "50", "11")
        self.assertEqual(code, 2)
        self.assertIn("more than half the shorter side", stderr)

    def test_rejects_non_finite_numbers(self):
        for value in ["nan", "inf"]:
            with self.subTest(value=value):
                code, _, stderr = self.run_main(value, "50", "1")
                self.assertEqual(code, 2)
                self.assertIn("not a finite number", stderr)

    def test_requires_all_three_measurements_or_a_preset(self):
        for args in [(), ("71.5",), ("71.5", "152.8")]:
            with self.subTest(args=args):
                code, _, stderr = self.run_main(*args)
                self.assertEqual(code, 2)
                self.assertIn("give width, height and radius, or --preset NAME", stderr)

    def test_save_records_the_measurements_and_names_the_file(self):
        code, stdout, _ = self.run_main("71.5", "152.8", "8", "--save", "pixel9")
        self.assertEqual(code, 0)
        self.assertIn("Saved preset pixel9", stdout)
        self.assertEqual(load_presets(self.presets_path), {"pixel9": Measurements(71.5, 152.8, 8, 0.5)})
        self.assertTrue(Path("screen-protector-pixel9-inset0.5.svg").is_file())

    def test_preset_cuts_the_same_outline_as_its_measurements(self):
        self.run_main("71.5", "152.8", "8", "--inset", "0.75", "-o", "measured.svg")
        self.run_main("71.5", "152.8", "8", "--inset", "0.75", "--save", "pixel9", "-o", "saved.svg")
        code, _, _ = self.run_main("--preset", "pixel9")
        self.assertEqual(code, 0)
        from_preset = self.svg_root("screen-protector-pixel9-inset0.75.svg")
        measured = self.svg_root("measured.svg")
        self.assertEqual(from_preset.get("width"), measured.get("width"))
        self.assertEqual(
            from_preset.find(f"{SVG_NS}path").get("d"), measured.find(f"{SVG_NS}path").get("d")
        )

    def test_inset_overrides_a_preset_without_changing_it(self):
        self.run_main("71.5", "152.8", "8", "--save", "pixel9")
        code, stdout, _ = self.run_main("--preset", "pixel9", "--inset", "1")
        self.assertEqual(code, 0)
        self.assertIn("69.5 x 150.8 mm, corner radius 7 mm", stdout)
        self.assertTrue(Path("screen-protector-pixel9-inset1.svg").is_file())
        self.assertEqual(load_presets(self.presets_path)["pixel9"].inset, 0.5)

    def test_save_replaces_a_preset_and_reports_the_old_values(self):
        self.run_main("71.5", "152.8", "8", "--save", "pixel9")
        code, stdout, _ = self.run_main("--preset", "pixel9", "--inset", "1", "--save", "pixel9")
        self.assertEqual(code, 0)
        self.assertIn(
            "Replaced preset pixel9, which was screen 71.5 x 152.8 mm, corner radius 8 mm, inset 0.5 mm",
            stdout,
        )
        self.assertEqual(load_presets(self.presets_path)["pixel9"].inset, 1)

    def test_save_keeps_the_other_presets(self):
        self.run_main("71.5", "152.8", "8", "--save", "pixel9")
        self.run_main("70.6", "147.6", "9", "--save", "iphone-15")
        self.assertEqual(set(load_presets(self.presets_path)), {"pixel9", "iphone-15"})

    def test_lists_presets_in_name_order(self):
        self.run_main("71.5", "152.8", "8", "--save", "pixel9")
        self.run_main("70.6", "147.6", "9", "--inset", "1", "--save", "iphone-15")
        code, stdout, _ = self.run_main("--list")
        self.assertEqual(code, 0)
        self.assertEqual(
            stdout,
            "iphone-15: screen 70.6 x 147.6 mm, corner radius 9 mm, inset 1 mm per side\n"
            "pixel9: screen 71.5 x 152.8 mm, corner radius 8 mm, inset 0.5 mm per side\n",
        )

    def test_list_with_no_presets(self):
        code, stdout, _ = self.run_main("--list")
        self.assertEqual(code, 0)
        self.assertEqual(stdout, "No presets saved\n")

    def test_unknown_preset_names_the_saved_ones(self):
        self.run_main("71.5", "152.8", "8", "--save", "pixel9")
        code, _, stderr = self.run_main("--preset", "pixel8")
        self.assertEqual(code, 2)
        self.assertIn("no preset named 'pixel8' (saved presets: pixel9)", stderr)

    def test_rejects_names_that_could_leave_the_directory(self):
        for name in ["../pixel9", "a/b", "Pixel9", "pixel.9", "-pixel9", ""]:
            with self.subTest(name=name):
                code, _, stderr = self.run_main("71.5", "152.8", "8", f"--save={name}")
                self.assertEqual(code, 2)
                self.assertFalse(self.presets_path.exists())

    def test_rejects_conflicting_arguments(self):
        self.run_main("71.5", "152.8", "8", "--save", "pixel9")
        cases = {
            ("--preset", "pixel9", "71.5", "152.8", "8"): "not both",
            ("--list", "--preset", "pixel9"): "--list takes no other arguments",
            ("--list", "71.5", "152.8", "8"): "--list takes no other arguments",
        }
        for args, message in cases.items():
            with self.subTest(args=args):
                code, _, stderr = self.run_main(*args)
                self.assertEqual(code, 2)
                self.assertIn(message, stderr)

    def test_a_broken_presets_file_does_not_block_a_cut_from_measurements(self):
        self.presets_path.write_text("{", encoding="utf-8")
        code, _, _ = self.run_main("71.5", "152.8", "8")
        self.assertEqual(code, 0)
        code, _, stderr = self.run_main("--list")
        self.assertEqual(code, 1)
        self.assertIn("is not valid JSON", stderr)

    def test_preset_name_is_recorded_in_the_svg(self):
        self.run_main("71.5", "152.8", "8", "--save", "pixel9")
        text = Path("screen-protector-pixel9-inset0.5.svg").read_text(encoding="utf-8")
        self.assertIn(
            "<!-- pixel9: screen 71.5 x 152.8 mm, corner radius 8 mm, inset 0.5 mm per side -->", text
        )


if __name__ == "__main__":
    unittest.main()
