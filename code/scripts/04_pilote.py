"""CLI locale : annotations manuelles, propagation et comparaison, sans génération."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from commun import RACINE
from atelier import normaliser, masque, masques_elements, propager, composer_robe, mesurer, geometrie, sha


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=['masques','temoins','propager','mesurer','apercus'])
    p.add_argument('--protocole', required=True)
    a = p.parse_args()
    protocol = json.loads((RACINE/a.protocole).read_text())
    out = RACINE/protocol['sortie']; out.mkdir(parents=True,exist_ok=True)
    poses = {k: json.loads((RACINE/v).read_text()) for k,v in protocol['annotations'].items()}
    masks = {k: masques_elements(v) for k,v in poses.items()}
    if a.operation == 'masques':
        for k, ann in poses.items():
            im = normaliser(Image.open(RACINE/ann['image']))
            overlay = im.copy(); d = ImageDraw.Draw(overlay)
            for name, polygons in ann['elements'].items():
                for polygon in polygons:
                    d.line([tuple(v) for v in polygon]+[tuple(polygon[0])],fill='magenta',width=2)
            for name, pt in ann['points'].items():
                x,y=pt; d.ellipse((x-3,y-3,x+3,y+3),fill='cyan');d.text((x+3,y),name,fill='cyan')
            overlay.save(out/f'annotation_{k}.png')
            for name, mask in masks[k].items(): mask.save(out/f'masque_{k}_{name}.png')
        return
    if not protocol.get('annotations_controlees_codex'):
        p.error('Annotations non contrôlées : examiner les superpositions avant usage')
    triangles = protocol['triangles']
    if a.operation == 'temoins':
        if protocol.get('temoins_finalises_externes'):
            if not all((RACINE/path).exists() for path in protocol['temoins'].values()):
                p.error('Témoins externes manquants : ne pas les reconstruire silencieusement')
            return print('[ok] Témoins finalisés existants conservés, sans écrasement')
        report=[]
        for k,path in protocol['bruts_temoins'].items():
            base=normaliser(Image.open(RACINE/poses[k]['image']))
            raw=normaliser(Image.open(RACINE/path))
            b=np.array(base); c=np.array(raw)
            fg=b[...,1].astype(int)-np.maximum(b[...,0],b[...,2]).astype(int)<=15
            green=c[...,1].astype(int)-np.maximum(c[...,0],c[...,2]).astype(int)>15
            allowed=fg.copy();allowed[:poses[k]['tete_protegee_jusqua_y']]=False
            # Une modification de silhouette ou de raccord requiert une revue visuelle séparée.
            used=allowed & ~green
            result=Image.composite(raw,base,Image.fromarray(used.astype('uint8')*255))
            assert np.array_equal(np.array(result)[~allowed],b[~allowed])
            dest=RACINE/protocol['temoins'][k];dest.parent.mkdir(parents=True,exist_ok=True);result.save(dest)
            report.append({'pose':k,'brut_sha256':sha(RACINE/path),'source_sha256':sha(RACINE/poses[k]['image']),
                           'pixels_verts_exclus':int((allowed&green).sum()),'differences_hors_zone':0,
                           'statut':'compose_a_controler_visuellement'})
        (out/'temoins.json').write_text(json.dumps(report,indent=2)+'\n')
    elif a.operation == 'propager':
        ref = protocol['reference']; image = normaliser(Image.open(RACINE/protocol['image_reference']))
        report=[]
        for k,path in protocol['temoins'].items():
            witness = normaliser(Image.open(RACINE/path))
            warped, coverage = propager(image,poses[ref]['points'],poses[k]['points'],triangles)
            result,qc = composer_robe(witness,warped,masks[k]['robe'],coverage)
            result.save(out/f'hybride_{k}.png'); witness.save(out/f'temoin_{k}.png')
            coverage.save(out/f'couverture_{k}.png')
            report.append({'pose':k,'controle':qc,'temoin_sha256':sha(RACINE/path)})
        (out/'propagation.json').write_text(json.dumps({'images':report,
            'limite':'Matière et éclairage de 9 transportés en 2D. Validation artistique requise.',
            'protocole_sha256':sha(RACINE/a.protocole)},indent=2)+'\n')
    elif a.operation == 'apercus':
        import runpy
        import shutil
        helper=runpy.run_path(str(RACINE/'travail/test/decor_geometrique_essai/incruster_fond_vert.py'))
        bg=Image.open(RACINE/'refs/decor_geometrique_v4/apercu_F001.png').convert('RGBA').resize((720,1280))
        keys=list(protocol['temoins']);board=Image.new('RGB',(1080,len(keys)*680),'white');draw=ImageDraw.Draw(board)
        for col,title in enumerate(('Flow','Temoin Nano','Robe propagee / memes membres')):draw.text((col*360+5,5),title,fill='black')
        for row,k in enumerate(keys):
            flow=RACINE/f'travail/test/src/s{int(k):04}.png'
            board.paste(normaliser(Image.open(flow)).resize((360,640)),(0,row*680+35))
            draw.text((5,row*680+20),f'Pose {k}',fill='black')
            for col,variant in enumerate(('temoin','hybride'),1):
                image=Image.open(out/f'{variant}_{k}.png')
                layer,_=helper['detourer'](image)
                composed=Image.alpha_composite(bg,layer).convert('RGB')
                board.paste(composed.resize((360,640)),(col*360,row*680+35))
                plan=RACINE/f'travail/pilote_{variant}_monte'
                for folder in ('src','out'): (plan/folder).mkdir(parents=True,exist_ok=True)
                shutil.copyfile(flow,plan/f'src/s{int(k):04}.png')
                composed.save(plan/f'out/r{int(k):04}.png')
        manifest={'video':'entree/source_animation.mp4','fps':24,'pas':3,
            'debut_s':(int(keys[0])-1)/8,'duree_s':len(keys)/8,
            'frames':[{'index':int(k),'fichier':f's{int(k):04}.png','frame_source':(int(k)-1)*3} for k in keys]}
        for variant in ('temoin','hybride'):
            (RACINE/f'travail/pilote_{variant}_monte/manifeste.json').write_text(json.dumps(manifest,indent=2)+'\n')
        board.save(RACINE/'sortie/pilote_propagation_planche.png')
    else:
        keys=protocol['ordre_mesure']
        if any(not poses[k].get('panneaux') for k in keys):
            p.error('Polygones de panneaux requis pour chaque pose; ne pas mesurer la robe entière comme un panneau')
        # Les domaines sont fixés par les bases, jamais par les sorties texturées.
        for name,paths in protocol['series'].items():
            if len(paths)!=len(keys): p.error(f'Série incomplète : {name}')
        series={name:[normaliser(Image.open(RACINE/path)) for path in paths]
                for name,paths in protocol['series'].items()}
        results={}
        for panel in ('rouge','bleu','jaune','ivoire'):
            domains=[]
            for k in keys:
                panel_mask=masque(poses[k]['panneaux'][panel]).filter(ImageFilter.MinFilter(5))
                common=np.minimum(np.array(panel_mask),np.array(masks[k]['robe']))
                domains.append(Image.fromarray(common))
            rows=mesurer(series,domains,[poses[k]['points'] for k in keys],triangles)
            for i,(_,domain) in enumerate(rows):domain.save(out/f'domaine_commun_{panel}_{i}.png')
            results[panel]=[v[0] for v in rows]
        (out/'mesures.json').write_text(json.dumps({'panneaux':results,
            'geometrie_independante':{k:geometrie(poses[k]['controle_flow'],poses[k]['controle_dessin'],poses[k]['points'])
                if 'controle_flow' in poses[k] and 'controle_dessin' in poses[k] else 'non renseignée : aucune validation géométrique'
                for k in keys},
            'limite':'Mesure conditionnée au maillage. Ne valide pas sa géométrie; pas de flux optique indépendant disponible.',
            'protocole_sha256':sha(RACINE/a.protocole)},indent=2)+'\n')

if __name__=='__main__':main()
