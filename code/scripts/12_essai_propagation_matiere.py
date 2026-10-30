"""Essai local indépendant : matière de 9, silhouettes et bandes des témoins conservées.

Les correspondances sont manuelles. Seuls les intérieurs de panneaux communs
à la base source et à la base cible reçoivent la matière; aucun appel API.
"""
import json
import argparse
from pathlib import Path
import runpy
import shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from commun import RACINE, journaliser
from normalisation import normaliser
from atelier import propager, masque, sha

# Repères géométriques approximatifs dans le cadre entier, fixés avant le score.
# Chaque ligne suit un niveau de la robe; les deux colonnes avant la dernière
# suivent le diviseur noir principal et sa courbure vers l'ourlet.
GRILLES={
9:[[[283,304],[347,304],[398,304],[432,304],[453,304],[482,304]],
   [[289,335],[347,332],[398,331],[430,332],[451,333],[479,334]],
   [[290,454],[345,454],[396,454],[430,454],[451,454],[477,454]],
   [[268,569],[340,571],[398,574],[431,575],[452,576],[480,577]],
   [[299,760],[347,752],[386,757],[399,764],[421,775],[463,782]],
   [[313,813],[355,804],[390,811],[401,819],[422,824],[452,823]]],
10:[[[286,314],[347,314],[398,314],[432,314],[453,314],[483,314]],
    [[291,345],[347,341],[398,340],[430,340],[451,340],[480,342]],
    [[294,464],[345,464],[396,464],[430,464],[451,464],[478,464]],
    [[268,577],[340,580],[398,583],[431,584],[452,586],[480,587]],
    [[293,779],[343,768],[383,775],[395,785],[419,794],[462,798]],
    [[308,828],[351,814],[389,823],[401,834],[421,839],[452,835]]],
11:[[[285,308],[347,308],[398,308],[432,308],[453,308],[483,308]],
    [[289,342],[347,337],[398,335],[430,335],[451,335],[481,337]],
    [[292,457],[345,457],[396,457],[429,457],[450,457],[478,457]],
    [[270,568],[340,572],[398,575],[429,577],[450,580],[480,581]],
    [[296,779],[344,767],[383,777],[396,787],[418,798],[464,803]],
    [[311,831],[354,816],[389,827],[402,838],[421,844],[453,841]]],
12:[[[285,300],[347,300],[398,300],[433,300],[455,300],[484,300]],
    [[290,335],[347,330],[398,328],[433,327],[455,327],[482,328]],
    [[288,450],[345,450],[397,450],[432,450],[454,450],[478,450]],
    [[268,564],[340,565],[398,569],[433,570],[455,573],[481,576]],
    [[272,777],[342,777],[396,779],[427,781],[450,783],[479,790]],
    [[274,825],[344,825],[397,827],[428,828],[451,832],[476,837]]]
}


def points(i):return {f'p{y}_{x}':pt for y,row in enumerate(GRILLES[i]) for x,pt in enumerate(row)}


def panneaux(base, i):
    """Domaines dérivés des BASES, pas des finitions à comparer."""
    a=np.array(base,dtype=float);r,g,b=a[...,0],a[...,1],a[...,2]
    y,x=np.indices(r.shape)
    grid=GRILLES[i]
    contour=grid[0]+[row[-1] for row in grid[1:]]+list(reversed(grid[-1][:-1]))+[row[0] for row in reversed(grid[1:-1])]
    robe=np.array(masque([contour]))>0
    red=robe&(r-g>40)&(r-b>35)&(r>1.35*g)
    blue=robe&(b>r*1.08)&(b>g*.95)&(r<140)&(y<350)
    yellow=robe&(r>120)&(g>90)&(r-b>80)&(g-b>55)&(y>750)
    ivory=robe&(r>115)&(g>105)&(b>80)&(r-g<25)&(g-b<40)&~red&~blue&~yellow
    # La partie haute et les bandes noires restent celles de la cible, ainsi que
    # les derniers pixels du contour. Pas de transfert de peau ni de silhouette.
    # Comble les trous internes SANS traverser le diviseur noir entre les deux
    # zones ivoire. Les enveloppes sont issues des bases, avant comparaison.
    levels=np.array([np.mean([p[1] for p in row]) for row in grid])
    left_black=np.interp(np.arange(1280),levels,[row[3][0] for row in grid])
    right_black=np.interp(np.arange(1280),levels,[row[4][0] for row in grid])
    def envelope(region):
        out=np.zeros_like(region)
        for yy in range(1280):
            xx=np.flatnonzero(region[yy])
            if len(xx)>2:out[yy,xx[0]:xx[-1]+1]=True
        return out&robe
    ivory_left=envelope(ivory&(x<left_black[:,None]-2))
    ivory_right=envelope(ivory&(x>right_black[:,None]+2))
    strong_yellow=envelope(yellow)
    # Le transfert s'arrête avant la peau sous l'ourlet, y compris ses creux.
    bottom=np.zeros(720)
    for xx in range(720):
        yy=np.flatnonzero(strong_yellow[:,xx])
        if len(yy):bottom[xx]=yy[-1]
    known=np.flatnonzero(bottom)
    if not len(known):raise ValueError('Ourlet jaune non identifié')
    bottom=np.interp(np.arange(720),known,bottom[known])
    garment=y<=bottom[None,:]
    return {name:Image.fromarray((m&garment).astype('uint8')*255).filter(ImageFilter.MinFilter(3))
            for name,m in [('rouge',envelope(red)),('bleu',envelope(blue)),
                           ('jaune',strong_yellow),('ivoire',ivory_left|ivory_right)]}


