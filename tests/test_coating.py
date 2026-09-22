"""めっき量定数（JIS G 3302・G 3313・ZAM®）の判定・マスタ・画面の検証。"""
import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import app_auto_length
from core.coating_registry import CoatingRegistry, validate
from core.weight import (Coating, coating_code, coating_codes, coating_detail, coating_mass,
                         default_master, plate_weight_kg, set_master, unit_mass_kg_m2)


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class RestoreMaster(unittest.TestCase):
    """目付マスタはモジュール共有のため、各テストで初期状態へ戻す。"""

    def setUp(self):
        set_master(default_master())
        self.addCleanup(set_master, default_master())


class MassConstantTests(RestoreMaster):
    def constants(self, codes):
        return {code: default_master()[code].constant_kg_m2 for code in codes}

    def test_jis_g3302_hot_dip_zinc(self):
        """日本製鉄U023／日鉄鋼板ニスクジンクのJIS G 3302 表8。"""
        self.assertEqual(self.constants(
            ["Z06", "Z08", "Z10", "Z12", "Z14", "Z18", "Z20", "Z22", "Z25", "Z27", "Z35", "Z37", "Z45", "Z60"]),
            {"Z06": 0.090, "Z08": 0.120, "Z10": 0.150, "Z12": 0.183, "Z14": 0.203, "Z18": 0.244,
             "Z20": 0.285, "Z22": 0.305, "Z25": 0.350, "Z27": 0.381, "Z35": 0.458, "Z37": 0.481,
             "Z45": 0.565, "Z60": 0.722})

    def test_jis_g3313_electro_zinc(self):
        """JIS G 3313 表25（等厚・両面合計）と表26（片面）。"""
        self.assertEqual(self.constants(["EB", "E8", "E16", "E24", "E32", "E40"]),
                         {"EB": 0.006, "E8": 0.018, "E16": 0.036, "E24": 0.054,
                          "E32": 0.072, "E40": 0.090})
        master = default_master()
        self.assertEqual({c: master[c].per_side_kg_m2 for c in ("E8", "E16", "E24", "E32", "E40")},
                         {"E8": 0.009, "E16": 0.018, "E24": 0.027, "E32": 0.036, "E40": 0.045})
        # 表26は表25のちょうど半分（片面ごとの和が等厚の定数になる）。
        for code in ("E8", "E16", "E24", "E32", "E40"):
            self.assertAlmostEqual(master[code].per_side_kg_m2 * 2, master[code].constant_kg_m2, places=6)

    def test_zam_alloy(self):
        """ZAM®総合カタログの質量表。K系は溶融亜鉛めっき相当、数字系は片面g/m²。"""
        self.assertEqual(self.constants(["K06", "K08", "K12", "K27", "K35"]),
                         {"K06": 0.090, "K08": 0.120, "K12": 0.183, "K27": 0.381, "K35": 0.458})
        self.assertEqual(self.constants(["ZAM45", "ZAM60", "ZAM90", "ZAM100", "ZAM120", "ZAM150", "ZAM190"]),
                         {"ZAM45": 0.090, "ZAM60": 0.120, "ZAM90": 0.180, "ZAM100": 0.200,
                          "ZAM120": 0.240, "ZAM150": 0.300, "ZAM190": 0.380})

    def test_unit_mass_matches_published_tables(self):
        """各カタログの単位質量表と一致すること（表示厚さ1.6mm）。"""
        for spec, expected in [("SGCC-Z06", 12.65), ("SGCC-Z08", 12.68), ("SGCC-Z12", 12.74),
                               ("SGCC-Z27", 12.94), ("SGCC-Z60", 13.28),
                               ("ZAM60", 12.68), ("ZAM90", 12.74), ("ZAM120", 12.80), ("ZAM190", 12.94),
                               ("ZAM-K08", 12.68), ("ZAM-K18", 12.80), ("ZAM-K27", 12.94)]:
            mass, warning = unit_mass_kg_m2(spec, 1.6)
            self.assertAlmostEqual(round(mass, 2), expected, places=2, msg=spec)
            self.assertIsNone(warning, spec)

    def test_constant_is_not_coating_divided_by_1000(self):
        # かつての誤り：付着量80g/m2を0.080kg/m2として加算していた。正しくは0.120。
        self.assertAlmostEqual(default_master()["Z08"].constant_kg_m2, 0.120, places=6)

    def test_codes_without_published_constant_stay_unregistered(self):
        # Z43・Z50は付着量の規定はあるが表8にめっき量定数がない。AZ系は未確認のため未登録。
        for spec in ("SGCC-Z43", "SGCC-Z50", "SGLCC-AZ150"):
            mass, warning = coating_mass(spec)
            self.assertEqual(mass, 0.0, spec)
            self.assertIn("未登録", warning, spec)


