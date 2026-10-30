import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
spec=importlib.util.spec_from_file_location('doux_motion',Path(__file__).resolve().parents[1]/'scripts/15_verifier_doux_mouvement.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class GrainLieAuPanneau(unittest.TestCase):
    def test_identite_et_translation_connue(self):
        rng=np.random.default_rng(7)
        grain=rng.normal(size=(64,64))
        source=np.zeros((64,64),dtype=bool);source[10:40,12:34]=True
        identity=m.grain_suivi(grain,source,source)
        np.testing.assert_allclose(identity[source],grain[source],atol=1e-12)
        target=np.zeros_like(source);target[15:45,15:37]=True
        moved=m.grain_suivi(grain,source,target)
        np.testing.assert_allclose(moved[15:45,15:37],grain[10:40,12:34],atol=1e-12)

    def test_domaine_vide_refuse(self):
        with self.assertRaises(ValueError):
            m.enveloppe(np.zeros((64,64),dtype=bool))


if __name__=='__main__':unittest.main()
