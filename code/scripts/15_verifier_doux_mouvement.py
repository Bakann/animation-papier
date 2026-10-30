"""Contrôle gratuit sur 6–8 : recette statique, palette fixe, grain lié aux panneaux."""
import argparse
import importlib.util
import json
from pathlib import Path
import runpy
import shutil

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from commun import RACINE, journaliser
from normalisation import normaliser

spec = importlib.util.spec_from_file_location('relief_local', Path(__file__).with_name('14_relief_doux_local.py'))
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


def enveloppe(mask):
    yy = np.flatnonzero(mask.any(axis=1))
    if len(yy) < 2:
        raise ValueError('Domaine insuffisant pour le repère du panneau')
    left = np.array([np.flatnonzero(mask[y])[0] for y in yy], dtype=float)
    right = np.array([np.flatnonzero(mask[y])[-1] for y in yy], dtype=float)
    return yy, left, right


def grain_suivi(grain, reference, cible):
    """Même grain dans un repère u/v de panneau, sans transporter ses ombres."""
    ry, rl, rr = enveloppe(reference)
    ty, tl, tr = enveloppe(cible)
    y, x = np.indices(cible.shape, dtype=float)
    v = (y-ty[0])/(ty[-1]-ty[0])
    source_y = ry[0] + v*(ry[-1]-ry[0])
    left = np.interp(y, ty, tl)
    right = np.interp(y, ty, tr)
    u = (x-left)/np.maximum(1, right-left)
    source_x = np.interp(source_y, ry, rl) + u*(np.interp(source_y, ry, rr)-np.interp(source_y, ry, rl))
    source_x = np.clip(source_x, 0, grain.shape[1]-1)
    source_y = np.clip(source_y, 0, grain.shape[0]-1)
    x0, y0 = np.floor(source_x).astype(int), np.floor(source_y).astype(int)
    x1, y1 = np.minimum(x0+1, grain.shape[1]-1), np.minimum(y0+1, grain.shape[0]-1)
    fx, fy = source_x-x0, source_y-y0
    result = ((1-fx)*(1-fy)*grain[y0,x0] + fx*(1-fy)*grain[y0,x1]
              + (1-fx)*fy*grain[y1,x0] + fx*fy*grain[y1,x1])
    return result


