"""Bloc correctif : Comfy crop -> 02_redessiner Google direct -> Comfy insertion.

La génération est une action explicite; préparer/appliquer ne font aucun appel payant.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import hashlib
import shutil
import subprocess
import sys
from PIL import Image
from commun import RACINE, journaliser
from correctif_detail import ComfyLocal, verifier_calage, masque_detail, finaliser_export, recettes


def charger_script(name):
    spec=importlib.util.spec_from_file_location(name.replace('.','_'),RACINE/'scripts'/name)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['preparer','appliquer','generer'],nargs='?',default='preparer')
    p.add_argument('--config',default='configs/correctif_boucle_pose10.json')
    p.add_argument('--essai',required=True)
    p.add_argument('--retouche',help='image déjà retouchée à insérer; action appliquer seulement')
    p.add_argument('--oui',action='store_true',help='uniquement pour une génération explicitement autorisée')
    a=p.parse_args();cfg=json.loads((RACINE/a.config).read_text())
    if not cfg.get('actif',False):return print('Bloc désactivé : frame originale conservée; 0 appel.')
    if not a.essai.replace('-','').replace('_','').isalnum():p.error('Nom d’essai invalide')
    name='correctif_'+a.essai;root=RACINE/'travail'/name
    if root.exists():p.error('Essai existant : nom distinct requis pour conserver les résultats')
    source=RACINE/cfg['source'];master=RACINE/cfg['master']
    image=Image.open(source).convert('RGB');verifier_calage(image,cfg)
    root.mkdir(parents=True);(root/'src').mkdir();(root/'local').mkdir()
    sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
    protocol={'config':a.config,'config_sha256':sha(RACINE/a.config),'source':cfg['source'],
        'source_sha256':sha(source),'master_sha256':sha(master),'action':a.action,'nouveaux_appels_payants':0,
        'statut':'preparation','validation_artistique':'requise après exécution'}
    (root/'protocole.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    client=ComfyLocal();redessin=charger_script('02_redessiner.py');interface=charger_script('07_guide_chaussure_comfy.py')
    replacements={}
    for token,path in [('__SOURCE__',source)]:
        replacements[token]=client.upload(path,'kirigami_couture/'+name,redessin.multipart)
    mask=masque_detail(image,cfg);mask.save(root/'masque_detail.png')
    replacements['__MASQUE__']=client.upload(root/'masque_detail.png','kirigami_couture/'+name,redessin.multipart)
    prep,insert=recettes(cfg)
    def resolve(graph):
        graph=json.loads(json.dumps(graph))
        for node in graph.values():
            for key,value in node['inputs'].items():
                if isinstance(value,str) and value in replacements:node['inputs'][key]=replacements[value]
        return graph
    def export(graph,tag):
        schemas={kind:json.loads(client.http('/object_info/'+kind))[kind] for kind in {n['class_type'] for n in graph.values()}}
        ui=interface.exporter_interface(graph,schemas)
        # Groupes importables et faciles à reconnaître dans une recette principale.
        ui['groups']=[{'title':'Correctif facultatif — '+tag,'bounding':[0,-50,3200,1350],'color':'#536b85','font_size':24,'flags':{}}]
        (RACINE/f'workflows/correctif_detail_{tag}.json').write_text(json.dumps(ui,ensure_ascii=False,indent=2)+'\n')
        (root/f'workflow_{tag}_api.json').write_text(json.dumps(graph,ensure_ascii=False,indent=2)+'\n')
    prep=resolve(prep);export(prep,'preparation')
    data,pid=client.executer(prep,root/'local','3');(root/'src/s0010.png').write_bytes(data)
    # Rétablit les pixels exacts du crop si SaveImage introduit seulement un arrondi.
    x,y,w,h=cfg['crop_xywh'];expected=image.crop((x,y,x+w,y+h))
    saved=Image.open(root/'src/s0010.png').convert('RGB')
    import numpy as np
    if saved.size!=expected.size or np.abs(np.array(saved,dtype=int)-np.array(expected,dtype=int)).max()>1:
        raise RuntimeError('Le crop Comfy ne correspond pas au cadre demandé')
    shutil.copyfile(root/'src/s0010.png',root/'crop_brut_comfy.png');expected.save(root/'src/s0010.png')
    shutil.copyfile(master,root/'master.png');shutil.copyfile(RACINE/cfg['prompt'],root/'prompt.txt')
    generation={'backend':'gemini','modele':cfg['modele'],'qualite':cfg['qualite'],
      'taille':cfg['aspect_ratio']+' / '+cfg['qualite'],'gemini_aspect_ratio':cfg['aspect_ratio'],
      'ancre':str((root/'master.png').relative_to(RACINE)),
      'prompt':str((root/'prompt.txt').relative_to(RACINE)),
      'cout_estime_usd_par_image':cfg['cout_estime_usd_par_image']}
    config_gen=root/'generation.json';config_gen.write_text(json.dumps(generation,ensure_ascii=False,indent=2)+'\n')
    protocol['prompt_id_preparation']=pid
    (root/'protocole.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    if a.action=='preparer':
        export(insert,'reinsertion_gabarit')
        return print(f'Crop, masque et configuration préparés dans {root}; 0 génération payante.')
    if a.action=='generer':
        cmd=[sys.executable,str(RACINE/'scripts/02_redessiner.py'),'--plan',name,'--config',str(config_gen.relative_to(RACINE))]
        if a.oui:cmd.append('--oui')
        subprocess.run(cmd,check=True)
        edited=root/'out/r0010.png'
    else:edited=RACINE/(a.retouche or cfg['retouche_test_existante'])
    if not edited.exists():raise ValueError('Image retouchée absente')
    shutil.copyfile(edited,root/'retouche_brute.png')
    replacements['__RETOUCHE__']=client.upload(root/'retouche_brute.png','kirigami_couture/'+name,redessin.multipart)
    insert=resolve(insert);export(insert,'reinsertion')
    data,pid=client.executer(insert,root/'local','7');(root/'reinsertion_brute_comfy.png').write_bytes(data)
    final,fullmask,rounding=finaliser_export(image,Image.open(root/'reinsertion_brute_comfy.png'),mask,cfg)
    final.save(root/'frame_corrigee.png');fullmask.save(root/'masque_plein_cadre.png')
    if sha(source)!=protocol['source_sha256']:raise RuntimeError('La source originale a changé')
    protocol.update({'statut':'execute_a_controler_visuellement','sortie':str((root/'frame_corrigee.png').relative_to(RACINE)),
      'source_preservee':True,'differences_hors_masque':0,'arrondis_export_comfy':rounding,
      'prompt_id_reinsertion':pid,'retouche_sha256':sha(edited),'sortie_sha256':sha(root/'frame_corrigee.png'),
      'nouveaux_appels_payants':1 if a.action=='generer' else 0,
      'limite':'Réutilisation d’une image intégrée pour le test local ne valide pas le rendu de Gemini direct.'})
    (root/'protocole.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    journaliser(root/'journal.jsonl',{'type':'bloc_correctif_local',**protocol})
    print(json.dumps(protocol,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
