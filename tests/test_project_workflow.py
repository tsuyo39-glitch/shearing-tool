import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core.project_io import save_project,load_project,parse_paste


def sample():
    return {"version":1,"name":"日本語案件","customer":"得意先A","notes":"再注文",
            "settings":["1219","10","1219","0","0"],
            "products":[{"values":["製品A","SPCC","","155","1219"],"qty":"7","rotate":False},
                        {"values":["製品B","SUS304","1.2","100","500"],"qty":"2","rotate":True}]}


class FileTests(unittest.TestCase):
    def test_roundtrip_and_atomic_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"案件.json"; data=sample()
            save_project(path,data)
            loaded=load_project(path)
            self.assertIn("saved_at",loaded)
            for key in data: self.assertEqual(data[key],loaded[key])
            original=path.read_bytes()
            changed=copy.deepcopy(data); changed["name"]="変更"
            with patch("core.project_io.os.replace",side_effect=OSError("locked")):
                with self.assertRaises(OSError): save_project(path,changed)
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(list(Path(tmp).glob("*.tmp")),[])

    def test_paste(self):
        for header in ("","製品名\t規格\t板厚\t幅\t長さ\t必要枚数\t回転可否\n"):
            rows,errors,preview=parse_paste(header+"製品A\t\t\t１５５\t１２１９\t７\t不可\n\t\t\t100\t200\t2\t\n")
            self.assertEqual(errors,[])
            self.assertEqual(rows[0]["values"][3],"155")
            self.assertFalse(rows[0]["rotate"])
            self.assertTrue(rows[1]["rotate"])
        for bad in ("=1+2","NaN","-1","0"):
            rows,errors,_=parse_paste(f"A\t\t\t{bad}\t100\t1\t可")
            self.assertTrue(errors); self.assertEqual(rows,[])
        _,errors,_=parse_paste("A\t\t\t100\t200\t1.5\t可")
        self.assertIn("1行目",errors[0])


class GuiTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from app_auto_length import AutoLengthApp
        self.root=tk.Tk(); self.root.withdraw()
        self.app=AutoLengthApp(self.root)
        self.app.loss_store=None
        self.app.apply_project(sample())

    def tearDown(self): self.root.destroy()

    def complete(self,mutate=False,cancel=False,error=False):
        from core.auto_length import optimize_auto
        from tests.test_auto_length import product
        app=self.app
        app.calculation_revision=app.input_revision
        app.current_products=[product()]
        if mutate: app.product_rows[0]["qty"].set("8")
        if cancel: app.cancel_event.set()
        app.pending=(optimize_auto(app.current_products),ValueError("test") if error else None)
        with patch("app_auto_length.messagebox.showerror"):
            app._poll()

    def test_success_and_edit_invalidate(self):
        self.complete()
        self.assertTrue(self.app.result_valid)
        self.app.product_rows[0]["vars"][3].set("156")
        self.assertFalse(self.app.result_valid)
        self.assertEqual(str(self.app.export_button.cget("state")),"disabled")
        self.assertIn("前回",self.app.sheet_total_var.get())

    def test_changed_during_calculation(self):
        self.complete(mutate=True)
        self.assertFalse(self.app.result_valid)

    def test_cancel(self):
        self.complete(cancel=True)
        self.assertFalse(self.app.result_valid)

    def test_error_and_no_candidates(self):
        self.complete(error=True)
        self.assertFalse(self.app.result_valid)
        self.app.pending=([],None)
        self.app._poll()
        self.assertEqual(str(self.app.export_button.cget("state")),"disabled")

    def test_paste_dialog_buttons_visible(self):
        import tkinter as tk
        with patch.object(self.root,"clipboard_get",return_value="A\t\t\t100\t200\t1\t可"):
            self.app.paste_excel()
        window=next(w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel))
        def descendants(w):
            for child in w.winfo_children():
                yield child
                yield from descendants(child)
        buttons=[w for w in descendants(window) if w.winfo_class()=="TButton"]
        for size in ("1050x500","780x360"):
            window.geometry(size); self.root.update()
            for button in buttons:
                self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),window.winfo_rooty()+window.winfo_height())
                self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),window.winfo_rootx()+window.winfo_width())

    def test_corrupt_does_not_change_inputs(self):
        before=self.app.snapshot()
        bad=sample(); bad["products"][0]["values"][3]="nan"
        with self.assertRaises(ValueError): self.app.apply_project(bad)
        self.assertEqual(self.app.snapshot(),before)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"bad.json"; path.write_text("{",encoding="utf-8")
            with patch("project_workflow.filedialog.askopenfilename",return_value=str(path)),patch("project_workflow.messagebox.showerror"):
                self.app.open_project_dialog()
        self.assertEqual(self.app.snapshot(),before)

    def test_append_preserves_existing(self):
        before=self.app.snapshot()["products"]
        rows,errors,_=parse_paste("追加\t\t\t100\t200\t3\tTRUE")
        self.app.append_products(rows)
        self.assertEqual(self.app.snapshot()["products"][:-1],before)
        self.assertTrue(self.app.project_dirty)

    def test_unsaved_choices(self):
        self.app.project_dirty=True
        for answer,expected in ((None,False),(False,True)):
            with patch("project_workflow.messagebox.askyesnocancel",return_value=answer):
                self.assertEqual(self.app.confirm_discard(),expected)
        with patch("project_workflow.messagebox.askyesnocancel",return_value=True),patch.object(self.app,"save_project_dialog",return_value=False):
            self.assertFalse(self.app.confirm_discard())
