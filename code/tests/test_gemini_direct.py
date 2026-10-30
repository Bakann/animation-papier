import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from gemini_direct import GeminiDirect, references_supplementaires

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2ioAAAAASUVORK5CYII=')


class Gemini(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src = self.root/'source.png'; self.src.write_bytes(PNG)
        self.ref = self.root/'reference.png'; self.ref.write_bytes(PNG+b'reference')
        self.cfg = {'modele':'gemini-3-pro-image','qualite':'2K'}
        self.env = patch.dict('os.environ', {'GEMINI_API_KEY':'secret-factice'})
        self.env.start(); self.addCleanup(self.env.stop)

    def response(self):
        return {'responseId':'google-id','usageMetadata':{'totalTokenCount':123},'candidates':[
            {'finishReason':'STOP','content':{'parts':[
                {'thought':True,'inlineData':{'mimeType':'image/png','data':base64.b64encode(PNG).decode()}},
                {'inlineData':{'mimeType':'image/png','data':base64.b64encode(PNG).decode()}}]}}]}

    def test_request_order_cache_and_usage(self):
        calls=[]; events=[]
        def http(url, body, headers):
            self.assertTrue(events)
            calls.append(json.loads(body))
            self.assertEqual(headers['x-goog-api-key'],'secret-factice')
            return json.dumps(self.response()).encode()
        g=GeminiDirect(self.cfg,self.root,http)
        g.on_accepted=events.append
        pid,images=g.redessiner(self.src,self.ref,'consigne inchangée',123)
        self.assertEqual(images,[PNG]);self.assertEqual(g.metadata['usage_gemini']['totalTokenCount'],123)
        parts=calls[0]['contents'][0]['parts']
        self.assertEqual(parts[0]['text'],'consigne inchangée')
        self.assertEqual(base64.b64decode(parts[1]['inlineData']['data']),PNG)
        self.assertEqual(base64.b64decode(parts[2]['inlineData']['data']),PNG+b'reference')
        self.assertEqual(calls[0]['generationConfig']['imageConfig'],{'aspectRatio':'9:16','imageSize':'2K'})
        self.assertEqual(g.attendre(pid)[1],[PNG]);self.assertEqual(len(calls),1)
        for path in self.root.rglob('*.json'):self.assertNotIn('secret-factice',path.read_text())

    def test_refusal_no_image_and_no_retry(self):
        calls=[]
        def http(*args):
            calls.append(1)
            return json.dumps({'promptFeedback':{'blockReason':'SAFETY'}}).encode()
        g=GeminiDirect(self.cfg,self.root,http)
        with self.assertRaisesRegex(RuntimeError,'SAFETY') as cm:g.redessiner(self.src,self.ref,'x',1)
        self.assertTrue(cm.exception.terminee);self.assertEqual(len(calls),1)

    def test_extra_reference_order_and_fingerprint(self):
        material = self.root/'matiere.png';material.write_bytes(PNG+b'matiere')
        self.cfg['gemini_references_supplementaires'] = [str(material)]
        calls=[]
        def http(url, body, headers):
            calls.append(json.loads(body))
            return json.dumps(self.response()).encode()
        before = references_supplementaires(self.cfg)
        g=GeminiDirect(self.cfg,self.root,http)
        g.redessiner(self.src,self.ref,'Trois images ordonnées',1)
        parts=calls[0]['contents'][0]['parts']
        self.assertEqual([base64.b64decode(p['inlineData']['data']) for p in parts[1:]],
                         [PNG,PNG+b'reference',PNG+b'matiere'])
        material.write_bytes(PNG+b'autre matiere')
        self.assertNotEqual(before,references_supplementaires(self.cfg))

    def test_bad_extra_reference_prevents_submission(self):
        self.cfg['gemini_references_supplementaires']=[str(self.root/'absente.png')]
        g=GeminiDirect(self.cfg,self.root,lambda *args:self.fail('POST inattendu'))
        g.on_accepted=lambda *args:self.fail('Soumission journalisée malgré fichier absent')
        with self.assertRaisesRegex(RuntimeError,'absente'):g.redessiner(self.src,self.ref,'x',1)
        self.assertIsNone(g.last_pid)

    def test_unknown_network_outcome(self):
        def http(*args):raise RuntimeError('réseau interrompu secret-factice')
        g=GeminiDirect(self.cfg,self.root,http)
        with self.assertRaises(RuntimeError) as cm:g.redessiner(self.src,self.ref,'x',1)
        self.assertFalse(cm.exception.terminee);self.assertNotIn('secret-factice',str(cm.exception))
        with self.assertRaisesRegex(RuntimeError,'issue inconnue'):g.attendre(g.last_pid)

    def test_http_refusal_is_terminal(self):
        def http(*args):
            e=RuntimeError('HTTP 403');e.http_status=403;raise e
        g=GeminiDirect(self.cfg,self.root,http)
        with self.assertRaises(RuntimeError) as cm:g.redessiner(self.src,self.ref,'x',1)
        self.assertTrue(cm.exception.terminee)

    def test_anchor_never_submits(self):
        g=GeminiDirect(self.cfg,self.root,lambda *args:self.fail('appel inattendu'))
        with self.assertRaises(SystemExit):g.propositions_ancre(self.src,'x',1)

    def test_jpeg_recovery_without_paid_request(self):
        import subprocess
        jpeg=subprocess.run(['ffmpeg','-v','error','-i','pipe:0','-frames:v','1',
            '-f','image2pipe','-vcodec','mjpeg','pipe:1'],input=PNG,capture_output=True,check=True).stdout
        rep=self.response()
        rep['candidates'][0]['content']['parts']=[{'inlineData':{
            'mimeType':'image/jpeg','data':base64.b64encode(jpeg).decode()}}]
        g=GeminiDirect(self.cfg,self.root,lambda *args:json.dumps(rep).encode())
        pid,images=g.redessiner(self.src,self.ref,'x',1)
        self.assertTrue(images[0].startswith(b'\x89PNG'))
        self.assertEqual(g.metadata['format_original_google'],'image/jpeg')
        g.http=lambda *args:self.fail('Reprise payante inattendue')
        self.assertEqual(g.attendre(pid)[1],images)

if __name__=='__main__':unittest.main()
