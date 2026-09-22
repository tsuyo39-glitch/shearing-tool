"""Dummy-data GUI button checks; all user data redirected to temporary folders."""
import copy
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import app_auto_length
from core.project_io import load_project, save_project


DUMMY = {
    'version': 1, 'name': '検証用_ダミー案件A', 'customer': '架空テスト株式会社',
    'notes': '動作確認専用・実注文ではありません',
    'settings': ['1219', '10', '1219', '0', '0', '0'],
    'products': [
        {'values': ['ダミー帯板', 'SPCC', '2.3', '155', '1219'], 'qty': '14', 'rotate': False},
        {'values': ['ダミー小板', 'SUS304', '', '300', '400'], 'qty': '6', 'rotate': True},
    ],
}


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class ProjectButtonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='shearing-project-buttons-')
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.directory_patch = patch.object(app_auto_length, 'APP_DIR', self.folder)
        self.directory_patch.start()
        self.addCleanup(self.directory_patch.stop)
        self.root = tk.Tk()
        self.root.geometry('+0+0')
        self.app = app_auto_length.AutoLengthApp(self.root)
        self.addCleanup(self.root.destroy)
        self.app.apply_project(copy.deepcopy(DUMMY))
        self.root.update()
        self.path = self.folder / '案件データ' / '検証用_ダミー案件A.json'

    def button(self, label, owner=None):
        return next(w for w in descendants(owner or self.root)
                    if w.winfo_class() == 'TButton' and str(w.cget('text')) == label)

    def edit(self, values, accept=True, empty_first=False):
        errors = []
        def interact():
            window = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
            try:
                entries = [w for w in descendants(window) if w.winfo_class() == 'TEntry']
                for entry, value in zip(entries, values):
                    entry.delete(0, 'end'); entry.insert(0, value)
                if empty_first:
                    entries[0].delete(0, 'end')
                    with patch('project_workflow.messagebox.showerror') as warning:
                        self.button('確定', window).invoke()
                        warning.assert_called_once()
                    self.assertTrue(window.winfo_exists())
                    entries[0].insert(0, values[0])
                for size in ('620x260', '500x240'):
                    window.geometry(size); self.root.update()
                    for widget in entries + [self.button('確定', window), self.button('キャンセル', window)]:
                        self.assertGreater(widget.winfo_height(), 10)
                        self.assertGreaterEqual(widget.winfo_rootx(), window.winfo_rootx())
                        self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(), window.winfo_rootx()+window.winfo_width())
                        self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(), window.winfo_rooty()+window.winfo_height())
                self.button('確定' if accept else 'キャンセル', window).invoke()
            except Exception as exc:
                errors.append(exc)
                if window.winfo_exists(): window.destroy()
        self.root.after(30, interact)
        self.button('情報編集').invoke()
        if errors: raise errors[0]

    def save(self, path=None):
        with patch('project_workflow.filedialog.asksaveasfilename', return_value=str(path or self.path)):
            self.button('案件を保存').invoke()

    def calculate(self):
        with patch('app_auto_length.messagebox.showerror') as error:
            self.app.calc_button.invoke()
            deadline = time.monotonic()+15
            while str(self.app.calc_button.cget('state')) == 'disabled' and time.monotonic()<deadline:
                self.root.update(); time.sleep(.01)
            self.assertNotEqual(str(self.app.calc_button.cget('state')), 'disabled')
            error.assert_not_called()
        self.assertTrue(self.app.result_valid)
        self.assertTrue(self.app.results[0].complete)
        self.assertEqual(self.app.results[0].placed_by_product, {'P1': 14, 'P2': 6})
        return [(len(r.sheets), r.yield_rate, r.placed_by_product) for r in self.app.results]

    def test_edit_save_open_recalculate(self):
        self.edit(['検証用_ダミー案件A_編集後', '架空得意先B', '再利用テスト'])
        expected = self.app.snapshot()
        self.assertTrue(self.app.project_dirty)
        before = self.calculate()
        self.save()
        self.assertTrue(self.path.exists())
        self.assertFalse(self.app.project_dirty)
        saved = load_project(self.path)
        for key, value in expected.items(): self.assertEqual(saved[key], value)
        self.assertIn('saved_at', saved)
        self.app.product_rows[0]['qty'].set('99')
        with patch('project_workflow.filedialog.askopenfilename', return_value=str(self.path)), \
             patch('project_workflow.messagebox.askyesnocancel', return_value=False):
            self.button('案件を開く').invoke()
        self.assertEqual(self.app.snapshot(), expected)
        self.assertFalse(self.app.result_valid)
        self.assertEqual(str(self.app.export_button.cget('state')), 'disabled')
        self.assertEqual(self.calculate(), before)
        self.assertEqual(str(self.app.export_button.cget('state')), 'normal')

    def test_edit_cancel_and_required_name(self):
        before = self.app.snapshot()
        self.edit(['破棄する編集', '', '破棄'], accept=False)
        self.assertEqual(self.app.snapshot(), before)
        self.assertFalse(self.app.project_dirty)
        self.edit(['必須名テスト', '', ''], empty_first=True)
        self.assertEqual(self.app.project_vars[0].get(), '必須名テスト')
        self.assertEqual(self.app.project_vars[1].get(), '')

    def test_save_cancel_and_failure_keep_saved_file(self):
        self.save()
        original = self.path.read_bytes()
        self.app.product_rows[0]['qty'].set('15')
        with patch('project_workflow.filedialog.asksaveasfilename', return_value=''):
            self.button('案件を保存').invoke()
        self.assertTrue(self.app.project_dirty)
        with patch('core.project_io.os.replace', side_effect=PermissionError('test locked')), \
             patch('project_workflow.messagebox.showerror') as error:
            self.save()
            error.assert_called_once()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(self.app.project_dirty)

    def test_open_cancel_corrupt_and_discard_cancel(self):
        self.save()
        self.app.product_rows[0]['qty'].set('15')
        before = self.app.snapshot()
        for selected, answer in [('', False), (str(self.path), None)]:
            with patch('project_workflow.filedialog.askopenfilename', return_value=selected), \
                 patch('project_workflow.messagebox.askyesnocancel', return_value=answer):
                self.button('案件を開く').invoke()
            self.assertEqual(self.app.snapshot(), before)
        corrupt = self.folder/'破損.json'; corrupt.write_text('{', encoding='utf-8')
        with patch('project_workflow.filedialog.askopenfilename', return_value=str(corrupt)), \
             patch('project_workflow.messagebox.showerror') as error:
            self.button('案件を開く').invoke()
            error.assert_called_once()
        self.assertEqual(self.app.snapshot(), before)

    def test_save_changes_before_opening_other_project(self):
        self.save()
        self.app.product_rows[0]['qty'].set('21')
        other = dict(copy.deepcopy(DUMMY), name='検証用_ダミー案件B')
        target = self.folder/'案件B.json'; save_project(target, other)
        with patch('project_workflow.filedialog.askopenfilename', return_value=str(target)), \
             patch('project_workflow.messagebox.askyesnocancel', return_value=True), \
             patch('project_workflow.filedialog.asksaveasfilename', return_value=str(self.path)):
            self.button('案件を開く').invoke()
        self.assertEqual(load_project(self.path)['products'][0]['qty'], '21')
        expected = dict(other, products=[dict(row, coating="なし") for row in other["products"]])
        self.assertEqual(self.app.snapshot(), expected)
        self.assertEqual(self.app.project_path, target)

    def test_toolbar_visible_initial_and_minimum(self):
        for size in ('1500x940', '1100x750'):
            self.root.geometry(size); self.root.update()
            for label in ('案件を保存', '案件を開く', '情報編集'):
                widget = self.button(label)
                self.assertTrue(widget.winfo_ismapped())
                self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(), self.root.winfo_rootx()+self.root.winfo_width())
                self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(), self.root.winfo_rooty()+self.root.winfo_height())