class CoatingCodeTests(RestoreMaster):
    def test_reads_symbol_from_spec(self):
        for spec, expected in [("SGCC-Z08-NC", "Z08"), ("SGCC-Z8-NC", "Z08"), ("SGCC-Z12", "Z12"),
                               ("SECC-E24", "E24"), ("SECC-EB", "EB"), ("SGLCC-AZ150", "AZ150"),
                               ("SGCC-F08", "F08"), ("ZAM-K27", "K27"), ("ZAMK27", "K27"),
                               ("ZAM120", "ZAM120"), ("ZAM-120", "ZAM120")]:
            self.assertEqual(coating_code(spec), expected, spec)
        for spec in ("SPCC", "SUS304", "SS400", "SPHC"):
            self.assertIsNone(coating_code(spec), spec)

    def test_differential_coating_sums_per_side_constants(self):
        """異厚めっき E8/E16 は片面ごとの定数の和（JIS G 3313 表26）。"""
        for spec in ("SECC-E8/E16", "SECC-E8/E16D"):
            self.assertEqual(coating_codes(spec), ["E8", "E16"], spec)
            mass, warning = coating_mass(spec)
            self.assertAlmostEqual(mass, 0.027, places=6, msg=spec)
            self.assertIsNone(warning, spec)

    def test_differential_without_per_side_value_is_refused(self):
        mass, warning = coating_mass("SGCC-Z08/Z12")
        self.assertEqual(mass, 0.0)
        self.assertIn("片面あたりの定数が登録されていません", warning)

    def test_registered_symbol_has_no_warning(self):
        mass, warning = coating_mass("SGCC-Z08-NC")
        self.assertAlmostEqual(mass, 0.120, places=6)
        self.assertIsNone(warning)

    def test_detail_reports_constant_and_note(self):
        code, entry = coating_detail("SGCC-Z27")
        self.assertEqual(code, "Z27")
        self.assertEqual(entry.constant_kg_m2, 0.381)
        self.assertIn("JIS G 3302", entry.note)

    def test_unconfirmed_entry_is_counted_but_warned(self):
        set_master(dict(default_master(), AZ150=Coating(0.149, None, "要確認", False)))
        mass, warning = coating_mass("SGLCC-AZ150")
        self.assertAlmostEqual(mass, 0.149, places=6)
        self.assertIn("未確認", warning)

    def test_coated_steel_without_symbol_warns(self):
        # 以前は黙ってめっき分0で計算していた危険なケース。
        for spec in ("SGCC", "SGCC Z12", "SECC", "SGLCC", "ZAM"):
            mass, warning = coating_mass(spec)
            self.assertEqual(mass, 0.0, spec)
            self.assertIn("読み取れません", warning, spec)

    def test_plain_steel_has_no_warning(self):
        for spec in ("SPCC", "SPHC", "SUS304", "SS400", ""):
            self.assertEqual(coating_mass(spec), (0.0, None), spec)

    def test_weight_includes_coating(self):
        # 1.6mm・1m2：原板 12.56kg ＋ めっき量定数 0.120kg
        weight, warning = plate_weight_kg("SGCC-Z08-NC", 1.6, 1000, 1000)
        self.assertAlmostEqual(weight, 12.68, places=6)
        self.assertIsNone(warning)


