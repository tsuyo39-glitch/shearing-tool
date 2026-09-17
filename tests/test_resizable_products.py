import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import app_auto_length


class ResizeTests(unittest.TestCase):
    def test_drag_resize_scroll_and_buttons(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(app_auto_length, 'APP_DIR', Path(tmp)):
            root = tk.Tk()
            try:
                app = app_auto_length.AutoLengthApp(root)
                for _ in range(19): app.add_product_row()
                root.geometry('1500x940+0+0'); root.update()
                self.assertEqual(tuple(map(int, root.resizable())), (1, 1))
                self.assertGreaterEqual(app.product_scroll.canvas.winfo_height(), 150)
                before = app.product_scroll.canvas.winfo_height()
                split = app.workspace_split
                x, y = split.sash_coord(0)
                split.event_generate('<ButtonPress-1>', x=x+50, y=y+4)
                split.event_generate('<B1-Motion>', x=x+50, y=y+94)
                split.event_generate('<ButtonRelease-1>', x=x+50, y=y+94)
                root.update()
                self.assertGreater(app.product_scroll.canvas.winfo_height(), before+50)
                app.product_scroll.canvas.yview_moveto(1)
                root.update()
                self.assertAlmostEqual(app.product_scroll.canvas.yview()[1], 1, places=2)
                self.assertTrue(app.product_scroll.scroll.winfo_ismapped())
                for size in ('1100x750', '1500x940'):
                    root.geometry(size); root.update()
                    for requested in (0, 10000):
                        split.sash_place(0, 0, requested); root.update()
                        self.assertGreaterEqual(app.product_scroll.canvas.winfo_height(), 60)
                        self.assertGreaterEqual(app.canvas.winfo_height(), 80)
                        for widget in (app.calc_button, app.export_button, app.product_scroll.scroll):
                            self.assertTrue(widget.winfo_ismapped())
                            self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(), root.winfo_rooty()+root.winfo_height())
                        def descendants(parent):
                            for child in parent.winfo_children():
                                yield child
                                yield from descendants(child)
                        for button in descendants(root):
                            if button.winfo_class() == 'TButton' and button.cget('text') in ('＋ 製品追加', 'Excelから貼り付け'):
                                self.assertLessEqual(button.winfo_rooty()+button.winfo_height(), app.calc_button.winfo_rooty())
            finally:
                root.destroy()
