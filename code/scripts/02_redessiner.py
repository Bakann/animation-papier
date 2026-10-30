"""Étape 2 — redessine les frames extraites en style kirigami couture via une API payante.

Trois moteurs au choix (clé "backend" de config.json, ou --backend) :
  comfy  : ComfyUI local qui appelle GPT Image via ses Partner Nodes (clé COMFY_API_KEY)
  openai : appel direct à l'API OpenAI, sans ComfyUI (clé OPENAI_API_KEY)
  gemini : appel direct à Google Gemini, sans ComfyUI (clé GEMINI_API_KEY)
Aucun modèle n'est installé ni exécuté sur la machine.

Usage :
  python scripts/02_redessiner.py --plan test --ancre            # 4 propositions pour l'image de référence
  python scripts/02_redessiner.py --plan test --choisir 2        # garde la proposition n°2 comme référence
  python scripts/02_redessiner.py --plan test --limite 2         # essai sur 2 frames seulement
  python scripts/02_redessiner.py --plan test                    # redessine toutes les frames manquantes
  python scripts/02_redessiner.py --plan test --refaire 5,9      # refait les frames 5 et 9
  python scripts/02_redessiner.py --exporter-workflows           # écrit les workflows JSON dans workflows/
"""
import argparse
import base64
import hashlib
import json
import os
import random
import shutil
import sys
import tempfile
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from commun import RACINE, charger_config, dossiers, journaliser, lire_texte

# --------------------------------------------------------------------------- workflows ComfyUI
# Nœuds vérifiés dans le code source de ComfyUI (comfy_api_nodes/nodes_openai.py et nodes.py).
# "OpenAIGPTImage1" s'affiche sous le nom "OpenAI GPT Image 2" ; il est marqué « deprecated »
# (masqué de la recherche) mais reste exécutable, et ses entrées sont simples.


def workflow_redessin(src, ancre, prompt, cfg, seed):
    # Un workflow externe permet de comparer d'autres Partner Nodes sans changer
    # le workflow GPT Image historique ni la configuration principale.
    if cfg.get("workflow_redessin"):
        modele = json.loads(lire_texte(cfg["workflow_redessin"]))
        valeurs = {"__SOURCE__": src, "__ANCRE__": ancre,
                   "__PROMPT__": prompt, "__SEED__": seed}

        def remplir(obj):
            if isinstance(obj, dict):
                return {k: remplir(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [remplir(v) for v in obj]
            return valeurs.get(obj, obj) if isinstance(obj, str) else obj

        return remplir(modele)
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": src},
              "_meta": {"title": "Frame Flow (pose)"}},
        "2": {"class_type": "LoadImage", "inputs": {"image": ancre},
              "_meta": {"title": "Référence de style (ancre)"}},
        "3": {"class_type": "ImageBatch", "inputs": {"image1": ["1", 0], "image2": ["2", 0]},
              "_meta": {"title": "Frame + ancre"}},
        "4": {"class_type": "OpenAIGPTImage1",
              "inputs": {"prompt": prompt, "seed": seed, "quality": cfg["qualite"],
                         "background": "opaque", "size": cfg["taille"], "n": 1,
                         "image": ["3", 0], "model": cfg["modele"]},
              "_meta": {"title": "GPT Image — kirigami couture"}},
        "5": {"class_type": "SaveImage",
              "inputs": {"images": ["4", 0], "filename_prefix": f"{cfg['comfy_sous_dossier']}/r"},
              "_meta": {"title": "Enregistrer"}},
    }


def workflow_ancre(src, prompt, cfg, seed):
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": src},
              "_meta": {"title": "Frame Flow (pose)"}},
        "4": {"class_type": "OpenAIGPTImage1",
              "inputs": {"prompt": prompt, "seed": seed, "quality": cfg["qualite"],
                         "background": "opaque", "size": cfg["taille"],
                         "n": int(cfg["variantes_ancre"]), "image": ["1", 0], "model": cfg["modele"]},
              "_meta": {"title": "GPT Image — propositions d'ancre"}},
        "5": {"class_type": "SaveImage",
              "inputs": {"images": ["4", 0], "filename_prefix": f"{cfg['comfy_sous_dossier']}/ancre"},
              "_meta": {"title": "Enregistrer"}},
    }


# --------------------------------------------------------------------------- HTTP sans dépendance


