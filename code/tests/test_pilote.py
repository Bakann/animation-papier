import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import atelier as a
import numpy as np
from PIL import Image
spec=importlib.util.spec_from_file_location('redessin',Path(__file__).resolve().parents[1]/'scripts/02_redessiner.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class Pilote(unittest.TestCase):
    def setUp(self):
        self.pts={'a':[0,0],'b':[31,0],'c':[0,31],'d':[31,31]}
        self.tri=[['a','b','c'],['b','d','c']]
        grid=np.indices((32,32)).sum(0)%2*255
        self.im=Image.fromarray(np.repeat(grid[...,None],3,2).astype('uint8'))
    def test_identite(self):
        out,cover=a.propager(self.im,self.pts,self.pts,self.tri,(32,32))
        self.assertTrue(np.array_equal(np.array(out),np.array(self.im)))
        self.assertEqual(np.array(cover).min(),255)
    def test_translation_connue(self):
        pts={k:[v[0]+3,v[1]+2] for k,v in self.pts.items()}
        out,_=a.propager(self.im,self.pts,pts,self.tri,(36,35))
        self.assertTrue(np.array_equal(np.array(out)[2:34,3:35],np.array(self.im)))
    def test_inversion(self):
        pts={**self.pts,'b':[0,31],'c':[31,0]}
        with self.assertRaises(ValueError):a.propager(self.im,self.pts,pts,self.tri,(32,32))
    def test_hors_robe_et_trous(self):
        m=a.masque([[[5,5],[25,5],[25,25],[5,25]]],(32,32))
        cover=a.masque([[[8,8],[20,8],[20,20],[8,20]]],(32,32))
        out,q=a.composer_robe(self.im,Image.new('RGB',(32,32),'red'),m,cover)
        self.assertTrue(np.array_equal(np.array(out)[np.array(m)==0],np.array(self.im)[np.array(m)==0]))
        self.assertGreater(q['pixels_repli_nano'],0)
    def test_domaine_commun_et_flou(self):
        m=Image.new('L',(32,32),255)
        rows=a.mesurer({'original':[self.im,self.im], 'lisse':[Image.new('RGB',(32,32),'gray')]*2},
                      [m,m],[self.pts]*2,self.tri)
        row=rows[0][0]
        self.assertEqual(row['pixels_communs'],1024)
        self.assertEqual(row['variantes']['original']['residu_rgb_moyen'],0)
        self.assertGreater(row['variantes']['original']['detail_local_moyen'],100)
        self.assertEqual(row['variantes']['lisse']['detail_local_moyen'],0)
        empty=Image.new('L',(32,32),0)
        row=a.mesurer({'x':[self.im]*2},[m,empty],[self.pts]*2,self.tri)[0][0]
        self.assertIsNone(row['variantes']['x']['residu_rgb_moyen'])
    def test_geometrie_independante(self):
        with self.assertRaises(ValueError):a.geometrie({'a':[1,1]},{'a':[1,1]},['a'])
        self.assertEqual(a.geometrie({'p':[1,1]},{'p':[4,5]},[])['p']['distance_px'],5)
    def comfy(self):
        c=r.Comfy.__new__(r.Comfy);c.url='http://test';c.cle='cle-factice';c.last_pid=None;c.on_accepted=None
        return c
    def test_journal_avant_attente_et_reprise_sans_post(self):
        c=self.comfy();events=[]
        c.on_accepted=lambda pid:events.append(('accepte',pid))
        def http(url,donnees=None,entetes=None,delai=600):
            if url.endswith('/prompt'):return b'{"prompt_id":"abc"}'
            if '/history/' in url:
                self.assertEqual(events[0],('accepte','abc'))
                return json.dumps({'abc':{'status':{'status_str':'success'},'outputs':{'5':{'images':[{'filename':'x.png'}]}}}}).encode()
            return b'png-factice'
        with patch.object(r,'http',http):self.assertEqual(c.executer({}),('abc',[b'png-factice']))
        with patch.object(r,'http',http):self.assertEqual(c.attendre('abc')[0],'abc')
    def test_timeout_conserve_identifiant(self):
        c=self.comfy()
        with patch.object(r,'http',return_value=b'{}'),patch.object(r.time,'time',side_effect=[0,901]):
            with self.assertRaisesRegex(RuntimeError,'--reprendre abc'):c.attendre('abc')
        self.assertEqual(c.last_pid,'abc')


class Montage(unittest.TestCase):
    def test_configuration_grain_et_cadence(self):
        import commun
        import subprocess
        spec=importlib.util.spec_from_file_location('assembler',Path(__file__).resolve().parents[1]/'scripts/03_assembler.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='papier_montage_') as tmp:
            t=Path(tmp);d=t/'travail/fixture'
            (d/'src').mkdir(parents=True);(d/'out').mkdir()
            frames=[]
            for i in range(1,17):
                im=Image.new('RGB',(64,96),(i*12,64,100));im.save(d/f'src/s{i:04}.png');im.save(d/f'out/r{i:04}.png')
                frames.append({'index':i,'fichier':f's{i:04}.png','frame_source':(i-1)*3})
            # Vidéo synthétique temporaire : aucun média privé n'est requis.
            video=t/'source_synthetique.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                'color=c=black:s=64x96:r=24:d=2','-an','-c:v','libx264',
                '-pix_fmt','yuv420p',str(video)],check=True)
            man={'frames':frames,'debut_s':0,'duree_s':2,'video':str(video)}
            (d/'manifeste.json').write_text(json.dumps(man))
            cfg={'fps':24,'pas':3,'sortie_largeur':64,'sortie_hauteur':96,'grain':5,'normalisation':'pillow'}
            (t/'fixture.json').write_text(json.dumps(cfg))
            with patch.object(commun,'RACINE',t),patch.object(m,'RACINE',t),patch.object(sys,'argv',['assembler','--plan','fixture','--config','fixture.json','--grain','0']):m.main()
            actual=json.loads((t/'sortie/fixture_montage.json').read_text())
            self.assertEqual(actual['grain_effectif'],0)
            self.assertEqual(actual['configuration_effective']['grain'],5)
            self.assertEqual(actual['images'][-1]['frames_sortie'],[45,47])
            result=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-count_frames','-show_entries','stream=nb_read_frames,r_frame_rate,width,height,duration','-of','json',str(t/'sortie/fixture_kirigami_couture_en3.mp4')]))['streams'][0]
            self.assertEqual(result['nb_read_frames'],'48');self.assertEqual(result['r_frame_rate'],'24/1')
            self.assertEqual((result['width'],result['height']),(64,96));self.assertEqual(float(result['duration']),2)

if __name__=='__main__':unittest.main()
