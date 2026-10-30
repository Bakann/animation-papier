"""Planches des essais A/B de la pose 6, sans retouche ni appel API."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from commun import RACINE
from normalisation import normaliser


def empreinte(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def silhouette(image):
    rgb = np.array(image, dtype=int)
    mask = rgb[..., 1] - np.maximum(rgb[..., 0], rgb[..., 2]) < 30
    # Les guides blancs de la source sont dans les marges latérales.
    # Ce domaine fixe est identique pour tous; aucun recalage du personnage.
    mask[:, :150] = False
    mask[:, 600:] = False
    return mask


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventaire', help='JSON avec source et essais (label, fichier), pour inclure les reprises')
    args = parser.parse_args()
    dest = RACINE / 'travail/pilote_amelioration/ab_pose6_google'
    if args.inventaire:
        inventory = json.loads((RACINE / args.inventaire).read_text())
        source = RACINE / inventory['source']
        paths = [(entry['label'], RACINE / entry['fichier']) for entry in inventory['essais']]
    else:
        source = RACINE / 'travail/pilote_ab_a_1/src/s0006.png'
        paths = [(label, RACINE / f'travail/pilote_ab_{name}/out/r0006.png')
                 for label, name in [('A1', 'a_1'), ('A2', 'a_2'),
                                     ('B1', 'b_1'), ('B2', 'b_2')]]
    for _, path in paths:
        if not path.exists():
            raise SystemExit(f'Essai manquant : {path.relative_to(RACINE)}')
    images = [('Flow / cible', normaliser(Image.open(source)))]
    records = []
    original = silhouette(images[0][1])
    ys, xs = np.where(original)
    reference_bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
    for label, path in paths:
        with Image.open(path) as raw:
            dimensions = list(raw.size)
            image = normaliser(raw)
        images.append((label, image))
        mask = silhouette(image)
        ys, xs = np.where(mask)
        bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
        overlay = np.full((1280, 720, 3), 255, dtype=np.uint8)
        overlay[original & mask] = [70, 70, 70]
        overlay[original & ~mask] = [0, 170, 255]
        overlay[mask & ~original] = [255, 70, 120]
        Image.fromarray(overlay).save(dest / f'silhouette_{label}.png')
        records.append({'essai': label, 'fichier': str(path.relative_to(RACINE)),
                        'sha256': empreinte(path), 'taille_native': dimensions,
                        'boite_720': bbox,
                        'ecart_boite_vs_source': [b-a for a, b in zip(reference_bbox, bbox)],
                        'iou_silhouette_domaine_fixe': float((original & mask).sum() / (original | mask).sum())})
    font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 22)
    full = Image.new('RGB', (360*len(images), 690), 'white')
    details = Image.new('RGB', (360*len(images), 800), 'white')
    for col, (label, image) in enumerate(images):
        ImageDraw.Draw(full).text((col*360+12, 12), label, font=font, fill='black')
        full.paste(image.resize((360, 640), Image.Resampling.LANCZOS), (col*360, 50))
        ImageDraw.Draw(details).text((col*360+12, 12), label, font=font, fill='black')
        # Même crop dans le cadre commun; aucun ajustement individuel.
        crop = ImageOps.contain(image.crop((250, 275, 530, 865)), (350, 738), Image.Resampling.LANCZOS)
        details.paste(crop, (col*360+5, 52))
    full.save(RACINE / 'sortie/ab_plis_pose6_planche.png')
    details.save(RACINE / 'sortie/ab_plis_pose6_details.png')
    report = {'source': str(source.relative_to(RACINE)), 'source_sha256': empreinte(source),
              'source_boite_720': reference_bbox, 'essais': records,
              'limite': 'Boîtes et IoU sont des diagnostics de cadrage/silhouette, sans validation de pose, de plis ou de qualité artistique. Les reprises sont présentées sans sélection; aucun gain statistique établi sur ce petit échantillon.'}
    (dest / 'controle_cadrage.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
