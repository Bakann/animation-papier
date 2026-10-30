"""Recettes ComfyUI gratuites et contrôles du bloc correctif facultatif."""
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request
import uuid
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def verifier_calage(image, cfg):
    if list(image.size)!=cfg['taille_source']:raise ValueError('Dimensions source différentes du calage')
    x,y,w,h=cfg['crop_xywh'];l,t,r,b=cfg['rectangle_retouche_dans_crop']
    if min(x,y)<0 or min(w,h)<=0 or x+w>image.width or y+h>image.height:
        raise ValueError('Crop hors du cadre')
    if not (0<=l<r<=w and 0<=t<b<=h):raise ValueError('Rectangle de retouche hors du crop')


def masque_detail(image, cfg):
    verifier_calage(image,cfg)
    x,y,w,h=cfg['crop_xywh']
    crop=image.crop((x,y,x+w,y+h)).convert('RGB')
    mask=Image.new('L',(w,h));ImageDraw.Draw(mask).rounded_rectangle(
        tuple(cfg['rectangle_retouche_dans_crop']),radius=cfg['rayon_coins'],fill=255)
    mask=mask.filter(ImageFilter.GaussianBlur(cfg['raccord_px']))
    arr=np.array(crop);values=np.array(mask)
    values[arr[...,1].astype(int)-np.maximum(arr[...,0],arr[...,2]).astype(int)>=5]=0
    full_y=y+np.arange(h)
    values[full_y>=cfg['preserver_depuis_y']]=0
    return Image.fromarray(values)


def finaliser_export(source, export_comfy, mask, cfg):
    x,y,w,h=cfg['crop_xywh']
    full=Image.new('L',source.size);full.paste(mask,(x,y))
    a=np.array(source);b=np.array(export_comfy.convert('RGB'));outside=np.array(full)==0
    if a.shape!=b.shape:raise ValueError('Taille de sortie inattendue')
    delta=np.abs(a.astype(int)-b.astype(int))
    if delta[outside].size and delta[outside].max()>1:raise ValueError('Altération hors masque supérieure à un arrondi')
    arrondis=int(np.any(a!=b,axis=2)[outside].sum())
    b[outside]=a[outside]
    if not np.array_equal(a[cfg['preserver_depuis_y']:],b[cfg['preserver_depuis_y']:]):
        raise ValueError('Semelle modifiée')
    return Image.fromarray(b),full,arrondis


def recettes(cfg):
    def node(kind,inputs,title):return {'class_type':kind,'inputs':inputs,'_meta':{'title':title}}
    x,y,w,h=cfg['crop_xywh']
    preparation={
      '1':node('LoadImage',{'image':'__SOURCE__'},'Frame à corriger'),
      '2':node('ImageCrop',{'image':['1',0],'width':w,'height':h,'x':x,'y':y},'Gros plan cible — coordonnées manuelles'),
      '3':node('SaveImage',{'images':['2',0],'filename_prefix':'kirigami_couture/correctif/crop'},'Exporter cible pour Google direct')}
    insertion={
      '1':node('LoadImage',{'image':'__SOURCE__'},'Frame originale à conserver'),
      '2':node('LoadImage',{'image':'__RETOUCHE__'},'Retouche du gros plan — Google ou outil intégré'),
      '3':node('LoadImage',{'image':'__MASQUE__'},'Masque du détail seulement'),
      '4':node('ImageScale',{'image':['2',0],'upscale_method':'lanczos','width':w,'height':h,'crop':'disabled'},'Retour aux dimensions du crop'),
      '5':node('ImageToMask',{'image':['3',0],'channel':'red'},'Lire le masque doux'),
      '6':node('ImageCompositeMasked',{'destination':['1',0],'source':['4',0],
          'x':x,'y':y,'resize_source':False,'mask':['5',0]},'Réinsérer seulement le détail'),
      '7':node('SaveImage',{'images':['6',0],'filename_prefix':'kirigami_couture/correctif/frame'},'Exporter candidat à contrôler')}
    return preparation,insertion


class ComfyLocal:
    AUTORISES={'LoadImage','ImageCrop','SaveImage','ImageScale','ImageToMask','ImageCompositeMasked'}
    def __init__(self,url='http://127.0.0.1:8188'):self.url=url
    def http(self,route,data=None,headers=None):
        req=urllib.request.Request(self.url+route,data=data,headers=headers or {})
        with urllib.request.urlopen(req,timeout=30) as r:return r.read()
    def upload(self,path,folder,multipart):
        data,ct=multipart({'subfolder':folder,'type':'input','overwrite':'true'},[('image',path)])
        r=json.loads(self.http('/upload/image',data,{'Content-Type':ct}))
        return (r.get('subfolder','')+'/'+r['name']).lstrip('/')
    def executer(self,graph,dossier,output_node):
        if any(n['class_type'] not in self.AUTORISES for n in graph.values()):
            raise ValueError('Le bloc local refuse tout nœud payant ou inconnu')
        reply=json.loads(self.http('/prompt',json.dumps({'prompt':graph,'client_id':uuid.uuid4().hex}).encode(),{'Content-Type':'application/json'}))
        if reply.get('node_errors'):raise RuntimeError('Workflow local refusé : '+json.dumps(reply['node_errors']))
        pid=reply['prompt_id'];(dossier/'prompt_id_local.txt').write_text(pid+'\n')
        for _ in range(60):
            hist=json.loads(self.http('/history/'+pid))
            if pid in hist:break
            time.sleep(1)
        else:raise RuntimeError('Tâche locale en attente; identifiant conservé, pas de resoumission')
        h=hist[pid]
        if h.get('status',{}).get('status_str')!='success':raise RuntimeError('Exécution locale échouée')
        im=h['outputs'][output_node]['images'][0]
        return self.http('/view?'+urllib.parse.urlencode(im)),pid
