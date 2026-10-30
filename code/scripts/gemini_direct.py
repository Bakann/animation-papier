"""Gemini REST direct : références ordonnées, aucun SDK ni clé sur disque."""
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

RACINE = Path(__file__).resolve().parents[1]

def historique_verifie(cfg):
    """Reconstruit le centre depuis son journal, sans réseau ni altération du tour modèle."""
    name = cfg.get('gemini_historique')
    if not name:
        return None
    root = RACINE
    path = root / name
    raw = path.read_bytes()
    manifest = json.loads(raw)
    for file, expected in manifest['empreintes'].items():
        if hashlib.sha256((root / file).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Historique : empreinte différente pour ' + file)
    rows = [json.loads(line) for line in (root/manifest['journal']).read_text().splitlines() if line.strip()]
    pid = manifest['reference_appel']
    frames = [r for r in rows if r.get('type') == 'frame' and r.get('reference_appel') == pid and r.get('statut') == 'ok']
    submissions = [r for r in rows if r.get('type') == 'soumission_gemini' and r.get('reference_appel') == pid]
    if len(frames) != 1 or len(submissions) != 1:
        raise RuntimeError('Historique : centre réussi et soumission uniques attendus')
    e, submitted = frames[0], submissions[0]
    centre_cfg = json.loads((root/e['config_fichier']).read_text())
    if centre_cfg.get('gemini_references_supplementaires') or cfg.get('gemini_references_supplementaires'):
        raise RuntimeError('Historique pilote : centre à deux références et branche à une grille attendus')
    if centre_cfg['modele'] != cfg['modele'] or centre_cfg['qualite'] != cfg['qualite']:
        raise RuntimeError('Historique : modèle ou qualité différents du centre')
    src = root / 'travail' / e['plan'] / 'src' / e['source']
    anchor = root / e['ancre']
    text = (root/e['prompt_fichier']).read_text().strip()
    required = [src, anchor, root/e['prompt_fichier'], root/e['config_fichier'], root/manifest['journal'], root/manifest['reponse']]
    if any(str(p.relative_to(root)) not in manifest['empreintes'] for p in required):
        raise RuntimeError('Historique : empreinte obligatoire absente')
    checks = {'source_sha256': hashlib.sha256(src.read_bytes()).hexdigest(),
              'ancre_sha256': hashlib.sha256(anchor.read_bytes()).hexdigest(),
              'prompt_sha256': hashlib.sha256(text.encode()).hexdigest(),
              'config_sha256': hashlib.sha256(json.dumps(centre_cfg, sort_keys=True).encode()).hexdigest()}
    if any(e.get(k) != v or submitted.get(k) != v for k,v in checks.items()):
        raise RuntimeError('Historique : empreinte différente du journal original')
    parts = [{'text': text}]
    for p in (src, anchor):
        data = p.read_bytes()
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise RuntimeError('Historique : entrée originale PNG attendue')
        parts.append({'inlineData': {'mimeType': 'image/png', 'data': base64.b64encode(data).decode()}})
    response = json.loads((root/manifest['reponse']).read_bytes())
    model = response['candidates'][0]['content']
    if response.get('responseId') != e['response_id_google'] or model.get('role') != 'model':
        raise RuntimeError('Historique : réponse du centre incorrecte')
    if not any(p.get('inlineData', {}).get('mimeType') == 'image/jpeg' and p.get('thoughtSignature') for p in model['parts']):
        raise RuntimeError('Historique : JPEG original signé attendu')
    u0 = {'role': 'user', 'parts': parts}
    fingerprint = lambda obj: hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()
    return u0, model, {'manifeste': name, 'manifeste_sha256': hashlib.sha256(raw).hexdigest(),
                      'centre_reference_appel': pid, 'tour_utilisateur_sha256': fingerprint(u0),
                      'tour_modele_sha256': fingerprint(model), 'empreintes_verifiees': manifest['empreintes']}


def preparer_requete(cfg, src, ancre, prompt):
    """Préparation pure : aucun accès réseau, y compris avec historique."""
    parts = [{'text': prompt}]
    history = historique_verifie(cfg)
    extra = references_supplementaires(cfg)
    paths = [src] if history else [src, ancre] + [Path(__file__).resolve().parents[1]/r['fichier'] for r in extra]
    for path in paths:
        data = Path(path).read_bytes()
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise RuntimeError('Les références Gemini doivent être des PNG')
        parts.append({'inlineData': {'mimeType': 'image/png', 'data': base64.b64encode(data).decode()}})
    contents = [history[0], history[1], {'role': 'user', 'parts': parts}] if history else [{'role': 'user', 'parts': parts}]
    body = {'contents': contents, 'generationConfig': {
        'responseModalities': ['IMAGE'], 'imageConfig': {
            'aspectRatio': cfg.get('gemini_aspect_ratio', '9:16'), 'imageSize': cfg['qualite']}}}
    return body, history[2] if history else None


def references_supplementaires(cfg):
    """Valide et empreinte les références optionnelles avant tout envoi payant."""
    refs = cfg.get('gemini_references_supplementaires', [])
    if not isinstance(refs, list) or len(refs) > 12 or any(not isinstance(p, str) or not p for p in refs):
        raise RuntimeError('gemini_references_supplementaires : liste de 0 à 12 chemins PNG attendue')
    records = []
    for name in refs:
        path = Path(__file__).resolve().parents[1] / name
        if not path.is_file():
            raise RuntimeError('Référence Gemini supplémentaire absente : ' + name)
        data = path.read_bytes()
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise RuntimeError('Les références Gemini supplémentaires doivent être des PNG')
        records.append({'fichier': name, 'sha256': hashlib.sha256(data).hexdigest()})
    return records


class GeminiDirect:
    def __init__(self, cfg, dossier, http):
        self.cfg, self.http = cfg, http
        self.cache = Path(dossier) / 'reponses_gemini'
        self.cle = os.environ.get('GEMINI_API_KEY', '')
        if not self.cle and sys.platform == 'darwin':
            self.cle = subprocess.run(['/bin/launchctl', 'getenv', 'GEMINI_API_KEY'],
                                      capture_output=True, text=True).stdout.rstrip('\n')
        if not self.cle or any(ord(c) < 32 or ord(c) == 127 for c in self.cle):
            raise SystemExit('[erreur] GEMINI_API_KEY absente ou contenant un caractère de contrôle')
        if cfg['modele'] != 'gemini-3-pro-image' or cfg['qualite'] not in ('1K', '2K', '4K'):
            raise SystemExit('[erreur] Gemini direct exige gemini-3-pro-image et une qualité 1K/2K/4K')
        self.last_pid = None
        self.on_accepted = None
        self.metadata = {}

    def redessiner(self, src, ancre, prompt, seed):
        # Le seed reste tracé localement; aucun déterminisme fournisseur n'est supposé.
        body, history = preparer_requete(self.cfg, src, ancre, prompt)
        payload = json.dumps(body).encode()
        if history and list((self.cache.parent/'requetes_gemini').glob('*.json')):
            raise RuntimeError('Historique : unique envoi déjà tenté dans ce dossier ; aucune relance autorisée')
        self.last_pid = 'gemini-' + uuid.uuid4().hex
        self.metadata = {}
        if history:
            requests = self.cache.parent/'requetes_gemini'
            requests.mkdir(parents=True, exist_ok=True)
            with (requests/(self.last_pid+'.json')).open('xb') as f:
                f.write(payload); f.flush(); os.fsync(f.fileno())
        if self.on_accepted:
            self.on_accepted(self.last_pid)  # identifiant LOCAL enregistré AVANT le POST
        url = 'https://generativelanguage.googleapis.com/v1beta/models/' + self.cfg['modele'] + ':generateContent'
        try:
            data = self.http(url, payload,
                             {'Content-Type': 'application/json', 'x-goog-api-key': self.cle})
        except RuntimeError as exc:
            if history:
                self.cache.mkdir(parents=True, exist_ok=True)
                failure = {'reference_locale': self.last_pid, 'message': str(exc).replace(self.cle, '[CLE MASQUEE]'),
                           'http_status': getattr(exc, 'http_status', None), 'aucune_relance': True}
                (self.cache/(self.last_pid+'_erreur.json')).write_text(json.dumps(failure, ensure_ascii=False))
                if hasattr(exc, 'corps_http'):
                    (self.cache/(self.last_pid+'_corps_http.bin')).write_bytes(exc.corps_http.replace(self.cle.encode(), b'[CLE MASQUEE]'))
            error = RuntimeError(str(exc).replace(self.cle, '[CLE MASQUEE]'))
            error.issue_inconnue = getattr(exc, 'issue_inconnue', False)
            # Une réponse HTTP 4xx (hors 408) est un refus explicite; réseau/5xx = issue inconnue.
            error.terminee = getattr(exc, 'http_status', 0) in (400,401,403,404,409,413,422,429)
            raise error from None
        self.cache.mkdir(parents=True, exist_ok=True)
        path = self.cache / (self.last_pid + '.json')
        with path.open('xb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        return self.attendre(self.last_pid)

    def attendre(self, pid):
        """Relit une réponse sauvegardée, sans appel réseau ni nouvelle facturation."""
        if not re.fullmatch(r'gemini-[0-9a-f]{32}', pid):
            raise RuntimeError('Identifiant local Gemini invalide')
        self.last_pid = pid
        path = self.cache / (pid + '.json')
        if not path.exists():
            raise RuntimeError('Réponse Gemini absente : issue inconnue. Vérifier le suivi Google avant toute nouvelle soumission; aucune relance automatique.')
        try:
            rep = json.loads(path.read_bytes())
        except (ValueError, UnicodeError):
            raise RuntimeError('Réponse Gemini illisible, conservée pour diagnostic') from None
        self.metadata = {'usage_gemini': rep.get('usageMetadata', {}),
                         'response_id_google': rep.get('responseId'),
                         'modele_reponse': rep.get('modelVersion'), 'seed_envoye': False}
        if self.cfg.get('gemini_historique'):
            request = self.cache.parent/'requetes_gemini'/(pid+'.json')
            self.metadata.update({'historique_gemini': historique_verifie(self.cfg)[2],
                                  'requete_sha256': hashlib.sha256(request.read_bytes()).hexdigest(),
                                  'requete_fichier': str(request)})
        images = []
        candidates = rep.get('candidates', [])
        for candidate in candidates:
            if candidate.get('finishReason') not in (None, 'STOP'):
                continue
            for part in candidate.get('content', {}).get('parts', []):
                inline = part.get('inlineData', {})
                mime = inline.get('mimeType')
                if part.get('thought') or mime not in ('image/png', 'image/jpeg', 'image/webp'):
                    continue
                try:
                    image = base64.b64decode(inline.get('data', ''), validate=True)
                except (ValueError, binascii.Error):
                    continue
                if mime != 'image/png':
                    converted = subprocess.run(['ffmpeg', '-v', 'error', '-i', 'pipe:0',
                        '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', 'pipe:1'],
                        input=image, capture_output=True)
                    if converted.returncode:
                        raise RuntimeError('Conversion locale JPEG/WebP vers PNG échouée; réponse conservée')
                    image = converted.stdout
                    self.metadata['format_original_google'] = mime
                if image.startswith(b'\x89PNG\r\n\x1a\n'):
                    images.append(image)
        if len(images) != 1:
            reasons = [c.get('finishReason') for c in candidates]
            error = RuntimeError(f'Gemini : une image PNG finale attendue, {len(images)} reçue(s); raisons : {reasons}; blocage : {rep.get("promptFeedback", {}).get("blockReason")}. Réponse conservée.')
            error.terminee = True
            raise error
        return pid, images

    def propositions_ancre(self, src, prompt, seed):
        raise SystemExit('[arrêt] Création d’ancres Gemini non prise en charge : utiliser l’ancre déjà approuvée. Aucun appel envoyé.')
