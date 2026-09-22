"""長さ丸め・計算時間・打ち切り表示の検証。"""
import copy
import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import app_auto_length
from core.auto_length import optimize_auto
from core.optimizer import validate_layout
from tests.test_auto_length import product
from tests.test_project_buttons import DUMMY


class LengthRoundTests(unittest.TestCase):
    def products(self):
        return [product(300, 400, 40, True), product(250, 900, 20, True, id="P2"),
                product(155, 600, 30, True, id="P3"), product(500, 500, 10, True, id="P4")]

    def test_snaps_length_up_to_multiple(self):
        result = optimize_auto(self.products(), 1219.0, 10.0, 2400.0, 0.0, length_round=100.0)[0]
        self.assertTrue(result.complete)
        self.assertEqual(validate_layout(result), [])
        for plan in result.sheets:
            length = plan.sheet_type.length
            content = max(p.y + p.length for p in plan.placements)
            self.assertEqual(length % 100, 0)
            self.assertLessEqual(length, 2400)
            # 切り上げ幅は丸め単位未満。配置より短くなることはない。
            self.assertTrue(0 <= length - content < 100)

    def test_reduces_length_variety(self):
        products = self.products()
        plain = {p.sheet_type.length for p in optimize_auto(products, 1219.0, 10.0, 2438.0, 0.0)[0].sheets}
        rounded = {p.sheet_type.length for p in optimize_auto(products, 1219.0, 10.0, 2438.0, 0.0, length_round=10.0)[0].sheets}
        self.assertGreater(len(plain), 1)
        self.assertLess(len(rounded), len(plain))

    def test_never_exceeds_max_length(self):
        result = optimize_auto([product(155, 1219, 7, False)], 1219.0, 10.0, 1219.0, 0.0, length_round=500.0)[0]
        self.assertTrue(result.complete)
        self.assertEqual(validate_layout(result), [])
        self.assertTrue(all(p.sheet_type.length <= 1219 for p in result.sheets))

    def test_rejects_negative_round(self):
        with self.assertRaises(ValueError):
            optimize_auto([product()], length_round=-1.0)


class AutoSettingsGuiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="shearing-auto-settings-")
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        directory = patch.object(app_auto_length, "APP_DIR", self.folder)
        directory.start()
        self.addCleanup(directory.stop)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = app_auto_length.AutoLengthApp(self.root)

    def stored(self):
        return json.loads((self.folder / "登録データ" / "ロス設定.json").read_text(encoding="utf-8"))

    def test_time_limit_and_round_persist(self):
        self.app.time_var.set("25")
        self.app.length_round_var.set("50")
        self.assertEqual(self.stored()["time"], 25)
        self.assertEqual(self.stored()["round"], 50)
        second = tk.Tk()
        second.withdraw()
        try:
            reopened = app_auto_length.AutoLengthApp(second)
            self.assertEqual(reopened.time_var.get(), "25")
            self.assertEqual(reopened.length_round_var.get(), "50")
        finally:
            second.destroy()

    def test_time_limit_reaches_optimizer_without_invalidating_result(self):
        self.app.current_products = [product()]
        self.app.results = optimize_auto(self.app.current_products)
        self.app.result_valid = True
        revision = self.app.input_revision
        self.app.time_var.set("3")
        # 計算時間は入力条件ではないので、計算済みの結果を無効化しない。
        self.assertEqual(self.app.input_revision, revision)
        self.assertTrue(self.app.result_valid)
        with patch("app_auto_length.optimize_auto", return_value=[]) as solver:
            self.app.start_calculation()
            self.root.update()
        self.assertEqual(solver.call_args.kwargs["time_limit"], 3)

    def test_round_invalidates_result_and_is_saved_in_project(self):
        self.app.current_products = [product()]
        self.app.results = optimize_auto(self.app.current_products)
        self.app.result_valid = True
        self.app.length_round_var.set("50")
        self.assertFalse(self.app.result_valid)
        self.assertEqual(self.app.snapshot()["settings"][-1], "50")

    def test_legacy_project_without_round_loads_as_zero(self):
        self.app.length_round_var.set("50")
        legacy = copy.deepcopy(DUMMY)
        legacy["settings"] = legacy["settings"][:5]
        self.app.apply_project(legacy)
        self.assertEqual(self.app.length_round_var.get(), "0")
        self.assertEqual(self.app.snapshot()["settings"], legacy["settings"] + ["0"])

    def test_complete_candidate_is_not_called_provisional(self):
        self.app.current_products = [product()]
        self.app.results = optimize_auto(self.app.current_products)
        self.app.result_valid = True
        result = self.app.results[0]
        self.assertTrue(result.complete)
        result.timed_out = True
        self.app.show_result(result)
        detail = self.app.detail.get("1.0", "end")
        self.assertNotIn("暫定候補", detail)
        self.assertIn("必要数量は満たしています", detail)
        result.complete = False
        self.app.show_result(result)
        self.assertIn("暫定候補", self.app.detail.get("1.0", "end"))
