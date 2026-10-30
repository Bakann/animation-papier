"""Fonctions partagées par les scripts du kit kirigami couture."""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def charger_config(chemin=None):
    with open(RACINE / (chemin or "config.json"), encoding="utf-8") as f:
        return json.load(f)


def dossiers(plan):
    """Dossiers de travail d'un plan (test ou complet)."""
    base = RACINE / "travail" / plan
    d = {
        "base": base,
        "src": base / "src",          # frames extraites de Flow (une sur `pas`)
        "out": base / "out",          # frames redessinées, même numéro que src
        "ancre": base / "ancre",      # candidates pour l'image de référence de style
        "journal": base / "journal.jsonl",
        "manifeste": base / "manifeste.json",
        "sortie": RACINE / "sortie",
    }
    for k in ("src", "out", "ancre", "sortie"):
        d[k].mkdir(parents=True, exist_ok=True)
    return d


def verifier_ffmpeg():
    for outil in ("ffmpeg", "ffprobe"):
        if shutil.which(outil) is None:
            sys.exit(f"[erreur] {outil} introuvable. Sur Mac : brew install ffmpeg")


def lancer(cmd):
    """Lance une commande et s'arrête proprement en cas d'erreur."""
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"[erreur] commande échouée :\n{' '.join(map(str, cmd))}\n{r.stderr[-2000:]}")
    return r.stdout


def journaliser(chemin, entree):
    entree = {"horodatage": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **entree}
    with open(chemin, "a", encoding="utf-8") as f:
        f.write(json.dumps(entree, ensure_ascii=False) + "\n")
        f.flush()
        import os
        os.fsync(f.fileno())


def lire_texte(chemin_relatif):
    return (RACINE / chemin_relatif).read_text(encoding="utf-8").strip()
