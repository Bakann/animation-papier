"""Prépare les entrées du pilote sans API; conserve les annotations déjà éditées."""
from pathlib import Path
import json,shutil,hashlib
R=Path(__file__).resolve().parents[1];D=R/'travail/pilote_amelioration';D.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,data):
 text=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
 if p.exists():
  if 'annotations' in p.parts or p.name in ('protocole.json','inventaire.json'): return
  assert p.read_text()==text, f'Préparation existante différente : {p}'
 else:p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
manifest=json.loads((R/'travail/test/manifeste.json').read_text())
def plan(name,config,indices,source):
 dest=R/'travail'/name
 (dest/'src').mkdir(parents=True,exist_ok=True)
 for i in indices:
  src=R/source/f'{"r" if "out" in source else "s"}{i:04}.png';target=dest/f'src/s{i:04}.png'
  if target.exists():assert sha(target)==sha(src)
  else:shutil.copyfile(src,target)
 m={**manifest,'frames':[v for v in manifest['frames'] if v['index'] in indices],
    'debut_s':(min(indices)-1)/8,'duree_s':len(indices)/8}
 write(dest/'manifeste.json',m)
 config['comfy_sous_dossier']='kirigami_couture/'+name
 config['normalisation']='pillow'
 write(R/f'configs/{name}.json',config)
 return dest
cfg=json.loads((R/'configs/test_nano_matiere9.json').read_text())
plan('pilote_temoin_10_12',cfg,[10,11,12],'travail/test_nano_banana_pro/out')
base=json.loads((R/'configs/reprise_base_nano_costume.json').read_text())
original=(R/base['prompt']).read_text()
paragraph='Translate only the main fold indications visible in IMAGE 1 into shallow paper curvature and relief. Preserve their positions and directions. Do not multiply ridges, add decorative folds, or turn a shadow into a cut. Keep every coloured panel and black strip continuous and intact.'
# Les deux variantes sont identiques hormis ce paragraphe ajouté à B.
for variant in ('a','b'):
 prompt=D/f'prompt_base_{variant}.txt'
 text=original if variant=='a' else original+'\n\nFOLD TRANSLATION: '+paragraph+'\n'
 if prompt.exists():assert prompt.read_text()==text
 else:prompt.write_text(text)
 for rep in (1,2):
  c={**base,'prompt':str(prompt.relative_to(R)),'grain':0}
  plan(f'pilote_ab_{variant}_{rep}',c,[6],'travail/test_nano_banana_pro/src')
# Correspondances initiales manuelles : ne deviennent utilisables qu'après inspection des overlays.
rows={
'9':[[[274,270],[350,258],[397,263],[494,270]],[[290,325],[375,325],[435,325],[484,325]],[[276,575],[368,581],[439,583],[478,583]],[[300,772],[358,772],[421,790],[464,790]],[[314,811],[360,810],[418,831],[453,823]]],
'10':[[[272,280],[349,267],[400,270],[493,280]],[[289,335],[375,335],[436,335],[483,335]],[[269,583],[363,591],[435,595],[478,591]],[[293,785],[349,781],[416,802],[463,799]],[[307,824],[353,821],[412,844],[453,835]]],
'11':[[[272,274],[348,262],[399,267],[493,276]],[[288,328],[376,328],[435,328],[482,328]],[[272,577],[365,586],[435,588],[478,585]],[[296,786],[352,780],[418,797],[464,797]],[[310,826],[357,819],[413,839],[454,834]]],
'12':[[[273,270],[351,256],[399,262],[494,268]],[[289,325],[375,325],[436,325],[483,325]],[[269,576],[361,582],[435,585],[478,585]],[[273,784],[346,786],[421,790],[477,792]],[[274,824],[347,825],[422,829],[475,830]]],
}
tri=[]
for y in range(4):
 for x in range(3):
  a,b,c,d=[f'p{yy}{xx}' for yy,xx in ((y,x),(y,x+1),(y+1,x),(y+1,x+1))]
  tri.extend([[a,b,c],[b,d,c]])
for k,rr in rows.items():
 points={f'p{y}{x}':pt for y,row in enumerate(rr) for x,pt in enumerate(row)}
 poly=rr[0]+[row[-1] for row in rr[1:]]+list(reversed(rr[-1][:-1]))+[row[0] for row in reversed(rr[1:-1])]
 ann={'image':f'travail/test_nano_banana_pro/out/r{int(k):04}.png','repere':'720x1280, cadre entier',
 'statut':'brouillon_manuel_a_controler','tete_protegee_jusqua_y':285,'points':points,'elements':{
 'robe':[poly],
 'tete':[[[300,50],[470,50],[470,253],[300,253]]],
 'bras_mains':[[[235,280],[272,280],[285,350],[270,580],[262,700],[280,730],[272,765],[226,742]],[[495,280],[521,280],[529,550],[540,640],[519,698],[477,692],[487,655],[495,590]]],
 'jambes_chaussures':[[[278,845],[476,845],[476,1270],[278,1270]]]},
 'limite':'Polygones de protection et points provisoires; pas une segmentation validée ni un contrôle anatomique.'}
 def poly(*keys):return [points[key] for key in keys]
 ann['panneaux']={'rouge':[poly('p10','p12','p22','p20')],'bleu':[poly('p02','p03','p13','p12')],'jaune':[poly('p30','p31','p32','p33','p43','p42','p41','p40')],'ivoire':[poly('p00','p01','p11','p10'),poly('p12','p13','p23','p22'),poly('p20','p22','p32','p31','p30')]}
 write(D/f'annotations/{k}.json',ann)
protocol={'sortie':'travail/pilote_amelioration/controle','reference':'9',
 'image_reference':'travail/essai_relief/nano_relief_tete_preservee.png',
 'annotations':{k:f'travail/pilote_amelioration/annotations/{k}.json' for k in rows},
 'annotations_controlees_codex':False,'triangles':tri,
 'bruts_temoins':{k:f'travail/pilote_temoin_10_12/out/r{int(k):04}.png' for k in ('10','11','12')},
 'temoins':{k:f'travail/pilote_amelioration/controle/protege_{k}.png' for k in ('10','11','12')},
 'ordre_mesure':['10','11','12'],
 'series':{name:[f'travail/pilote_amelioration/controle/{name}_{k}.png' for k in ('10','11','12')] for name in ('temoin','hybride')}}
write(D/'protocole.json',protocol)
write(D/'inventaire.json',{'autorisation':'l’auteur : implement this plan', 'appels_effectues':0,
 'temoins':{'images':3,'estimation_usd':0.4824},'ab_pose6':{'images':4,'estimation_usd':0.6432},
 'source_reference_sha256':sha(R/protocol['image_reference']),
 'arrets':['Après propagation 10–12 : l’auteur','Après quatre bases A/B6 : l’auteur','Avant extension 16 : l’auteur']})
print('Témoins, quatre essais A/B et annotations provisoires préparés; 0 appel API.')