class RegistryTests(RestoreMaster):
    def test_defaults_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = CoatingRegistry(Path(tmp) / "目付マスタ.json")
            self.assertEqual(registry.values["Z08"].constant_kg_m2, 0.120)
            self.assertEqual(registry.values["E24"].per_side_kg_m2, 0.027)
            self.assertEqual(registry.values["ZAM120"].constant_kg_m2, 0.240)

    def test_roundtrip_and_applies_to_weight(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "目付マスタ.json"
            registry = CoatingRegistry(path)
            values = dict(registry.values)
            values["AZ150"] = Coating(0.149, None, "ガルバリウム 社内確認値", True)
            registry.save(values)
            self.assertEqual(coating_mass("SGLCC-AZ150"), (0.149, None))
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["version"], 5)
            self.assertEqual(stored["codes"]["AZ150"],
                             {"constant_kg_m2": 0.149, "per_side_kg_m2": None,
                              "note": "ガルバリウム 社内確認値", "confirmed": True})
            set_master(default_master())
            self.assertEqual(CoatingRegistry(path).values["AZ150"].constant_kg_m2, 0.149)

    def test_rejects_bad_input(self):
        for code, constant in [("ZZ", 0.12), ("Z12", 0), ("Z12", -1), ("Z12", "abc"), ("Z12", 99), ("", 0.12)]:
            with self.assertRaises(ValueError):
                validate(code, constant, None, "", True)
        self.assertEqual(validate(" z12 ", "0.183", "", "出典", False),
                         ("Z12", Coating(0.183, None, "出典", False)))
        self.assertEqual(validate("E24", "0.054", "0.027", " 備考 ", True),
                         ("E24", Coating(0.054, 0.027, "備考", True)))

    def test_old_format_is_rejected_with_guidance(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "目付マスタ.json"
            path.write_text('{"version": 2, "codes": {"Z08": {"constant_kg_m2": 0.12}}}', encoding="utf-8")
            with self.assertRaises(ValueError) as raised:
                CoatingRegistry(path)
            self.assertIn("削除", str(raised.exception))
            self.assertAlmostEqual(coating_mass("SGCC-Z08-NC")[0], 0.120, places=6)


class CoatingGuiTests(RestoreMaster):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory(prefix="shearing-coating-")
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        directory = patch.object(app_auto_length, "APP_DIR", self.folder)
        directory.start()
        self.addCleanup(directory.stop)
        self.root = tk.Tk()
        # 表示位置を固定するだけ。withdrawすると可視性の検証ができない。
        self.root.geometry("+0+0")
        self.addCleanup(self.root.destroy)
        self.app = app_auto_length.AutoLengthApp(self.root)

    def dialog(self):
        self.app.open_coating_master()
        self.root.update()
        return next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))

    def button(self, window, label):
        return next(w for w in descendants(window)
                    if w.winfo_class() == "TButton" and str(w.cget("text")) == label)

    def test_lists_every_family_and_saves_new_symbol(self):
        window = self.dialog()
        tree = next(w for w in descendants(window) if w.winfo_class() == "Treeview")
        self.assertEqual(tree.item("Z08")["values"][:4], ["Z08", "0.12", "—", "確認済"])
        self.assertEqual(tree.item("E24")["values"][:4], ["E24", "0.054", "0.027", "確認済"])
        self.assertEqual(tree.item("ZAM120")["values"][:4], ["ZAM120", "0.24", "—", "確認済"])
        entries = [w for w in descendants(window) if w.winfo_class() == "TEntry"]
        for entry, text in zip(entries, ("AZ150", "0.149", "", "ガルバリウム 社内確認値")):
            entry.insert(0, text)
        self.button(window, "追加・更新").invoke()
        self.root.update()
        self.assertEqual(tree.item("AZ150")["values"][:2], ["AZ150", "0.149"])
        self.button(window, "保存して閉じる").invoke()
        self.root.update()
        stored = json.loads((self.folder / "登録データ" / "目付マスタ.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["codes"]["AZ150"]["constant_kg_m2"], 0.149)
        self.assertEqual(coating_mass("SGLCC-AZ150"), (0.149, None))

    def test_rejects_unusable_symbol(self):
        window = self.dialog()
        entries = [w for w in descendants(window) if w.winfo_class() == "TEntry"]
        entries[0].insert(0, "ZZZ")
        entries[1].insert(0, "0.35")
        with patch("app_auto_length.messagebox.showerror") as error:
            self.button(window, "追加・更新").invoke()
            error.assert_called_once()
        self.assertFalse((self.folder / "登録データ" / "目付マスタ.json").exists())

    def test_buttons_visible_at_minimum_size(self):
        window = self.dialog()
        for size in ("920x660", "840x560"):
            window.geometry(size)
            self.root.update()
            for label in ("追加・更新", "編集", "保存して閉じる", "キャンセル"):
                widget = next(w for w in descendants(window) if w.winfo_class() in ("TButton","TMenubutton") and w.cget("text")==label)
                self.assertTrue(widget.winfo_ismapped(), label)
                self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(),
                                     window.winfo_rooty() + window.winfo_height(), label)
                self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(),
                                     window.winfo_rootx() + window.winfo_width(), label)

    def test_edit_menu_delete_confirmation(self):
        window=self.dialog()
        tree=next(w for w in descendants(window) if w.winfo_class()=="Treeview")
        button=next(w for w in descendants(window) if w.winfo_class()=="TMenubutton")
        menu=button.nametowidget(button.cget("menu"))
        self.assertEqual(menu.entrycget(0,"label"),"選択を確認済にする")
        self.assertEqual(menu.entrycget(1,"label"),"項目を削除")
        tree.selection_set("F08")
        with patch("app_auto_length.messagebox.askyesno",return_value=False) as ask:
            menu.invoke(1)
            ask.assert_called_once()
        self.assertTrue(tree.exists("F08"))
        with patch("app_auto_length.messagebox.askyesno",return_value=True) as ask:
            menu.invoke(1)
            ask.assert_called_once()
        self.assertFalse(tree.exists("F08"))
        self.assertIn("F08",self.app.coating.values)
        self.button(window,"保存して閉じる").invoke()
        self.assertNotIn("F08",self.app.coating.values)

    def test_detail_shows_mass_constant(self):
        from core.auto_length import optimize_auto
        from core.models import ProductSpec
        products = [ProductSpec("P1", "SECC-E24", 1.6, 300, 400, 20, True, "板")]
        self.app.current_products = products
        self.app.results = optimize_auto(products)
        self.app.result_valid = True
        self.app.show_result(self.app.results[0])
        self.assertIn("めっき：E24 めっき量定数 0.054 kg/m²", self.app.detail.get("1.0", "end"))