def multipart(champs, fichiers):
    """champs: {nom: valeur} ; fichiers: [(nom_champ, chemin)] -> (corps, content_type)."""
    limite = uuid.uuid4().hex
    morceaux = []
    for nom, valeur in champs.items():
        morceaux += [f"--{limite}\r\n".encode(),
                     f'Content-Disposition: form-data; name="{nom}"\r\n\r\n'.encode(),
                     str(valeur).encode(), b"\r\n"]
    for nom, chemin in fichiers:
        chemin = Path(chemin)
        morceaux += [f"--{limite}\r\n".encode(),
                     f'Content-Disposition: form-data; name="{nom}"; filename="{chemin.name}"\r\n'.encode(),
                     b"Content-Type: image/png\r\n\r\n", chemin.read_bytes(), b"\r\n"]
    morceaux.append(f"--{limite}--\r\n".encode())
    return b"".join(morceaux), f"multipart/form-data; boundary={limite}"


def http(url, donnees=None, entetes=None, delai=600):
    req = urllib.request.Request(url, data=donnees, headers=entetes or {})
    try:
        with urllib.request.urlopen(req, timeout=delai) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raw_error = e.read()
        corps = raw_error.decode("utf-8", "replace")[:3000]
        error = RuntimeError(f"HTTP {e.code} sur {url}\n{corps}")
        error.http_status = e.code
        error.corps_http = raw_error
        raise error from None
    except TimeoutError:
        error = RuntimeError(f"délai réseau dépassé sur {url} ; issue de l'appel inconnue, aucune relance automatique")
        error.issue_inconnue = True
        raise error from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"impossible de joindre {url} ({e.reason})") from None


# --------------------------------------------------------------------------- moteur ComfyUI


class Comfy:
    def __init__(self, cfg):
        self.cfg = cfg
        self.url = cfg["comfy_url"].rstrip("/")
        self.cle = os.environ.get("COMFY_API_KEY", "")
        self.last_pid = None
        self.on_accepted = None
        if not self.cle:
            sys.exit("[erreur] variable COMFY_API_KEY absente (clé de compte ComfyUI, "
                     "pas une clé OpenAI). Voir LISEZMOI.md.")
        try:
            http(f"{self.url}/system_stats", delai=10)
        except RuntimeError as e:
            sys.exit(f"[erreur] ComfyUI ne répond pas sur {self.url} : {e}\n"
                     f"Lance ComfyUI (application ou `comfy launch`) puis recommence.")

    def televerser(self, chemin, nom):
        """Envoie une image dans input/<sous_dossier>/<nom> de ComfyUI et renvoie la valeur pour LoadImage."""
        with tempfile.TemporaryDirectory() as t:
            copie = Path(t) / nom  # ComfyUI range le fichier sous le nom du fichier envoyé
            shutil.copyfile(chemin, copie)
            corps, ct = multipart({"subfolder": self.cfg["comfy_sous_dossier"], "type": "input",
                                   "overwrite": "true"}, [("image", copie)])
            rep = json.loads(http(f"{self.url}/upload/image", corps, {"Content-Type": ct}))
        return f"{rep['subfolder']}/{rep['name']}" if rep.get("subfolder") else rep["name"]

    def executer(self, workflow):
        self.last_pid = None
        corps = json.dumps({"prompt": workflow, "client_id": uuid.uuid4().hex,
                            "extra_data": {"api_key_comfy_org": self.cle}}).encode()
        rep = json.loads(http(f"{self.url}/prompt", corps, {"Content-Type": "application/json"}))
        if rep.get("node_errors"):
            raise RuntimeError(f"workflow refusé par ComfyUI : {json.dumps(rep['node_errors'], ensure_ascii=False)}")
        pid = rep["prompt_id"]
        self.last_pid = pid
        if self.on_accepted:
            self.on_accepted(pid)
        return self.attendre(pid)

    def attendre(self, pid):
        """Lit une tâche existante. Ne soumet aucun workflow payant."""
        self.last_pid = pid
        debut = time.time()
        while True:
            hist = json.loads(http(f"{self.url}/history/{pid}", delai=30))
            if pid in hist:
                break
            if time.time() - debut > 900:
                raise RuntimeError(f"délai dépassé (15 min), tâche conservée : {pid}. Utiliser --reprendre {pid}")
            time.sleep(2)
        h = hist[pid]
        statut = h.get("status", {})
        if statut.get("status_str") == "error":
            msgs = [m for m in statut.get("messages", []) if m and m[0] == "execution_error"]
            detail = msgs[-1][1].get("exception_message", "") if msgs else json.dumps(statut)[:1500]
            error = RuntimeError(f"erreur d'exécution dans ComfyUI : {detail}")
            error.terminee = True
            raise error
        images = []
        for sortie in h.get("outputs", {}).values():
            for im in sortie.get("images", []):
                q = urllib.parse.urlencode({"filename": im["filename"], "subfolder": im.get("subfolder", ""),
                                            "type": im.get("type", "output")})
                images.append(http(f"{self.url}/view?{q}"))
        if not images:
            raise RuntimeError("ComfyUI n'a renvoyé aucune image")
        return pid, images

    def redessiner(self, src, ancre, prompt, seed):
        s = self.televerser(src, f"src_{Path(src).name}")
        a = self.televerser(ancre, "ancre_style.png")
        return self.executer(workflow_redessin(s, a, prompt, self.cfg, seed))

    def propositions_ancre(self, src, prompt, seed):
        s = self.televerser(src, f"src_{Path(src).name}")
        return self.executer(workflow_ancre(s, prompt, self.cfg, seed))


