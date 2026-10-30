"""Délais réseau simulés : journal persistant et absence de resoumission."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import commun
spec = importlib.util.spec_from_file_location('redessin_timeout', Path(__file__).resolve().parents[1] / 'scripts/02_redessiner.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class TimeoutHTTP(unittest.TestCase):
    def test_timeout_on_connect_or_read_is_controlled(self):
        response = MagicMock()
        response.__enter__.return_value.read.side_effect = TimeoutError('read timed out')
        for kwargs in ({'side_effect': TimeoutError('connect timed out')}, {'return_value': response}):
            with self.subTest(kwargs=list(kwargs)), patch.object(r.urllib.request, 'urlopen', **kwargs) as call:
                with self.assertRaisesRegex(RuntimeError, 'issue de l.appel inconnue') as caught:
                    r.http('https://example.invalid/generate', b'{}')
                self.assertTrue(caught.exception.issue_inconnue)
                self.assertFalse(getattr(caught.exception, 'terminee', False))
                self.assertEqual(call.call_count, 1)

    def test_timeout_is_journaled_and_next_submission_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folders = {'base': root, 'src': root/'src', 'out': root/'out',
                       'ancre': root/'ancre', 'journal': root/'journal.jsonl'}
            for name in ('src', 'out', 'ancre'):
                folders[name].mkdir()
            # Le transport valide l'en-tête PNG; aucune image n'est décodée ici.
            (folders['src']/'s0006.png').write_bytes(b'\x89PNG\r\n\x1a\nsource')
            (root/'reference.png').write_bytes(b'\x89PNG\r\n\x1a\nreference')
            (root/'prompt.txt').write_text('consigne de test')
            cfg = {'backend': 'gemini', 'modele': 'gemini-3-pro-image', 'qualite': '2K',
                   'taille': '9:16 / 2K', 'ancre': 'reference.png', 'prompt': 'prompt.txt',
                   'cout_estime_usd_par_image': .1608}
            argv = ['redessin', '--plan', 'fixture', '--config', 'fixture.json', '--oui']
            with patch.object(r, 'RACINE', root), patch.object(commun, 'RACINE', root), \
                 patch.object(r, 'charger_config', return_value=cfg), \
                 patch.object(r, 'dossiers', return_value=folders), patch.object(sys, 'argv', argv), \
                 patch.dict('os.environ', {'GEMINI_API_KEY': 'cle-factice'}), \
                 patch.object(r.urllib.request, 'urlopen', side_effect=TimeoutError('SSL read timeout')) as call:
                with self.assertRaisesRegex(SystemExit, 'premier échec'):
                    r.main()
                events = [json.loads(line) for line in folders['journal'].read_text().splitlines()]
                self.assertEqual([e['type'] for e in events], ['soumission_gemini', 'frame'])
                self.assertEqual(events[1]['statut'], 'erreur')
                self.assertEqual(events[1]['issue_appel'], 'inconnue')
                self.assertEqual(events[0]['reference_appel'], events[1]['reference_appel'])
                self.assertFalse(list(folders['out'].glob('*.png')))
                self.assertNotIn('cle-factice', folders['journal'].read_text())
                with self.assertRaisesRegex(SystemExit, 'tâche déjà soumise'):
                    r.main()
                self.assertEqual(call.call_count, 1)


if __name__ == '__main__':
    unittest.main()
