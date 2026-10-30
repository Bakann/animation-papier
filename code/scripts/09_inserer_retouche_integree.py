"""Insère l'édition imagegen de la boucle; conserve les contours du pied et les bruts."""
from pathlib import Path
import hashlib
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from commun import RACINE, journaliser


def main():
    d=RACINE/'travail/pilote_chaussure_master_10';dest=d/'imagegen'
    source=d/'out/r0010.png';generated=dest/'retouche_pieds_integree_brute.png'
    image=Image.open(source).convert('RGB');raw=Image.open(generated).convert('RGB')
    patch=raw.resize((320,400),Image.Resampling.LANCZOS)
    # La génération porte sur le crop (704,2320,1024,2720). Retenir seulement
    # le dessus de chaussure; ni le pied arrière ni la semelle ne sont repris.
    local_mask=Image.new('L',(320,400));ImageDraw.Draw(local_mask).rounded_rectangle((104,234,203,286),radius=8,fill=255)
    local_mask=local_mask.filter(ImageFilter.GaussianBlur(2))
    original_crop=image.crop((704,2320,1024,2720));a=np.array(original_crop)
    # Ne pas modifier les pixels extérieurs du pied, y compris l'anticrénelage.
    foreground=(a[...,1].astype(int)-np.maximum(a[...,0],a[...,2]).astype(int)<5)
    m=np.array(local_mask);m[~foreground]=0;local_mask=Image.fromarray(m)
    result=image.copy();result.paste(patch,(704,2320),local_mask)
    full_mask=Image.new('L',image.size);full_mask.paste(local_mask,(704,2320))
    orig=np.array(image);final=np.array(result);outside=np.array(full_mask)==0
    assert np.array_equal(orig[outside],final[outside]),'Pixels hors zone changés'
    assert np.array_equal(orig[2620:],final[2620:]),'Semelle modifiée'
    output=d/'corrigees/r0010_boucle_imagegen.png'
    if output.exists():raise SystemExit('Variante déjà présente : pas d’écrasement')
    output.parent.mkdir(exist_ok=True);result.save(output)
    full_mask.save(dest/'masque_insertion_boucle.png')
    sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
    report={'type':'edition_image_integree','outil':'image_gen intégré',
      'source':str(source.relative_to(RACINE)),'source_sha256':sha(source),
      'references':[str(dest.relative_to(RACINE)/'cible_pieds.png'),
        '~/oct/geometrique/essai_kirigami/preparation/chaussure_master_detail.png',str(source.relative_to(RACINE))],
      'prompt_fichier':str(dest.relative_to(RACINE)/'prompt_boucle.txt'),
      'brut_genere':str(generated.relative_to(RACINE)),'brut_genere_sha256':sha(generated),
      'generation_origine':'~/.codex/generated_images/<image>.png',
      'sortie':str(output.relative_to(RACINE)),'sortie_sha256':sha(output),
      'taille_imagegen':raw.size,'taille_finale':result.size,
      'crop_source':[704,2320,1024,2720],'zone_copie_dans_crop':[104,234,203,286],
      'pixels_changes':int(np.any(orig!=final,axis=2).sum()),'differences_hors_masque':0,
      'semelle_et_bas_image_preserves':True,'nombre_images_generees':1,
      'appels_api_projet':0,'cout_outil_integre':None,'cout_note':'Tarif non exposé par l’outil; aucun appel aux comptes Comfy/Google par les scripts.',
      'statut':'candidat_controle_visuellement','limite':'Pose 10 seulement; ni validation de séquence ni validation des autres détails.'}
    (dest/'controle_imagegen.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    journaliser(d/'journal.jsonl',report)
    board=Image.new('RGB',(1280,960),'white');draw=ImageDraw.Draw(board)
    local=Image.open(d/'corrigees/r0010_boucle_master.png').convert('RGB')
    ref=Image.open('~/oct/geometrique/essai_kirigami/preparation/chaussure_master_detail.png').convert('RGB')
    for col,(title,im) in enumerate([('Master',ref),('Brut avant',image),('Ancien collage local',local),('Retouche outil integre',result)]):
        draw.text((col*320+5,8),title,fill='black')
        if col==0:
            thumb=ImageOps.pad(ref,(310,220),method=Image.Resampling.LANCZOS,color='white')
        else:
            thumb=im.crop((770,2540,928,2630)).resize((310,177),Image.Resampling.LANCZOS)
        board.paste(thumb,(col*320+5,40))
        if col>0:board.paste(ImageOps.pad(im,(300,600),method=Image.Resampling.LANCZOS,color='white'),(col*320+10,320))
    board.save(RACINE/'sortie/boucle_imagegen_comparatif.png')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