# --------------------------------------------------------------------------- moteur OpenAI direct


class OpenAIDirect:
    def __init__(self, cfg):
        self.cfg = cfg
        self.URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/images/edits"
        self.cle = os.environ.get("OPENAI_API_KEY", "")
        if not self.cle:
            sys.exit("[erreur] variable OPENAI_API_KEY absente. Voir LISEZMOI.md.")

    def _appel(self, images, prompt, n):
        champ = "image" if len(images) == 1 else "image[]"
        corps, ct = multipart({"model": self.cfg["modele"], "prompt": prompt, "n": n,
                               "size": self.cfg["taille"], "quality": self.cfg["qualite"]},
                              [(champ, p) for p in images])
        rep = json.loads(http(self.URL, corps, {"Content-Type": ct, "Authorization": f"Bearer {self.cle}"}))
        sorties = []
        for d in rep.get("data", []):
            if d.get("b64_json"):
                sorties.append(base64.b64decode(d["b64_json"]))
            elif d.get("url"):
                sorties.append(http(d["url"]))
        if not sorties:
            raise RuntimeError(f"réponse OpenAI sans image : {json.dumps(rep)[:1500]}")
        return rep.get("created", ""), sorties

    def redessiner(self, src, ancre, prompt, seed):
        return self._appel([src, ancre], prompt, 1)

    def propositions_ancre(self, src, prompt, seed):
        return self._appel([src], prompt, int(self.cfg["variantes_ancre"]))


# --------------------------------------------------------------------------- programme


def creer_moteur(cfg, dossier):
    if cfg['backend'] == 'gemini':
        from gemini_direct import GeminiDirect
        return GeminiDirect(cfg, dossier, http)
    if cfg['backend'] == 'comfy':
        return Comfy(cfg)
    if cfg['backend'] == 'openai':
        return OpenAIDirect(cfg)
    raise SystemExit('[erreur] backend inconnu')


def confirmer(n, cfg, oui):
    cout = n * cfg["cout_estime_usd_par_image"]
    print(f"→ {n} image(s) à générer avec {cfg['modele']} ({cfg['qualite']}, {cfg['taille']}) via {cfg['backend']} — "
          f"coût estimé ≈ {cout:.2f} $ (ordre de grandeur, voir LISEZMOI.md)")
    if "cout_estime_usd_min_par_image" in cfg:
        print(f"  Plage affichée par Comfy pour ce workflow : "
              f"≈ {n * cfg['cout_estime_usd_min_par_image']:.3f} – "
              f"{n * cfg['cout_estime_usd_max_par_image']:.3f} $ ; débit réel non garanti.")
    if not oui and input("Continuer ? [o/N] ").strip().lower() not in ("o", "oui", "y", "yes"):
        sys.exit("Annulé.")


