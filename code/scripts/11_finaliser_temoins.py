"""Finalise les témoins 10–12 avec têtes protégées, sans génération payante."""
from pathlib import Path
import hashlib
import json
import runpy
import shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from commun import RACINE, journaliser
from normalisation import normaliser


def proteger_tete(base, finition, fin_protection=240, fin_raccord=270):
    if base.size!=finition.size:raise ValueError('Images natives de dimensions différentes')
    h=base.height;y0=round(fin_protection*h/1280);y1=round(fin_raccord*h/1280)
    rows=np.clip((np.arange(h)-y0)/max(1,y1-y0),0,1)
    mask=np.broadcast_to(np.rint(rows[:,None]*255).astype('uint8'),(h,base.width)).copy()
    result=Image.composite(finition,base,Image.fromarray(mask))
    a,b,c=np.array(base),np.array(finition),np.array(result)
    assert np.array_equal(c[:y0],a[:y0]),'Tête modifiée'
    assert np.array_equal(c[y1:],b[y1:]),'Corps modifié hors raccord'
    return result,Image.fromarray(mask),y0,y1


def main():
    plan='temoins_10_12_finalises';d=RACINE/'travail'/plan
    if (d/'controle.json').exists():raise SystemExit('Témoins déjà finalisés : nouvelle variante nécessaire pour les modifier')
    for sub in ('src','out','protegees','masques','alpha','comparaisons'):(d/sub).mkdir(parents=True,exist_ok=True)
    helper=runpy.run_path(str(RACINE/'travail/test/decor_geometrique_essai/incruster_fond_vert.py'))
    bgfile=RACINE/'refs/decor_geometrique_v4/apercu_F001.png'
    bg=Image.open(bgfile).convert('RGBA').resize((720,1280),Image.Resampling.LANCZOS)
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    board=Image.new('RGB',(1440,2040),'white');draw=ImageDraw.Draw(board)
    faces=Image.new('RGB',(1080,900),'white');fd=ImageDraw.Draw(faces)
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',19)
    for col,title in enumerate(('Flow','Base avant finition','Finition retenue (10 corrigee)','Temoin finalise / decor')):
        draw.text((col*360+5,8),title,font=font,fill='black')
    for col,title in enumerate(('Base / tete de reference','Finition avant protection','Tete protegee')):
        fd.text((col*360+5,5),title,font=font,fill='black')
    records=[]
    for row,i in enumerate((10,11,12)):
        basefile=RACINE/f'travail/test_nano_banana_pro/out/r{i:04}.png'
        rawfile=RACINE/('travail/correctif_bloc_boucle10_test/frame_corrigee.png' if i==10 else f'travail/pilote_temoin_10_12/out/r{i:04}.png')
        base=Image.open(basefile).convert('RGB');raw=Image.open(rawfile).convert('RGB')
        result,mask,y0,y1=proteger_tete(base,raw)
        result.save(d/f'protegees/r{i:04}.png');mask.save(d/f'masques/m{i:04}.png')
        small=normaliser(result);layer,detourage=helper['detourer'](small)
        layer.save(d/f'alpha/r{i:04}.png')
        composed=Image.alpha_composite(bg,layer).convert('RGB');composed.save(d/f'out/r{i:04}.png')
        flowfile=RACINE/f'travail/test/src/s{i:04}.png';shutil.copyfile(flowfile,d/f'src/s{i:04}.png')
        flow=Image.open(flowfile).convert('RGB')
        maskflow=Image.open(RACINE/f'travail/test/cibles_vertes/masques/s{i:04}.png')
        flow_points=helper['reperes'](flow,maskflow)
        final_points=helper['reperes'](small,layer.getchannel('A'))
        record={'index':i,'base':str(basefile.relative_to(RACINE)),'base_sha256':sha(basefile),
            'finition':str(rawfile.relative_to(RACINE)),'finition_sha256':sha(rawfile),
            'source_flow_sha256':sha(flowfile),'protection_tete_fin_y_native':y0,
            'raccord_fin_y_native':y1,'differences_tete':0,'differences_corps_sous_raccord':0,
            'sortie_protegee_sha256':sha(d/f'protegees/r{i:04}.png'),
            'sortie_composee_sha256':sha(d/f'out/r{i:04}.png'),
            'reperes_flow':flow_points,'reperes_temoin':final_points,
            'ecarts_temoin_flow':{k:final_points[k]-flow_points[k] for k in flow_points},
            'detourage':detourage,'statut':'prepare_et_controle_visuellement_pas_valide_en_production'}
        records.append(record)
        for col,im in enumerate((flow,normaliser(base),normaliser(raw),composed)):
            board.paste(im.resize((360,640),Image.Resampling.LANCZOS),(col*360,row*670+50))
        draw.text((5,row*670+30),f'Pose {i}',font=font,fill='black')
        for col,im in enumerate((base,raw,result)):
            face=normaliser(im).crop((290,45,480,285)).resize((210,265),Image.Resampling.LANCZOS)
            faces.paste(face,(col*360+60,row*285+35))
    board.save(RACINE/'sortie/temoins_10_12_finalises_planche_detaillee.png')
    faces.save(RACINE/'sortie/temoins_10_12_finalises_tetes.png')
    manifest={'video':'entree/source_animation.mp4','fps':24,'pas':3,'debut_s':1.125,'duree_s':0.375,
        'frames':[{'index':i,'fichier':f's{i:04}.png','frame_source':(i-1)*3} for i in (10,11,12)]}
    (d/'manifeste.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    report={'type':'finalisation_locale_temoins','images':records,'decor':str(bgfile.relative_to(RACINE)),
        'decor_sha256':sha(bgfile),'fond':'F001 fixe; aucune ombre de contact ajoutée',
        'appels_api':0,'cout_usd':0,'cadence':'3 dessins tenus 3 frames à 24 i/s',
        'limites':['Pas le test entier de 16 dessins.','Repères tête/pieds heuristiques; pas une mesure complète des articulations.',
          'Relief de robe et genoux toujours variable; témoins destinés à la comparaison suivante.',
          'Les masques de propagation restent indépendants et non validés par cette finalisation.']}
    (d/'controle.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    journaliser(d/'journal.jsonl',report)
    print(json.dumps({'plan':plan,'images':len(records),'cout':0,
        'ecarts_reperes':{str(r['index']):r['ecarts_temoin_flow'] for r in records}},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
