import random
import unittest
from collections import Counter
from core.auto_length import optimize_auto
from core.models import ProductSpec


class AuditTests(unittest.TestCase):
    def verify(self, products, width, edge, length, gap):
        results=optimize_auto(products,width,edge,length,gap,time_limit=2)
        self.assertTrue(results)
        for result in results:
            self.assertTrue(result.complete)
            self.assertEqual(Counter(p.product_id for s in result.sheets for p in s.placements),
                             {p.id:p.required_qty for p in products})
            for plan in result.sheets:
                self.assertLessEqual(plan.sheet_type.length,length+1e-8)
                for i,p in enumerate(plan.placements):
                    self.assertGreaterEqual(p.x,edge-1e-8)
                    self.assertGreaterEqual(p.y,-1e-8)
                    self.assertLessEqual(p.x+p.width,width+1e-8)
                    self.assertLessEqual(p.y+p.length,plan.sheet_type.length+1e-8)
                    for q in plan.placements[i+1:]:
                        self.assertTrue(p.x+p.width+gap<=q.x+1e-8 or q.x+q.width+gap<=p.x+1e-8 or
                                        p.y+p.length+gap<=q.y+1e-8 or q.y+q.length+gap<=p.y+1e-8)
            expected=sum(p.width*p.length*p.required_qty for p in products)/sum(s.sheet_type.area for s in result.sheets)*100
            self.assertAlmostEqual(result.yield_rate,expected)

    def test_random_200_cases(self):
        rng=random.Random(20260911)
        for case in range(200):
            width=rng.choice([914,1000,1219,1524])
            length=rng.choice([914,1800,2438,3000])
            edge=rng.choice([0,5,10,20])
            gap=rng.choice([0,1,3,5])
            products=[ProductSpec(str(i),"SPCC" if i%2 else "SUS",1 if i%3 else 2,
                      rng.randint(20,int(width-2*edge)),rng.randint(20,int(length-2*edge)),rng.randint(1,12),bool(rng.randrange(2)))
                      for i in range(rng.randint(1,5))]
            with self.subTest(case=case):
                self.verify(products,width,edge,length,gap)

    def test_submillimeter_boundary(self):
        self.verify([ProductSpec("P1","",None,599.5004,100,2,False)],1219,10,2438,0)

    def test_cancel_and_timeout(self):
        from threading import Event
        cancel=Event()
        cancel.set()
        p=ProductSpec("P1","",None,500,500,20000,False)
        self.assertEqual(optimize_auto([p],cancel=cancel),[])
        results=optimize_auto([p],time_limit=0.02)
        for result in results:
            self.assertTrue(result.timed_out)
            self.assertLessEqual(result.placed_by_product.get("P1",0),20000)

    def test_quantity_limit(self):
        with self.assertRaises(ValueError):
            optimize_auto([ProductSpec("P1","",None,100,100,20001,False)])
