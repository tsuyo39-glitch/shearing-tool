import tempfile
from pathlib import Path
import unittest
from core.loss_settings import LossSettings
from core.auto_length import optimize_auto
from tests.test_auto_length import product

class LossTests(unittest.TestCase):
    def test_width_loss_one_side(self):
        result=optimize_auto([product(1209,1219,1,False)],width=1219,edge=10,max_length=1219)[0]
        self.assertTrue(result.complete)
        placement=result.sheets[0].placements[0]
        self.assertEqual(placement.x,10)
        self.assertEqual(placement.x+placement.width,1219)
        with self.assertRaises(ValueError):
            optimize_auto([product(1210,1219,1,False)],width=1219,edge=10,max_length=1219)

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"loss.json"
            store=LossSettings(path)
            self.assertEqual(store.values["length"],0)
            store.save("width","12.5")
            store.save("length","5")
            store.save("gap","2")
            for bad in ("","-1","nan","inf"):
                store.save("length",bad)
            self.assertEqual(LossSettings(path).values,{"width":12.5,"length":5,"gap":2})

    def test_length_loss(self):
        p=product(155,1219,7,False)
        with self.assertRaises(ValueError):
            optimize_auto([p],max_length=1219,length_loss=10)
        r=optimize_auto([p],max_length=1239,length_loss=10)[0]
        self.assertTrue(r.complete)
        self.assertEqual(len(r.sheets),1)
        self.assertEqual(r.sheets[0].sheet_type.length,1239)
        self.assertTrue(all(q.y==10 for q in r.sheets[0].placements))
        self.assertEqual(optimize_auto([p],max_length=1219)[0].sheets[0].sheet_type.length,1219)
