"""Normalisation du cadre entier commune aux variantes du pilote et à son montage."""
from PIL import Image, ImageOps


def normaliser(image, taille=(720, 1280)):
    return ImageOps.pad(image.convert('RGB'), taille, method=Image.Resampling.LANCZOS,
                        color=(0, 255, 0))
