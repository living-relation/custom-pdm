"""Tests for tools/thermal_a.py (board A heat model) and the shared parts of tools/thermal_board_b.py.

usage (repo root, KiCad 9 python with numpy + scipy):
    python tools/test_thermal_models.py          (about 1 min: one coarse solve)
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thermal_a as TA  # noqa: E402
import thermal_board_b as TB  # noqa: E402
import verify_copper as VC  # noqa: E402


class Inputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = TA.load_board()

    def test_ep_matches_footprint(self):
        """The heat goes into each BTS7008's exposed pad (pad 15): the EP rectangle the model uses is that pad."""
        for ref in TA.A_DRV:
            fp = self.board.FindFootprintByReference(ref)
            ep = [p for p in fp.Pads() if p.GetNumber() == "15"]
            self.assertEqual(len(ep), 1, ref)
            bb = ep[0].GetBoundingBox()
            w, h = VC.mm(bb.GetWidth()), VC.mm(bb.GetHeight())
            cx, cy = VC.mm(bb.GetCenter().x), VC.mm(bb.GetCenter().y)
            ew, eh = TB.EP["BTS7008"]
            x, y = VC.mm(fp.GetPosition().x), VC.mm(fp.GetPosition().y)
            self.assertAlmostEqual(w, ew, delta=0.05, msg=ref)
            self.assertAlmostEqual(h, eh, delta=0.05, msg=ref)
            self.assertAlmostEqual(cx, x, delta=0.3, msg=ref)
            self.assertAlmostEqual(cy, y, delta=0.3, msg=ref)

    def test_chips_over_pedestals(self):
        """Every driver's EP sits over a pedestal (hull + margin), else the model has the wrong heat path."""
        for ref in TA.A_DRV:
            fp = self.board.FindFootprintByReference(ref)
            x, y = VC.mm(fp.GetPosition().x), VC.mm(fp.GetPosition().y)
            m = TB.PED_MARGIN
            self.assertTrue(any(a - m <= x <= b + m and c - m <= y <= d + m for (a, b, c, d) in TA.PED_A), ref)

    def test_logic_parts_exist(self):
        for ref in TA.LOGIC_REFS_A:
            self.assertIsNotNone(self.board.FindFootprintByReference(ref), ref)


class Cases(unittest.TestCase):
    def test_rating(self):
        c = TA.case_currents("rating")
        self.assertEqual(len(c["this"]), 8)
        self.assertAlmostEqual(sum(c["this"].values()), 60.0)
        self.assertAlmostEqual(sum(c["this"].values()) + sum(c["other_a"].values()) + c["I_B"], 304.0)

    def test_feed150a_is_the_feed_limit(self):
        c = TA.case_currents("feed150a")
        self.assertAlmostEqual(sum(c["this"].values()) + sum(c["other_a"].values()) + c["I_B"], 150.0)

    def test_car(self):
        c = TA.case_currents("car")
        self.assertAlmostEqual(sum(c["this"].values()), 20.35, places=2)    # A1, docs/car-loads.dummy.md
        self.assertAlmostEqual(c["I_B"], 118.1, places=1)                    # thermal_board_b car case

    def test_chip_loss(self):
        """1.80 W per BTS7008 with both channels at 7.5 A (docs/enclosure-layout.md 4.3 worst case)."""
        chips = TA.chip_list(TA.case_currents("rating")["this"])
        self.assertEqual(len(chips), 4)
        for c in chips:
            self.assertAlmostEqual(c["P"], 1.80, places=6)


class Solve(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = TA.load_board()
        th, diel = VC.stackup(TA.PCB)
        cls.th, _, _ = VC.copper_order.apply(th, "A", None, None)
        cls.diel = diel
        cls.T = TB.Thermal(cls.board, cls.th, cls.diel, 0.8, peds=TA.PED_A)

    def test_ordered_copper(self):
        """Board A ordered copper: 1 oz outer + 1 oz inner (tools/copper_order.py, 2026-11-22)."""
        for n in VC.CU:
            self.assertAlmostEqual(self.th[n], 35e-6, delta=0.1e-6, msg=n)

    def test_no_heat_is_isothermal(self):
        A, gb = self.T.matrix(3.0, 3.0, 8.5, True)
        import scipy.sparse.linalg as spla
        Tn = spla.spsolve(A, gb * 70.0 + self.T.gbar * 70.0)
        self.assertLess(float(np.abs(Tn - 70.0).max()), 1e-6)

    def test_energy_balance(self):
        """Heat in (chips + 5 V module) = heat out through the boundaries (pad, air gap, top, bar)."""
        A, gb = self.T.matrix(3.0, 3.0, 8.5, True)
        chips = TA.chip_list(TA.case_currents("rating")["this"])
        for c in chips:
            fp = self.board.FindFootprintByReference(c["ref"])
            c["xy"] = (VC.mm(fp.GetPosition().x), VC.mm(fp.GetPosition().y))
        Q = self.T.heat([], chips, [("U21", 0.2)])
        import scipy.sparse.linalg as spla
        ts = 70.0
        Tn = spla.spsolve(A, Q + gb * ts + self.T.gbar * (ts + 10.0))
        out = float((gb * (Tn - ts)).sum() + (self.T.gbar * (Tn - ts - 10.0)).sum())
        self.assertAlmostEqual(out, 7.4, delta=0.01)
        self.assertGreater(float(Tn.max()), ts)

    def test_b_defaults(self):
        """thermal_board_b keeps board B's pedestals; the pad is the revF 0.86 mm squeezed TGP 3000."""
        self.assertEqual(TB.PAD_T, 0.86e-3)
        self.assertIs(TB.Thermal.__init__.__defaults__[0], None)


class InputBoard(unittest.TestCase):
    def test_losses(self):
        """16 V on an input: 4.7 k series into the 3.65 V clamp + 10 k pull-down = 59 mW per input."""
        import thermal_input as TI
        L = dict(TI.losses(16.0))
        self.assertAlmostEqual(L["R1"] + L["R17"] + L["D1"], (12.35 / 4.7e3) ** 2 * 4.7e3 + 0.0256 + 12.35 / 4.7e3 * 0.35,
                               places=6)
        self.assertAlmostEqual(sum(L.values()), 0.488, delta=0.005)
        self.assertEqual(sum(TI.losses(0.0)[i][1] for i in range(27)), 0.0)

    def test_energy_balance_and_parts(self):
        import pcbnew
        import thermal_input as TI
        b = pcbnew.LoadBoard(TI.PCB)
        for ref, _ in TI.losses(16.0):
            self.assertIsNotNone(b.FindFootprintByReference(ref), ref)
        g, edge, ids, Tn, p_in, p_out = TI.solve(b, 0.5, 3.0, 60.0, TI.losses(16.0))
        self.assertAlmostEqual(p_in, p_out, delta=1e-6)
        self.assertGreater(float(Tn.min()), 60.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
