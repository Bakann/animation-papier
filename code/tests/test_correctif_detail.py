import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from correctif_detail import verifier_calage,masque_detail,finaliser_export,ComfyLocal


class Correctif(unittest.TestCase):
    def cfg(self):return {'taille_source':[20,30],'crop_xywh':[3,4,12,20],
        'rectangle_retouche_dans_crop':[2,2,10,18],'rayon_coins':1,'raccord_px':1,'preserver_depuis_y':18}
    def test_wrong_frame_size_and_crop_rejected(self):
        with self.assertRaises(ValueError):verifier_calage(Image.new('RGB',(21,30)),self.cfg())
        c=self.cfg();c['crop_xywh']=[19,0,12,20]
        with self.assertRaises(ValueError):verifier_calage(Image.new('RGB',(20,30)),c)
    def test_mask_respects_green_and_sole(self):
        im=Image.new('RGB',(20,30),(80,70,60));a=np.array(im);a[:,9:]=[0,255,0];im=Image.fromarray(a)
        mask=np.array(masque_detail(im,self.cfg()))
        self.assertEqual(mask[:,6:].sum(),0)
        self.assertEqual(mask[14:].sum(),0)
        self.assertGreater(mask.sum(),0)
    def test_only_authorized_pixels_can_change(self):
        im=Image.new('RGB',(20,30),(80,70,60));c=self.cfg();mask=masque_detail(im,c)
        edited=im.copy();edited.paste(Image.new('RGB',(12,20),(100,90,80)),(3,4),mask)
        values=np.array(edited);values[0,0,0]+=1
        result,full,count=finaliser_export(im,Image.fromarray(values),mask,c)
        outside=np.array(full)==0
        self.assertTrue(np.array_equal(np.array(result)[outside],np.array(im)[outside]))
        self.assertTrue(np.array_equal(np.array(result)[18:],np.array(im)[18:]))
        self.assertEqual(count,1)
    def test_large_outside_change_fails(self):
        im=Image.new('RGB',(20,30),(80,70,60));c=self.cfg();mask=masque_detail(im,c)
        values=np.array(im);values[0,0,0]+=2
        with self.assertRaises(ValueError):finaliser_export(im,Image.fromarray(values),mask,c)
    def test_local_graph_rejects_paid_nodes_before_http(self):
        c=ComfyLocal();c.http=lambda *args:self.fail('Réseau inattendu')
        with self.assertRaises(ValueError):c.executer({'1':{'class_type':'GeminiImage2Node'}},Path('/unused'),'1')
    def test_disabled_block_never_calls_comfy(self):
        spec=importlib.util.spec_from_file_location('correctif_runner',ROOT/'scripts/10_correctif_detail.py')
        runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
        with tempfile.TemporaryDirectory() as temp:
            t=Path(temp);(t/'cfg.json').write_text(json.dumps({'actif':False}))
            with patch.object(runner,'RACINE',t),patch.object(runner,'ComfyLocal',side_effect=AssertionError('appel interdit')),patch.object(sys,'argv',['correctif','--config','cfg.json','--essai','off']):
                runner.main()

if __name__=='__main__':unittest.main()
