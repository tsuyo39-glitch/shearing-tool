import tkinter as tk
import unittest

from app import ShearingApp
from core.optimizer import optimize


class GuiTests(unittest.TestCase):
    @staticmethod
    def fill_sheet(row, name, width, length, thickness=""):
        values = [name, "", thickness, width, length, "", "10", "0"]
        for var, value in zip(row["vars"], values):
            var.set(value)

    @staticmethod
    def ensure_two_sheets(app):
        if len(app.sheet_rows) < 2:
            app.add_sheet_row()

    def test_initial_rows_and_blank_specs(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = ShearingApp(root)
            self.assertEqual(len(app.sheet_rows), 1)
            self.assertEqual(len(app.product_rows), 1)
            self.assertEqual(app.sheet_rows[0]["vars"][0].get(), "大板1")
            self.assertEqual(app.sheet_rows[0]["vars"][1].get(), "")
            self.assertEqual(app.sheet_rows[0]["vars"][2].get(), "")
            self.assertEqual(app.sheet_rows[0]["vars"][3].get(), "")
            self.assertEqual(app.sheet_rows[0]["vars"][4].get(), "")
            self.assertEqual(app.product_rows[0]["vars"][1].get(), "")
            self.assertEqual(app.product_rows[0]["vars"][2].get(), "")
            self.assertEqual(app.result_tree.heading("sheets")["text"], "合計枚数")
            self.assertEqual(app.result_tree.heading("sheet_names")["text"], "大板名称")
            self.assertEqual(app.result_tree.heading("breakdown")["text"], "大板別必要枚数")
        finally:
            root.destroy()

    def test_manual_product_input(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = ShearingApp(root)
            product_vars = app.product_rows[0]["vars"]
            for var, value in zip(product_vars, ["製品A", "SPCC", "1.2", "293", "293"]):
                var.set(value)
            self.ensure_two_sheets(app)
            self.fill_sheet(app.sheet_rows[0], "大板1", "1219", "1219")
            self.fill_sheet(app.sheet_rows[1], "大板2", "1219", "914")
            products, sheets = app._read_inputs()
            self.assertEqual(len(products), 1)
            self.assertEqual(products[0].name, "製品A")
            self.assertEqual(products[0].spec, "SPCC")
            self.assertEqual(sheets[0].spec, "SPCC")
            self.assertEqual(sheets[1].spec, "SPCC")
            self.assertEqual(len(sheets), 2)
            self.assertEqual(sheets[0].thickness, 1.2)
            self.assertEqual(sheets[1].thickness, 1.2)
            self.assertIsNone(sheets[0].max_sheets)
            self.assertIsNone(sheets[1].max_sheets)
            self.assertTrue(optimize(products, sheets, 1)[0].complete)
        finally:
            root.destroy()

    def test_candidate_sheet_count_breakdown_lists_every_sheet_type(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = ShearingApp(root)
            product_vars = app.product_rows[0]["vars"]
            for var, value in zip(product_vars, ["製品A", "SPCC", "1.2", "293", "293"]):
                var.set(value)
            self.ensure_two_sheets(app)
            self.fill_sheet(app.sheet_rows[0], "大板1", "1219", "1219")
            self.fill_sheet(app.sheet_rows[1], "大板2", "1219", "914")
            products, sheets = app._read_inputs()
            app.current_sheets = sheets
            result = optimize(products, sheets, 1)[0]
            counts = {sheet.id: 0 for sheet in sheets}
            for plan in result.sheets:
                counts[plan.sheet_type.id] += 1
            expected = " / ".join(f"{sheet.name}-{counts[sheet.id]}枚" for sheet in sheets)
            self.assertEqual(app._sheet_count_text(result), expected)
            self.assertIn("大板1", expected)
            self.assertIn("大板2", expected)
        finally:
            root.destroy()

    def test_screenshot_case_calculates_18_and_25_sheets(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = ShearingApp(root)
            self.ensure_two_sheets(app)
            self.fill_sheet(app.sheet_rows[0], "大板1", "1219", "1219", "2.3")
            self.fill_sheet(app.sheet_rows[1], "大板2", "1219", "914", "2.3")
            product_vars = app.product_rows[0]["vars"]
            for var, value in zip(product_vars, ["製品1", "", "2.3", "155", "1219"]):
                var.set(value)
            app.product_rows[0]["qty"].set("124")
            products, sheets = app._read_inputs()
            app.current_sheets = sheets
            results = optimize(products, sheets, 2)
            complete = [result for result in results if result.complete]
            self.assertEqual(app._sheet_name_text(complete[0]), "大板1")
            self.assertEqual(app._sheet_name_text(complete[1]), "大板2")
            self.assertEqual(sum(app._sheet_name_text(result) == "大板1" for result in complete), 1)
            by_name = {app._sheet_name_text(result): result for result in complete}
            self.assertIn("大板1", by_name)
            self.assertIn("大板2", by_name)
            self.assertEqual(len(by_name["大板1"].sheets), 18)
            self.assertEqual(len(by_name["大板2"].sheets), 25)
            self.assertEqual(app._sheet_count_text(by_name["大板1"]), "大板1-18枚 / 大板2-0枚")
            self.assertEqual(app._sheet_count_text(by_name["大板2"]), "大板1-0枚 / 大板2-25枚")
            expected_loss1 = 100 - (155 * 1219 * 124) / (1219 * 1219 * 18) * 100
            expected_loss2 = 100 - (155 * 1219 * 124) / (1219 * 914 * 25) * 100
            self.assertAlmostEqual(by_name["大板1"].loss_rate, expected_loss1, places=6)
            self.assertAlmostEqual(by_name["大板2"].loss_rate, expected_loss2, places=6)
        finally:
            root.destroy()

    def test_blank_thickness_still_calculates_layout(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = ShearingApp(root)
            product_vars = app.product_rows[0]["vars"]
            for var, value in zip(product_vars, ["製品B", "SPCC", "", "293", "293"]):
                var.set(value)
            self.ensure_two_sheets(app)
            self.fill_sheet(app.sheet_rows[0], "大板1", "1219", "1219")
            self.fill_sheet(app.sheet_rows[1], "大板2", "1219", "914")
            products, sheets = app._read_inputs()
            self.assertIsNone(products[0].thickness)
            self.assertIsNone(sheets[0].thickness)
            result = optimize(products, sheets, 1)[0]
            self.assertTrue(result.complete)
            self.assertEqual(result.sheet_weight, 0.0)
            self.assertEqual(result.product_weight, 0.0)
            self.assertEqual(result.scrap_weight, 0.0)
            self.assertIn("板厚が空欄のため重量は計算していません。", result.warnings)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
