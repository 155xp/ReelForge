"""The text charts: round-number axes, bar heights to the eighth, areas, marks (dashboard.charts)."""

from __future__ import annotations

import math
import unittest

from rich.cells import cell_len
from rich.style import Style

from dashboard import charts


class AxisTest(unittest.TestCase):
    def test_nice_range(self):
        self.assertEqual(charts.nice_range(0, 23, 4), (0, 25, 5))
        self.assertEqual(charts.nice_range(0, 0.4, 4), (0, 1, 1))  # counts step by whole numbers
        lo, hi, step = charts.nice_range(1180, 1630, 3, whole=False)
        self.assertLessEqual(lo, 1180)
        self.assertGreaterEqual(hi, 1630)
        self.assertIn(step, (100, 200, 250))

    def test_tick_labels(self):
        self.assertEqual([charts.fmt_tick(v) for v in (0, 250, 2500, 10000, 1_200_000)],
                         ["0", "250", "2.5K", "10K", "1.2M"])


def plain(rows):
    return [r.plain for r in rows]


def cells(row):
    """[(character, foreground hex or None, background hex or None)] for each column of a drawn row."""
    out = [(ch, None, None) for ch in row.plain]
    for span in row.spans:
        style = Style.parse(span.style) if isinstance(span.style, str) else span.style
        fg = style.color.triplet.hex if style.color and style.color.triplet else None
        bg = style.bgcolor.triplet.hex if style.bgcolor and style.bgcolor.triplet else None
        for k in range(span.start, span.end):
            out[k] = (row.plain[k], fg, bg)
    return out


class BarsTest(unittest.TestCase):
    def test_size_and_heights(self):
        a = charts.Series("a", "A", "#25f4ee", values=[0, 4, 8, None])
        rows, lay = charts.bars([a], 4, 40, 12, [(0, "x")])
        self.assertEqual(len(rows), 12)
        self.assertTrue(all(cell_len(r.plain) <= 40 for r in rows))
        # The tallest bar fills the plot up to its value: 8 on an axis that tops out at 8 or above.
        self.assertGreaterEqual(lay.hi, 8)
        self.assertIn("x", plain(rows)[-1])

    def test_stacks_have_no_slivers(self):
        # Inside a stack every cell is one colour (the platform filling most of it): no 1/8-row slivers or thin
        # lines where platforms meet, a platform too thin to see joins its neighbour, and only the top cell is a
        # partial block.
        a = charts.Series("a", "A", "#ff0000", values=[1.5, 9.0, 4.0])
        b = charts.Series("b", "B", "#0000ff", values=[1.5, 2.6, 0.0])
        x = charts.Series("x", "X", "#ffffff", values=[0.1, 0.1, 0.1])  # the white X series: never a white sliver
        rows, lay = charts.bars([a, b, x], 3, 40, 14)
        for row in rows[:lay.ph]:
            for ch, fg, bg in cells(row)[lay.lw + 1:]:
                if ch in charts.EIGHTHS[1:8]:
                    self.assertIn(bg, (None, charts.HOVER))  # a partial block is only ever a bar's top
                self.assertNotIn("#ffffff", (fg, bg))  # the X series' 0.1 is too thin to show: no white sliver

    def test_a_thin_top_joins_the_cell_below(self):
        # Red fills four rows exactly and white adds an eighth: the top eighth is red, not a white line. White
        # filling most of a row's top piece does show.
        lay = charts.Layout(2, 1, 6, 0, 10, 5)
        for white_top, expect in ((33, "#ff0000"), (38, "#ffffff")):
            canvas = charts.Canvas(1, 6)
            charts._stack(canvas, lay, range(1), [(0, 32, "#ff0000"), (32, white_top, "#ffffff")])
            ch, fg, _ = canvas.cells[(lay.ph - 1 - 4, 0)]
            self.assertEqual((ch, fg), (charts.EIGHTHS[white_top - 32], expect))

    def test_bars_keep_a_gap(self):
        # Two or more columns per slot: every bar is the same width with a one-column gap after it.
        a = charts.Series("a", "A", "#25f4ee", values=[5.0] * 12)
        for w in (40, 47, 60, 75, 100):
            rows, lay = charts.bars([a], 12, w, 8)
            bottom = "".join("#" if bg == "#25f4ee" else "." for _, _, bg in cells(rows[lay.ph - 1])[lay.lw + 1:])
            runs = [len(r) for r in bottom.split(".") if r]
            self.assertEqual(len(runs), 12, (w, bottom))
            self.assertEqual(len(set(runs)), 1, (w, bottom))  # all the same width

    def test_bars_use_the_whole_width(self):
        # One axis, on the left: the plot runs to the right edge (no second axis for a running total).
        a = charts.Series("a", "A", "#25f4ee", values=[1, 2, 3])
        rows, lay = charts.bars([a], 3, 50, 10)
        self.assertEqual(lay.lw + 1 + lay.pw, 50)
        self.assertTrue(all(len(r.plain) <= 50 for r in rows))


