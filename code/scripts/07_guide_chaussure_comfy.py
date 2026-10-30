"""Préparation locale geometrique par nœuds ComfyUI natifs. Aucun nœud payant."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time
import urllib.parse
import urllib.request
from PIL import Image, ImageDraw, ImageOps
import numpy as np

from commun import RACINE
from normalisation import normaliser

MASTER = Path('~/oct/geometrique/essai_kirigami/preparation/chaussure_nette_pour_guides.png')
AUTORISES = {'LoadImage','ImageScale','InvertMask','MaskToImage','ImageToMask',
             'CropMask','MaskComposite','ImageCompositeMasked','SaveImage','SolidMask'}


def proteger_export(base, guide, allowed):
    b,g=np.array(base),np.array(guide)
    outside=np.abs(b.astype(int)-g.astype(int))[~allowed]
    if outside.size and outside.max()>1:
        raise ValueError('Modification hors masque dépassant un arrondi de quantification')
    raw_changes=int(np.any(b!=g,axis=2)[~allowed].sum())
    g[~allowed]=b[~allowed]
    return Image.fromarray(g),raw_changes


def workflow(x, y, width, height, semelle=False):
    def node(kind, inputs, title):return {'class_type':kind,'inputs':inputs,'_meta':{'title':title}}
    def scale(image):return {'image':image,'upscale_method':'lanczos','width':width,'height':height,'crop':'disabled'}
    graph={
        '1':node('LoadImage',{'image':'__BASE__'},'Pose cible — cadre entier 720 × 1280'),
        '2':node('LoadImage',{'image':'__MASQUE_FLOW__'},'Silhouette Flow — autorité géométrique'),
        '3':node('LoadImage',{'image':'__MASTER__'},'Escarpin master transparent — aspect seulement'),
        '4':node('ImageToMask',{'image':['2',0],'channel':'red'},'Lire la silhouette Flow'),
        '5':node('InvertMask',{'mask':['3',1]},'Alpha du master (LoadImage inverse la transparence)'),
        '6':node('MaskToImage',{'mask':['5',0]},'Préparer alpha'),
        '7':node('ImageScale',scale(['3',0]),'Échelle du master — calage manuel'),
        '8':node('ImageScale',scale(['6',0]),'Même échelle pour alpha'),
        '9':node('ImageToMask',{'image':['8',0],'channel':'red'},'Alpha redimensionné'),
        '10':node('CropMask',{'mask':['4',0],'x':x,'y':y,'width':width,'height':height},'Silhouette à la position du pied'),
        '11':node('MaskComposite',{'destination':['10',0],'source':['9',0],'x':0,'y':0,'operation':'multiply'},'Intersection master × silhouette Flow'),
        '12':node('ImageCompositeMasked',{'destination':['1',0],'source':['7',0],
            'x':x,'y':y,'resize_source':False,'mask':['11',0]},'Guide chaussure — pixels extérieurs conservés'),
        '13':node('SaveImage',{'images':['12',0],'filename_prefix':'kirigami_couture/chaussure_master/guide'},'Exporter le guide gratuit'),
        '14':node('SolidMask',{'value':0.0,'width':720,'height':1280},'Masque plein cadre vide'),
        '15':node('MaskComposite',{'destination':['14',0],'source':['11',0],'x':x,'y':y,'operation':'add'},'Zone de modification autorisée'),
        '16':node('MaskToImage',{'mask':['15',0]},'Afficher le masque final'),
        '17':node('SaveImage',{'images':['16',0],'filename_prefix':'kirigami_couture/chaussure_master/masque'},'Exporter le masque de contrôle')}
    if semelle:
        graph['11']=node('SolidMask',{'value':0.0,'width':width,'height':height},'Semelle visible : conserver le pied source sans boucle')
    return graph


def verifier_graphe(graph):
    if any(n['class_type'] not in AUTORISES for n in graph.values()):
        raise ValueError('Nœud non autorisé dans le prétraitement gratuit')


def exporter_interface(graph, schemas):
    """Format de workflow graphique ComfyUI 0.4, avec connexions typées."""
    positions={'1':[0,0],'2':[0,330],'3':[0,660],'4':[360,330],
        '5':[360,660],'6':[720,660],'7':[1080,0],'8':[1080,660],
        '9':[1440,660],'10':[1080,330],'11':[1800,330],'12':[2160,0],
        '13':[2520,0],'14':[1440,990],'15':[2160,660],'16':[2520,660],'17':[2880,660]}
    nodes={};links=[]
    for order,(nid,node) in enumerate(graph.items()):
        schema=schemas[node['class_type']]
        nodes[nid]={'id':int(nid),'type':node['class_type'],'title':node['_meta']['title'],
            'pos':positions[nid],'size':[320,230],'flags':{},'order':order,'mode':0,
            'inputs':[],'outputs':[{'name':name,'type':name,'links':[]} for name in schema['output']],
            'properties':{'Node name for S&R':node['class_type']},'widgets_values':[]}
    for nid,node in graph.items():
        schema=schemas[node['class_type']]; specs={**schema['input'].get('required',{}),**schema['input'].get('optional',{})}
        for name,value in node['inputs'].items():
            if isinstance(value,list):
                origin,slot=value;linkid=len(links)+1;inputslot=len(nodes[nid]['inputs'])
                typ=specs[name][0]
                nodes[nid]['inputs'].append({'name':name,'type':typ,'link':linkid})
                nodes[origin]['outputs'][slot]['links'].append(linkid)
                links.append([linkid,int(origin),slot,int(nid),inputslot,typ])
            else:nodes[nid]['widgets_values'].append(value)
    return {'last_node_id':max(map(int,graph)),'last_link_id':len(links),
            'nodes':list(nodes.values()),'links':links,'groups':[],
            'config':{},'extra':{'ds':{'scale':0.5,'offset':[30,30]}},'version':0.4}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--index',type=int,default=10)
    p.add_argument('--x',type=int,default=352);p.add_argument('--y',type=int,default=1151)
    p.add_argument('--largeur',type=int,default=84);p.add_argument('--hauteur',type=int,default=86)
    p.add_argument('--angle',type=float,default=0)
    p.add_argument('--semelle',action='store_true')
    p.add_argument('--fragment-dessus',action='store_true',help='Retient le dessus et la boucle; écarte semelle et talon du master')
    p.add_argument('--essai',default='initial',help='Nom distinct pour conserver chaque calage')
    p.add_argument('--calage',default='refs/chaussures_geometrique/calage_pose10.json')
    p.add_argument('--executer-local',action='store_true')
    a=p.parse_args()
    if min(a.x,a.y)<0 or min(a.largeur,a.hauteur)<1 or a.x+a.largeur>720 or a.y+a.hauteur>1280:
        p.error('Le rectangle doit rester dans le cadre 720 × 1280')
    if not a.essai.replace('_','').replace('-','').isalnum():p.error('Nom d’essai invalide')
    dest=RACINE/f'travail/guide_chaussure_{a.index:02d}_{a.essai}'
    dest.mkdir(parents=True,exist_ok=True)
    if (dest/'protocole.json').exists():p.error('Essai déjà présent : conserver les résultats et utiliser un autre dossier pour une variante')
    base_path=RACINE/f'travail/test_nano_banana_pro/out/r{a.index:04d}.png'
    flow_mask=RACINE/f'travail/test/cibles_vertes/masques/s{a.index:04d}.png'
    base=normaliser(Image.open(base_path));base.save(dest/'base.png')
    mask=Image.open(flow_mask).convert('L')
    if mask.size!=(720,1280):p.error('Masque Flow de dimensions inattendues')
    calage=json.loads((RACINE/a.calage).read_text())
    if calage['index']!=a.index or calage['cadre']!=[720,1280]:p.error('Un calage spécifique à cette pose est requis')
    zone=Image.new('L',(720,1280));ImageDraw.Draw(zone).polygon([tuple(v) for v in calage['polygone_chaussure_flow']],fill=255)
    mask=Image.fromarray(np.minimum(np.array(mask),np.array(zone)))
    mask.save(dest/'flow_mask.png')
    master=Image.open(MASTER).convert('RGBA')
    if a.fragment_dessus:
        alpha=np.array(master.getchannel('A'));alpha[110:]=0
        master.putalpha(Image.fromarray(alpha))
    if a.angle:master=master.rotate(a.angle,Image.Resampling.BICUBIC,expand=True)
    master.save(dest/'master.png')
    graph=workflow(a.x,a.y,a.largeur,a.hauteur,a.semelle);verifier_graphe(graph)
    template=RACINE/'workflows/guide_chaussure_master_local_api.json'
    template.write_text(json.dumps(graph,ensure_ascii=False,indent=2)+'\n')
    sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
    proto={'index':a.index,'parametres':vars(a),'source_base':str(base_path),'base_sha256':sha(base_path),
        'source_master':str(MASTER),'master_sha256':sha(MASTER),'masque_flow_sha256':sha(flow_mask),
        'calage_sha256':sha(RACINE/a.calage),
        'cout_api_usd':0,'statut':'prepare','controle_artistique':'candidat non validé',
        'limite':'Le calage est manuel par pose; masque de silhouette approximatif. Un master de face ne permet pas de reconstruire une semelle ou une vue absente.'}
    (dest/'protocole.json').write_text(json.dumps(proto,ensure_ascii=False,indent=2)+'\n')
    if not a.executer_local:
        return print('Workflow préparé; aucun appel API. Ajouter --executer-local au premier lancement pour le tester.')
    url='http://127.0.0.1:8188'
    def http(route,data=None,headers=None):
        req=urllib.request.Request(url+route,data=data,headers=headers or {})
        with urllib.request.urlopen(req,timeout=30) as r:return r.read()
    # Multipart local uniquement; pas de clé Comfy ni Google transmise.
    import importlib.util
    spec=importlib.util.spec_from_file_location('redessin_local',RACINE/'scripts/02_redessiner.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    replacements={}
    for token,name in [('__BASE__','base.png'),('__MASQUE_FLOW__','flow_mask.png'),('__MASTER__','master.png')]:
        body,ct=module.multipart({'subfolder':f'kirigami_couture/guide_{a.index:02d}_{a.essai}','type':'input','overwrite':'true'},[('image',dest/name)])
        reply=json.loads(http('/upload/image',body,{'Content-Type':ct}))
        replacements[token]=reply.get('subfolder','')+'/'+reply['name']
    for n in graph.values():
        for key,value in n['inputs'].items():
            if isinstance(value,str) and value in replacements:n['inputs'][key]=replacements[value]
    schemas={}
    for kind in sorted({n['class_type'] for n in graph.values()}):
        schemas[kind]=json.loads(http('/object_info/'+kind))[kind]
    (RACINE/'workflows/guide_chaussure_master_local.json').write_text(json.dumps(exporter_interface(graph,schemas),ensure_ascii=False,indent=2)+'\n')
    (dest/'workflow_execute.json').write_text(json.dumps(graph,ensure_ascii=False,indent=2)+'\n')
    reply=json.loads(http('/prompt',json.dumps({'prompt':graph}).encode(),{'Content-Type':'application/json'}))
    if reply.get('node_errors'):raise RuntimeError('Workflow local refusé : '+json.dumps(reply['node_errors']))
    pid=reply['prompt_id'];proto['prompt_id_local']=pid
    (dest/'protocole.json').write_text(json.dumps(proto,ensure_ascii=False,indent=2)+'\n')
    for _ in range(60):
        history=json.loads(http('/history/'+pid))
        if pid in history:break
        time.sleep(1)
    else:raise RuntimeError('Attente locale expirée : consulter le prompt_id, aucun appel payant envoyé')
    h=history[pid]
    if h.get('status',{}).get('status_str')!='success':raise RuntimeError('Exécution locale non réussie')
    for nid,name in [('13','guide.png'),('17','masque_autorise.png')]:
        im=h['outputs'][nid]['images'][0]
        (dest/name).write_bytes(http('/view?'+urllib.parse.urlencode(im)))
    guide=Image.open(dest/'guide.png').convert('RGB');allowed=np.array(Image.open(dest/'masque_autorise.png').convert('L'))>0
    shutil.copyfile(dest/'guide.png',dest/'guide_brut_comfy.png')
    guide,rounding=proteger_export(base,guide,allowed);guide.save(dest/'guide.png')
    b,g=np.array(base),np.array(guide);changed=np.any(b!=g,axis=2)
    assert not (changed&~allowed).any(),'Pixels hors masque modifiés'
    assert not (allowed&(np.array(mask)==0)).any(),'Masque débordant de la silhouette Flow'
    proto.update({'statut':'execute_localement','pixels_changes':int(changed.sum()),
                  'differences_hors_masque':0,'arrondis_brut_comfy_hors_masque':rounding,
                  'guide_sha256':sha(dest/'guide.png')})
    (dest/'protocole.json').write_text(json.dumps(proto,ensure_ascii=False,indent=2)+'\n')
    board=Image.new('RGB',(1080,940),'white');draw=ImageDraw.Draw(board)
    flow=Image.open(RACINE/f'travail/test/src/s{a.index:04d}.png').convert('RGB')
    for col,(title,im) in enumerate([('Flow',flow),('Base avant',base),('Guide master - candidat',guide)]):
        draw.text((col*360+5,8),title,fill='black');board.paste(im.resize((360,640)),(col*360,30))
        board.paste(im.crop((330,1110,450,1260)).resize((200,250)),(col*360+80,680))
    board.save(RACINE/'sortie/guide_chaussure_master_comparatif.png')
    plan=RACINE/f'travail/pilote_chaussure_master_{a.index:02d}'
    (plan/'src').mkdir(parents=True,exist_ok=True)
    source=plan/f'src/s{a.index:04d}.png'
    if source.exists() and sha(source)!=sha(dest/'guide.png'):
        raise ValueError('Une autre cible de finition est déjà préparée : ne pas la remplacer silencieusement')
    shutil.copyfile(dest/'guide.png',source)
    manifest={'video':'entree/source_animation.mp4','fps':24,'pas':3,
              'debut_s':(a.index-1)/8,'duree_s':1/8,
              'frames':[{'index':a.index,'fichier':source.name,'frame_source':(a.index-1)*3}]}
    (plan/'manifeste.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (plan/'provenance_guide.json').write_text(json.dumps({'guide':str(dest.relative_to(RACINE)/'guide.png'),
        'guide_sha256':sha(source),'calage_artistique':'non validé par l’auteur','cout_generation':0},ensure_ascii=False,indent=2)+'\n')
    print('Guide local exporté; 0 appel payant; pixels hors masque conservés. Calage artistique à vérifier.')

if __name__=='__main__':main()
