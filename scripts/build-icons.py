"""Render brand-mark.svg's round M/C strokes with Pillow; no extra dependency."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw

destination = Path(__file__).resolve().parent.parent / 'static' / 'images'
source = (destination/'brand-mark.svg').read_text(encoding='utf-8')
svg = ET.fromstring(source)
size = 2048
scale = size / 64
mark = Image.new('RGBA', (size, size))
draw = ImageDraw.Draw(mark)
for path in svg.findall('.//{http://www.w3.org/2000/svg}path'):
    tokens = re.findall(r'[A-Za-z]|-?\d+(?:\.\d+)?', path.attrib['d'])
    points = []
    cursor = 0
    while cursor < len(tokens):
        command = tokens[cursor]
        cursor += 1
        if command == 'M':
            start = tuple(map(float, tokens[cursor:cursor+2]))
            points.append(start)
            cursor += 2
        elif command == 'C':
            values = list(map(float, tokens[cursor:cursor+6]))
            control1, control2, end = values[:2], values[2:4], values[4:]
            for step in range(1, 101):
                t = step / 100
                points.append(tuple((1-t)**3*start[i] + 3*(1-t)**2*t*control1[i]
                                    + 3*(1-t)*t*t*control2[i] + t**3*end[i] for i in (0, 1)))
            start = end
            cursor += 6
        else:
            raise ValueError(f'Unsupported SVG command: {command}')
    points = [(x*scale, y*scale) for x,y in points]
    width = round(float(path.attrib['stroke-width'])*scale)
    color = svg.find('{http://www.w3.org/2000/svg}g').attrib['stroke']
    # Pillow's curved joins on densely sampled short segments can cut pale
    # wedges into a thick stroke. Union round brush stamps instead: each stamp
    # only adds color, leaving a solid stroke with round joins and end caps.
    radius = width/2
    for x,y in points:
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color)

def tile(background=True, inset=0):
    image = Image.new('RGBA', (size,size), '#f2e9db' if background else None)
    if not background:
        ImageDraw.Draw(image).rounded_rectangle((0,0,size-1,size-1),radius=size*15/64,fill='#f2e9db')
    if inset:
        reduced = mark.resize((size-2*inset, size-2*inset), Image.Resampling.LANCZOS)
        image.alpha_composite(reduced, (inset,inset))
    else:
        image.alpha_composite(mark)
    return image

favicon = tile(background=False)
favicon.resize((32,32), Image.Resampling.LANCZOS).save(destination/'favicon-32.png')
favicon.resize((64,64), Image.Resampling.LANCZOS).save(destination/'favicon.ico',format='ICO',sizes=[(16,16),(32,32),(48,48)])
app_icon = tile().convert('RGB')
for name, pixels in [('app-192.png',192),('app-512.png',512),('apple-touch-icon.png',180)]:
    app_icon.resize((pixels,pixels), Image.Resampling.LANCZOS).save(destination/name)
# Keep the entire symbol inside the maskable icon's central safe circle.
tile(inset=192).convert('RGB').resize((512,512),Image.Resampling.LANCZOS).save(destination/'app-maskable-512.png')
(destination/'favicon.svg').write_text(source.replace('fill="none">', 'fill="none">\n  <rect width="64" height="64" rx="15" fill="#f2e9db"/>', 1), encoding='utf-8')
print('Iconos de Canela preparados.')
