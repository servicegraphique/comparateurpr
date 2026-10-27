import sys, re
src_path, out = sys.argv[1], sys.argv[2]
s = open(src_path).read()
repl = {
 'https://ajax.googleapis.com/ajax/libs/webfont/1.6.26/webfont.js': '/conversion/vendor/webfont.js',
 'https://d3e54v103j8qbb.cloudfront.net/js/jquery-3.5.1.min.dc5e7f18c8.js?site=65cdd89a107bcefe374dd647': '/conversion/vendor/jquery.min.js',
 'https://cdn.jsdelivr.net/gh/videsigns/webflow-tools@latest/multi-step.js': '/conversion/vendor/multi-step.js',
 'https://cdnjs.cloudflare.com/ajax/libs/jquery.inputmask/5.0.9-beta.45/jquery.inputmask.min.js': '/conversion/vendor/inputmask.min.js',
 'https://cdn.jsdelivr.net/npm/lumious-components@latest/component/ticker.js': '/conversion/vendor/ticker.js',
}
for k, v in repl.items():
    s = s.replace(k, v)
rest = re.findall(r'<script[^>]*src="(https?://[^"]+)"', s)
open(out, 'w').write(s)
print("écrite:", out, "| srcs distantes restantes:", rest)
