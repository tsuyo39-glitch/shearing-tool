import json
import tempfile
import unittest
from pathlib import Path
from core.coating_registry import CoatingRegistry
from core.weight import default_master, set_master, coating_mass
from core.models import ProductSpec
from core.auto_length import optimize_auto


class AlloyTests(unittest.TestCase):
    def tearDown(self):
        set_master(default_master())

    def test_constants_and_material_separation(self):
        set_master(default_master())
        for code,value in {'F04':.060,'F06':.090,'F08':.120,'F10':.150,'F12':.183,'F18':.244,
                           'EB':.006,'E8':.018,'E16':.036,'E24':.054,'E32':.072,'E40':.090}.items():
            self.assertEqual(coating_mass(code),(value,None))
            result=optimize_auto([ProductSpec('P','任意規格',1,1000,1000,coating=code)],1000,0,1000,time_limit=.1)[0]
            self.assertAlmostEqual(result.product_weight,7.85+value)
            self.assertAlmostEqual(result.sheet_weight,7.85+value)

    def test_migration_preserves_custom_values_and_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'master.json'
            original=json.dumps({'version':3,'codes':{'E24':{'constant_kg_m2':.055,'per_side_kg_m2':.0275,
                'note':'社内値','confirmed':False},'Z08':{'constant_kg_m2':.12,'note':'保持','confirmed':True}}},ensure_ascii=False)
            path.write_text(original,encoding='utf-8')
            registry=CoatingRegistry(path)
            self.assertEqual(registry.values['E24'].constant_kg_m2,.055)
            self.assertFalse(registry.values['E24'].confirmed)
            self.assertEqual(registry.values['F08'].constant_kg_m2,.120)
            self.assertIn('E8',registry.values)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['version'],5)
            backups=list(Path(tmp).glob('*.bak'))
            self.assertEqual(len(backups),1)
            self.assertEqual(backups[0].read_text(encoding='utf-8'),original)
            # 一度移行後に利用者が削除した記号を毎回再追加しない。
            values=dict(registry.values); values.pop('F04'); registry.save(values)
            self.assertNotIn('F04',CoatingRegistry(path).values)
            self.assertEqual(len(list(Path(tmp).glob('*.bak'))),1)
