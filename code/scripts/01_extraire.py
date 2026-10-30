"""Étape 1 — extrait une frame sur `pas` de la vidéo Flow (les seules à redessiner).

Usage :
    python scripts/01_extraire.py --plan test       # 2 s par défaut, soit 16 frames en 3
    python scripts/01_extraire.py --plan complet    # toute la vidéo
"""
import argparse
import json
import sys

from commun import RACINE, charger_config, dossiers, lancer, verifier_ffmpeg


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", default="test", help="nom d'un plan défini dans config.json")
    a = p.parse_args()

    verifier_ffmpeg()
    cfg = charger_config()
    if a.plan not in cfg["plans"]:
        sys.exit(f"[erreur] plan inconnu : {a.plan} (voir config.json)")
    plan = cfg["plans"][a.plan]
    d = dossiers(a.plan)
    video = RACINE / cfg["video"]
    if not video.exists():
        sys.exit(f"[erreur] vidéo introuvable : {video}")

    fps, pas = cfg["fps"], cfg["pas"]
    debut = float(plan["debut_s"] or 0)
    duree = plan["duree_s"]

    # Nettoie les anciennes extractions de ce plan (les redessins dans out/ sont conservés).
    for f in d["src"].glob("s*.png"):
        f.unlink()

    trim = f"trim=start={debut}" + (f":duration={duree}" if duree else "")
    filtre = f"{trim},setpts=PTS-STARTPTS,select='not(mod(n\\,{pas}))'"
    lancer(["ffmpeg", "-v", "error", "-i", str(video), "-vf", filtre,
            "-fps_mode", "passthrough", "-start_number", "1", str(d["src"] / "s%04d.png"), "-y"])

    fichiers = sorted(d["src"].glob("s*.png"))
    premiere = round(debut * fps)
    manifeste = {
        "video": cfg["video"], "fps": fps, "pas": pas,
        "debut_s": debut, "duree_s": duree,
        "frames": [{"index": i + 1, "fichier": f.name, "frame_source": premiere + i * pas}
                   for i, f in enumerate(fichiers)],
    }
    d["manifeste"].write_text(json.dumps(manifeste, indent=2, ensure_ascii=False), encoding="utf-8")
    n = len(fichiers)
    print(f"[ok] {n} frames extraites dans {d['src'].relative_to(RACINE)} "
          f"(une sur {pas}) — environ {n * cfg['cout_estime_usd_par_image']:.2f} $ à redessiner")


if __name__ == "__main__":
    main()
