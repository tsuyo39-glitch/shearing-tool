import tempfile
import unittest
from pathlib import Path
from core.product_registry import ProductRegistry


class RegistryTests(unittest.TestCase):
    def test_persist_update_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"登録"/"products.sqlite3"
            registry=ProductRegistry(path)
            registry.save(["製品A","SUS304","1.2","599.5","500"],"10",True)
            registry=ProductRegistry(path)
            self.assertEqual(registry.list()[0],("製品A","SUS304","1.2","599.5","500",10,1))
            registry.save(["製品A","","","600","510"],"2",False)
            self.assertEqual(len(registry.list()),1)
            self.assertEqual(registry.list()[0][-2:],(2,0))
            for value in ("0","-1","nan","inf",""):
                with self.assertRaises(ValueError):
                    registry.save(["製品A","","",value,"500"],"2",False)
            self.assertEqual(registry.list()[0][3],"600")
            registry.delete("製品A")
            self.assertEqual(registry.list(),[])

    def test_gui_register_and_load(self):
        import tkinter as tk
        from app_auto_length import AutoLengthApp
        root=tk.Tk()
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                app=AutoLengthApp(root)
                app.registry=ProductRegistry(Path(tmp)/"test.sqlite3")
                row=app.product_rows[0]
                for var,value in zip(row["vars"],["試験品","SPCC","","500","600"]):
                    var.set(value)
                row["qty"].set("12")
                app.register_product(row)
                app.remove_product_row(row)
                app.open_registry()
                def walk(widget):
                    yield widget
                    for child in widget.winfo_children():
                        yield from walk(child)
                widgets=list(walk(root))
                window=next(w for w in widgets if isinstance(w,tk.Toplevel))
                for size in ("960x500","780x360"):
                    window.geometry(size)
                    root.update()
                    for button in (w for w in widgets if w.winfo_class()=="TButton" and w.cget("text") in ("選択した製品を追加","選択した登録を削除")):
                        self.assertGreaterEqual(button.winfo_rooty(),window.winfo_rooty())
                        self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),window.winfo_rooty()+window.winfo_height())
                        self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),window.winfo_rootx()+window.winfo_width())
                tree=next(w for w in widgets if w.winfo_class()=="Treeview" and w is not app.result_tree)
                tree.selection_set("0")
                next(w for w in widgets if w.winfo_class()=="TButton" and w.cget("text")=="選択した製品を追加").invoke()
                self.assertEqual(app.product_rows[0]["vars"][0].get(),"試験品")
                self.assertEqual(app.product_rows[0]["qty"].get(),"12")
        finally:
            root.destroy()
