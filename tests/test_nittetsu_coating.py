import unittest
import tempfile
import json
from pathlib import Path
from core.weight import coating_mass, coating_codes, default_master, set_master
from core.coating_registry import CoatingRegistry

class NittetsuTests(unittest.TestCase):
    def tearDown(self):
        set_master(default_master())

    def test_nittetsu_labels(self):
        set_master(default_master())
        for label,value in [('10/10',.018),('20/20',.036),('30/30',.054),('40/40',.072)]:
            self.assertEqual(coating_mass(label),(value,None))
            self.assertEqual(coating_codes('SECC-P'+label),[label])
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'master.json'
            p.write_text(json.dumps({'version':4,'codes':{}}),encoding='utf-8')
            r=CoatingRegistry(p)
            self.assertEqual(r.values['10/10'].constant_kg_m2,.018)
            self.assertEqual(CoatingRegistry(p).values,r.values)
