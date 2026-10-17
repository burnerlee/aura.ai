import json
layers = json.load(open('layers.json'))
css = open('app.clean.css').read()
tl = open('timeline.json').read()
tpl = open('scripts/video.tpl.html').read()
divs = ''.join(f'<div class="layer" id="L-{k}"><div id="root">{v}</div></div>' for k, v in layers.items())
out = tpl.replace('/*APPCSS*/', css).replace('<!--LAYERS-->', divs).replace('/*TIMELINE*/', tl)
open('video.html', 'w').write(out)
print('ok', len(out))
