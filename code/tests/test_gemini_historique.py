"""Historique en étoile : intégrité, ordre, conservation du JPEG/signatures et envoi unique."""
import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import gemini_direct as gd

PNG = b'\x89PNG\r\n\x1a\n'


class Historique(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        rootpatch = patch.object(gd, 'RACINE', self.root);rootpatch.start();self.addCleanup(rootpatch.stop)
        env = patch.dict('os.environ', {'GEMINI_API_KEY':'secret-factice'});env.start();self.addCleanup(env.stop)
        (self.root/'travail/centre/src').mkdir(parents=True)
        self.files = {'travail/centre/src/s0001.png':PNG+b'centre', 'ancre.png':PNG+b'ancre',
                      'prompt.txt':b'  prompt original\n', 'centre.json':json.dumps({'modele':'gemini-3-pro-image','qualite':'2K'}).encode()}
        self.model = {'role':'model','parts':[{'text':'Texte original éventuel'},
            {'inlineData':{'mimeType':'image/jpeg','data':base64.b64encode(b'JPEG original, pas PNG converti').decode()},
             'thoughtSignature':'signature+/=\nexacte'}]}
        self.files['response.json'] = json.dumps({'responseId':'original-id','candidates':[{'content':self.model}]}).encode()
        self.sha = lambda b: hashlib.sha256(b).hexdigest()
        event = {'plan':'centre','reference_appel':'gemini-'+'0'*32,'source':'s0001.png','ancre':'ancre.png',
                 'prompt_fichier':'prompt.txt','config_fichier':'centre.json','response_id_google':'original-id',
                 'source_sha256':self.sha(self.files['travail/centre/src/s0001.png']),
                 'ancre_sha256':self.sha(self.files['ancre.png']),
                 'prompt_sha256':self.sha(self.files['prompt.txt'].decode().strip().encode()),
                 'config_sha256':self.sha(json.dumps(json.loads(self.files['centre.json']),sort_keys=True).encode())}
        self.files['journal.jsonl'] = ('\n'.join(json.dumps({**event,**extra}) for extra in
            ({'type':'soumission_gemini'}, {'type':'frame','statut':'ok'}))+'\n').encode()
        for name,data in self.files.items():(self.root/name).write_bytes(data)
        self.manifest = {'journal':'journal.jsonl','reference_appel':event['reference_appel'],'reponse':'response.json',
                         'empreintes':{name:self.sha(data) for name,data in self.files.items()}}
        (self.root/'historique.json').write_text(json.dumps(self.manifest))
        self.src=self.root/'branche.png';self.src.write_bytes(PNG+b'branche')
        self.cfg={'modele':'gemini-3-pro-image','qualite':'2K','gemini_historique':'historique.json'}
        self.response={'responseId':'branche-id','candidates':[{'finishReason':'STOP','content':{'role':'model','parts':[
            {'inlineData':{'mimeType':'image/png','data':base64.b64encode(PNG+b'resultat').decode()}}]}}]}

    def test_turn_order_original_signature_and_jpeg_intact(self):
        calls=[]
        def http(url,body,headers):calls.append(json.loads(body));return json.dumps(self.response).encode()
        g=gd.GeminiDirect(self.cfg,self.root/'essai',http)
        g.redessiner(self.src,self.root/'ancre.png','Nouvelle grille seule autorité',1)
        contents=calls[0]['contents']
        self.assertEqual([c['role'] for c in contents],['user','model','user'])
        self.assertEqual(contents[0]['parts'][0],{'text':'prompt original'})
        self.assertEqual([base64.b64decode(p['inlineData']['data']) for p in contents[0]['parts'][1:]],
                         [self.files['travail/centre/src/s0001.png'],self.files['ancre.png']])
        self.assertEqual(contents[1],self.model)
        self.assertEqual(len(contents[2]['parts']),2)
        self.assertEqual(base64.b64decode(contents[2]['parts'][1]['inlineData']['data']),PNG+b'branche')
        saved=json.loads(next((self.root/'essai/requetes_gemini').glob('*.json')).read_bytes())
        self.assertEqual(saved,calls[0])

    def test_each_changed_fingerprint_blocks_before_send(self):
        for name,data in self.files.items():
            with self.subTest(file=name):
                (self.root/name).write_bytes(data+b'change')
                g=gd.GeminiDirect(self.cfg,self.root/'essai',lambda *args:self.fail('POST interdit'))
                g.on_accepted=lambda *args:self.fail('Soumission interdite')
                with self.assertRaisesRegex(RuntimeError,'empreinte différente'):g.redessiner(self.src,self.root/'ancre.png','x',1)
                self.assertIsNone(g.last_pid)
                (self.root/name).write_bytes(data)

    def test_original_journal_is_authority_even_if_manifest_updated(self):
        (self.root/'prompt.txt').write_text('texte différent')
        self.manifest['empreintes']['prompt.txt']=self.sha((self.root/'prompt.txt').read_bytes())
        (self.root/'historique.json').write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(RuntimeError,'journal original'):gd.historique_verifie(self.cfg)

    def test_resume_without_new_post_and_second_submission_blocked(self):
        calls=[]
        def http(*args):calls.append(1);return json.dumps(self.response).encode()
        g=gd.GeminiDirect(self.cfg,self.root/'essai',http)
        pid,images=g.redessiner(self.src,self.root/'ancre.png','x',1)
        self.assertEqual(g.attendre(pid)[1],images)
        with self.assertRaisesRegex(RuntimeError,'unique envoi'):g.redessiner(self.src,self.root/'ancre.png','x',2)
        self.assertEqual(len(calls),1)

    def test_timeout_preserves_request_and_error_without_retry(self):
        calls=[]
        def http(*args):
            calls.append(1);e=RuntimeError('timeout secret-factice');e.issue_inconnue=True;raise e
        g=gd.GeminiDirect(self.cfg,self.root/'essai',http)
        with self.assertRaises(RuntimeError):g.redessiner(self.src,self.root/'ancre.png','x',1)
        self.assertTrue((g.cache/(g.last_pid+'_erreur.json')).exists())
        with self.assertRaisesRegex(RuntimeError,'unique envoi'):g.redessiner(self.src,self.root/'ancre.png','x',1)
        self.assertEqual(len(calls),1)
        for p in (self.root/'essai').rglob('*.json'):self.assertNotIn('secret-factice',p.read_text())


if __name__=='__main__':unittest.main()
