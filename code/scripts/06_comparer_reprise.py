"""Planche locale Flow/base/ancien brut Comfy/reprise Google, sans appel API."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from normalisation import normaliser


def main():
    root = Path(__file__).resolve().parents[1]
    out = root/'travail/pilote_temoin_10_12/out'
    archives = sorted((out/'_anciennes').glob('r0010_*.png'), key=lambda p:p.stat().st_mtime)
    if not archives:
        raise SystemExit('Ancienne version manquante')
    paths = [root/'travail/test/src/s0010.png', root/'travail/pilote_temoin_10_12/src/s0010.png',
             archives[-1], out/'r0010.png']
    titles = ['Flow', 'Base Nano', 'Ancien brut Comfy', 'Reprise Google directe']
    board = Image.new('RGB',(1440,1060),'white')
    draw = ImageDraw.Draw(board)
    font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',20)
    for col,(path,title) in enumerate(zip(paths,titles)):
        im = normaliser(Image.open(path))
        board.paste(im.resize((360,640)),(col*360,40))
        draw.text((col*360+5,8),title,font=font,fill='black')
        crop = im.crop((290,1030,490,1280))
        board.paste(crop.resize((280,350)),(col*360+40,700))
    board.save(root/'sortie/reprise10_google_comparatif.png')

if __name__=='__main__':main()