class LinesTest(unittest.TestCase):
    def test_area_and_line(self):
        area = charts.Series("this", "this", "#25f4ee", xs=[0, 5, 10], ys=[0, 50, 100], style="area")
        line = charts.Series("typical", "typical", "#ffb020", xs=[0, 10], ys=[0, 60])
        rows, lay = charts.lines([area, line], 10, 60, 14, lambda pw: charts.age_labels(10, pw), zero=True)
        self.assertEqual(len(rows), 14)
        body = "".join(plain(rows))
        self.assertTrue(any(ch in body for ch in "─╭╯╮╰"))

    def test_marks_close_together_share_a_label(self):
        canvas = charts.Canvas(40, 6)
        lay = charts.Layout(2, 40, 6, 0, 10, 5)
        charts._marks(canvas, lay, [charts.Mark(5.0, "one"), charts.Mark(5.05, "two"), charts.Mark(30, "far")])
        top = canvas.row(0).plain
        self.assertIn("one + two", top)
        self.assertIn("far", top)


class RegressionTest(unittest.TestCase):
    """Cases the adversarial pass found."""

    def test_hover_maps_every_column_back_to_its_bar(self):
        for slots in (7, 24, 28, 30, 48):
            for w in (40, 63, 100, 137, 200):
                a = charts.Series("a", "A", "#25f4ee", values=[float(i % 5 + 1) for i in range(slots)])
                rows, lay = charts.bars([a], slots, w, 12)
                self.assertTrue(all(cell_len(r.plain) <= w for r in rows), (slots, w))
                for c in range(lay.pw):
                    slot = lay.slot_at(c)
                    self.assertIsNotNone(slot)
                    self.assertIn(c, lay.columns(slot), (slots, w, c))

    def test_more_slots_than_columns_keeps_the_newest(self):
        a = charts.Series("a", "A", "#25f4ee", values=[10.0 if i % 2 == 0 else 1.0 for i in range(48)])
        rows, lay = charts.bars([a], 48, 40, 10)
        self.assertEqual(lay.first + lay.slots, 48)
        self.assertLessEqual(lay.slots, lay.pw)

    def test_axis_labels_stay_distinct(self):
        for ys in ([1001, 1004], [1001, 1003], [1234567] * 4, [52340, 52351]):
            lay = charts._layout(60, 10, *charts._hug(ys), True, True)
            labels = list(charts.y_labels(lay).values())
            self.assertEqual(len(labels), len(set(labels)), (ys, labels))

    def test_count_axes_use_whole_round_steps(self):
        for hi in (7, 10, 23, 99, 1000, 2500, 33333):
            lo, top, step = charts.nice_range(0, hi, 4)
            self.assertEqual(step, round(step))
            mantissa = step / 10 ** math.floor(math.log10(step))
            self.assertIn(round(mantissa, 6), (1, 2, 2.5, 5))
            self.assertGreaterEqual(top, hi)

    def test_marks_get_a_clear_top_row(self):
        # With marks, the bars stop short of the top row so every mark's label has room.
        a = charts.Series("a", "A", "#25f4ee", values=[10.0] * 10)
        rows, lay = charts.bars([a], 10, 60, 12, marks=[charts.Mark(5.5, "car")])
        self.assertIn("▼ car", rows[0].plain)

    def test_marks_and_labels_land_on_their_bars(self):
        # A mark late in a bucket, and a label in the middle of one, point at that bucket's bar, not the gap after it.
        a = charts.Series("a", "A", "#25f4ee", values=[1.0] * 6)
        rows, lay = charts.bars([a], 6, 30, 10, [(i + 0.5, "x") for i in range(6)], [charts.Mark(1.9, "car")])
        self.assertGreater(lay.per - lay.bar, 1)  # wide enough that a slot has room for a gap
        bar = range(lay.columns(1).start, lay.columns(1).start + lay.bar)
        self.assertIn(rows[0].plain.index("▼") - lay.lw - 1, bar)
        axis = rows[lay.ph].plain[lay.lw + 1:]
        for i in range(6):
            c = lay.col(i + 0.5)
            self.assertEqual(axis[c], "┬")
            self.assertIn(c, range(lay.columns(i).start, lay.columns(i).start + lay.bar))

    def test_crowded_marks_are_shortened_not_dropped(self):
        # Two marks too close for both labels in full: both are shortened alike, so each still says which video.
        canvas = charts.Canvas(18, 6)
        lay = charts.Layout(2, 18, 6, 0, 10, 5)
        charts._marks(canvas, lay, [charts.Mark(0.2, "world dropped"), charts.Mark(12.2, "raindrop size")])
        top = canvas.row(0).plain
        self.assertEqual(top.count("▼"), 2, top)
        self.assertTrue(top.startswith("▼ wor") and "▼ rai" in top, top)

    def test_a_mark_with_no_room_is_left_out(self):
        canvas = charts.Canvas(20, 6)
        lay = charts.Layout(2, 20, 6, 0, 10, 5)
        for c in range(20):
            canvas.put(0, c, " ", None, "#25f4ee")  # a bar fills the top row
        charts._marks(canvas, lay, [charts.Mark(8, "car")])
        body = "".join(canvas.row(r).plain for r in range(6))
        self.assertNotIn("▼", body)  # no arrow that doesn't say what it is
        self.assertNotIn("┊", body)


if __name__ == "__main__":
    unittest.main()
