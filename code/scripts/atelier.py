"""Outils locaux du pilote : aucun appel API, aucun modèle installé."""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps, ImageFilter
from normalisation import normaliser

TAILLE = (720, 1280)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def masque(polygones, taille=TAILLE):
    im = Image.new('L', taille)
    d = ImageDraw.Draw(im)
    for poly in polygones:
        d.polygon([tuple(p) for p in poly], fill=255)
    return im


def masques_elements(annotation, taille=TAILLE):
    """Les éléments devant la robe ont priorité. Les zones restent manuelles."""
    masks = {k: masque(v, taille) for k, v in annotation['elements'].items()}
    robe = np.array(masks['robe'])
    for name in ('tete', 'bras_mains', 'jambes_chaussures'):
        robe[np.array(masks[name]) > 0] = 0
    masks['robe'] = Image.fromarray(robe)
    return masks


def propager(image, source, cible, triangles, taille=TAILLE):
    """Affine par triangle, échantillonnage inverse; rejette les plis du maillage."""
    out = Image.new('RGB', taille, (0, 255, 0))
    coverage = Image.new('L', taille)
    for ids in triangles:
        s = np.asarray([source[k] for k in ids], dtype=float)
        t = np.asarray([cible[k] for k in ids], dtype=float)
        sm = np.column_stack((s, np.ones(3)))
        tm = np.column_stack((t, np.ones(3)))
        ds, dt = np.linalg.det(sm), np.linalg.det(tm)
        if abs(ds) < 1 or abs(dt) < 1 or ds * dt <= 0:
            raise ValueError(f'Triangle dégénéré ou inversé : {ids}')
        # [x_cible,y_cible,1] @ coefficients = [x_source,y_source]
        coeff = np.round(np.linalg.solve(tm, s), 12)
        affine = tuple(coeff[:, 0]) + tuple(coeff[:, 1])
        warped = image.transform(taille, Image.Transform.AFFINE, affine,
                                 resample=Image.Resampling.BICUBIC, fillcolor=(0,255,0))
        m = masque([t.tolist()], taille)
        out.paste(warped, (0,0), m)
        coverage.paste(255, (0,0), m)
    return out, coverage


def composer_robe(temoin, propagation, autorise, couverture):
    # Pas de raccord en dehors du masque autorisé. Les trous restent explicitement Nano.
    a, c = np.array(autorise) > 0, np.array(couverture) > 0
    active = a & c
    result = Image.composite(propagation, temoin, Image.fromarray(active.astype('uint8')*255))
    assert np.array_equal(np.array(result)[~a], np.array(temoin)[~a])
    return result, {'pixels_autorises': int(a.sum()), 'pixels_propages': int(active.sum()),
                    'pixels_repli_nano': int((a & ~c).sum()), 'differences_hors_robe': 0}


def mesurer(series, domaines, mouvements, triangles):
    """Même domaine ET même transformation pour chaque variante. Aucun score global."""
    names = list(series)
    if not names or len({len(v) for v in series.values()}) != 1:
        raise ValueError('Séries absentes ou longueurs différentes')
    n = len(series[names[0]])
    if len(domaines) != n or len(mouvements) != n:
        raise ValueError('Un domaine et un maillage sont requis par pose')
    rows = []
    for i in range(n-1):
        taille = domaines[i+1].size
        wmask, covered = propager(domaines[i].convert('RGB'), mouvements[i], mouvements[i+1], triangles, taille)
        common = ((np.array(wmask)[...,0] > 250) & (np.array(domaines[i+1]) > 250)
                  & (np.array(covered) > 0))
        count = int(common.sum())
        row = {'paire': [i,i+1], 'pixels_communs': count,
               'couverture_cible': count/max(1,int((np.array(domaines[i+1])>250).sum())),
               'variantes': {}}
        for name, images in series.items():
            warped, _ = propager(images[i], mouvements[i], mouvements[i+1], triangles, taille)
            a = np.asarray(warped,dtype=float); b = np.asarray(images[i+1],dtype=float)
            # Contraste local en luminance; dénominateur et domaine identiques.
            lum = np.array(images[i+1].convert('L'),dtype=float)
            low = np.array(images[i+1].convert('L').filter(ImageFilter.GaussianBlur(2)),dtype=float)
            row['variantes'][name] = {
                'residu_rgb_moyen': float(np.abs(a-b)[common].mean()) if count else None,
                'detail_local_moyen': float(np.abs(lum-low)[common].mean()) if count else None}
        rows.append((row, Image.fromarray(common.astype('uint8')*255)))
    return rows


def geometrie(points_flow, points_dessin, points_ajustement):
    """Réservé aux points tenus à l'écart du réglage du maillage."""
    if set(points_flow) & set(points_ajustement):
        raise ValueError('Les points de contrôle doivent être indépendants du maillage')
    if set(points_flow) != set(points_dessin):
        raise ValueError('Repères de contrôle non correspondants')
    return {k: {'dx': float(points_dessin[k][0]-v[0]),
                'dy': float(points_dessin[k][1]-v[1]),
                'distance_px': float(np.linalg.norm(np.array(points_dessin[k])-v))}
            for k,v in points_flow.items()}