def main():
    p=argparse.ArgumentParser();p.add_argument('--version',default='v2');args=p.parse_args()
    if not args.version.isalnum():p.error('Version invalide')
    prefix='propagation9_'+args.version
    d=RACINE/('travail/propagation_9_'+args.version)
    if (d/'controle.json').exists():raise SystemExit('Essai présent : nouvelle version nécessaire pour le modifier')
    d.mkdir(exist_ok=True)
    for folder in ('masques','annotations','bruts','comparaisons'):(d/folder).mkdir(exist_ok=True)
    reference=normaliser(Image.open(RACINE/'travail/essai_relief/nano_relief_tete_preservee.png'))
    base9=normaliser(Image.open(RACINE/'travail/test_nano_banana_pro/out/r0009.png'))
    source_masks=panneaux(base9,9)
    triangles=[]
    for y in range(5):
        for x in range(5):
            a,b,c,e=[f'p{yy}_{xx}' for yy,xx in ((y,x),(y,x+1),(y+1,x),(y+1,x+1))]
            triangles.extend([[a,b,c],[b,e,c]])
    protocol={'reference':'travail/essai_relief/nano_relief_tete_preservee.png',
        'reference_sha256':sha(RACINE/'travail/essai_relief/nano_relief_tete_preservee.png'),
        'grilles_manuelles':GRILLES,'triangles':triangles,'cout_usd':0,'version':args.version,
        'limite':'Intérieurs de panneaux seulement; épaules, col, diviseurs, bords et zones non communes restent Nano. Correspondances de travail à apprécier visuellement.'}
    (d/'protocole.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    helper=runpy.run_path(str(RACINE/'travail/test/decor_geometrique_essai/incruster_fond_vert.py'))
    bg=Image.open(RACINE/'refs/decor_geometrique_v4/apercu_F001.png').convert('RGBA').resize((720,1280),Image.Resampling.LANCZOS)
    board=Image.new('RGB',(1440,2040),'white');draw=ImageDraw.Draw(board)
    details=Image.new('RGB',(1080,1800),'white');dd=ImageDraw.Draw(details)
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',18)
    for col,title in enumerate(('Flow','Temoin finalise','Matiere propagee depuis 9','Masque de transfert')):draw.text((col*360+5,8),title,font=font,fill='black')
    records=[]
    for row,i in enumerate((10,11,12)):
        witness_path=RACINE/f'travail/temoins_10_12_finalises/protegees/r{i:04}.png'
        witness=normaliser(Image.open(witness_path));base=normaliser(Image.open(RACINE/f'travail/test_nano_banana_pro/out/r{i:04}.png'))
        target_masks=panneaux(base,i)
        for label,m in target_masks.items():m.save(d/f'masques/domaine_base_{label}_{i}.png')
        warped,coverage=propager(reference,points(9),points(i),triangles)
        warped.save(d/f'bruts/robe9_vers_{i}.png')
        def core(im):
            rgb=np.array(im,dtype=int)
            fg=rgb[...,1]-np.maximum(rgb[...,0],rgb[...,2])<=5
            return np.array(Image.fromarray(fg.astype('uint8')*255).filter(ImageFilter.MinFilter(11)))==255
        safe_core=core(witness)&core(warped)
        base_rgb=np.array(base,dtype=int)
        black_bands=(base_rgb.max(2)<105)&(np.abs(base_rgb[...,0]-base_rgb[...,1])<20)&(np.abs(base_rgb[...,1]-base_rgb[...,2])<20)
        safe_core &= ~black_bands
        mask=Image.new('L',(720,1280));combined=np.zeros((1280,720),dtype=np.uint8);stats={}
        for name,src_mask in source_masks.items():
            mapped,_=propager(src_mask.convert('RGB'),points(9),points(i),triangles)
            src_ok=np.array(mapped)[...,0]>250;dst_ok=np.array(target_masks[name])>250
            use=src_ok&dst_ok&(np.array(coverage)>0)&safe_core
            combined[use]=255
            stats[name]={'pixels_cibles':int(dst_ok.sum()),'pixels_communs_propages':int(use.sum()),
                'couverture':float(use.sum()/max(1,dst_ok.sum()))}
            Image.fromarray(use.astype('uint8')*255).save(d/f'masques/{name}_{i}.png')
        hard_mask=Image.fromarray(combined)
        alpha_values=np.minimum(combined,np.array(hard_mask.filter(ImageFilter.GaussianBlur(2))))
        mask=Image.fromarray(alpha_values)
        result=Image.composite(warped,witness,mask)
        a,b=np.array(witness),np.array(result);outside=combined==0
        assert np.array_equal(a[outside],b[outside]),'Pixels hors panneaux modifiés'
        assert np.array_equal(a[:300],b[:300]),'Tête modifiée'
        assert np.array_equal(a[880:],b[880:]),'Jambes ou chaussures modifiées'
        assert np.array_equal(a[black_bands],b[black_bands]),'Bandes noires modifiées'
        alpha,_=helper['detourer'](result)
        original_alpha,_=helper['detourer'](witness)
        # Les masques érodés ne doivent pas modifier la silhouette visible.
        assert np.array_equal(np.array(alpha.getchannel('A')),np.array(original_alpha.getchannel('A'))),'Silhouette modifiée'
        mask.save(d/f'masques/transfert_{i}.png');result.save(d/f'bruts/hybride_{i}.png')
        overlay=base.copy();od=ImageDraw.Draw(overlay)
        for tri in triangles:od.line([tuple(points(i)[p]) for p in tri]+[tuple(points(i)[tri[0]])],fill='cyan',width=1)
        overlay.save(d/f'annotations/maillage_{i}.png')
        flowfile=RACINE/f'travail/test/src/s{i:04}.png';flow=Image.open(flowfile).convert('RGB')
        variants=[]
        for tag,im in [('temoin',witness),('propage',result)]:
            layer,_=helper['detourer'](im)
            composed=Image.alpha_composite(bg,layer).convert('RGB');variants.append(composed)
            plan=RACINE/f'travail/{prefix}_{tag}'
            for sub in ('src','out'):(plan/sub).mkdir(parents=True,exist_ok=True)
            composed.save(plan/f'out/r{i:04}.png');shutil.copyfile(flowfile,plan/f'src/s{i:04}.png')
        for col,im in enumerate([flow,*variants,mask.convert('RGB')]):board.paste(im.resize((360,640)),(col*360,row*670+50))
        draw.text((5,row*670+30),f'Pose {i}',font=font,fill='black')
        for col,im in enumerate([witness,result,reference]):
            thumb=ImageOps.contain(im.crop((255,310,490,810)),(350,520),Image.Resampling.LANCZOS)
            details.paste(thumb,(col*360+40,row*580+50))
        for col,title in enumerate(('Temoin','Propagation','Reference 9')):dd.text((col*360+5,row*580+10),f'{title} / pose {i}',font=font,fill='black')
        # Comparaison quantitative limitée au domaine fixe, avant tout jugement esthétique.
        records.append({'pose':i,'temoin_sha256':sha(witness_path),'panneaux':stats,
            'pixels_propages':int((combined>0).sum()),'differences_hors_masque':0,
            'tete_membres_chaussures_preserves':True,'silhouette_preservee':True,
            'bandes_noires_protegees':True,
            'limite':'Les ombres et plis de 9 sont transportés en 2D; ce contrôle ne prouve pas leur conformité au mouvement de Flow.'})
    manifest={'video':'entree/source_animation.mp4','fps':24,'pas':3,'debut_s':1.125,'duree_s':.375,
        'frames':[{'index':i,'fichier':f's{i:04}.png','frame_source':(i-1)*3} for i in (10,11,12)]}
    for tag in ('temoin','propage'):(RACINE/f'travail/{prefix}_{tag}/manifeste.json').write_text(json.dumps(manifest,indent=2)+'\n')
    board.save(RACINE/f'sortie/{prefix}_planche.png')
    details.save(RACINE/f'sortie/{prefix}_details.png')
    report={'type':'essai_propagation_locale','images':records,'cout_usd':0,'appels_api':0,
        'statut':'essai_partiel_a_controler_visuellement','protocole_sha256':sha(d/'protocole.json')}
    (d/'controle.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');journaliser(d/'journal.jsonl',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
