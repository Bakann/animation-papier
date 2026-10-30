"""Essai gratuit : grain fin de 9, indications d'ombre de Flow, hors masque inchangé."""
import argparse
import hashlib
import json
import runpy
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from commun import RACINE, journaliser
from normalisation import normaliser


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def blur_float(values, radius):
    # Pillow ne floute pas les images F avec GaussianBlur : encoder les valeurs
    # [0,255] en L ici est suffisant pour cet essai de luminance.
    return np.asarray(Image.fromarray(np.uint8(np.clip(np.rint(values), 0, 255)))
                      .filter(ImageFilter.GaussianBlur(radius)), dtype=float)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', default='v1')
    args = parser.parse_args()
    if not args.version.isalnum():
        parser.error('Version alphanumérique attendue')
    root = RACINE / f'travail/relief_doux_local_{args.version}'
    if root.exists():
        raise SystemExit('Essai existant : choisir une autre version pour le conserver')
    for name in ('entrees', 'masques', 'diagnostics', 'out'):
        (root / name).mkdir(parents=True, exist_ok=True)
    paths = {'flow': RACINE/'travail/pilote_ab_a_1/src/s0006.png',
             'a1': RACINE/'travail/pilote_ab_a_1/out/r0006.png',
             'grain9': RACINE/'travail/test_nano_matiere9/ancre/extraits/01_grain_rouge.png'}
    flow = normaliser(Image.open(paths['flow']))
    a1 = normaliser(Image.open(paths['a1']))
    flow.save(root/'entrees/flow_720.png')
    a1.save(root/'entrees/a1_720.png')
    original = np.asarray(a1, dtype=float)
    source = np.asarray(flow, dtype=float)
    y, x = np.indices((1280, 720))
    sr, sg, sb = source.transpose(2, 0, 1)
    tr, tg, tb = original.transpose(2, 0, 1)
    source_red = (sr > 1.7*sg) & (sr > 1.7*sb) & (sr > 70)
    target_red = (tr > 1.7*tg) & (tr > 1.7*tb) & (tr > 70)
    source_ivory = (sr > 110) & (sg > 100) & (sb > 65) & (sr-sg < 28) & (sg-sb < 60)
    masks = {
        'rouge': source_red & target_red & (y > 325) & (y < 585) & (x > 270) & (x < 440),
        'ivoire_bas': source_ivory & (y > 595) & (y < 815) & (x > 280) & (x < 435),
    }
    # Les ombres foncées de Flow font partie du panneau : remplir uniquement
    # ses trous internes sur chaque ligne, sans étendre ses bords externes.
    ivory = masks['ivoire_bas'].copy()
    for yy in range(1280):
        xx = np.flatnonzero(ivory[yy])
        if len(xx) > 2:
            ivory[yy, xx[0]:xx[-1]+1] = True
    masks['ivoire_bas'] = ivory
    # Les bandes du témoin sont protégées, même aux petits écarts avec Flow.
    black = (original.max(2) < 105) & (np.ptp(original, axis=2) < 25)
    foreground = tg - np.maximum(tr, tb) <= 5
    foreground = np.asarray(Image.fromarray(foreground.astype('uint8')*255)
                             .filter(ImageFilter.MinFilter(11))) == 255
    for name, mask in masks.items():
        mask = mask & ~black & foreground
        masks[name] = np.asarray(Image.fromarray(mask.astype('uint8')*255)
                                 .filter(ImageFilter.MinFilter(3))) == 255
        Image.fromarray(masks[name].astype('uint8')*255).save(root/f'masques/{name}.png')

    # Prélèvement au centre de l'extrait existant : pas de silhouette ni de pli
    # entier. L'échelle correspond approximativement à la réduction 2K -> 720.
    crop_box = (40, 15, 140, 110)
    crop = Image.open(paths['grain9']).convert('L').crop(crop_box).resize((47, 45), Image.Resampling.LANCZOS)
    highpass = np.asarray(crop, dtype=float) - blur_float(np.asarray(crop), 2)
    highpass -= highpass.mean()
    highpass /= max(highpass.std(), .001)
    tile = np.concatenate([highpass, highpass[:, ::-1]], axis=1)
    tile = np.concatenate([tile, tile[::-1]], axis=0)
    grain = np.tile(tile, (15, 8))[:1280, :720]
    crop.save(root/'diagnostics/extrait_grain.png')
    Image.fromarray(np.uint8(np.clip(128+highpass*15, 0, 255))).save(root/'diagnostics/grain_separe_contraste_amplifie.png')
    panels = {}
    luminance = source @ np.array([.2126, .7152, .0722])
    allowed = np.zeros((1280, 720), dtype=bool)
    for name, mask in masks.items():
        assert mask.sum() > 1000, f'Domaine {name} insuffisant'
        hard = mask.astype('uint8')*255
        alpha = np.minimum(hard, blur_float(hard, 3)) / 255
        weight = blur_float(hard, 2) / 255
        mean = blur_float(luminance * mask, 2) / np.maximum(weight, .01)
        reference = np.percentile(mean[mask], 85)
        shade = np.clip(mean/max(reference, 1)-1, -.4, .1)
        # Palette du témoin dans les zones claires de Flow : pas de couleur de
        # peau ni de collage de l'image 9 dans le personnage.
        flat = mask & (mean >= np.percentile(mean[mask], 65))
        colour = np.median(original[flat], axis=0)
        panels[name] = {'mask': mask, 'alpha': alpha, 'shade': shade, 'colour': colour}
        allowed |= mask
        Image.fromarray(np.uint8(np.clip(128+shade*220, 0, 255))).save(root/f'diagnostics/ombre_flow_{name}.png')

    helper = runpy.run_path(str(RACINE/'travail/test/decor_geometrique_essai/incruster_fond_vert.py'))
    alpha_before, _ = helper['detourer'](a1)
    bg = Image.open(RACINE/'refs/decor_geometrique_v4/apercu_F001.png').convert('RGBA').resize((720, 1280), Image.Resampling.LANCZOS)
    variants = [('Flow', flow), ('A1', a1)]
    records = []
    for label, contrast, strength in [('Doux', .45, 1.8), ('Plus_marque', .75, 3.5)]:
        result = original.copy()
        for panel in panels.values():
            rendering = panel['colour'][None, None, :] * (1 + contrast*panel['shade'][..., None])
            rendering = np.clip(rendering + strength*grain[..., None], 0, 255)
            alpha = panel['alpha'][..., None]
            result = result*(1-alpha) + rendering*alpha
        image = Image.fromarray(np.uint8(np.clip(np.rint(result), 0, 255)))
        actual = np.asarray(image)
        assert np.array_equal(actual[~allowed], np.uint8(original)[~allowed]), 'Modification hors masque'
        assert np.array_equal(actual[:300], np.uint8(original)[:300]), 'Tête modifiée'
        assert np.array_equal(actual[880:], np.uint8(original)[880:]), 'Jambes modifiées'
        assert np.array_equal(actual[black], np.uint8(original)[black]), 'Bandes noires modifiées'
        layer, _ = helper['detourer'](image)
        assert np.array_equal(np.asarray(layer.getchannel('A')), np.asarray(alpha_before.getchannel('A'))), 'Alpha modifié'
        dest = root/f'out/{label}.png'
        image.save(dest)
        Image.alpha_composite(bg, layer).convert('RGB').save(root/f'out/{label}_geometrique.png')
        records.append({'variante': label, 'fichier': str(dest.relative_to(RACINE)), 'sha256': sha(dest),
                        'contraste_ombres_flow': contrast, 'amplitude_grain': strength,
                        'differences_hors_masque': 0, 'alpha_et_bandes_noires_preserves': True})
        variants.append((label.replace('_', ' '), image))
    full = Image.new('RGB', (1440, 690), 'white')
    detail = Image.new('RGB', (1440, 800), 'white')
    font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 22)
    for col, (label, im) in enumerate(variants):
        for board in (full, detail):
            ImageDraw.Draw(board).text((col*360+10, 12), label, font=font, fill='black')
        full.paste(im.resize((360, 640), Image.Resampling.LANCZOS), (col*360, 50))
        thumb = ImageOps.contain(im.crop((265, 320, 490, 820)), (350, 738), Image.Resampling.LANCZOS)
        detail.paste(thumb, (col*360+5, 52))
    full.save(RACINE/f'sortie/relief_doux_local_{args.version}_planche.png')
    detail.save(RACINE/f'sortie/relief_doux_local_{args.version}_details.png')
    report = {'type': 'essai_local_relief_doux', 'autorisation': 'l’auteur : rechercher un relief plus doux',
              'source_et_references': {name: {'fichier': str(p.relative_to(RACINE)), 'sha256': sha(p)} for name, p in paths.items()},
              'normalisation': 'Cadre entier à 720x1280, aucune transformation individuelle',
              'crop_grain_extrait_pixels': list(crop_box), 'filtre_passe_haut_rayon_720': 2,
              'panneaux': {name: {'pixels': int(p['mask'].sum()), 'couleur_mediane_A1': p['colour'].tolist()} for name, p in panels.items()},
              'variantes': records, 'appels_api': 0, 'cout_usd': 0,
              'statut': 'essai_statique_partiel_a_examiner',
              'limites': ['Rouge et grand ivoire seulement; autres zones restent A1',
                         'Le grain filtré ne garantit pas une séparation physique parfaite de la matière et de la lumière',
                         'Texture répétée par symétrie; coordonnées écran fixes, non validées en mouvement',
                         'Ombres Flow atténuées et légèrement adoucies; pas de nouveau calcul 3D du papier',
                         'Les assertions préservent le témoin normalisé, pas ses pixels natifs 2K']}
    (root/'controle.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    journaliser(root/'journal.jsonl', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
