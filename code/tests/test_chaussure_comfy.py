import importlib.util
from pathlib import Path
import sys
import unittest
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('shoes',ROOT/'scripts/07_guide_chaussure_comfy.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class ChaussureComfy(unittest.TestCase):
    def test_workflow_cannot_submit_paid_node(self):
        graph=m.workflow(352,1151,84,86)
        m.verifier_graphe(graph)
        graph['18']={'class_type':'GeminiImage2Node','inputs':{}}
        with self.assertRaises(ValueError):m.verifier_graphe(graph)

    def test_sole_mode_never_adds_buckle(self):
        graph=m.workflow(352,1151,84,86,semelle=True)
        self.assertEqual(graph['11']['class_type'],'SolidMask')
        self.assertEqual(graph['11']['inputs']['value'],0)

    def test_export_restores_only_outside(self):
        base=Image.new('RGB',(4,4),(100,100,100))
        raw=np.array(base);raw[0,0]=99;raw[1,1]=200
        allowed=np.zeros((4,4),bool);allowed[1,1]=True
        final,rounding=m.proteger_export(base,Image.fromarray(raw),allowed)
        self.assertEqual(rounding,1)
        self.assertTrue(np.array_equal(np.array(final)[~allowed],np.array(base)[~allowed]))
        self.assertEqual(np.array(final)[1,1,0],200)

    def test_unexpected_outside_change_is_rejected(self):
        with self.assertRaises(ValueError):
            m.proteger_export(Image.new('RGB',(4,4),'black'),Image.new('RGB',(4,4),'white'),np.zeros((4,4),bool))

if __name__=='__main__':unittest.main()
