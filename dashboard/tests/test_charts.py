"""The text charts: round-number axes, bar heights to the eighth, areas, marks (dashboard.charts)."""

from __future__ import annotations

import math
import unittest

from rich.cells import cell_len

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


class BarsTest(unittest.TestCase):
    def test_size_and_heights(self):
        a = charts.Series("a", "A", "#25f4ee", values=[0, 4, 8, None])
        rows, lay = charts.bars([a], 4, 40, 12, [(0, "x")])
        self.assertEqual(len(rows), 12)
        self.assertTrue(all(cell_len(r.plain) <= 40 for r in rows))
        # The tallest bar fills the plot up to its value: 8 on an axis that tops out at 8 or above.
        self.assertGreaterEqual(lay.hi, 8)
        self.assertIn("x", plain(rows)[-1])

    def test_stacked_cell_split(self):
        # Where one platform's part of a bar ends inside a cell, the cell shows both colours at the right split.
        a = charts.Series("a", "A", "#ff0000", values=[1.5])
        b = charts.Series("b", "B", "#0000ff", values=[1.5])
        rows, lay = charts.bars([a, b], 1, 20, 6)
        split_cells = []
        for row in rows[:lay.ph]:
            for span in row.spans:
                text = row.plain[span.start:span.end]
                style = span.style
                if any(ch in charts.EIGHTHS[1:8] for ch in text) and style.color and style.bgcolor:
                    split_cells.append((style.color.triplet.hex, style.bgcolor.triplet.hex))
        self.assertIn(("#ff0000", "#0000ff"), split_cells)

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

    def test_marks_go_round_bars(self):
        a = charts.Series("a", "A", "#25f4ee", values=[10.0] * 10)
        rows, lay = charts.bars([a], 10, 60, 12, marks=[charts.Mark(5.5, "car")])
        top = rows[0].plain
        self.assertNotIn("car", top)  # the bars fill the top row, so there's no room for the label...
        body = "".join(r.plain for r in rows)
        self.assertNotIn("▼", body)  # ...and then the mark is left out: no arrow that doesn't say what it is
        self.assertNotIn("┊", body)


if __name__ == "__main__":
    unittest.main()
