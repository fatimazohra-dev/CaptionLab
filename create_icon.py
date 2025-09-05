from PIL import Image, ImageDraw, ImageFont
import os

def create_icon():
    # Créer une image 256x256 avec fond transparent
    img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Dessiner un cercle bleu
    draw.ellipse([20, 20, 236, 236], fill='#2196F3')
    
    # Ajouter le texte "CL"
    try:
        font = ImageFont.truetype("arial.ttf", 120)
    except:
        font = ImageFont.load_default()
    
    draw.text((80, 60), "CL", fill='white', font=font)
    
    # Sauvegarder en .ico
    img.save('icon.ico', format='ICO')

if __name__ == '__main__':
    create_icon() 