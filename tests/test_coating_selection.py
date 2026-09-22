import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace
from core.models import ProductSpec
from core.auto_length import optimize_auto
from core.auto_exporter import export_auto
from core.product_registry import ProductRegistry
from core.project_io import save_project, load_project
from openpyxl import load_workbook


class SelectionTests(unittest.TestCase):
    def test_separate_materials_and_export(self):
        a=ProductSpec('A','任意規格-Z27',1,500,1000,coating='Z08')
        b=replace(a,id='B',coating='')
        result=optimize_auto([a,b],1000,0,1000,time_limit=1)[0]
        self.assertEqual(len(result.sheets),2)
        self.assertAlmostEqual(result.product_weight,3.985+3.925)
        self.assertEqual({s.sheet_type.coating for s in result.sheets},{'Z08',''})
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'result.xlsx'
            export_auto(path,result,[a,b],(1000,0,1000,0,0))
            wb=load_workbook(path); rows=list(wb['結果一覧'].values)
            first=next(r for r in rows if r[0]=='A')
            second=next(r for r in rows if r[0]=='B')
            self.assertEqual(first[2],'任意規格-Z27')
            self.assertEqual(first[4:6],('Z08',0.120))
            self.assertEqual(second[4],'なし')
            self.assertAlmostEqual(first[12],3.985)
            wb.close()

    def test_gui_persistence_and_layout(self):
        import tkinter as tk
        import app_auto_length
        with tempfile.TemporaryDirectory() as tmp, patch.object(app_auto_length,'APP_DIR',Path(tmp)):
            root=tk.Tk()
            try:
                app=app_auto_length.AutoLengthApp(root)
                app.loss_store=None
                row=app.product_rows[0]
                for var,value in zip(row['vars'],['A','自由入力の規格','1','500','1000']): var.set(value)
                self.assertEqual(str(row['coating_combo'].cget('state')),'readonly')
                row['coating'].set('Z08')
                app.project_vars[0].set('目付選択')
                data=app.snapshot()
                path=Path(tmp)/'project.json'; save_project(path,data)
                app.apply_project(load_project(path))
                self.assertEqual(app.product_rows[0]['coating'].get(),'Z08')
                self.assertEqual(app.product_rows[0]['vars'][1].get(),'自由入力の規格')
                app.result_valid=True
                app.product_rows[0]['coating'].set('なし')
                self.assertFalse(app.result_valid)
                registry=ProductRegistry(Path(tmp)/'products.sqlite3')
                registry.save(data['products'][0]['values'],1,True,'Z08')
                self.assertEqual(registry.list()[0][7],'Z08')
                old=data['products'][0].copy(); old.pop('coating'); old['values']=list(old['values']); old['values'][1]='SGCC-Z12'
                app.append_products([old])
                self.assertEqual(app.product_rows[-1]['coating'].get(),'Z12')
                self.assertEqual(app.product_rows[-1]['vars'][1].get(),'SGCC-Z12')
                for size in ('1500x940','1100x750'):
                    root.geometry(size); root.update()
                    for row in app.product_rows:
                        for child in row['frame'].winfo_children():
                            self.assertLessEqual(child.winfo_rootx()+child.winfo_width(),root.winfo_rootx()+root.winfo_width(),str(child))
            finally:
                root.destroy()
