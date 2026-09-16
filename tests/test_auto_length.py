import math
import unittest
from collections import Counter
from core.auto_length import optimize_auto
from core.models import ProductSpec
from core.optimizer import validate_layout


def product(w=599, h=500, qty=10, rotate=False, id="P1", thickness=None):
    return ProductSpec(id,"",thickness,w,h,qty,rotate,id)


class AutoLengthTests(unittest.TestCase):
    def check_result(self, products, **kwargs):
        result=optimize_auto(products,**kwargs)[0]
        self.assertTrue(result.complete)
        self.assertEqual(validate_layout(result),[])
        actual=Counter(p.product_id for s in result.sheets for p in s.placements)
        self.assertEqual(actual,{p.id:p.required_qty for p in products})
        for plan in result.sheets:
            s=plan.sheet_type
            self.assertLessEqual(s.length,kwargs.get("max_length",2438))
            self.assertAlmostEqual(s.length,max(p.y+p.length for p in plan.placements))
            for p in plan.placements:
                self.assertGreaterEqual(p.x,s.edge_loss)
                self.assertGreaterEqual(p.y,0)
                self.assertLessEqual(p.x+p.width,s.width+1e-7)
                self.assertLessEqual(p.y+p.length,s.length+1e-7)
        return result

    def test_default_exact_quantity(self):
        r=self.check_result([product()])
        self.assertEqual(len(r.sheets),2)
        self.assertEqual(sorted(s.sheet_type.length for s in r.sheets),[500,2000])

    def test_edges(self):
        self.check_result([product(1199,2418,1)])
        with self.assertRaises(ValueError):
            optimize_auto([product(1210,2418,1)])

    def test_full_length_1219(self):
        for qty, sheets in [(1,1),(7,1),(8,2),(124,18)]:
            with self.subTest(qty=qty):
                result=self.check_result([product(155,1219,qty,False)],max_length=1219)
                self.assertEqual(len(result.sheets),sheets)
                for plan in result.sheets:
                    self.assertEqual(plan.sheet_type.length,1219)
                    self.assertTrue(all(p.y==0 for p in plan.placements))
        self.check_result([product(1199,1219,1,False)],max_length=1219)
        self.check_result([product(1199,5,1,False)],max_length=5)
        with self.assertRaises(ValueError):
            optimize_auto([product(155,1220,1,False)],max_length=1219)

    def test_rotation(self):
        r=self.check_result([product(1500,500,1,True)])
        self.assertTrue(r.sheets[0].placements[0].rotated)

    def test_custom(self):
        self.check_result([product(600,700,5)],width=1250,edge=20,max_length=1500,gap=5)
        self.check_result([product(1219,2438,1)],edge=0)

    def test_mixed_products(self):
        self.check_result([product(330,470,17,True),product(220,550,8,True,"P2")])

    def test_separate_thickness(self):
        r=self.check_result([product(qty=1),product(qty=1,id="P2",thickness=1)])
        self.assertEqual(len(r.sheets),2)

    def test_invalid(self):
        for values in [dict(width=math.nan),dict(edge=-1),dict(max_length=20),dict(gap=math.inf)]:
            with self.assertRaises(ValueError):
                optimize_auto([product()],**values)
        for p in [product(qty=0),product(w=math.nan),product(qty=1.5)]:
            with self.assertRaises(ValueError):
                optimize_auto([p])

    def test_gui(self):
        import tkinter as tk
        from app_auto_length import AutoLengthApp
        root=tk.Tk()
        root.withdraw()
        try:
            app=AutoLengthApp(root)
            self.assertEqual([v.get() for v in app.settings],["1219","10","1219","0"])
            app.current_products=[product()]
            app.results=optimize_auto(app.current_products)
            app.show_result(app.results[0])
            self.assertIn("1219 × 2000",app.detail.get("1.0","end"))
            self.assertGreater(len(app.canvas.find_all()),10)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