def preparer(flow, base):
    source = np.asarray(flow, dtype=float)
    original = np.asarray(base, dtype=float)
    y,x = np.indices((1280,720))
    sr,sg,sb = source.transpose(2,0,1)
    tr,tg,tb = original.transpose(2,0,1)
    red = (sr>1.7*sg)&(sr>1.7*sb)&(sr>70)
    target_red = (tr>1.7*tg)&(tr>1.7*tb)&(tr>70)
    ivory = (sr>110)&(sg>100)&(sb>65)&(sr-sg<28)&(sg-sb<60)
    # Recette v2 inchangée pour vérifier son comportement hors de la pose 6.
    geometry = {'rouge':red&(y>325)&(y<585)&(x>270)&(x<440),
                'ivoire_bas':ivory&(y>595)&(y<815)&(x>280)&(x<435)}
    for yy in range(1280):
        xx = np.flatnonzero(geometry['ivoire_bas'][yy])
        if len(xx)>2:
            geometry['ivoire_bas'][yy,xx[0]:xx[-1]+1] = True
    masks = {name:m.copy() for name,m in geometry.items()}
    masks['rouge'] &= target_red
    black = (original.max(2)<105)&(np.ptp(original,axis=2)<25)
    foreground = tg-np.maximum(tr,tb)<=5
    foreground = np.asarray(Image.fromarray(foreground.astype('uint8')*255).filter(ImageFilter.MinFilter(11)))==255
    panels = {}
    luminance = source@np.array([.2126,.7152,.0722])
    for name,m in masks.items():
        m = np.asarray(Image.fromarray((m&~black&foreground).astype('uint8')*255).filter(ImageFilter.MinFilter(3)))==255
        hard = m.astype('uint8')*255
        alpha = np.minimum(hard,local.blur_float(hard,3))/255
        weight = local.blur_float(hard,2)/255
        mean = local.blur_float(luminance*m,2)/np.maximum(weight,.01)
        shade = np.clip(mean/max(np.percentile(mean[m],85),1)-1,-.4,.1)
        flat = m&(mean>=np.percentile(mean[m],65))
        panels[name] = {'mask':m,'alpha':alpha,'shade':shade,'colour':np.median(original[flat],axis=0),'geometry':geometry[name]}
    return panels, black


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version',default='v1')
    args = parser.parse_args()
    if not args.version.isalnum():parser.error('Version invalide')
    prefix = f'doux_mouvement_{args.version}'
    root = RACINE/f'travail/{prefix}'
    if root.exists():raise SystemExit('Essai existant : choisir une autre version')
    for sub in ('entrees','masques','bruts','diagnostics'):(root/sub).mkdir(parents=True,exist_ok=True)
    grainfile = RACINE/'travail/test_nano_matiere9/ancre/extraits/01_grain_rouge.png'
    crop = Image.open(grainfile).convert('L').crop((40,15,140,110)).resize((47,45),Image.Resampling.LANCZOS)
    high = np.asarray(crop,dtype=float)-local.blur_float(np.asarray(crop),2)
    high -= high.mean(); high /= max(high.std(),.001)
    tile = np.concatenate([high,high[:,::-1]],axis=1)
    tile = np.concatenate([tile,tile[::-1]],axis=0)
    grain = np.tile(tile,(15,8))[:1280,:720]
    helper = runpy.run_path(str(RACINE/'travail/test/decor_geometrique_essai/incruster_fond_vert.py'))
    bg = Image.open(RACINE/'refs/decor_geometrique_v4/apercu_F001.png').convert('RGBA').resize((720,1280),Image.Resampling.LANCZOS)
    records=[]; refs=None; colours=None
    board = Image.new('RGB',(1440,2070),'white')
    detail = Image.new('RGB',(1440,2400),'white')
    grainboard = Image.new('RGB',(960,1200),'white')
    font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',20)
    variants = ('temoin','original','palette','suivi')
    for i in (6,7,8):
        row=i-6
        srcpath=RACINE/f'travail/test_nano_banana_pro/src/s{i:04}.png'
        basepath=RACINE/'travail/pilote_ab_a_1/out/r0006.png' if i==6 else RACINE/f'travail/test_nano_banana_pro/out/r{i:04}.png'
        flow=normaliser(Image.open(srcpath));base=normaliser(Image.open(basepath))
        flow.save(root/f'entrees/flow_{i}.png');base.save(root/f'entrees/temoin_{i}.png')
        panels,black=preparer(flow,base)
        if refs is None:
            refs={name:p['geometry'].copy() for name,p in panels.items()}
            colours={name:p['colour'].copy() for name,p in panels.items()}
        allowed=np.logical_or.reduce([p['mask'] for p in panels.values()])
        original=np.asarray(base)
        alpha_before,_=helper['detourer'](base)
        result_images={'temoin':base}
        counts={}
        for name,p in panels.items():
            Image.fromarray(p['mask'].astype('uint8')*255).save(root/f'masques/{name}_{i}.png')
            counts[name]=int(p['mask'].sum())
            p['grain_suivi']=grain_suivi(grain,refs[name],p['geometry'])
        for tag in variants[1:]:
            result=original.astype(float).copy()
            for name,p in panels.items():
                colour=p['colour'] if tag=='original' else colours[name]
                noise=p['grain_suivi'] if tag=='suivi' else grain
                rendering=np.clip(colour[None,None,:]*(1+.45*p['shade'][...,None])+1.8*noise[...,None],0,255)
                a=p['alpha'][...,None];result=result*(1-a)+rendering*a
            image=Image.fromarray(np.uint8(np.clip(np.rint(result),0,255)))
            arr=np.asarray(image)
            assert np.array_equal(arr[~allowed],original[~allowed]),'Pixels hors masque modifiés'
            assert np.array_equal(arr[:300],original[:300]),'Tête modifiée'
            assert np.array_equal(arr[880:],original[880:]),'Jambes modifiées'
            assert np.array_equal(arr[black],original[black]),'Bandes noires modifiées'
            layer,_=helper['detourer'](image)
            assert np.array_equal(np.asarray(layer.getchannel('A')),np.asarray(alpha_before.getchannel('A'))),'Alpha modifié'
            image.save(root/f'bruts/{tag}_{i}.png');result_images[tag]=image
        if i==6:
            expected=np.asarray(Image.open(RACINE/'travail/relief_doux_local_v2/out/Doux.png'))
            assert np.array_equal(np.asarray(result_images['original']),expected),'Recette statique non reproduite'
            assert np.array_equal(np.asarray(result_images['suivi']),expected),'Le suivi change déjà la pose de référence'
        for col,tag in enumerate(variants):
            im=result_images[tag]
            layer,_=helper['detourer'](im);composed=Image.alpha_composite(bg,layer).convert('RGB')
            plan=RACINE/f'travail/{prefix}_{tag}'
            for sub in ('src','out'):(plan/sub).mkdir(parents=True,exist_ok=True)
            composed.save(plan/f'out/r{i:04}.png')
            shutil.copyfile(RACINE/f'travail/test/src/s{i:04}.png',plan/f'src/s{i:04}.png')
            board.paste(composed.resize((360,640),Image.Resampling.LANCZOS),(col*360,row*690+50))
            ImageDraw.Draw(board).text((col*360+5,row*690+10),f'{i} / {tag}',font=font,fill='black')
            thumb=ImageOps.contain(im.crop((265,320,490,820)),(350,738),Image.Resampling.LANCZOS)
            detail.paste(thumb,(col*360+5,row*800+55))
            ImageDraw.Draw(detail).text((col*360+5,row*800+10),f'{i} / {tag}',font=font,fill='black')
        for col,tag in enumerate(('original','suivi')):
            noise=grain if tag=='original' else panels['rouge']['grain_suivi']
            # Diagnostic amplifié uniquement : il n'est pas utilisé dans les rendus.
            diagnostic=Image.fromarray(np.uint8(np.clip(128+noise*25,0,255)))
            diagnostic.save(root/f'diagnostics/grain_{tag}_{i}.png')
            thumb=ImageOps.contain(diagnostic.crop((280,330,435,580)),(470,350),Image.Resampling.NEAREST)
            grainboard.paste(thumb,(col*480+5,row*400+45))
            ImageDraw.Draw(grainboard).text((col*480+5,row*400+5),f'Grain amplifie {i} / {tag}',font=font,fill='black')
        ry,_,_=enveloppe(panels['rouge']['geometry'])
        records.append({'pose':i,'source':str(srcpath.relative_to(RACINE)),'source_sha256':local.sha(srcpath),
                        'temoin':str(basepath.relative_to(RACINE)),'temoin_sha256':local.sha(basepath),
                        'palette_locale':{name:p['colour'].tolist() for name,p in panels.items()},
                        'palette_fixe':{name:c.tolist() for name,c in colours.items()},
                        'pixels_masques':counts,'rouge_bornes_y_repere_uv':[int(ry[0]),int(ry[-1])],
                        'differences_hors_masque':0,'alpha_et_bandes_preserves':True})
    manifest=json.loads((RACINE/'travail/test/manifeste.json').read_text())
    manifest.update({'debut_s':.625,'duree_s':.375,'frames':[f for f in manifest['frames'] if f['index'] in (6,7,8)]})
    for tag in variants:(RACINE/f'travail/{prefix}_{tag}/manifeste.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    board.save(RACINE/f'sortie/{prefix}_planche.png');detail.save(RACINE/f'sortie/{prefix}_details.png')
    grainboard.save(RACINE/f'sortie/{prefix}_grain_amplifie.png')
    report={'type':'test_local_doux_6_8','poses':records,'recette':{'contraste_ombres':.45,'amplitude_grain':1.8,'normalisation':'720x1280 cadre entier'},
            'variantes':{'original':'Recette statique v2 par pose : palette locale, grain en coordonnées écran',
                         'palette':'Même grain écran, palette des panneaux fixée à 6',
                         'suivi':'Palette fixée à 6, grain dans un repère u/v des enveloppes des panneaux Flow'},
            'pose6_identique_essai_statique':True,'appels_api':0,'cout_usd':0,
            'limites':['Panneaux rouge et grand ivoire seulement, fenêtres de masque statiques conservées pour cet essai',
                       'Témoins existants : A1 en6 et bases Nano en7–8; les variations hors masque leur appartiennent',
                       'Le suivi u/v suit les enveloppes 2D, pas une déformation physique 3D ni les plis internes',
                       'Le mouvement utilisé pour produire le suivi ne constitue pas une évaluation indépendante du suivi']}
    (root/'controle.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');journaliser(root/'journal.jsonl',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
