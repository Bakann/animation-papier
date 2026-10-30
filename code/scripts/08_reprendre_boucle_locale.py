"""Retouche locale autorisée de la boucle de la pose 10, sans appel API.

Calage spécifique à cette pose : retrait de la plaque générée par prélèvement
de texture voisine, puis collage du détail du guide. Le brut reste intact.
"""
from pathlib import Path
import datetime
import hashlib
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from commun import RACINE, journaliser


def main():
    d=RACINE/'travail/pilote_chaussure_master_10'
    source=d/'out/r0010.png'; guide_path=d/'src/s0010.png'
    raw=Image.open(source).convert('RGB'); guide=Image.open(guide_path).convert('RGB')
    before_sha=hashlib.sha256(source.read_bytes()).hexdigest()
    w,h=raw.size
    if (w,h)!=(1536,2752) or guide.size!=(720,1280):
        raise SystemExit('Calage spécifique 1536 × 2752 / guide 720 × 1280 : dimensions inattendues')
    # Inverse exact de la normalisation du CADRE ENTIER, sans recalage du personnage.
    cw,ch=ImageOps.contain(raw,(720,1280)).size
    ox,oy=round((720-cw)/2),round((1280-ch)/2)
    reference=guide.crop((ox,oy,ox+cw,oy+ch)).resize(raw.size,Image.Resampling.LANCZOS)
    def point(x,y):return ((x-ox)*w/cw,(y-oy)*h/ch)
    def polygon(coords):
        mask=Image.new('L',raw.size)
        ImageDraw.Draw(mask).polygon([point(x,y) for x,y in coords],fill=255)
        return mask
    repair=polygon([(386,1190),(416,1190),(420,1208),(384,1208)])
    loop=polygon([(379,1203),(382,1199),(386,1196),(393,1193),
                  (400,1193),(405,1196),(408,1203),(404,1205),
                  (397,1204),(389,1206),(382,1207)])
    # Reconstruction de la petite zone occultée par la plaque d'après le bord du guide.
    arr=np.array(raw); texture=arr.copy(); yy,xx=np.indices((h,w))
    xn=xx*cw/w+ox;yn=yy*ch/h+oy
    boundary=np.interp(xn,[379,384,390,399,404,409,414,420],
                            [1203,1198,1195,1193,1195,1198,1202,1207])
    skin_y=np.rint((1180+(yn%4)-oy)*h/ch).astype(int)
    leather_y=np.rint((1210+(yn%2)-oy)*h/ch).astype(int)
    texture=np.where((yn<boundary)[...,None],arr[skin_y,xx],arr[leather_y,xx])
    repaired=Image.composite(Image.fromarray(texture),raw,repair)
    # Raccord sur un pixel natif; coeur du détail copié sans modification de couleur.
    rim=loop.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(.5))
    alpha=np.maximum(np.array(loop),np.array(rim))
    allowed=(np.array(repair)>0)|(alpha>0)
    result=Image.composite(reference,repaired,Image.fromarray(alpha))
    out=np.array(result); ref=np.array(reference); core=np.array(loop)==255
    assert np.array_equal(out[~allowed],arr[~allowed]),'Pixels hors zone modifiés'
    assert np.array_equal(out[core],ref[core]),'Boucle du guide altérée'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before_sha,'Brut modifié'
    (d/'corrigees').mkdir(exist_ok=True);(d/'masques').mkdir(exist_ok=True)
    final=d/'corrigees/r0010_boucle_master.png'
    if final.exists():raise SystemExit('Correction déjà présente : conservation sans écrasement')
    result.save(final)
    Image.fromarray(allowed.astype('uint8')*255).save(d/'masques/m0010_zone_boucle.png')
    loop.save(d/'masques/m0010_detail_master.png')
    report={'date_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'operation':'correction_locale_boucle_pose10','source':str(source.relative_to(RACINE)),
        'source_sha256':before_sha,'guide_sha256':hashlib.sha256(guide_path.read_bytes()).hexdigest(),
        'sortie':str(final.relative_to(RACINE)),'sortie_sha256':hashlib.sha256(final.read_bytes()).hexdigest(),
        'pixels_zone_autorisee':int(allowed.sum()),'pixels_changes':int(np.any(out!=arr,axis=2).sum()),
        'differences_hors_zone':0,'differences_coeur_guide':0,'brut_conserve':True,
        'appels_api':0,'cout_usd':0,'methode':'Retrait local de la plaque par textures peau/cuir voisines, puis copie du détail du guide avec raccord périphérique de 1 pixel natif.',
        'limite':'Retouche de la boucle uniquement. Pas de validation des plis, du visage ni de la continuité temporelle.'}
    (d/'controle_boucle_locale.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    journaliser(d/'journal.jsonl',report)
    board=Image.new('RGB',(1260,1000),'white');draw=ImageDraw.Draw(board)
    for col,(title,im) in enumerate([('Guide master',reference),('Brut avant',raw),('Correction locale',result)]):
        draw.text((col*420+8,8),title,fill='black')
        crop=im.crop(tuple(round(v) for p in [(365,1183),(430,1220)] for v in point(*p)))
        board.paste(crop.resize((410,233),Image.Resampling.NEAREST),(col*420+5,35))
        preview=ImageOps.pad(im,(360,640),method=Image.Resampling.LANCZOS)
        board.paste(preview,(col*420+30,310))
    board.save(RACINE/'sortie/boucle_master_locale_comparatif.png')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