def exporter_workflows(cfg):
    dossier = RACINE / "workflows"
    dossier.mkdir(exist_ok=True)
    sd = cfg["comfy_sous_dossier"]
    (dossier / "redessin_kirigami_couture_api.json").write_text(json.dumps(
        workflow_redessin(f"{sd}/src_s0001.png", f"{sd}/ancre_style.png", lire_texte(cfg["prompt"]), cfg, 1),
        indent=2, ensure_ascii=False), encoding="utf-8")
    (dossier / "ancre_kirigami_couture_api.json").write_text(json.dumps(
        workflow_ancre(f"{sd}/src_s0001.png", lire_texte(cfg["prompt_ancre"]), cfg, 1),
        indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[ok] workflows écrits dans {dossier.relative_to(RACINE)}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", default="test")
    p.add_argument("--config", help="configuration JSON alternative, relative au projet")
    p.add_argument("--backend", choices=["comfy", "openai", "gemini"])
    p.add_argument("--ancre", action="store_true", help="génère des propositions d'image de référence")
    p.add_argument("--frame", type=int, default=1, help="frame utilisée pour --ancre (index dans src)")
    p.add_argument("--choisir", type=int, help="copie la proposition n° N vers refs/ancre_style.png")
    p.add_argument("--refaire", help="indices à refaire, ex. 5,9")
    p.add_argument("--indices", help="limite les frames manquantes à ces indices, sans refaire les sorties existantes")
    p.add_argument("--reprendre", metavar="PROMPT_ID", help="récupère une tâche Comfy existante, sans nouvel appel")
    p.add_argument("--simulation", action="store_true", help="affiche la sélection et son estimation sans contacter une API")
    p.add_argument("--limite", type=int, help="ne traite que N frames manquantes")
    p.add_argument("--oui", action="store_true", help="ne demande pas de confirmation")
    p.add_argument("--exporter-workflows", action="store_true")
    a = p.parse_args()

    cfg = charger_config(a.config)
    if a.backend:
        cfg["backend"] = a.backend
    if a.exporter_workflows:
        return exporter_workflows(cfg)

    d = dossiers(a.plan)
    ancre_finale = RACINE / cfg["ancre"]

    # --- choix d'une proposition d'ancre
    if a.choisir:
        cand = d["ancre"] / f"proposition_{a.choisir:02d}.png"
        if not cand.exists():
            sys.exit(f"[erreur] {cand.relative_to(RACINE)} n'existe pas")
        ancre_finale.parent.mkdir(parents=True, exist_ok=True)
        if ancre_finale.exists():
            archive = ancre_finale.with_name(f"ancre_style_{time.strftime('%Y%m%d-%H%M%S')}.png")
            ancre_finale.rename(archive)
            print(f"[info] ancienne ancre archivée : {archive.relative_to(RACINE)}")
        shutil.copyfile(cand, ancre_finale)
        return print(f"[ok] {cand.name} → {cfg['ancre']}")

    sources = sorted(d["src"].glob("s*.png"))
    if not sources:
        sys.exit(f"[erreur] aucune frame dans {d['src'].relative_to(RACINE)} — lance d'abord 01_extraire.py")

    base_journal = {"plan": a.plan, "backend": cfg["backend"], "modele": cfg["modele"],
                    "qualite": cfg["qualite"], "taille": cfg["taille"]}
    base_journal["config_sha256"] = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()
    base_journal["cout_estime_usd_par_image"] = cfg["cout_estime_usd_par_image"]
    base_journal.update({"config_fichier": a.config or "config.json",
        "workflow_fichier": cfg.get("workflow_redessin"),
        "ancre_sha256": hashlib.sha256(ancre_finale.read_bytes()).hexdigest() if ancre_finale.exists() else None,
        "prompt_sha256": hashlib.sha256(lire_texte(cfg["prompt"]).encode()).hexdigest()})
    if cfg['backend'] == 'gemini' and cfg.get('gemini_references_supplementaires'):
        from gemini_direct import references_supplementaires
        base_journal['references_supplementaires'] = references_supplementaires(cfg)
    if cfg['backend'] == 'gemini' and cfg.get('gemini_historique'):
        from gemini_direct import historique_verifie
        base_journal['historique_gemini'] = historique_verifie(cfg)[2]
    historique = [json.loads(line) for line in d["journal"].read_text().splitlines() if line.strip()] if d["journal"].exists() else []
    acceptes = {e["reference_appel"]: e for e in historique if e.get("type") in ("soumission_comfy", "soumission_gemini")}
    termines = {e.get("reference_appel") for e in historique if e.get("statut") in ("ok", "echec_termine")}
    if a.reprendre:
        if cfg["backend"] not in ("comfy", "gemini") or a.reprendre not in acceptes:
            sys.exit("[erreur] tâche inconnue dans le journal de ce plan, ou backend incompatible")
        entry = acceptes[a.reprendre]
        if entry.get("config_sha256") != base_journal["config_sha256"]:
            sys.exit("[erreur] configuration différente de la soumission : utiliser sa configuration d'origine")
        if entry.get('references_supplementaires', []) != base_journal.get('references_supplementaires', []):
            sys.exit('[erreur] référence supplémentaire modifiée depuis la soumission')
        if entry.get('historique_gemini') != base_journal.get('historique_gemini'):
            sys.exit('[erreur] historique modifié depuis la soumission')
        src = d["src"] / entry["source"]
        if hashlib.sha256(src.read_bytes()).hexdigest() != entry["source_sha256"]:
            sys.exit("[erreur] source modifiée depuis la soumission")
        print(f"→ Récupération de {a.reprendre} — 0 nouvel appel payant")
        moteur = creer_moteur(cfg, d['base'])
        try:
            ref, images = moteur.attendre(a.reprendre)
        except RuntimeError as e:
            if getattr(e, "terminee", False):
                journaliser(d["journal"], {**entry, "type": "fin_" + cfg['backend'], "statut": "echec_termine"})
            sys.exit(f"[arrêt] {e}; aucun nouvel appel soumis")
        destinations = [d["ancre"] / f"proposition_{i:02d}.png" for i in range(1, len(images)+1)] if entry.get("operation") == "ancre" else [d["out"] / entry["sortie"]]
        if len(destinations) != len(images):
            sys.exit("[erreur] nombre d'images inattendu : aucun fichier remplacé")
        for dest, data in zip(destinations, images):
            if dest.exists() and dest.read_bytes() != data:
                arch = dest.parent / "_anciennes"
                arch.mkdir(exist_ok=True)
                shutil.copy2(dest, arch / f"{dest.stem}_{time.time_ns()}.png")
            dest.write_bytes(data)
        journaliser(d["journal"], {**entry, "type": "recuperation", "statut": "ok", "nouvel_appel": False,
                                   **getattr(moteur, 'metadata', {})})
        return print("[ok] résultat existant récupéré")
    if a.config:
        base_journal.update({"config_fichier": a.config,
                            "workflow_fichier": cfg.get("workflow_redessin"),
                            "ancre_sha256": hashlib.sha256(ancre_finale.read_bytes()).hexdigest()
                            if ancre_finale.exists() else None,
                            "prompt_sha256": hashlib.sha256(lire_texte(cfg["prompt"]).encode()).hexdigest()})

    # --- propositions d'ancre
    if a.ancre:
        if a.simulation:
            return confirmer(int(cfg["variantes_ancre"]), cfg, True)
        if any(pid not in termines and e.get("operation") == "ancre" for pid, e in acceptes.items()):
            sys.exit("[arrêt] ancre soumise non résolue : utiliser --reprendre")
        if cfg['backend'] == 'gemini':
            sys.exit('[arrêt] Ancres Gemini non prises en charge; utiliser l’ancre approuvée. Aucun appel envoyé.')
        moteur = creer_moteur(cfg, d['base'])
        src = d["src"] / f"s{a.frame:04d}.png"
        confirmer(int(cfg["variantes_ancre"]), cfg, a.oui)
        prompt = lire_texte(cfg["prompt_ancre"])
        seed = random.randint(1, 2**31 - 1)
        t0 = time.time()
        if isinstance(moteur, Comfy):
            moteur.on_accepted = lambda pid: journaliser(d["journal"], {**base_journal,
                "type": "soumission_comfy", "operation": "ancre", "source": src.name,
                "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
                "reference_appel": pid, "seed": seed, "statut": "accepte"})
        ref, images = moteur.propositions_ancre(src, prompt, seed)
        for f in d["ancre"].glob("proposition_*.png"):
            f.unlink()
        for i, im in enumerate(images, 1):
            (d["ancre"] / f"proposition_{i:02d}.png").write_bytes(im)
        journaliser(d["journal"], {**base_journal, "type": "ancre", "source": src.name, "seed": seed,
                                   "reference_appel": ref, "images": len(images),
                                   "secondes": round(time.time() - t0, 1), "prompt": prompt})
        return print(f"[ok] {len(images)} propositions dans {d['ancre'].relative_to(RACINE)} — "
                     f"choisis-en une avec --choisir N")

    # --- redessin des frames
    if not ancre_finale.exists():
        sys.exit(f"[erreur] pas d'image de référence ({cfg['ancre']}). Lance --ancre puis --choisir N, "
                 f"ou dépose ta propre image kirigami couture à cet emplacement.")
    prompt = lire_texte(cfg["prompt"])

    if a.refaire:
        indices = [int(x) for x in a.refaire.split(",") if x.strip()]
        a_faire = [d["src"] / f"s{i:04d}.png" for i in indices]
        manquantes = [s for s in a_faire if not s.exists()]
        if manquantes:
            sys.exit(f"[erreur] frames inexistantes : {', '.join(m.name for m in manquantes)}")
    else:
        a_faire = [s for s in sources if not (d["out"] / s.name.replace("s", "r", 1)).exists()]
    if a.indices:
        indices = {int(x) for x in a.indices.split(",")}
        a_faire = [s for s in a_faire if int(s.stem[1:]) in indices]
    if a.limite:
        a_faire = a_faire[: a.limite]
    if not a_faire:
        return print("[ok] rien à faire : toutes les frames de ce plan sont déjà redessinées")

    if a.simulation:
        print("Sources : " + ", ".join(s.name for s in a_faire))
        return confirmer(len(a_faire), cfg, True)
    unresolved = [e for pid, e in acceptes.items() if pid not in termines and e["source"] in {s.name for s in a_faire}]
    if unresolved:
        sys.exit("[arrêt] tâche déjà soumise, aucun doublon créé. Utiliser --reprendre " + unresolved[0]["reference_appel"])
    confirmer(len(a_faire), cfg, a.oui)
    moteur = creer_moteur(cfg, d['base'])
    erreurs = 0
    for k, src in enumerate(a_faire, 1):
        dest = d["out"] / src.name.replace("s", "r", 1)
        issue_appel = None
        seed = random.randint(1, 2**31 - 1)  # change aussi la clé de cache de ComfyUI
        t0 = time.time()
        if cfg['backend'] in ('comfy', 'gemini'):
            moteur.last_pid = None
            moteur.on_accepted = lambda pid: journaliser(d["journal"], {**base_journal,
                "type": "soumission_" + cfg['backend'], "operation": "frame", "source": src.name,
                "sortie": dest.name, "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
                "seed": seed, "reference_appel": pid,
                "statut": "emission" if cfg['backend'] == 'gemini' else "accepte"})
        try:
            ref, images = moteur.redessiner(src, ancre_finale, prompt, seed)
            if dest.exists():  # --refaire réussi : l'ancienne version est gardée pour comparer
                arch = d["out"] / "_anciennes"
                arch.mkdir(exist_ok=True)
                dest.rename(arch / f"{dest.stem}_{time.strftime('%Y%m%d-%H%M%S')}.png")
            dest.write_bytes(images[0])
            statut, msg = "ok", ""
        except RuntimeError as e:
            statut, msg = "erreur", str(e)
            if getattr(e, "issue_inconnue", False):
                issue_appel = "inconnue"
            erreurs += 1
            ref = getattr(moteur, "last_pid", None) or ""
            if getattr(e, "terminee", False):
                journaliser(d["journal"], {**base_journal, "type": "fin_" + cfg['backend'], "reference_appel": ref,
                                          "statut": "echec_termine"})
        duree = round(time.time() - t0, 1)
        journaliser(d["journal"], {**base_journal, "type": "frame", "source": src.name,
                                   **({"source_sha256": hashlib.sha256(src.read_bytes()).hexdigest()}
                                      if a.config else {}),
                                   "sortie": dest.name if statut == "ok" else None, "seed": seed,
                                   "reference_appel": ref, "statut": statut, "message": msg[:500],
                                   **({"issue_appel": issue_appel} if issue_appel else {}),
                                   "secondes": duree, "ancre": cfg["ancre"], "prompt_fichier": cfg["prompt"],
                                   **getattr(moteur, 'metadata', {})})
        print(f"[{k}/{len(a_faire)}] {src.name} → {dest.name if statut == 'ok' else 'ÉCHEC'} ({duree} s)"
              + (f"\n    {msg[:300]}" if msg else ""))
        if statut == "erreur":
            sys.exit("[arrêt] premier échec : aucun autre appel lancé.")
        if erreurs >= 3 and erreurs == k:
            sys.exit("[arrêt] 3 échecs d'affilée dès le début : vérifie la clé, les crédits ou le workflow.")
    print(f"[fin] {len(a_faire) - erreurs} réussie(s), {erreurs} échec(s). Journal : "
          f"{d['journal'].relative_to(RACINE)}")


if __name__ == "__main__":
    main()
