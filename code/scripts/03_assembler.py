"""Étape 3 — assemble les frames redessinées en vidéo « en 3 » (chaque image tenue `pas` frames).

Produit dans sortie/ :
  <plan>_kirigami_couture_en3.mp4   la vidéo finale (audio d'origine conservé)
  <plan>_comparatif.mp4          Flow en 3 | redessin, côte à côte
  <plan>_planche.png             toutes les frames redessinées en grille (lecture de gauche à droite)

Usage :
  python scripts/03_assembler.py --plan test
  python scripts/03_assembler.py --plan test --combler   # remplace les frames manquantes par la frame Flow
"""
import argparse
import json
import math
import sys
import tempfile
from pathlib import Path

from commun import RACINE, charger_config, dossiers, lancer, verifier_ffmpeg


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", default="test")
    p.add_argument("--config", help="configuration JSON alternative, relative au projet")
    p.add_argument("--combler", action="store_true")
    p.add_argument("--grain", type=float, help="intensité du grain (0 = aucun)")
    a = p.parse_args()

    verifier_ffmpeg()
    cfg = charger_config(a.config)
    d = dossiers(a.plan)
    if not d["manifeste"].exists():
        sys.exit("[erreur] pas de manifeste — lance d'abord 01_extraire.py")
    man = json.loads(d["manifeste"].read_text(encoding="utf-8"))
    fps, pas = cfg["fps"], cfg["pas"]
    W, H = cfg["sortie_largeur"], cfg["sortie_hauteur"]
    grain = cfg["grain"] if a.grain is None else a.grain

    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / "redessin").mkdir()
        (t / "flow").mkdir()
        manquantes = []
        provenance = []
        for i, f in enumerate(man["frames"], 1):
            src = d["src"] / f["fichier"]
            out = d["out"] / f["fichier"].replace("s", "r", 1)
            if not out.exists():
                manquantes.append(out.name)
                if not a.combler:
                    continue
                out = src
            import hashlib
            provenance.append({"source": f["fichier"], "frame_source": f.get("frame_source"),
                               "dessin": str(out.relative_to(RACINE)),
                               "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
                               "frames_sortie": [(i - 1) * pas, i * pas - 1]})
            # normalise chaque image à la taille de sortie (les redessins et Flow n'ont pas la même taille)
            if cfg.get("normalisation") == "pillow":
                from normalisation import normaliser
                from PIL import Image
                for path, subdir in ((out, "redessin"), (src, "flow")):
                    normaliser(Image.open(path), (W,H)).save(t/subdir/f"f{i:04d}.png")
            else:
                lancer(["ffmpeg", "-v", "error", "-i", str(out), "-vf",
                        f"scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,"
                        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2", str(t / "redessin" / f"f{i:04d}.png"), "-y"])
                lancer(["ffmpeg", "-v", "error", "-i", str(src), "-vf", f"scale={W}:{H}:flags=lanczos",
                        str(t / "flow" / f"f{i:04d}.png"), "-y"])
        if manquantes and not a.combler:
            sys.exit(f"[erreur] {len(manquantes)} frame(s) pas encore redessinée(s) : {', '.join(manquantes[:10])}"
                     f"{' …' if len(manquantes) > 10 else ''}\nRelance 02_redessiner.py, ou ajoute --combler.")

        n = len(man["frames"])
        cadence = f"{fps}/{pas}"
        total = str(n * pas)  # nombre exact de frames : chaque image tenue `pas` frames, la dernière comprise
        tenir = f"fps={fps},tpad=stop_mode=clone:stop={pas}"
        bruit = f",noise=alls={grain}:allf=t" if grain else ""
        audio = ["-ss", str(man["debut_s"])] + (["-t", str(man["duree_s"])] if man["duree_s"] else []) \
            + ["-i", str(RACINE / man["video"])]
        finale = d["sortie"] / f"{a.plan}_kirigami_couture_en{pas}.mp4"
        lancer(["ffmpeg", "-v", "error", "-framerate", cadence, "-start_number", "1",
                "-i", str(t / "redessin" / "f%04d.png"), *audio,
                "-filter_complex", f"[0:v]{tenir}{bruit},format=yuv420p[v]",
                "-map", "[v]", "-map", "1:a?", "-frames:v", total, "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "18", "-c:a", "aac", str(finale), "-y"])

        demi_w, demi_h = W // 2 // 2 * 2, H // 2 // 2 * 2
        comparatif = d["sortie"] / f"{a.plan}_comparatif.mp4"
        lancer(["ffmpeg", "-v", "error",
                "-framerate", cadence, "-start_number", "1", "-i", str(t / "flow" / "f%04d.png"),
                "-framerate", cadence, "-start_number", "1", "-i", str(t / "redessin" / "f%04d.png"),
                "-filter_complex",
                f"[0:v]scale={demi_w}:{demi_h}[a];[1:v]scale={demi_w}:{demi_h}[b];"
                f"[a][b]hstack=2,{tenir},format=yuv420p[v]",
                "-map", "[v]", "-frames:v", total, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                str(comparatif), "-y"])

        cols = min(8, n)
        rangs = math.ceil(n / cols)
        planche = d["sortie"] / f"{a.plan}_planche.png"
        lancer(["ffmpeg", "-v", "error", "-framerate", "1", "-start_number", "1",
                "-i", str(t / "redessin" / "f%04d.png"),
                "-vf", f"scale=180:-2,tile={cols}x{rangs}:padding=4:color=white",
                "-frames:v", "1", str(planche), "-y"])

    (d["sortie"] / f"{a.plan}_montage.json").write_text(json.dumps({
        "config_fichier": a.config or "config.json", "configuration_effective": cfg,
        "grain_effectif": grain, "fps": fps, "pas": pas, "nombre_frames": n * pas,
        "images": provenance,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    rel = lambda x: x.relative_to(RACINE)
    print(f"[ok] {n} images × {pas} frames à {fps} i/s"
          + (f" ({len(manquantes)} comblée(s) par Flow)" if manquantes else ""))
    print(f"     {rel(finale)}\n     {rel(comparatif)}\n     {rel(planche)}")


if __name__ == "__main__":
    main()
