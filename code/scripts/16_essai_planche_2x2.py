"""Préparation et découpe déterministes d'un essai 2x2; aucune API dans ce script."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from commun import RACINE, journaliser
from normalisation import normaliser


PROMPT = '''You receive two images.
IMAGE 1 is an exact 2 by 2 contact sheet containing FOUR consecutive Flow poses of the SAME character. Each cell has its own complete vertical canvas and original green margins. The four cells are equal and meet exactly at the horizontal and vertical midlines. They are NOT four characters standing together in one scene.
IMAGE 2 contains approved facial identity, corrected short dark paper hairstyle and matte paper material details ONLY. It does not determine pose, framing or panel geometry.

Redraw IMAGE 1 as ONE complete 2 by 2 contact sheet, preserving its exact layout and the distinct pose INSIDE EACH corresponding cell. Top-left = pose {p0}; top-right = pose {p1}; bottom-left = pose {p2}; bottom-right = pose {p3}. Preserve the source silhouette, head orientation, hand positions, limb overlaps, leg crossings, shoe angles, character scale and all four margins separately in each cell. No recentering, zoom, extending the legs, swapping cells, copying the pose from one cell into another, or adding a fifth figure. Keep every head and every visible shoe inside its own cell.

Use the SAME restrained kirigami couture paper treatment in all four cells: same matte paper stock, fine grain scale, palette, edge thickness, light direction, shadow softness and contrast. Follow the actual red, blue, yellow and ivory geometrique panel layout and fold indications of EACH source pose. Every divider and hem border must remain charcoal BLACK, distinct from the blue upper-right panel. Keep the coloured panels continuous and intact, with restrained paper folds; do not introduce pockets, cut-outs, tears or decorative flaps. Preserve black pumps with silver rectangular buckles, red fingernails and white earrings.

Match the approved face and short hairstyle while following each source head orientation. Cover the exposed scalp strip with overlapping dark blue-black paper strands; preserve the forehead and outer hair silhouette. No bald gap or glossy highlights. Never omit the face.

The entire background of all four cells must be the SAME perfectly uniform opaque chroma green #00FF00, including gaps between limbs. No scenery, floor, cast shadow on the green, text, labels, logos, calibration marks, panel borders, gutters or white separators. The only visible content is the four separately posed paper characters at their original coordinates inside their respective cells. Canvas: vertical 9:16, full contact sheet. Return ONE image with all four cells, not four separate files.
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preparer(name, indices, identite=None, matiere=None):
    if len(indices)!=4 or len(set(indices))!=4 or any(i<1 or i>16 for i in indices):
        raise SystemExit('Quatre indices distincts du test 1–16 sont requis')
    if bool(identite) != bool(matiere):
        raise SystemExit('Fournir ensemble --identite et --matiere, ou aucune des deux')
    for ref in (identite, matiere):
        if ref and not (RACINE/ref).is_file():
            raise SystemExit('Référence absente : '+ref)
    root=RACINE/'travail'/name
    if root.exists():raise SystemExit('Essai existant : examiner son journal avant nouvelle préparation')
    (root/'src').mkdir(parents=True)
    (root/'entrees').mkdir()
    grid=Image.new('RGB',(1440,2560),(0,255,0))
    cells=[]
    for n,i in enumerate(indices):
        source=RACINE/f'travail/test_nano_banana_pro/src/s{i:04}.png'
        image=normaliser(Image.open(source))
        a=np.asarray(image)
        margin=np.zeros((1280,720),dtype=bool);margin[:,:150]=True;margin[:,600:]=True
        rgb=a.astype(int);nongreen=rgb[...,1]-np.maximum(rgb[...,0],rgb[...,2])<30
        white=rgb.min(2)>180
        assert not (margin&nongreen&~white).any(),'Les marges contiennent autre chose que fond et guides'
        # Retirer les seuls repères des marges, sans toucher au personnage.
        clean=a.copy();clean[margin]=[0,255,0]
        assert np.array_equal(clean[~margin],a[~margin])
        image=Image.fromarray(clean)
        image.save(root/f'entrees/flow_{i}.png')
        left=(n%2)*720;top=(n//2)*1280
        grid.paste(image,(left,top))
        cells.append({'pose':i,'ordre':n,'source':str(source.relative_to(RACINE)),'source_sha256':sha(source),
                      'rectangle_grille_entree':[left,top,left+720,top+1280],
                      'frame_source':(i-1)*3})
    grid.save(root/'src/s0001.png')
    prompt=PROMPT.format(p0=indices[0],p1=indices[1],p2=indices[2],p3=indices[3])
    if identite:
        prompt=prompt.replace('You receive two images.', 'You receive three ordered images.')
        prompt=prompt.replace('IMAGE 2 contains approved facial identity, corrected short dark paper hairstyle and matte paper material details ONLY. It does not determine pose, framing or panel geometry.',
            'IMAGE 2 is the approved FACE AND HAIR reference ONLY. Use it for identity and the corrected short dark hairstyle, never for body pose, head angle, framing or dress material.\n'
            'IMAGE 3 contains cropped PAPER MATERIAL DETAILS from the approved image 9, without its silhouette. Use it as the authority for fine grain, matte paper stock, shallow curvature, edge thickness, light direction and shadow softness. These are samples, not extra objects or costume patches. Do not copy their fold geometry: IMAGE 1 alone determines the location and direction of each pose\'s main folds. Never reproduce samples, grey rectangles or black swatches outside the characters.\n'
            'Reference priority: IMAGE 1 owns every pose, scale, occlusion, panel layout and colour; IMAGE 2 owns identity; IMAGE 3 owns paper appearance. Apply the SAME material interpretation to every cell. Preserve credible paper volume instead of replacing curved paper shadows with flat cel-shaded shapes. Keep relief shallow; no added decorative creases or cut flaps.')
    (root/'prompt.txt').write_text(prompt)
    cfg=json.loads((RACINE/'configs/pilote_ab_a_1.json').read_text())
    cfg.update({'backend':'gemini','prompt':str((root/'prompt.txt').relative_to(RACINE)),
                'gemini_aspect_ratio':'9:16','grain':0})
    if identite:
        cfg.update({'ancre':identite, 'gemini_references_supplementaires':[matiere]})
    cfg.pop('workflow_redessin',None)
    (root/'config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n')
    (root/'manifeste.json').write_text(json.dumps({'type':'planche_2x2_experimentale',
        'video':'entree/source_animation.mp4','fps':24,'pas':3,'debut_s':(indices[0]-1)/8,'duree_s':.5,
        'frames':[{'index':1,'fichier':'s0001.png','poses_logiques':indices}]},ensure_ascii=False,indent=2)+'\n')
    protocol={'type':'preparation_planche_2x2','autorisation':'l’auteur : lance, après revue du 30 octobre',
              'ordre':indices,'cellules':cells,'dimensions_entree':[1440,2560],
              'ancre':cfg['ancre'],'ancre_sha256':sha(RACINE/cfg['ancre']),
              'grille_sha256':sha(root/'src/s0001.png'),'prompt_sha256':sha(root/'prompt.txt'),
              'modification_source':'Repères retirés uniquement dans les marges x<150 ou x>=600, cadre entier normalisé720x1280 conservé',
              'appels_preparation':0,'appels_payants_prevus':1,'estimation_usd':cfg['cout_estime_usd_par_image'],
              'limites':'Grille géométrique demandée, pas garantie par le modèle. Sortie unique pour quatre poses logiques; découpe seulement après inspection du brut.'}
    if identite:
        protocol.update({'variante':'identite_et_matiere_separees',
            'references_ordonnees':[{'role':'grille_Flow','fichier':str((root/'src/s0001.png').relative_to(RACINE)),'sha256':sha(root/'src/s0001.png')},
                {'role':'identite_visage_cheveux','fichier':identite,'sha256':sha(RACINE/identite)},
                {'role':'matiere_sans_silhouette_image9','fichier':matiere,'sha256':sha(RACINE/matiere)}],
            'limite_comparaison':'Références séparées, matière et description adaptées ensemble; graines non contrôlées. Essai qualitatif, pas isolation causale du seul nombre de références.'})
    (root/'protocole.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n');journaliser(root/'journal.jsonl',protocol)
    shutil.copyfile(__file__,root/'recette_preparation.py')
    print(json.dumps(protocol,ensure_ascii=False,indent=2))


def decouper(name):
    root=RACINE/'travail'/name
    protocol=json.loads((root/'protocole.json').read_text())
    target=RACINE/'travail'/(name+'_cellules')
    if target.exists():raise SystemExit('Découpe déjà présente : aucune sortie remplacée')
    rawfile=root/'out/r0001.png';raw=Image.open(rawfile).convert('RGB');w,h=raw.size
    if w%2 or h%2:raise SystemExit('Dimensions impaires : pas de découpe automatique')
    for sub in ('src','out'):(target/sub).mkdir(parents=True,exist_ok=True)
    compare=Image.new('RGB',(1440,1380),'white');details=Image.new('RGB',(1440,800),'white')
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',20)
    records=[]
    for n,c in enumerate(protocol['cellules']):
        i=c['pose'];left=(n%2)*(w//2);top=(n//2)*(h//2);box=(left,top,left+w//2,top+h//2)
        cut=raw.crop(box);dest=target/f'out/r{i:04}.png';cut.save(dest)
        shutil.copyfile(RACINE/f'travail/test/src/s{i:04}.png',target/f'src/s{i:04}.png')
        flow=Image.open(root/f'entrees/flow_{i}.png').convert('RGB');draw=normaliser(cut)
        row=n//2;start=(n%2)*720
        for k,(label,im) in enumerate([('Flow',flow),('Planche',draw)]):
            compare.paste(im.resize((360,640),Image.Resampling.LANCZOS),(start+k*360,row*690+50))
            ImageDraw.Draw(compare).text((start+k*360+8,row*690+12),f'{label} / pose {i}',font=font,fill='black')
        thumb=ImageOps.contain(draw.crop((250,280,530,865)),(350,738),Image.Resampling.LANCZOS)
        details.paste(thumb,(n*360+5,52));ImageDraw.Draw(details).text((n*360+10,12),f'Pose {i}',font=font,fill='black')
        records.append({'pose':i,'rectangle_sortie':list(box),'taille_cellule':list(cut.size),
                        'sortie':str(dest.relative_to(RACINE)),'sha256':sha(dest),
                        'decoupe_sans_recalage':True,'conformite_pose':'a_controler_visuellement'})
    manifest=json.loads((RACINE/'travail/test/manifeste.json').read_text())
    manifest.update({'debut_s':(protocol['ordre'][0]-1)/8,'duree_s':len(records)/8,
                     'frames':[f for f in manifest['frames'] if f['index'] in protocol['ordre']]})
    (target/'manifeste.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    compare.save(RACINE/f'sortie/{name}_comparaison.png');details.save(RACINE/f'sortie/{name}_robes.png')
    report={'type':'decoupe_planche_2x2','brut':str(rawfile.relative_to(RACINE)),'brut_sha256':sha(rawfile),
            'taille_brut':[w,h],'cellules':records,'appels_api':0,
            'limite':'Découpe exacte des quatre quadrants; aucune correction d’une grille mal respectée par le modèle.'}
    (root/'decoupe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');journaliser(root/'journal.jsonl',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('operation',choices=['preparer','decouper']);p.add_argument('--nom',required=True)
    p.add_argument('--poses',default='6,7,8,9')
    p.add_argument('--identite');p.add_argument('--matiere');a=p.parse_args()
    if not a.nom.replace('_','').isalnum():p.error('Nom de plan invalide')
    if a.operation=='preparer':preparer(a.nom,[int(i) for i in a.poses.split(',')],a.identite,a.matiere)
    else:decouper(a.nom)
