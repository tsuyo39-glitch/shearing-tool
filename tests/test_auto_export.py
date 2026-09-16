from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile
from openpyxl import load_workbook
from core.auto_exporter import export_auto
from core.auto_length import optimize_auto
from tests.test_auto_length import product


class ExportTests(unittest.TestCase):
    def test_report_images_and_exact_quantities(self):
        products=[product()]
        result=optimize_auto(products)[0]
        with tempfile.TemporaryDirectory() as tmp:
            path=export_auto(Path(tmp)/"report.xlsx",result,products,(1219,10,2438,0),2)
            wb=load_workbook(path)
            self.assertEqual(wb.sheetnames,["結果一覧","図解一覧"])
            self.assertEqual(wb["結果一覧"]["D2"].value,2)
            self.assertEqual(wb["結果一覧"]["D3"].value,2)
            for name in wb.sheetnames[1:]:
                self.assertEqual(len(wb[name]._images),1)
                self.assertEqual(wb[name].page_setup.fitToWidth,1)
                self.assertEqual(wb[name].page_setup.fitToHeight,1)
                self.assertEqual(str(wb[name].page_setup.paperSize),str(wb[name].PAPERSIZE_A4))
                self.assertEqual(wb[name].page_setup.orientation,"landscape")
            with ZipFile(path) as archive:
                self.assertEqual(len([n for n in archive.namelist() if n.startswith("xl/media/")]),1)

    def test_gui_exports_selected_snapshot(self):
        import tkinter as tk
        from unittest.mock import patch
        from app_auto_length import AutoLengthApp
        root=tk.Tk()
        root.withdraw()
        try:
            app=AutoLengthApp(root)
            app.current_products=[product()]
            app.current_settings=(1219,10,2438,0)
            app.results=optimize_auto(app.current_products)
            app.result_tree.insert("","end",iid="1")
            app.result_tree.selection_set("1")
            app.settings[0].set("999")
            with patch("app_auto_length.filedialog.asksaveasfilename",return_value="sample.xlsx"),patch("app_auto_length.export_auto") as export,patch("app_auto_length.messagebox.showinfo"):
                app.export_excel()
                export.assert_not_called()
                app.result_valid=True
                app.result_revision=app.input_revision
                app.export_excel()
                self.assertIs(export.call_args.args[1],app.results[1])
                self.assertEqual(export.call_args.args[3],(1219,10,2438,0))
        finally:
            root.destroy()
