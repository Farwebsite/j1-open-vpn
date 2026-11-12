#!/usr/bin/python3
"""Personal J1 appliance controller. SPDX-License-Identifier: GPL-2.0"""
import base64, hashlib, hmac, html, http.server, ipaddress, json, os, re, secrets
import signal, socketserver, ssl, struct, subprocess, tarfile, threading, time, unicodedata, urllib.error, urllib.parse, urllib.request
import io, gzip, ctypes, ctypes.util
from pathlib import Path
STATE = Path(os.environ.get('J1_STATE', '/etc/j1'))
RUN = Path(os.environ.get('J1_RUN', '/run'))
LOCK = threading.RLock()
CSRF = secrets.token_hex(32)
RUNTIME = {'vpn': 'Iniciando', 'ddns': 'Sin configurar', 'ddns6': 'Desactivado', 'upnp': 'Comprobando...', 'scan': 'Pulsa Buscar redes', 'networks': []}
CSS = '''
:root{--bg:#000;--grp:#1c1c1e;--field:#2c2c2e;--sep:#38383a;--txt:#ebebf5;--mut:#8e8e93;--acc:#0a84ff;--grn:#30d158;--red:#ff453a;--yel:#ffd60a;--ease:cubic-bezier(.32,.72,0,1);color-scheme:dark}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}html{background:var(--bg)}
body{margin:0;background:var(--bg);color:var(--txt);font:17px/1.35 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif;-webkit-font-smoothing:antialiased;-webkit-text-size-adjust:100%}
a{color:var(--acc);text-decoration:none}p{margin:8px 0}h3{font-size:13px;font-weight:500;color:var(--mut);text-transform:uppercase;margin:24px 4px 6px}
.ic{width:20px;height:20px;fill:currentColor;flex:none}
.bar{display:flex;align-items:center;gap:12px;height:60px}.bar h1{flex:1;margin:0;font-size:21px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.clock{font-size:15px;font-weight:600}.bat{font-size:15px;font-weight:600;color:var(--grn)}.bat.low{color:var(--red)}
.status p,p.kv{display:flex;align-items:center;gap:10px;margin:7px 0}.status .m{color:var(--mut)}
.dot{width:10px;height:10px;border-radius:50%;flex:none}.dot.g{background:var(--grn)}.dot.y{background:var(--yel)}.dot.r{background:var(--red)}
nav .t{display:flex;color:var(--txt)}
.brand{color:var(--mut);font-size:14px;margin:4px 2px;line-height:1.5}
label{display:block;margin:16px 4px 6px;font-size:13px;color:var(--mut)}
input,select,textarea{width:100%;font:inherit;color:var(--txt);background:var(--field);border:1px solid transparent;border-radius:12px;padding:11px 14px;outline:none}
input:focus,select:focus,textarea:focus{border-color:var(--acc)}input::placeholder,textarea::placeholder{color:#636366}
label:has(input[type=checkbox]){display:flex;align-items:center;justify-content:space-between;flex-direction:row-reverse;gap:12px;color:var(--txt);font-size:17px;margin:12px 0}
input[type=checkbox]{appearance:none;-webkit-appearance:none;position:relative;width:51px;height:31px;padding:0;border:0;border-radius:99px;background:#39393d;flex:none;cursor:pointer;transition:background .25s}
input[type=checkbox]::after{content:"";position:absolute;top:2px;left:2px;width:27px;height:27px;border-radius:50%;background:#fff;box-shadow:0 2px 6px rgba(0,0,0,.3);transition:left .25s var(--ease)}
input[type=checkbox]:checked{background:var(--grn)}input[type=checkbox]:checked::after{left:22px}
button{display:block;width:100%;margin-top:16px;padding:13px;border:0;border-radius:14px;background:var(--acc);color:#fff;font:inherit;font-weight:600;cursor:pointer}
button:active{opacity:.7}.sec{background:var(--field);color:var(--txt)}.danger{background:#3a1616;color:var(--red)}
small,.muted{color:var(--mut);font-size:13px}form small{display:block;margin:8px 4px 0}
section>p{margin:12px 4px}section form{background:var(--grp);border-radius:16px;padding:2px 16px 16px;margin:12px 0}
details{margin:12px 4px}summary{cursor:pointer;color:var(--acc)}
code{background:var(--field);padding:1px 6px;border-radius:6px;font-size:.85em;overflow-wrap:anywhere}
.list{list-style:none;padding:0;margin:8px 0;background:var(--grp);border-radius:16px;overflow:hidden}
.list li{position:relative;display:flex;align-items:center;gap:12px;padding:10px 16px}.list li+li::before{content:"";position:absolute;top:0;right:0;left:58px;border-top:.5px solid var(--sep)}
.list .who{flex:1;min-width:0;overflow-wrap:anywhere}.list .who small{display:block}.list form{margin:0;padding:0;background:none}
.list .tile{width:30px;height:30px;border-radius:8px;display:grid;place-items:center;background:var(--field)}
.btn2{display:inline-flex;align-items:center;gap:6px;padding:7px 12px;border-radius:99px;background:var(--field);color:var(--txt);font-weight:600;font-size:15px}.btn2 .ic{width:17px;height:17px}
.list button{width:auto;margin:0;padding:7px 12px;border-radius:99px;font-size:15px}
.notice{position:fixed;z-index:30;top:10px;left:50%;width:min(92vw,420px);margin:0;padding:13px 16px;border-radius:16px;background:rgba(44,44,46,.94);-webkit-backdrop-filter:blur(20px);backdrop-filter:blur(20px);color:var(--txt);font-size:15px;box-shadow:0 10px 30px rgba(0,0,0,.5);transform:translate(-50%,0);animation:toast 6s var(--ease) forwards;pointer-events:none}
.notice::before{content:"\\2713";color:var(--grn);font-weight:700;margin-right:8px}.notice.err::before{content:"!";color:var(--red)}.notice.err{animation-duration:10s}
p.err{color:var(--red);margin:12px 4px}
@keyframes toast{0%{transform:translate(-50%,-140%)}8%,88%{transform:translate(-50%,0)}100%{transform:translate(-50%,-140%);visibility:hidden}}
footer{color:var(--mut);font-size:12px;text-align:center;padding:20px 16px 34px}footer p{margin:4px 0}
.tile{display:none}
/* phone: the J1's own home screen; tile pages swipe sideways, a section slides in from the right */
@media(max-width:899px){
html,body{overflow-x:hidden}
.root{padding:0 16px;transition:transform .45s var(--ease),filter .45s}
body:has(main section:target) .root{transform:translateX(-28%);filter:brightness(.55);pointer-events:none}
.bar{margin:0 -16px;padding:0 16px;border-bottom:1px solid var(--grp)}
.status{margin:12px 2px 14px}
nav.pages{display:grid;grid-auto-flow:column;grid-auto-columns:100%;overflow-x:auto;scroll-snap-type:x mandatory;scrollbar-width:none;overscroll-behavior-x:contain;margin:0 -16px}nav.pages::-webkit-scrollbar{display:none}
.page{scroll-snap-align:start;scroll-snap-stop:always;display:grid;grid-template-columns:1fr 1fr;grid-template-rows:repeat(3,132px);gap:12px;padding:0 16px}
nav .t{flex-direction:column;align-items:center;justify-content:center;gap:12px;border-radius:20px;background:var(--grp);font-size:17px;text-align:center;padding:8px 6px;line-height:1.2}
nav .t:active{background:#3a3a3c}nav .t .ic{width:46px;height:46px}
.dots{display:flex;justify-content:center;gap:12px;margin:14px 0 10px}.dots i{width:10px;height:10px;border-radius:50%;background:#3a3a3c;cursor:pointer}.dots i.on{background:#fff}
main section{position:fixed;inset:0;z-index:10;background:var(--bg);overflow-y:auto;-webkit-overflow-scrolling:touch;padding:0 16px 40px;transform:translateX(100%);visibility:hidden;box-shadow:-10px 0 30px rgba(0,0,0,.6);transition:transform .45s var(--ease),visibility 0s .45s}
main section:target{transform:none;visibility:visible;transition:transform .45s var(--ease),visibility 0s}
h2{position:sticky;top:0;z-index:2;display:flex;align-items:center;gap:6px;height:60px;margin:0 -16px 6px;padding:0 16px 0 6px;background:rgba(0,0,0,.88);-webkit-backdrop-filter:blur(20px);backdrop-filter:blur(20px);border-bottom:1px solid var(--grp);font-size:21px;font-weight:700}
.back{display:grid;place-items:center;width:44px;height:44px}.back::before{content:"";width:13px;height:13px;border-left:3px solid var(--acc);border-bottom:3px solid var(--acc);transform:rotate(45deg);margin-left:6px;border-radius:2px}
}
/* PC: the same parts as a sidebar and one section at a time */
@media(min-width:900px){
body{font-size:14px}
.app{display:grid;grid-template-columns:290px 1fr;min-height:100vh}
.root{position:sticky;top:0;height:100vh;overflow-y:auto;padding:10px 14px 18px;background:#121214;border-right:1px solid #232326}
.bar{height:auto;padding:12px 8px 4px}.bar h1{font-size:17px}.clock,.bat{font-size:13px}
.status{margin:8px 8px 16px;font-size:13px}.status p{margin:5px 0}.dot{width:8px;height:8px}
nav.pages{display:block}.page{display:contents}
nav .t{align-items:center;gap:12px;padding:8px 10px;margin:1px 0;border-radius:10px;font-size:14px}nav .t:hover{background:#1f1f22}
.dots{display:none}.brand{font-size:12px;margin:18px 8px 0}
main{padding:0 48px 40px;max-width:860px}
main section{display:none}main section:target,main:not(:has(section:target)) #wifi{display:block}
h2{position:sticky;top:0;z-index:2;display:flex;align-items:center;height:64px;margin:0 -48px 10px;padding:0 48px;background:rgba(0,0,0,.85);-webkit-backdrop-filter:blur(20px);backdrop-filter:blur(20px);border-bottom:1px solid #1c1c1e;font-size:22px;font-weight:700}
.back{display:none}
label{font-size:12px;margin:14px 2px 6px}label:has(input[type=checkbox]){font-size:14px}
input,select,textarea{font-size:14px;padding:8px 12px;border-radius:8px;background:#2a2a2c;border:1px solid #3a3a3c}
input:focus,select:focus,textarea:focus{border-color:var(--acc);box-shadow:0 0 0 3px rgba(10,132,255,.3)}
input[type=checkbox]{width:42px;height:25px}input[type=checkbox]::after{width:21px;height:21px}input[type=checkbox]:checked::after{left:19px}
button{display:inline-block;width:auto;min-width:120px;margin:16px 0 0;padding:8px 18px;border-radius:8px;font-size:14px}
section>p{margin:10px 2px}section form{background:#1c1c1e;border:1px solid #262628;border-radius:12px;padding:4px 20px 18px;margin:14px 0}
small,.muted{font-size:12px}.list{background:#1c1c1e;border:1px solid #262628;border-radius:12px}.list li{padding:8px 16px}.list button,.btn2{font-size:13px;padding:6px 12px;border-radius:8px}
.notice{top:16px;font-size:14px}footer{text-align:left;padding:16px 48px 30px;margin-left:290px;max-width:860px}
}
'''.replace('\n','')
# ---- icons: generated by rootfs/display/gen-font.py from Material Icons (Apache 2.0)
ICONS_SVG={
    'wifi':'M107 235Q169 296 256.5 296Q344 296 405 235L363 192Q345 210 313.5 223Q282 236 256 236Q230 236 198.5 223Q167 210 149 192ZM192 149Q219 176 256 176Q293 176 320 149L256 85ZM21 320Q119 417 256.5 417Q394 417 491 320L448 277Q368 356 256 356Q144 356 64 277Z',
    'cable':'M379 395 495 256 379 117 346 144 439 256 346 368ZM235 235V277H277V235ZM363 277V235H320V277ZM149 235V277H192V235ZM166 368 73 256 166 144 133 117 17 256 133 395Z',
    'vpn':'M213 149 384 320 354 350 213 210 158 265 128 235ZM256 491 448 405V277Q448 188 393 114.5Q338 41 256 21Q174 41 119 114.5Q64 188 64 277V405Z',
    'dns':'M413 298Q454 295 483 264.5Q512 234 512 192Q512 148 480.5 116.5Q449 85 405 85H128Q75 85 37.5 122.5Q0 160 0 213Q0 260 33.5 297.5Q67 335 114 340Q135 379 173 403Q211 427 256 427Q310 427 356.5 389Q403 351 413 298Z',
    'key':'M448 299H270Q261 324 243.5 343Q226 362 201.5 373Q177 384 149 384Q114 384 85 366.5Q56 349 38.5 320Q21 291 21 256Q21 221 38.5 192Q56 163 85 145.5Q114 128 149 128Q177 128 201.5 139Q226 150 243.5 169Q261 188 270 213H277L320 171L363 213L405 171L491 257ZM149 192Q132 192 117.5 200.5Q103 209 94 223.5Q85 238 85 256Q85 274 94 288.5Q103 303 117.5 311.5Q132 320 149 320Q167 320 181.5 311.5Q196 303 204.5 288.5Q213 274 213 256Q213 238 204.5 223.5Q196 209 181.5 200.5Q167 192 149 192Z',
    'ap':'M469 235Q469 177 440.5 127.5Q412 78 363 50L341 87Q380 110 403.5 149.5Q427 189 427 235Q427 305 377 355Q327 405 256 405Q185 405 135 355Q85 305 85 235Q85 188 108 149Q131 110 170 87L149 50Q100 78 71.5 127.5Q43 177 43 235Q43 324 105.5 386Q168 448 256 448Q344 448 406.5 386Q469 324 469 235ZM384 235Q384 200 366.5 170.5Q349 141 320 124L299 161Q341 186 341 235Q341 270 316 295Q291 320 256 320Q221 320 196 295Q171 270 171 235Q171 186 213 161L192 124Q163 141 145.5 170.5Q128 200 128 235Q128 288 165.5 325.5Q203 363 256 363Q309 363 346.5 325.5Q384 288 384 235ZM226 264.5Q239 277 256 277Q273 277 286 264.5Q299 252 299 235Q299 218 286 205Q273 192 256 192Q239 192 226 205Q213 218 213 235Q213 252 226 264.5Z',
    'lock':'M322 341V384Q322 411 302.5 430.5Q283 450 256 450Q229 450 209.5 430.5Q190 411 190 384V341ZM226 162Q239 149 256 149Q273 149 286 162Q299 175 299 192Q299 209 286 222Q273 235 256 235Q239 235 226 222Q213 209 213 192Q213 175 226 162ZM384 341Q401 341 414 328.5Q427 316 427 299V85Q427 68 414 55.5Q401 43 384 43H128Q111 43 98 55.5Q85 68 85 85V299Q85 316 98 328.5Q111 341 128 341H149V384Q149 428 180.5 459.5Q212 491 256 491Q300 491 331.5 459.5Q363 428 363 384V341Z',
    'tz':'M267 363V251L363 194L347 167L235 235V363ZM135.5 135.5Q186 85 256 85Q326 85 376.5 135.5Q427 186 427 256Q427 326 376.5 376.5Q326 427 256 427Q186 427 135.5 376.5Q85 326 85 256Q85 186 135.5 135.5ZM105.5 406.5Q168 469 256 469Q344 469 406.5 406.5Q469 344 469 256Q469 168 406.5 105.5Q344 43 256 43Q168 43 105.5 105.5Q43 168 43 256Q43 344 105.5 406.5Z',
    'ssh':'M427 427H85Q68 427 55.5 414.5Q43 402 43 384V128Q43 110 55.5 97.5Q68 85 85 85H427Q444 85 456.5 97.5Q469 110 469 128V384Q469 402 456.5 414.5Q444 427 427 427ZM427 128H85V341H427ZM384 149H256V192H384ZM160 149 130 179 185 235 130 290 160 320 245 235Z',
    'bat':'M334 427Q346 427 354.5 418.5Q363 410 363 398V71Q363 59 354.5 51Q346 43 334 43H178Q166 43 157.5 51Q149 59 149 71V398Q149 410 157.5 418.5Q166 427 178 427H213V469H299V427Z',
    'download':'M107 85H405V128H107ZM405 320H320V448H192V320H107L256 171Z',
    'user':'M427 128V85H85V128Q85 166 143.5 189.5Q202 213 256 213Q310 213 368.5 189.5Q427 166 427 128ZM316 281Q291 256 256 256Q221 256 196 281Q171 306 171 341Q171 376 196 401.5Q221 427 256 427Q291 427 316 401.5Q341 376 341 341Q341 306 316 281Z',
    'notify':'M384 171 427 128V107H85V128L128 171V277Q128 327 153.5 364Q179 401 224 412V427Q224 440 233 449.5Q242 459 256 459Q270 459 279 449.5Q288 440 288 427V412Q333 401 358.5 364Q384 327 384 277ZM256 43Q238 43 225.5 55Q213 67 213 85H299Q299 68 286 55.5Q273 43 256 43Z',
    'backup':'M299 235H363L256 341L149 235H213V149H299ZM413 298Q454 295 483 264.5Q512 234 512 192Q512 148 480.5 116.5Q449 85 405 85H128Q75 85 37.5 122.5Q0 160 0 213Q0 260 33.5 297.5Q67 335 114 340Q135 379 173 403Q211 427 256 427Q310 427 356.5 389Q403 351 413 298Z',
    'update':'M341 235 256 149 171 235H235V341H277V235ZM363 107V405H149V107ZM363 490Q380 490 392.5 477.5Q405 465 405 448V64Q405 47 392.5 34Q380 21 363 21H149Q132 21 119.5 34Q107 47 107 64V448Q107 465 119.5 478Q132 491 149 491Z',
    'https':'M322 341V384Q322 411 302.5 430.5Q283 450 256 450Q229 450 209.5 430.5Q190 411 190 384V341ZM226 162Q239 149 256 149Q273 149 286 162Q299 175 299 192Q299 209 286 222Q273 235 256 235Q239 235 226 222Q213 209 213 192Q213 175 226 162ZM384 341Q401 341 414 328.5Q427 316 427 299V85Q427 68 414 55.5Q401 43 384 43H128Q111 43 98 55.5Q85 68 85 85V299Q85 316 98 328.5Q111 341 128 341H149V384Q149 428 180.5 459.5Q212 491 256 491Q300 491 331.5 459.5Q363 428 363 384V341Z',
}
# ---- end of icons
# each section: icon and color of its tile on the screen
SECTIONS=(('wifi','Wi-Fi','wifi','#30d158'),('red','Red de configuración','ap','#64d2ff'),('bat','Batería','bat','#34c759'),('vpn','WireGuard','vpn','#ff9f0a'),('avisos','Avisos al móvil','notify','#ff375f'),
          ('dns','Cloudflare DNS','dns','#0a84ff'),('usb','Cable USB','cable','#bf5af2'),('clave','Contraseña del panel','key','#5ac8fa'),
          ('pantalla','Pantalla de bloqueo','lock','#98989d'),('hora','Zona horaria','tz','#ff9f0a'),('ssh','SSH','ssh','#98989d'),
          ('https','HTTPS','https','#30d158'),('copia','Copia de seguridad','backup','#30d158'),('actualizar','Actualizar','update','#0a84ff'))
# moves the page dots of the phone home screen (the swipe itself is CSS)
DOTS_JS=(b"(function(){var n=document.querySelector('nav.pages'),d=document.querySelectorAll('.dots i');if(!n||!d.length)return;"
         b"function u(){var p=Math.round(n.scrollLeft/n.clientWidth);for(var i=0;i<d.length;i++)d[i].className=i==p?'on':''}"
         b"n.addEventListener('scroll',u,{passive:true});d.forEach(function(e,i){e.addEventListener('click',function(){n.scrollTo({left:i*n.clientWidth,behavior:'smooth'})})})})();")
CSS+=''.join('body:has(#%s:target) nav a[href="#%s"]%s{background:#0a64d9}'%(sid,sid,',body:not(:has(main section:target)) nav a[href="#wifi"]' if sid=='wifi' else '') for sid,_,_,_ in SECTIONS).join(('@media(min-width:900px){','}'))
def icon(name,color=''):
    return ('<svg class=ic viewBox="0 -512 512 512" aria-hidden=true'+(' style="color:'+color+'"' if color else '')+
            '><path transform="scale(1 -1)" d="'+ICONS_SVG[name]+'"/></svg>')
def with_icons(body):
    # '<section id=x><h2>' gets the tile of section x and the back arrow (phone);
    # its forms post to '#x' so the answer opens on the same section
    for sid,_,ic,color in SECTIONS:
        body=body.replace('<section id='+sid+'><h2>','<section id='+sid+'><h2><a class=back href="#top" aria-label=Volver></a>',1)
        a=body.find('<section id='+sid+'>')
        if a>=0:
            b=body.find('</section>',a)
            body=body[:a]+body[a:b].replace('<form method=post>','<form method=post action="#'+sid+'">')+body[b:]
    return body
def esc(s): return html.escape(str(s), quote=True)
def log(s):
    with (RUN/'appliance.log').open('a') as f: f.write(time.strftime('%H:%M:%S ') + s + '\n')
def atomic(path, data, mode=0o600):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.new')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, 'w') as f:
        os.fchmod(f.fileno(), mode); f.write(data); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    d = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(d)
    finally: os.close(d)
def load(name, default):
    try: return json.loads((STATE/name).read_text())
    except FileNotFoundError: return default

def save(name, value): atomic(STATE/name, json.dumps(value, indent=2))
def command(args, data=None, timeout=15):
    p = subprocess.run(args, input=data, text=True, capture_output=True, timeout=timeout)
    if p.returncode: raise RuntimeError('Fallo en ' + Path(args[0]).name)
    return p.stdout.strip()
def hostname(s):
    s = s.strip().rstrip('.').lower()
    if not s: return ''
    try: s = s.encode('idna').decode('ascii')
    except UnicodeError: raise ValueError('Dominio no valido')
    if len(s)>253 or '.' not in s or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', x) for x in s.split('.')):
        raise ValueError('Indica un dominio completo, sin http:// ni rutas')
    return s

def ensure_vpn_state():
    v = load('vpn.json', None)
    if v is None:
        private = command(['wg','genkey']); public = command(['wg','pubkey'], private+'\n')
        v = {'port':51820,'endpoint':'','private_key':private,'public_key':public,'clients':[]}
        save('vpn.json', v)
    return v

def firewall():
    cmd = ['/usr/sbin/iptables-legacy','-w','2']
    def call(*a, check=True):
        p = subprocess.run(cmd+list(a), capture_output=True, timeout=10)
        if check and p.returncode: raise RuntimeError('No se pudo aplicar el encaminamiento VPN')
        return p.returncode
    call('-N','J1_FORWARD',check=False)
    if call('-C','FORWARD','-j','J1_FORWARD',check=False): call('-I','FORWARD','1','-j','J1_FORWARD')
    call('-F','J1_FORWARD')
    call('-A','J1_FORWARD','-m','conntrack','--ctstate','ESTABLISHED,RELATED','-j','ACCEPT')
    call('-A','J1_FORWARD','-i','wg0','-j','ACCEPT')
    call('-A','J1_FORWARD','-i','p2p+','-j','DROP')
    call('-A','J1_FORWARD','-i','rndis0','-j','DROP')
    call('-t','nat','-N','J1_NAT',check=False)
    if call('-t','nat','-C','POSTROUTING','-j','J1_NAT',check=False): call('-t','nat','-A','POSTROUTING','-j','J1_NAT')
    call('-t','nat','-F','J1_NAT')
    # every uplink (cable and Wi-Fi), so clients keep working if one drops
    routes = command(['ip','-4','route','show','default'])
    uplinks = [d for d in dict.fromkeys(re.findall(r'\bdev\s+(\S+)', routes))
               if d not in ('wg0','rndis0') and not d.startswith('p2p')]
    for d in uplinks:
        call('-t','nat','-A','J1_NAT','-s','10.66.0.0/24','-o',d,'-j','MASQUERADE')
    Path('/proc/sys/net/ipv4/ip_forward').write_text('1\n')
    return bool(uplinks)

# tunnel MTU: WireGuard's usual 1420 (IPv4 outside, 1500 links); fewer packets for
# the same data, and every packet costs air time on the J1's Wi-Fi
WG_MTU=1420
def apply_vpn():
    with LOCK:
        v = ensure_vpn_state()
        # in-kernel WireGuard (kernel -j1wg) is far cheaper; wireguard-go is the fallback
        if not Path('/sys/class/net/wg0').exists() and \
           subprocess.run(['ip','link','add','wg0','type','wireguard'],capture_output=True,timeout=10).returncode==0:
            log('WireGuard: modulo del kernel')
        if not Path('/sys/class/net/wg0').exists():
            out = (RUN/'wireguard.log').open('a')
            subprocess.Popen(['wireguard-go','-f','wg0'], stdin=subprocess.DEVNULL, stdout=out, stderr=out, start_new_session=True)
            out.close()
            for _ in range(50):
                if Path('/run/wireguard/wg0.sock').exists(): break
                time.sleep(.1)
            else: raise RuntimeError('WireGuard no ha creado su interfaz')
        lines=['[Interface]','PrivateKey = '+v['private_key'],'ListenPort = '+str(v['port'])]
        for c in v['clients']:
            if c.get('paused'):continue   # paused: no peer, so no tunnel, until resumed
            lines += ['','[Peer]','PublicKey = '+c['public_key'],'PresharedKey = '+c['psk'],
                      'AllowedIPs = 10.66.0.%s/32, fd66:6a31::%x/128' % (c['ip'],c['ip'])]
        atomic(RUN/'wg0.conf', '\n'.join(lines)+'\n')
        command(['wg','syncconf','wg0',str(RUN/'wg0.conf')])
        command(['ip','address','replace','10.66.0.1/24','dev','wg0'])
        command(['ip','-6','address','replace','fd66:6a31::1/64','dev','wg0'])
        command(['ip','link','set','wg0','mtu',str(WG_MTU),'up'])
        uplink=firewall()
        atomic(RUN/'vpn-summary', 'WG: UDP %s / %s clientes\n' % (v['port'],len(v['clients'])))
        RUNTIME['vpn']='Activo: UDP %s%s' % (v['port'], '' if uplink else ' (sin enlace a Internet)')
        return v

def client_create(name):
    name=name.strip()
    if not name or len(name)>64 or any(ord(c)<32 for c in name): raise ValueError('Nombre de cliente no valido')
    with LOCK:
        v=ensure_vpn_state(); used={c['ip'] for c in v['clients']}
        ip=next((i for i in range(2,255) if i not in used),None)
        if ip is None: raise ValueError('No quedan direcciones libres')
        private=command(['wg','genkey']); public=command(['wg','pubkey'],private+'\n')
        c={'id':secrets.token_hex(8),'name':name,'ip':ip,'private_key':private,'public_key':public,'psk':command(['wg','genpsk'])}
        v['clients'].append(c);save('vpn.json',v)
        try: apply_vpn()
        except Exception:
            v['clients'].remove(c);save('vpn.json',v);raise
        log('Cliente VPN creado');return c

def client_delete(cid):
    with LOCK:
        v=ensure_vpn_state(); old=list(v['clients']); v['clients']=[c for c in old if c['id']!=cid]
        if len(v['clients'])==len(old):raise ValueError('El cliente ya no existe')
        save('vpn.json',v)
        try:apply_vpn()
        except Exception:v['clients']=old;save('vpn.json',v);raise
        log('Cliente VPN revocado')

def client_pause(cid, paused):
    with LOCK:
        v=ensure_vpn_state();c=next((c for c in v['clients'] if c['id']==cid),None)
        if c is None:raise ValueError('El cliente ya no existe')
        c['paused']=bool(paused);save('vpn.json',v);apply_vpn()
        log('Cliente VPN '+('en pausa' if paused else 'reanudado'))
def client_state(c, p):
    # one line for the screen and the web: paused, last connection, traffic
    if c.get('paused'):return 'en pausa'
    return ago(p.get('handshake',0))+(' · ↓%s ↑%s'%(size_h(p.get('tx',0)),size_h(p.get('rx',0))) if p.get('handshake') else '')

def client_profile(cid, fallback, endpoint=None):
    v=ensure_vpn_state();c=next((c for c in v['clients'] if c['id']==cid),None)
    if c is None:raise ValueError('Cliente no encontrado')
    cf=load('cloudflare.json',{})
    endpoint=endpoint or v.get('endpoint') or (cf.get('hostname') if cf.get('enabled') else '') or fallback
    return f'''[Interface]
PrivateKey = {c['private_key']}
Address = 10.66.0.{c['ip']}/32, fd66:6a31::{c['ip']:x}/128
DNS = 1.1.1.1
MTU = {WG_MTU}

[Peer]
PublicKey = {v['public_key']}
PresharedKey = {c['psk']}
Endpoint = {endpoint}:{v['port']}
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
'''

def cf_request(settings, path, method='GET', body=None):
    data=None if body is None else json.dumps(body).encode()
    req=urllib.request.Request('https://api.cloudflare.com/client/v4'+path, data=data, method=method,
        headers={'Authorization':'Bearer '+settings['token'],'Content-Type':'application/json','User-Agent':'J1-VPN/1.0'})
    with urllib.request.urlopen(req,timeout=20) as r: result=json.load(r)
    if not result.get('success'):raise RuntimeError('Cloudflare rechazo la actualizacion DNS')
    return result['result']

def public_ip(trace_url):
    # IP literal of the trace: picks the address family
    with urllib.request.urlopen(trace_url,timeout=20) as r:
        fields=dict(line.split('=',1) for line in r.read(16384).decode().splitlines() if '=' in line)
    return fields.get('ip','')

def cf_upsert(s, rtype, name, content):
    """Creates or updates the single unproxied record rtype/name; returns True if it changed."""
    path='/zones/'+s['zone_id']+'/dns_records'
    records=cf_request(s,path+'?'+urllib.parse.urlencode({'type':rtype,'name':name}))
    if len(records)>1:raise RuntimeError('Hay varios registros %s para ese nombre; revisalos en Cloudflare'%rtype)
    body={'type':rtype,'name':name,'content':content,'ttl':120,'proxied':False}
    if not records:cf_request(s,path,'POST',body);return True
    if records[0]['content']!=content or records[0].get('proxied'):
        cf_request(s,path+'/'+records[0]['id'],'PUT',body);return True
    return False

def update_ddns6(s):
    # IPv6 test name (AAAA): reaches the J1 directly, there is no CG-NAT on IPv6
    if not s.get('enabled6') or not s.get('hostname6'):
        RUNTIME['ddns6']='Desactivado';return
    ip=ipaddress.IPv6Address(public_ip('https://[2606:4700:4700::1111]/cdn-cgi/trace'))
    if not ip.is_global:raise RuntimeError('La IPv6 no es pública')
    if cf_upsert(s,'AAAA',s['hostname6'],str(ip)):log('DNS IPv6 actualizado: '+str(ip))
    RUNTIME['ddns6']='Actualizado: '+str(ip)

def update_ddns():
    with LOCK:s=load('cloudflare.json',{})
    if not s.get('token') or not s.get('zone_id'):
        RUNTIME['ddns']='Faltan ajustes' if s.get('enabled') else 'Desactivado';return
    try:update_ddns6(s)
    except Exception as e:
        RUNTIME['ddns6']='No se pudo actualizar (¿hay IPv6?)'
        log('DNS IPv6 error: '+type(e).__name__+': '+str(e)[:200])
    if not s.get('enabled'):
        RUNTIME['ddns']='Desactivado';return
    if not s.get('hostname'):
        RUNTIME['ddns']='Faltan ajustes';return
    public=str(ipaddress.IPv4Address(public_ip('https://1.1.1.1/cdn-cgi/trace')))
    if cf_upsert(s,'A',s['hostname'],public):log('DNS VPN actualizado')
    notify_ip(public)
    RUNTIME['ddns']='Actualizado: '+public
    atomic(RUN/'ddns-status',RUNTIME['ddns']+'\n')

def scan_networks():
    RUNTIME['scan']='Buscando redes...'
    command(['wpa_cli','-i','wlan0','-p','/run/wpa_supplicant','p2p_stop_find'])
    for _ in range(5):
        if command(['wpa_cli','-i','wlan0','-p','/run/wpa_supplicant','scan'])=='OK':break
        time.sleep(1)
    time.sleep(3)
    raw=command(['wpa_cli','-i','wlan0','-p','/run/wpa_supplicant','scan_results'])
    found={}
    for row in raw.splitlines()[1:]:
        fields=row.split('\t',4)
        if len(fields)!=5 or not fields[4]:continue
        # wpa_cli represents non-printable SSID bytes with \\xNN.
        txt=fields[4]; b=bytearray();i=0
        while i<len(txt):
            if txt[i:i+2]=='\\x' and re.fullmatch('[0-9a-fA-F]{2}',txt[i+2:i+4]):b.append(int(txt[i+2:i+4],16));i+=4
            else:b.extend(txt[i].encode());i+=1
        if not 1<=len(b)<=32 or bytes(b).startswith(b'DIRECT-J1-'):continue
        try:signal=int(fields[2])
        except ValueError:continue
        key=bytes(b).hex();item={'hex':key,'name':bytes(b).decode('utf8','replace'),'signal':signal,'secure':'WPA' in fields[3] or 'RSN' in fields[3]}
        if key not in found or signal>found[key]['signal']:found[key]=item
    RUNTIME['networks']=sorted(found.values(),key=lambda x:-x['signal'])
    RUNTIME['scan']=str(len(found))+' redes encontradas'

def wifi_save(form):
    manual=form.get('ssid','').strip()
    if manual:b=manual.encode('utf8')
    else:
        try:b=bytes.fromhex(form.get('ssidhex',''))
        except ValueError:raise ValueError('Selecciona una red')
    if not 1<=len(b)<=32 or b'\x00' in b:raise ValueError('Selecciona una red o indica un SSID valido')
    password=form.get('password','');is_open=form.get('open')=='1'
    if is_open:
        security='    key_mgmt=NONE\n'
    else:
        if not 8<=len(password.encode())<=63 or any(ord(c)<32 for c in password):raise ValueError('Contrasena Wi-Fi: 8 a 63 bytes')
        q=password.replace('\\','\\\\').replace('"','\\"')
        security='    psk="'+q+'"\n    key_mgmt=WPA-PSK\n'
    atomic(STATE/'wifi.conf','ctrl_interface=/run/wpa_supplicant\nupdate_config=0\nnetwork={\n    ssid='+b.hex()+'\n'+security+'}\n')
    flag('wifi-off',False)
    atomic(RUN/'wifi-reconfigure','1\n');log('Configuracion Wi-Fi guardada')

def flag(name, on):
    # /etc/j1 flag files read by j1-network / j1-ap-ensure
    if on: atomic(STATE/name,'1\n')
    else: (STATE/name).unlink(missing_ok=True)

def wifi_enable(on):
    flag('wifi-off',not on);log('Wi-Fi cliente '+('activada' if on else 'apagada'))

def ap_enable(on):
    flag('ap-off',not on);log('Red de configuracion '+('activada' if on else 'apagada'))

def wpa(*args): return command(['wpa_cli','-i','wlan0','-p','/run/wpa_supplicant',*args])

def ap_password(pw):
    # the AP passphrase; also the panel password until the panel gets its own
    if not 8<=len(pw)<=63 or any(not 33<=ord(c)<=126 or c in '"\\' for c in pw):
        raise ValueError('Clave: 8 a 63 caracteres, sin espacios, comillas ni \\')
    with LOCK:
        conf=(STATE/'p2p.conf').read_text()
        new,n=re.subn(r'(?m)^(\s*psk=).*$',lambda m:m[1]+'"'+pw+'"',conf,count=1)
        if n!=1:raise RuntimeError('No se encontró la clave de la red de configuración')
        atomic(STATE/'p2p.conf',new);atomic(STATE/'admin-password',pw+'\n');PANEL_AUTH_OK.clear()
        atomic(RUN/'ap-password','Clave: '+pw+'\n',0o644)
        # live: update the persistent group, then let j1-ap-ensure recreate it
        nid=next((r.split('\t')[0] for r in wpa('list_networks').splitlines()[1:] if 'P2P-PERSISTENT' in r),None)
        if nid is not None:
            wpa('set_network',nid,'psk','"'+pw+'"')
            go=(RUN/'ap-interface').read_text().strip() if (RUN/'ap-interface').exists() else ''
            if go and Path('/sys/class/net/'+go).exists():wpa('p2p_group_remove',go)
    log('Clave de la red de configuracion cambiada')

IP_CLASSES={'wlan0':'Wi-Fi','eth':'Cable'}
def cls_ok(cls):
    if cls not in IP_CLASSES:raise ValueError('Interfaz no válida')
    return cls
def ip_load(cls):
    try:text=(STATE/('ip-'+cls+'.conf')).read_text()
    except FileNotFoundError:return {}
    return {k:v.strip("'") for k,_,v in (l.partition('=') for l in text.splitlines()) if k}

def ip_save(cls, f):
    if cls not in IP_CLASSES:raise ValueError('Interfaz no válida')
    try:
        ip=ipaddress.IPv4Address(f.get('ip','').strip());prefix=int(f.get('prefix','24') or 24)
        net=ipaddress.IPv4Network('%s/%s'%(ip,prefix),strict=False)
    except ValueError:raise ValueError('IP o prefijo no válidos (ejemplo 192.168.1.50 y 24)')
    if not 8<=prefix<=30 or ip in (net.network_address,net.broadcast_address):raise ValueError('IP o prefijo no válidos (ejemplo 192.168.1.50 y 24)')
    try:gw=ipaddress.IPv4Address(f.get('gw','').strip())
    except ValueError:raise ValueError('Puerta de enlace no válida')
    if gw not in net or gw==ip:raise ValueError('La puerta de enlace debe estar en la misma red que la IP')
    try:dns=[str(ipaddress.IPv4Address(x)) for x in re.split(r'[\s,]+',f.get('dns','').strip()) if x] or [str(gw)]
    except ValueError:raise ValueError('DNS no válido')
    if len(dns)>3:raise ValueError('Como máximo 3 servidores DNS')
    atomic(STATE/('ip-'+cls+'.conf'),"ip=%s\nsubnet=%s\nrouter=%s\ndns='%s'\n"%(ip,net.netmask,gw,' '.join(dns)))
    atomic(RUN/'ip-reconfigure','1\n');log('IP fija '+IP_CLASSES[cls]+': '+str(ip))

def ip_auto(cls):
    if cls not in IP_CLASSES:raise ValueError('Interfaz no válida')
    (STATE/('ip-'+cls+'.conf')).unlink(missing_ok=True)
    atomic(RUN/'ip-reconfigure','1\n');log('IP automatica '+IP_CLASSES[cls])

def ip_other(cls):return 'eth' if cls=='wlan0' else 'wlan0'
def ip_shared():
    a,b=ip_load('wlan0'),ip_load('eth')
    return bool(a) and a.get('ip')==b.get('ip')
def ip_share(cls):
    # the same fixed IP on both links: j1-network keeps it on one of them (cable first)
    conf=ip_load(cls_ok(cls))
    if not conf:raise ValueError('Primero guarda una IP manual')
    atomic(STATE/('ip-'+ip_other(cls)+'.conf'),''.join("%s=%s\n"%(k,"'%s'"%v if k=='dns' else v) for k,v in conf.items()))
    atomic(RUN/'ip-reconfigure','1\n');log('IP compartida Wi-Fi y cable: '+conf['ip'])

def vpn_settings(port, endpoint):
    try:port=int(port)
    except ValueError:port=0
    if not 1<=port<=65535 or port in (67,68):raise ValueError('Elige un puerto UDP válido que no sea el de DHCP')
    endpoint=endpoint.strip()
    if endpoint:
        try:endpoint=str(ipaddress.IPv4Address(endpoint))
        except ValueError:endpoint=hostname(endpoint)
    with LOCK:
        v=ensure_vpn_state();old=dict(v);v.update(port=port,endpoint=endpoint);save('vpn.json',v)
        try:apply_vpn()
        except Exception:save('vpn.json',old);apply_vpn();raise
    if old['port']!=port:atomic(RUN/'upnp-request','1\n')   # move the router mapping now

def upnp_enable(on):
    save('upnp.json',{'enabled':on});atomic(RUN/'upnp-request','1\n')
    RUNTIME['upnp']='Comprobando...' if on else 'Cerrando...'

def dns_settings(enabled, domain, zone, token, enabled6=None, domain6=None):
    with LOCK:
        old=load('cloudflare.json',{});token=token.strip() or old.get('token','')
        zone=zone.strip();domain=hostname(domain)
        enabled6=old.get('enabled6',False) if enabled6 is None else enabled6
        domain6=hostname(old.get('hostname6','') if domain6 is None else domain6)
        if token and (len(token)>256 or any(ord(c)<33 or ord(c)>126 for c in token)):raise ValueError('Token no válido')
        if zone and not re.fullmatch('[0-9a-fA-F]{32}',zone):raise ValueError('El ID de zona debe tener 32 caracteres hexadecimales')
        if enabled and not(domain and zone and token):raise ValueError('Faltan dominio, ID de zona o token')
        if enabled6 and not(domain6 and zone and token):raise ValueError('Para IPv6 faltan el nombre IPv6, el ID de zona o el token')
        if enabled6 and domain6==domain:raise ValueError('Usa un nombre IPv6 distinto del principal (por ejemplo vpn6...)')
        save('cloudflare.json',{'enabled':enabled,'hostname':domain,'zone_id':zone,'token':token,'enabled6':enabled6,'hostname6':domain6})
        RUNTIME['ddns6']='Pendiente de actualizar' if enabled6 else 'Desactivado'
        RUNTIME['ddns']='Pendiente de actualizar' if enabled else 'Desactivado';atomic(RUN/'ddns-request','1\n')

def usb_set(boost):
    with LOCK:save('usb.json',{'boost':boost});apply_usb()
    log('Alimentacion USB: '+('automatica' if boost else 'solo externa'))

USB_PARAMS = Path('/sys/module/dwc_otg/parameters')
def usb_param(name):
    try:return (USB_PARAMS/name).read_text().strip()
    except OSError:return ''
def apply_usb():
    # kernel j1otg: j1_boost 1 = automatic 5 V for an unpowered adapter,
    # 0 = never. Without a saved choice the kernel default stays.
    s=load('usb.json',{})
    if 'boost' not in s:return
    try:(USB_PARAMS/'j1_boost').write_text(('1' if s['boost'] else '0')+'\n')
    except OSError:pass

def usb_section():
    if not (USB_PARAMS/'j1_boost').exists():
        return '<section id=usb><h2>Cable de red USB</h2><p>Este kernel no admite modo host USB.</p></section>'
    try:eth=(RUN/'eth-summary').read_text().strip()
    except FileNotFoundError:eth='Cable: sin adaptador'
    host='Modo host (adaptador)' if usb_param('j1_host_active')=='1' else 'Modo dispositivo (PC)'
    power='el J1 da 5 V' if usb_param('j1_boost_on')=='1' else 'el J1 no da 5 V'
    locked=''
    if usb_param('j1_boost_locked')=='1':
        locked=('<p class=notice>5 V bloqueados hasta reconectar el OTG: se detectó alimentación externa '
            'o el cargador avisó de un fallo ('+esc(usb_param('j1_boost_tries') or '0')+' intentos).</p>')
    checked=' checked' if usb_param('j1_boost')=='1' else ''
    return ('<section id=usb><h2>Cable de red USB</h2><p>'+esc(eth)+'</p><p class=muted>'+esc(host+' · '+power)+'</p>'+locked+
        '<form method=post>'+hidden()+'<input type=hidden name=action value=usb>'
        '<label><input type=checkbox name=boost value=1'+checked+'> Alimentación automática del adaptador</label>'
        '<small>Activado: si el adaptador llega sin corriente, el J1 espera 2 s, comprueba que nadie más alimenta el cable '
        'y entonces da 5 V; los corta si aparece otra fuente. Con un hub o cable OTG con alimentación, el J1 no da 5 V y se carga desde ahí. '
        'Desactivado: el J1 no da 5 V nunca. El cable tiene prioridad sobre la Wi-Fi para Internet y la VPN.</small><br>'
        '<button>Guardar alimentación USB</button></form></section>')

# ---- SSH over USB (optional): dropbear listens on 192.168.77.1 only and
# accepts keys only; /root/.ssh/authorized_keys links to this file, which lives
# with the configuration (it survives a system reinstall)
SSH_KEY_RE=re.compile(r'(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521)) [A-Za-z0-9+/]+={0,3}( [ -~]{0,100})?')
def ssh_keys():
    try:return [l for l in (STATE/'authorized_keys').read_text().splitlines() if SSH_KEY_RE.fullmatch(l)]
    except OSError:return []
def ssh_add(pub):
    pub=pub.strip()
    if '\n' in pub or '\r' in pub:raise ValueError('Pega una sola clave pública (una línea)')
    pub=' '.join(pub.split())
    if not SSH_KEY_RE.fullmatch(pub):raise ValueError('Clave pública no válida: pega una línea que empiece por ssh-ed25519 o ssh-rsa')
    with LOCK:
        keys=ssh_keys()
        if pub not in keys:atomic(STATE/'authorized_keys',''.join(k+'\n' for k in keys+[pub]))
    log('SSH por USB: clave añadida')
def ssh_generate():
    # new key pair: the public half is authorized, the private half is only
    # handed to the browser (OpenSSH format) and never stored on the J1
    tmp=RUN/('sshkey-'+secrets.token_hex(4))
    try:
        command(['dropbearkey','-t','ed25519','-f',str(tmp)])
        pub=next(l for l in command(['dropbearkey','-y','-f',str(tmp)]).splitlines() if l.startswith('ssh-ed25519 '))
        command(['dropbearconvert','dropbear','openssh',str(tmp),str(tmp)+'.openssh'])
        private=Path(str(tmp)+'.openssh').read_bytes()
    finally:
        for p in (tmp,Path(str(tmp)+'.openssh')):
            try:p.unlink()
            except OSError:pass
    ssh_add(pub.split()[0]+' '+pub.split()[1]+' j1-open-vpn')
    return private
def ssh_disable():
    with LOCK:
        try:(STATE/'authorized_keys').unlink()
        except FileNotFoundError:pass
    log('SSH por USB desactivado')
def lock_section():
    on=display_lock();pin=on and display_pin() is not None
    return ('<section id=pantalla><h2>Pantalla de bloqueo</h2><p>'+('Activada' if on else 'Desactivada')+(' · con código' if pin else '')+'</p>'+
        ('<p class=err>Bloqueada tras %d códigos erróneos: la pantalla no acepta ningún código.</p><form method=post>'%PIN_FAIL['n']+hidden()+'<input type=hidden name=action value=lockunblock><button>Desbloquear la pantalla</button></form>' if pin and pin_blocked() else '')+
        ('<form method=post>'+hidden()+'<input type=hidden name=action value=lockpinoff><button class=danger>Quitar el código de desbloqueo</button><small>Por si se ha olvidado.</small></form>' if pin else '')+
        '<form method=post>'+hidden()+'<input type=hidden name=action value=lockpin>'+'<label>Contraseña actual del panel<input type=password name=current autocomplete=current-password></label>'+
        '<label>'+('Código nuevo' if pin else 'Código de desbloqueo')+' (4 a 8 cifras)<input type=password name=pin inputmode=numeric pattern="[0-9]{4,8}" maxlength=8 autocomplete=off></label><label>Repítelo<input type=password name=pin2 inputmode=numeric maxlength=8 autocomplete=off></label>'
        '<button>'+('Cambiar' if pin else 'Poner')+' código</button><small>Activa también la pantalla de bloqueo. Mejor 6 cifras o más.</small></form>'+'<p class=muted>Activada: cuando la pantalla del J1 se apaga, tocarla solo enciende el reloj y hay que deslizar para usarla, así no se pulsa nada sin querer.</p><form method=post>'+hidden()+
        '<input type=hidden name=action value=lock><input type=hidden name=on value='+('0' if on else '1')+'><button class=sec>'+('Desactivar' if on else 'Activar')+' pantalla de bloqueo</button></form></section>')
def tz_section():
    cur=tz_get()
    opts=''.join('<option value=%d%s>%s</option>'%(i,' selected' if z==cur else '',esc(n)) for i,(n,z) in enumerate(TZ_ZONES))
    return ('<section id=hora><h2>Zona horaria</h2><p>'+esc(tz_name(cur))+' · ahora '+time.strftime('%H:%M')+'</p><form method=post>'+hidden()+
        '<input type=hidden name=action value=tz><select name=zone>'+opts+'</select><button>Guardar zona horaria</button></form></section>')
def pw_section():
    return ('<section id=clave><h2>Contraseña del panel</h2><p>'+('Propia.' if panel_own_password() else 'Ahora es la clave de la red de configuración.')+'</p><form method=post>'+hidden()+
        '<input type=hidden name=action value=panelpw><label>Contraseña actual<input type=password name=current autocomplete=current-password></label>'
        '<label>Nueva (8 a 64 caracteres)<input type=password name=pw autocomplete=new-password minlength=8 maxlength=64></label><label>Repítela<input type=password name=pw2 autocomplete=new-password></label>'
        '<button>Cambiar contraseña</button><small>Después el navegador volverá a pedirla. Si la olvidas, cámbiala desde la pantalla del J1 (Panel web).</small></form></section>')
def ap_section():
    own=panel_own_password() is not None;on=not (STATE/'ap-off').exists()
    return ('<section id=red><h2>Red de configuración</h2><p>'+('Activada: <b>'+esc(readrun('ap-name','AP').replace('AP: ',''))+'</b>.' if on else 'Apagada.')+'</p><form method=post>'+hidden()+
        '<input type=hidden name=action value=ap><input type=hidden name=on value='+('0' if on else '1')+'><button class=sec>'+('Apagar' if on else 'Activar')+' red de configuración</button>'+
        ('<small>Si estás conectado a esta red perderás el panel: vuelve a activarla desde la pantalla del J1 o por el cable USB.'+(' La Wi-Fi cliente también está apagada: solo quedarán USB y la pantalla.' if (STATE/'wifi-off').exists() else '')+'</small>' if on else '')+'</form>'
        '<h3>Clave</h3><p class=muted>'+

        ('El panel tiene contraseña propia: no cambia.' if own else 'Es también la contraseña de este panel: después el navegador te pedirá la nueva.')+
        ' Los equipos conectados a esa red se desconectarán y tendrán que volver a conectarse con la clave nueva.</p><form method=post>'+hidden()+
        '<input type=hidden name=action value=appass>'+'<label>Contraseña actual del panel<input type=password name=current autocomplete=current-password></label>'+
        '<label>Clave nueva (8 a 63 caracteres)<input type=password name=pw minlength=8 maxlength=63 autocomplete=new-password></label><label>Repítela<input type=password name=pw2 maxlength=63 autocomplete=new-password></label>'
        '<button>Cambiar clave de la red</button></form></section>')
def https_section():
    on=panel_conf()['https'];fp=https_fingerprint()
    return ('<section id=https><h2>Conexión segura (HTTPS)</h2><p>'+('Activada: el panel va cifrado también en la red de casa.' if on else 'Desactivada: en la red de casa el panel va sin cifrar (por la VPN ya va cifrado).')+'</p>'
        '<form method=post>'+hidden()+'<input type=hidden name=action value=https><input type=hidden name=on value='+('0' if on else '1')+'><button class='+('sec' if on else '')+'>'+('Desactivar' if on else 'Activar')+' HTTPS</button>'
        '<small>El certificado lo crea el propio J1, así que el navegador avisa la primera vez: acéptalo si la huella coincide. Con HTTPS, http:// redirige a https://.</small></form>'+
        ('<p class=muted>Huella SHA-256 del certificado:<br><code>'+esc(fp)+'</code></p>' if fp else '')+'</section>')
def ssh_section():
    n=len(ssh_keys())
    state='Activo: %d clave%s autorizada%s.'%(n,'' if n==1 else 's','' if n==1 else 's') if n else 'Desactivado (ninguna clave autorizada).'
    return pw_section()+ap_section()+lock_section()+tz_section()+('<section id=ssh><h2>Acceso SSH por USB</h2><p>'+state+'</p><p class=muted>Opcional, para usuarios avanzados. Solo funciona con el J1 conectado al PC por USB: <code>ssh -i clave root@192.168.77.1</code>. Nunca desde la Wi-Fi ni desde Internet, y solo con clave (sin contraseña).</p>'
        '<form method=post>'+hidden()+'<input type=hidden name=action value=sshgen><button>Generar una clave y descargarla</button><small>Guarda el archivo descargado: es la llave para entrar y no se puede volver a descargar.</small></form>'
        '<form method=post>'+hidden()+'<input type=hidden name=action value=sshadd><label>O pega tu clave pública (id_ed25519.pub)<textarea name=key rows=3 maxlength=1000></textarea></label><button>Añadir clave pública</button></form>'
        +('<form method=post>'+hidden()+'<input type=hidden name=action value=sshoff><button class=danger>Desactivar SSH (borrar todas las claves)</button></form>' if n else '')+'</section>')

def hidden():return '<input type="hidden" name="csrf" value="'+CSRF+'">'
def home_html():
    # same lines as the screen's home (ui_home), then its tiles in pages of 6
    try:bat=int(Path('/sys/class/power_supply/battery/capacity').read_text())
    except (OSError,ValueError):bat=None
    out=['<header class=bar><h1>J1 · Servidor VPN</h1><span class=clock>'+time.strftime('%H:%M')+'</span>'+
         ('<span class="bat'+(' low' if bat<=15 else '')+'">%d%%</span>'%bat if bat is not None else '')+'</header><div class=status>']
    for r in ui_home().rows:
        if r[0]=='L':out.append('<p'+(' class=m' if r[2] not in 'gyr' else '')+'>'+('<span class="dot '+r[2]+'"></span>' if r[2] in 'gyr' else '')+esc(r[1])+'</p>')
    pages=[SECTIONS[i:i+6] for i in range(0,len(SECTIONS),6)]
    out.append('</div><nav class=pages>'+''.join('<div class=page>'+''.join('<a class=t href="#'+sid+'">'+icon(ic,color)+'<span>'+esc(name)+'</span></a>' for sid,name,ic,color in pg)+'</div>' for pg in pages)+'</nav>')
    out.append('<div class=dots>'+''.join('<i'+(' class=on' if i==0 else '')+'></i>' for i in range(len(pages)))+'</div><p class=brand>'+esc(BRAND)+'<br>'+REPO+'</p>')
    return ''.join(out)
def page(message='',error=False):
    v=ensure_vpn_state();cf=load('cloudflare.json',{})
    try:wifi=(RUN/'wifi-summary').read_text().strip()
    except FileNotFoundError:wifi='Sin configurar'
    note='<p class="notice'+(' err' if error else '')+'" role=status>'+esc(message)+'</p>'
    vpn_ok=RUNTIME['vpn'].startswith('Activo');wifi_ok=bool(re.search(r'\d+\.\d+\.\d+\.\d+',wifi))
    out=['<!doctype html><html lang=es><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><meta name=theme-color content="#000000"><title>J1 VPN</title><style>'+CSS+'</style>'
         '<div class=app id=top><aside class=root>'+home_html()+         '</aside><main>'+(note if message else '')]
    out+=['<section id=wifi><h2>Conexión Wi-Fi</h2><p>'+esc(wifi)+'</p><form method=post>'+hidden()+'<input type=hidden name=action value=scan><button class=sec>Buscar redes</button></form><p class=muted>'+esc(RUNTIME['scan'])+'</p><form method=post>'+hidden()+'<input type=hidden name=action value=wifi><label for=net>Redes encontradas</label><select name=ssidhex id=net><option value="">Selecciona una red</option>']
    for n in RUNTIME['networks']:out.append('<option value="'+n['hex']+'">'+esc(n['name'])+' · '+str(n['signal'])+' dBm'+('' if n['secure'] else ' · abierta')+'</option>')
    out+=['</select><details><summary>Red oculta o nombre manual</summary><label>Nombre de la red<input name=ssid maxlength=32 autocomplete=off></label></details><label>Contraseña Wi-Fi<input type=password name=password maxlength=63 autocomplete=new-password></label><label><input type=checkbox name=open value=1> Red abierta, sin contraseña</label><button>Guardar y conectar</button></form><p><small>La red de configuración se mantiene disponible.</small></p></section>',usb_section(),bat_section()]
    out+=['<section id=vpn><h2>WireGuard</h2><p>'+esc(RUNTIME['vpn'])+'</p><form method=post>'+hidden()+'<input type=hidden name=action value=vpn><label>Puerto UDP<input type=number name=port min=1 max=65535 required value="'+str(v['port'])+'"></label><label>Dominio o IP de conexión<input name=endpoint value="'+esc(v.get('endpoint',''))+'" placeholder="vpn2.tudominio.com"></label><small>Vacío: usa el dominio de Cloudflare o la IP de acceso actual. Web en TCP 80; VPN en UDP. Si cambias el puerto o dominio, descarga otra vez los perfiles.</small><br><button>Guardar puerto y dirección</button></form><h3>Clientes</h3><ul class=list>'+('' if v['clients'] else '<li><small>Ninguno todavía.</small></li>')]
    peers=wg_peers()
    for c in v['clients']:
        pa=c.get('paused')
        out.append('<li><span class=tile>'+icon('user','#0a84ff')+'</span><span class=who><b>'+esc(c['name'])+'</b><small>10.66.0.'+str(c['ip'])+' · '+esc(client_state(c,peers.get(c['public_key'],{})))+'</small></span>'
                   '<a class=btn2 href="/client/'+c['id']+'.conf">'+icon('download')+'.conf</a>'
                   '<form method=post>'+hidden()+'<input type=hidden name=action value=pause><input type=hidden name=id value="'+c['id']+'"><input type=hidden name=on value='+('0' if pa else '1')+'><button class=sec>'+('Reanudar' if pa else 'Pausar')+'</button></form>'
                   '<form method=post>'+hidden()+'<input type=hidden name=action value=delete><input type=hidden name=id value="'+c['id']+'"><button class=danger>Quitar</button></form></li>')
    out+=['</ul><form method=post>'+hidden()+'<input type=hidden name=action value=client><label>Nombre del nuevo cliente<input name=name maxlength=64 required placeholder="Mi móvil"></label><button>Crear cliente</button></form><p><small>El perfil contiene claves privadas. Al quitar un cliente, su acceso se revoca en el servidor. En pausa no puede conectarse, pero conserva su perfil: al reanudarlo vuelve a funcionar sin importarlo de nuevo. ↓ es lo que ha recibido el cliente; ↑, lo que ha enviado.</small></p></section>']
    checked=' checked' if cf.get('enabled') else ''
    out+=['<section id=dns><h2>Cloudflare · DNS dinámico</h2><p>'+esc(RUNTIME['ddns'])+'</p><form method=post>'+hidden()+'<input type=hidden name=action value=dns><label><input type=checkbox name=enabled value=1'+checked+'> Actualizar automáticamente el registro DNS</label><label>Nombre completo del registro<input name=hostname value="'+esc(cf.get('hostname',''))+'" placeholder="vpn2.tudominio.com"></label><label>ID de zona de Cloudflare<input name=zone_id value="'+esc(cf.get('zone_id',''))+'" maxlength=32></label><label>Token API<input type=password name=token autocomplete=new-password placeholder="'+('Guardado; deja vacío para conservarlo' if cf.get('token') else 'Token con permiso DNS:Editar en esta zona')+'"></label><small>El registro A se crea o actualiza en modo Solo DNS, sin proxy naranja. Revisión cada 5 minutos. No se conecta a Cloudflare hasta que actives esta opción.</small><br><button>Guardar Cloudflare</button></form></section>'+notify_section()+https_section()+ssh_section()+backup_section()+update_section()+'</main></div><script src="/j1.js" defer></script><footer><p>Acceso externo: el router debe redirigir el puerto UDP al J1. El DNS dinámico no elimina CG-NAT. La VPN proporciona salida IPv4; el perfil dirige IPv6 al túnel para evitar salida directa.</p></footer></html>']
    return with_icons(''.join(out)).encode()

# ---- web panel: on/off and who may reach it (set from the screen) ----
# Decided by who connects, not by the address used: a VPN client sends
# everything through the tunnel, so it could also reach 192.168.78.1.
PANEL_FIXED=('192.168.77.1','192.168.78.1')   # USB and the J1's own network
PANEL_NETS=tuple(ipaddress.ip_network(n) for n in ('192.168.77.0/30','192.168.78.0/24'))
VPN_NET=ipaddress.ip_network('10.66.0.0/24')
PANEL_CHANGED=threading.Event()
def panel_conf():
    c=load('panel.json',{})
    return {'enabled':c.get('enabled',True) is not False,'lan':c.get('lan') is True,'vpn':c.get('vpn') is True,'https':c.get('https') is True}
def panel_set(**kw):
    raw=load('panel.json',{});raw.update(kw);save('panel.json',raw);PANEL_CHANGED.set();c=panel_conf()
    extra=[n for n,k in (('red local','lan'),('VPN','vpn')) if c[k]]
    log('Panel web: '+('activado' if c['enabled'] else 'desactivado')+(' (también desde '+' y '.join(extra)+')' if c['enabled'] and extra else ''))
# panel password: its own (salted PBKDF2 hash in panel.json) or, until one is
# set, the key of the J1's network. Checked headers are remembered so each page
# does not pay the hash again; any change forgets them.
PANEL_AUTH_OK=set()
def panel_own_password():
    p=load('panel.json',{}).get('password')
    return p if isinstance(p,dict) and 'salt' in p and 'hash' in p else None
def panel_password_ok(pw):
    p=panel_own_password()
    if p:return hmac.compare_digest(pin_hash(pw,p['salt']),p['hash'])
    try:return hmac.compare_digest(pw.encode(),(STATE/'admin-password').read_text().strip().encode())
    except FileNotFoundError:return False
def panel_password_set(pw,again):
    if not 8<=len(pw)<=64 or any(not 32<=ord(c)<=126 for c in pw):raise ValueError('Contraseña: 8 a 64 caracteres sin acentos ni ñ')
    if pw!=again:raise ValueError('Las dos contraseñas no coinciden')
    salt=secrets.token_hex(16);raw=load('panel.json',{});raw['password']={'salt':salt,'hash':pin_hash(pw,salt)}
    save('panel.json',raw);PANEL_AUTH_OK.clear();log('Contraseña del panel web cambiada')
def panel_password_reset():
    raw=load('panel.json',{});raw.pop('password',None);save('panel.json',raw);PANEL_AUTH_OK.clear()
    log('Panel web: vuelve a usar la clave de la red de configuración')
def lan_nets():
    """The J1's networks at home (Wi-Fi / cable), fixed or from DHCP."""
    try:out=command(['ip','-4','-o','addr','show']);routes=command(['ip','-4','route','show','scope','link'])
    except (RuntimeError,OSError,subprocess.SubprocessError):return []
    nets=[]
    for cidr in re.findall(r'\binet (\d+\.\d+\.\d+\.\d+/\d+)',out):
        n=ipaddress.ip_interface(cidr)
        if str(n.ip) not in PANEL_FIXED and not n.ip.is_loopback and n.ip not in VPN_NET:nets.append(n)
    # a fixed IP is set as /32 plus a route for its subnet: take the subnet from the route
    ips={str(n.ip) for n in nets}
    for net,src in re.findall(r'^(\d+\.\d+\.\d+\.\d+/\d+) .*\bsrc (\d+\.\d+\.\d+\.\d+)',routes,re.M):
        n=ipaddress.ip_interface(src+'/'+net.split('/')[1])
        if src in ips and n not in nets:nets.append(n)
    return nets
def lan_ips():return list(dict.fromkeys(str(n.ip) for n in lan_nets()))
def panel_allowed(peer):
    c=panel_conf()
    try:p=ipaddress.ip_address(peer)
    except ValueError:return False
    if not c['enabled']:return False
    if p in VPN_NET:return c['vpn']
    if any(p in n for n in PANEL_NETS):return True
    return c['lan'] and any(p in n.network for n in lan_nets())
class PanelServer(http.server.ThreadingHTTPServer):
    # one socket for every address (DHCP may change the home one)
    daemon_threads=True
    def verify_request(self,request,client_address):return panel_allowed(client_address[0])
# ---- HTTPS (optional): certificate made on the J1 itself, self-signed, so the
# browser warns once; the fingerprint shown on the screen and in the panel lets
# you check it is this J1's. With HTTPS on, port 80 only redirects to 443.
def cert_path():return STATE/'https.pem'   # key + certificate, in the configuration (it goes into the backup)
def https_cert():
    if not cert_path().exists():
        key,crt=RUN/'https-key.pem',RUN/'https-crt.pem'
        try:
            command(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-nodes','-days','3650','-subj','/CN=J1 Open VPN',
                     '-addext','subjectAltName=IP:192.168.77.1,IP:192.168.78.1,IP:10.66.0.1,DNS:galaxy-j1-linux','-keyout',str(key),'-out',str(crt)],timeout=60)
            atomic(cert_path(),key.read_text()+crt.read_text())
        except FileNotFoundError:raise RuntimeError('Falta openssl para crear el certificado')
        finally:key.unlink(missing_ok=True);crt.unlink(missing_ok=True)
        log('HTTPS: certificado creado')
    return cert_path()
def https_fingerprint():
    try:pem=cert_path().read_text();i=pem.index('-----BEGIN CERTIFICATE-----')
    except (OSError,ValueError):return ''
    h=hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem[i:])).hexdigest().upper()
    return ':'.join(h[i:i+2] for i in range(0,64,2))
def https_set(on):
    if on:https_cert()
    panel_set(https=bool(on))
class PanelTLSServer(PanelServer):
    def __init__(self,addr,handler,ctx):self.ctx=ctx;super().__init__(addr,handler)
    def finish_request(self,request,client_address):
        # the TLS handshake in the request's own thread: a slow client blocks nobody
        request.settimeout(20)
        try:tls=self.ctx.wrap_socket(request,server_side=True)
        except (ssl.SSLError,OSError):return
        try:super().finish_request(tls,client_address)
        finally:tls.close()
def panel_serve():
    srv=tls=None
    while True:
        c=panel_conf();on=c['enabled'];want_tls=on and c['https']
        if on and not srv:
            try:srv=PanelServer(('0.0.0.0',80),Handler);threading.Thread(target=srv.serve_forever,daemon=True).start()
            except OSError:srv=None
        elif srv and not on:srv.shutdown();srv.server_close();srv=None   # port 80 closed
        if want_tls and not tls:
            try:
                ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.minimum_version=ssl.TLSVersion.TLSv1_2;ctx.load_cert_chain(https_cert())
                tls=PanelTLSServer(('0.0.0.0',443),Handler,ctx);threading.Thread(target=tls.serve_forever,daemon=True).start()
            except (OSError,RuntimeError,ssl.SSLError) as e:tls=None;log('HTTPS: no se pudo iniciar: '+type(e).__name__)
        elif tls and not want_tls:tls.shutdown();tls.server_close();tls=None
        PANEL_CHANGED.wait(3);PANEL_CHANGED.clear()

def multipart(ctype, body):
    # -> (fields, files) of a multipart/form-data body
    from email.parser import BytesParser
    from email import policy
    msg=BytesParser(policy=policy.HTTP).parsebytes(b'Content-Type: '+ctype.encode('latin1')+b'\r\n\r\n'+body)
    if not msg.is_multipart():raise ValueError('Solicitud no valida')
    fields={};files={}
    for part in msg.iter_parts():
        name=part.get_param('name',header='content-disposition')
        if not name:continue
        data=part.get_payload(decode=True) or b''
        if part.get_filename() is not None:files[name]=data
        else:fields[name]=data.decode('utf8','replace')
    return fields,files
class Handler(http.server.BaseHTTPRequestHandler):
    server_version='J1-VPN'
    def log_message(self,*args):pass
    def auth(self):
        if not panel_own_password() and not (STATE/'admin-password').exists():
            self.respond(b'Configuracion aun no disponible',503,'text/plain');return False
        h=self.headers.get('Authorization','');key=hashlib.sha256(h.encode()).digest()
        if key in PANEL_AUTH_OK:return True
        try:user,_,pw=base64.b64decode(h[6:],validate=True).decode('utf8').partition(':') if h.startswith('Basic ') else ('','','')
        except (ValueError,UnicodeDecodeError):user=pw=''
        if user=='admin' and panel_password_ok(pw):
            if len(PANEL_AUTH_OK)>16:PANEL_AUTH_OK.clear()
            PANEL_AUTH_OK.add(key);return True
        self.send_response(401);self.send_header('WWW-Authenticate','Basic realm="J1 VPN"');self.send_header('Content-Length','0');self.end_headers();return False
    def respond(self, body, code=200, content='text/html; charset=utf-8', filename=None):
        self.send_response(code);self.send_header('Content-Type',content);self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        if filename:self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def to_https(self):
        # HTTPS on: plain HTTP only redirects, before asking for the password
        if not panel_conf()['https'] or isinstance(self.connection,ssl.SSLSocket):return False
        host=self.headers.get('Host') or ''
        host=host.split(']')[0]+']' if host.startswith('[') else host.rsplit(':',1)[0]   # without the port
        if not re.fullmatch(r'[A-Za-z0-9.-]{1,253}|\[[0-9A-Fa-f:]{2,39}\]',host):host=self.connection.getsockname()[0]
        self.send_response(301);self.send_header('Location','https://'+host+'/');self.send_header('Content-Length','0');self.end_headers();return True
    def do_GET(self):
        if self.to_https() or not self.auth():return
        try:
            m=re.fullmatch(r'/client/([0-9a-f]{16})\.conf',urllib.parse.urlsplit(self.path).path)
            if m:
                self.respond(client_profile(m[1],self.server.server_address[0]).encode(),content='application/x-wireguard-profile',filename='j1-'+m[1]+'.conf');return
            if urllib.parse.urlsplit(self.path).path=='/j1.js':self.respond(DOTS_JS,content='text/javascript; charset=utf-8');return
            if urllib.parse.urlsplit(self.path).path not in ('/','/cgi-bin/config.cgi'):
                self.respond(b'No encontrado',404,'text/plain');return
            with LOCK:body=page()
            self.respond(body)
        except ValueError as e:self.respond(str(e).encode(),404,'text/plain; charset=utf-8')
    def do_POST(self):
        if self.to_https() or not self.auth():return
        try:
            size=int(self.headers.get('Content-Length','0'));ctype=self.headers.get('Content-Type','');files={}
            if ctype.startswith('multipart/form-data'):
                # only the restore form sends a file (small: a backup is a few KB)
                if not 0<size<=BACKUP_MAX:raise ValueError('Archivo demasiado grande')
                f,files=multipart(ctype,self.rfile.read(size))
            else:
                if not 0<size<=8192:raise ValueError('Solicitud no valida')
                f={k:v[-1] for k,v in urllib.parse.parse_qs(self.rfile.read(size).decode('utf8'),keep_blank_values=True,max_num_fields=20).items()}
            if not hmac.compare_digest(f.get('csrf',''),CSRF):raise ValueError('Recarga la página y vuelve a intentarlo')
            action=f.get('action')
            if action=='scan':scan_networks();message=RUNTIME['scan']
            elif action=='wifi':wifi_save(f);message='Red guardada. Espera unos segundos y recarga para ver el estado.'
            elif action=='client':client_create(f.get('name',''));message='Cliente creado. Descarga su perfil .conf.'
            elif action=='usb':
                boost=f.get('boost')=='1';usb_set(boost)
                message='Alimentación USB guardada: '+('automática.' if boost else 'el J1 no dará 5 V.')
            elif action=='delete':client_delete(f.get('id',''));message='Cliente revocado.'
            elif action=='pause':client_pause(f.get('id',''),f.get('on')=='1');message='Cliente '+('en pausa: no puede conectarse.' if f.get('on')=='1' else 'reanudado.')
            elif action=='vpn':
                vpn_settings(f.get('port','0'),f.get('endpoint',''))
                message='Puerto y dirección guardados. Descarga perfiles actualizados.'
            elif action=='sshgen':
                key=ssh_generate()
                self.respond(key,content='application/octet-stream',filename='j1-open-vpn-ssh-key');return
            elif action=='sshadd':ssh_add(f.get('key',''));message='Clave añadida. Ya puedes entrar por USB: ssh root@192.168.77.1'
            elif action=='panelpw':
                if not panel_password_ok(f.get('current','')):raise ValueError('La contraseña actual no es correcta')
                panel_password_set(f.get('pw',''),f.get('pw2',''));message='Contraseña del panel cambiada: el navegador te la volverá a pedir.'
            elif action=='lockpin':
                if not panel_password_ok(f.get('current','')):raise ValueError('La contraseña actual no es correcta')
                pin_set(f.get('pin',''),f.get('pin2',''));message='Código de desbloqueo puesto: se pedirá al desbloquear la pantalla.'
            elif action=='appass':
                if not panel_password_ok(f.get('current','')):raise ValueError('La contraseña actual no es correcta')
                if f.get('pw','')!=f.get('pw2',''):raise ValueError('Las dos claves no coinciden')
                ap_password(f.get('pw',''))
                message='Clave de la red de configuración cambiada.'+('' if panel_own_password() else ' Es también la del panel: el navegador te la pedirá.')
            elif action=='ap':
                ap_enable(f.get('on')=='1');message='Red de configuración '+('activada.' if f.get('on')=='1' else 'apagada.')
            elif action=='lockunblock':pin_unblock();message='Pantalla desbloqueada: vuelve a aceptar el código.'
            elif action=='lockpinoff':pin_clear();message='Código de desbloqueo quitado.'
            elif action=='lock':display_save(lock=f.get('on')=='1');message='Pantalla de bloqueo '+('activada.' if display_lock() else 'desactivada.')
            elif action=='tz':message='Zona horaria: '+tz_set(f.get('zone',''))
            elif action=='batlimit':
                v=f.get('limit','');v=(int(v) if v.isdigit() else -1) if f.get('on')=='1' else 0
                bat_limit_save(v);message='Carga limitada al %d %%.'%v if v else 'Sin límite de carga.'
            elif action=='sshoff':ssh_disable();message='SSH desactivado.'
            elif action=='notify':
                notify_save(enabled=f.get('enabled')=='1',server=f.get('server',''),events=[k for k,_ in NOTIFY_EVENTS if f.get('ev_'+k)=='1'])
                message='Avisos guardados.'
            elif action=='backup':
                blob=backup_make(f.get('pw',''),f.get('pw2',''))
                self.respond(blob,content='application/octet-stream',filename='j1-copia-'+time.strftime('%Y%m%d')+'.j1bak');return
            elif action=='restore':
                n=backup_restore(files.get('file',b''),f.get('pw',''));message='Copia restaurada (%d archivos). El J1 se reinicia: vuelve a entrar en un minuto.'%n
            elif action=='updcheck':update_look();message=UPD['state']
            elif action=='updrun':update_start();message='Actualizando: tarda unos minutos y el J1 se reinicia solo.'
            elif action=='https':
                https_set(f.get('on')=='1')
                message='HTTPS activado: entra por https:// y acepta el aviso del navegador comparando la huella.' if f.get('on')=='1' else 'HTTPS desactivado.'
            elif action=='notifytest':notify_test();message='Aviso de prueba enviado: debería llegarte en unos segundos.'
            elif action=='notifytopic':notify_save(new_topic=True);message='Tema nuevo. Vuelve a suscribirte en la app.'
            elif action=='dns':
                dns_settings(f.get('enabled')=='1',f.get('hostname',''),f.get('zone_id',''),f.get('token',''))
                message='Cloudflare guardado.'
            else:raise ValueError('Acción no válida')
            with LOCK:body=page(message)
            self.respond(body)
        except (ValueError,RuntimeError,subprocess.SubprocessError) as e:
            with LOCK:body=page(str(e) if isinstance(e,(ValueError,RuntimeError)) else 'No se pudo completar la operación',True)
            self.respond(body,400)

# ---- Touch screen (j1-display) over /run/j1-ui.sock ----
# Request: urlencoded a=<action>&s=<screen>&f_<field>=<value>, cp437 bytes.
# Reply: one widget per line, tab separated, cp437 (the screen font):
#  T id title back | R seconds | M text kind(o/e) | L text color | l small-text color
#  B action text style(n/p/d/i) | S action text 0/1 | F name label value kind(t/p/n/i)
#  Q row,row,... (QR, 1 = dark) | G (gap) | C action text icon (home tile, two per row)
#  X tap-action switch-action hint color (full screen camera: live picture from
#    /run/j1-camera.preview, painted by the screen itself) | Y action settings
#    (camera controls: brightness, metering, contrast, sharpness, focus; the
#    screen sends action:key=value)
#  P name column column color (table row, small print) | D action value min max (slider) | O idle-seconds | V brightness | K lock-screen 0/1
LOGS = Path('/root/j1-logs')
def cp437(s):
    out=[]
    for ch in str(s):
        if ord(ch)<32:ch=' '
        # not in the screen font
        if ch in '©→':out.append({'©':'(c)','→':'->'}[ch]);continue
        try:ch.encode('cp437')
        except UnicodeEncodeError:ch=unicodedata.normalize('NFKD',ch).encode('cp437','ignore').decode('cp437')[:1] or '?'
        out.append(ch)
    return ''.join(out)

class Screen:
    def __init__(s, sid, title, back='nav:home', refresh=0):
        s.rows=[['T',sid,title,back]]+([['R',str(refresh)]] if refresh else [])
    def add(s,*r):s.rows.append([str(x) for x in r]);return s
    def label(s,t,c='n'):return s.add('L',t,c)
    def small(s,t,c='n'):return s.add('l',t,c)
    def button(s,a,t,st='n',ic=''):return s.add('B',a,t,st,ic)
    def tile(s,a,t,ic):return s.add('C',a,t,ic)
    def toggle(s,a,t,on):return s.add('S',a,t,'1' if on else '0')
    def field(s,n,l,v='',k='t'):return s.add('F',n,l,v,k)
    def gap(s):return s.add('G')
    def slider(s,a,v,lo,hi):return s.add('D',a,v,lo,hi)
    def msg(s,t,k='o'):s.rows.insert(1,['M',str(t),k]);return s
    def encode(s):return ('\n'.join('\t'.join(cp437(x) for x in r) for r in s.rows)+'\n').encode('cp437')

def readrun(name, default=''):
    try:return (RUN/name).read_text().strip() or default
    except OSError:return default

def tail(path, n=100, size=24576):
    # newest first
    try:
        with open(path,'rb') as f:
            f.seek(0,2);end=f.tell();f.seek(max(0,end-size));data=f.read()
    except OSError:return []
    lines=data.decode('utf8','replace').splitlines()
    if end>size:lines=lines[1:]
    return lines[-n:][::-1]

def ago(ts):
    if not ts:return 'nunca'
    d=max(0,int(time.time())-ts)
    return 'hace %d s'%d if d<120 else 'hace %d min'%(d//60) if d<7200 else 'hace %d h'%(d//3600)

def size_h(n):
    for u in ('B','KB','MB','GB'):
        if n<1024 or u=='GB':return ('%d %s' if u=='B' else '%.1f %s')%(n,u)
        n/=1024

def wg_peers():
    try:rows=command(['wg','show','wg0','dump']).splitlines()[1:]
    except (RuntimeError,OSError,subprocess.SubprocessError):return {}
    return {r[0]:{'endpoint':r[2],'handshake':int(r[4]),'rx':int(r[5]),'tx':int(r[6])} for r in (x.split('\t') for x in rows) if len(r)>=7}

def local_ip():
    for name in ('eth-summary','wifi-summary'):
        m=re.search(r'(\d+\.\d+\.\d+\.\d+)',readrun(name))
        if m:return m[1]
    return '192.168.77.1'

def qr_rows(text):
    try:p=subprocess.run(['qrencode','-t','ASCII','-m','0','-l','L','-o','-'],input=text,capture_output=True,text=True,timeout=10)
    except OSError:raise RuntimeError('Falta qrencode (apk add libqrencode-tools)')
    if p.returncode:raise RuntimeError('No se pudo generar el QR')
    rows=[l[::2].replace('#','1').replace(' ','0') for l in p.stdout.splitlines() if l.strip()]
    w=max(map(len,rows));return [r.ljust(w,'0') for r in rows]

def wifi_qr_text(ssid, pw):
    q=lambda x:re.sub(r'([\\;,:"])',r'\\\1',x)
    return 'WIFI:T:%s;S:%s;%s;'%('WPA' if pw else 'nopass',q(ssid),'P:'+q(pw)+';' if pw else '')

def client_wifi():
    """(ssid, password) of the saved client network, from wifi.conf"""
    try:t=(STATE/'wifi.conf').read_text()
    except FileNotFoundError:return None
    m=re.search(r'^\s*ssid=([0-9a-f]+)\s*$',t,re.M)
    if not m:return None
    p=re.search(r'^\s*psk="((?:[^"\\]|\\.)*)"',t,re.M)
    return bytes.fromhex(m[1]).decode('utf8','replace'),re.sub(r'\\(.)',r'\1',p[1]) if p else ''

def ui_wifiqr(which):
    if which=='ap':
        ssid=readrun('ap-name').replace('AP: ','');pw=(STATE/'admin-password').read_text().strip()
        s=Screen('wifiqr:ap','QR · Red config','nav:ap')
    else:
        net=client_wifi()
        if not net:raise ValueError('No hay red Wi-Fi guardada')
        ssid,pw=net;s=Screen('wifiqr:client','QR · '+ssid,'nav:wifi')
    s.add('Q',','.join(qr_rows(wifi_qr_text(ssid,pw))))
    return s.small('Cámara del móvil: apunta al código para conectarte a '+ssid,'m')

# Wi-Fi from a QR code read with the J1's own cameras (j1-camera). The camera is
# on only while scanning; the password read stays in memory and is never shown.
CAMQR={}
CAMQR_SECONDS=90
CAM_NAMES={'rear':'trasera','front':'delantera'}
def qr_wifi_parse(text):
    """WIFI:T:WPA;S:name;P:password;H:true;; -> dict(ssid, password)"""
    if not text[:5].upper()=='WIFI:':raise ValueError('El código no es de una red Wi-Fi')
    fields={};key=None;val='';i=5
    while i<len(text):
        ch=text[i]
        if ch=='\\' and i+1<len(text):val+=text[i+1];i+=2;continue
        if key is None and ch==':':key=val.upper();val=''
        elif ch==';':
            if key:fields[key]=val
            key=None;val=''
        else:val+=ch
        i+=1
    if key:fields[key]=val
    ssid=fields.get('S','');kind=fields.get('T','').upper();pw=fields.get('P','')
    if not 1<=len(ssid.encode())<=32:raise ValueError('El código no trae el nombre de la red')
    if kind=='WEP':raise ValueError('Red WEP: el J1 no la admite')
    if kind=='NOPASS' or (not kind and not pw):pw=''
    elif not 8<=len(pw.encode())<=63:raise ValueError('La contraseña del código no es válida (8 a 63 caracteres)')
    return {'ssid':ssid,'password':pw}
# rear camera settings, kept while web.py runs; j1-camera reads CAM_CTL whenever
# it changes: b brightness (a automatic, 0-8), m metering (m matrix, c centre,
# s spot), c contrast 0-4, s sharpness 0-2, f focus (n normal, m macro)
CAM_CTL='/run/j1-camera.ctl';CAM_LEVEL='/run/j1-camera.level'
CAM_OPTS={'b':'a012345678','m':'mcs','c':'01234','s':'012','f':'nm'}
CAM_SET={'b':'a','m':'s','c':'2','s':'1','f':'m'}
def camqr_control():
    with LOCK:line=' '.join('%s=%s'%(k,CAM_SET[k]) for k in CAM_OPTS)
    try:
        with open(CAM_CTL+'.tmp','w') as f:f.write(line+'\n')
        os.replace(CAM_CTL+'.tmp',CAM_CTL)
    except OSError:pass
def camqr_set(arg):
    k,_,v=arg.partition('=')
    if k not in CAM_OPTS or len(v)!=1 or v not in CAM_OPTS[k]:raise ValueError('Ajuste de cámara no válido')
    with LOCK:CAM_SET[k]=v
    camqr_control()
def camqr_settings():
    """Y row: b (a + level in use when automatic), then the rest"""
    try:level=open(CAM_LEVEL).read().strip()[:1]
    except OSError:level=''
    with LOCK:st=dict(CAM_SET)
    if st['b']=='a':st['b']='a'+(level if level.isdigit() else '4')
    return ' '.join('%s=%s'%(k,st[k]) for k in CAM_OPTS)
CAM_DEVICE=threading.Lock()   # one j1-camera at a time: they share the sensors
def camqr_run(cam,gen):
    """one scan; gen tells this run from a newer one (camera switched or started again)"""
    def done(**kw):
        with LOCK:
            if CAMQR.get('gen')==gen:CAMQR.update(kw,running=False,proc=None)
    try:subprocess.run(['/usr/local/sbin/j1-camera-tables'],capture_output=True,timeout=60,check=True)
    except (OSError,subprocess.SubprocessError):return done(error='No se pudo usar la cámara')
    with CAM_DEVICE:
        with LOCK:
            if CAMQR.get('gen')!=gen or CAMQR.get('cancel'):return
            if cam=='rear':camqr_control()
            try:p=subprocess.Popen(['/usr/local/bin/j1-camera','qr',cam,str(CAMQR_SECONDS)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            except OSError:p=None
            CAMQR['proc']=p
        if not p:return done(error='No se pudo usar la cámara')
        try:out,err=p.communicate(timeout=CAMQR_SECONDS+30)
        except subprocess.SubprocessError:p.kill();p.wait();return done(error='No se pudo usar la cámara')
    if p.returncode==1:return done(error='Cancelado' if CAMQR.get('cancel') else 'No se ha visto ningún código QR')
    if p.returncode:
        log('Cámara %s: %s'%(cam,err.decode('utf8','replace').strip()[-200:]))
        return done(error='La cámara %s no responde'%CAM_NAMES[cam])
    try:
        net=qr_wifi_parse(out.decode('utf8','replace'))
        wifi_save({'ssid':net['ssid'],'password':net['password'],'open':'' if net['password'] else '1'})
    except ValueError as e:return done(error=str(e))
    log('Red Wi-Fi %s leída con la cámara %s'%(net['ssid'],CAM_NAMES[cam]))
    done(joined=net['ssid'])
def camqr_start(cam):
    if cam not in CAM_NAMES:raise ValueError('Cámara no válida')
    with LOCK:
        if CAMQR.get('running') and CAMQR.get('cam')==cam:return
        old=CAMQR.get('proc');gen=CAMQR.get('gen',0)+1
        CAMQR.clear();CAMQR.update(running=True,cam=cam,gen=gen)
    if old:old.terminate()   # j1-camera turns the camera off on SIGTERM
    threading.Thread(target=camqr_run,args=(cam,gen),daemon=True).start()
def camqr_switch():
    with LOCK:cam=CAMQR.get('cam','rear')
    camqr_start('front' if cam=='rear' else 'rear')
def camqr_focus():
    with LOCK:p=CAMQR.get('proc') if CAMQR.get('cam')=='rear' else None
    if p:p.send_signal(signal.SIGUSR1)
def camqr_stop():
    with LOCK:
        p=CAMQR.get('proc');CAMQR['cancel']=True
    if p:p.terminate()

def ui_camqr(arg):
    """full screen camera (X row: tap action, switch action, hint, hint color;
    Y row, rear camera running: settings action, settings as camqr_settings)"""
    with LOCK:
        q=dict(CAMQR)
        if q.get('joined'):CAMQR.clear();CAMQR['gen']=q['gen']   # shown once
    if q.get('joined'):return ui_wifi('').msg('Red %s guardada, conectando...'%q['joined'])
    cam=q.get('cam','rear')
    s=Screen('camqr','Escanear QR','camqr.close',refresh=1 if q.get('running') else 0)
    if q.get('running'):
        hint='Apunta al código QR de la red Wi-Fi' if cam=='rear' else 'Pon el código QR delante de la pantalla'
        s.add('X','camqr.focus' if cam=='rear' else '-','camqr.switch',hint,'n')
        return s.add('Y','camqr.set',camqr_settings()) if cam=='rear' else s
    return s.add('X','camqr.start:'+cam,'camqr.switch',(q.get('error') or 'Cámara apagada')+'. Toca para volver a intentarlo','y')

# Time zone: POSIX TZ strings (no tzdata needed). Stored in /etc/j1/tz, read by
# j1-init at boot; web.py, j1-display, j1-network and j1-time-save pick a
# change up at once, so no restart is needed.
TZ_DEFAULT='CET-1CEST,M3.5.0,M10.5.0/3'
TZ_ZONES=(('España, Europa central','CET-1CEST,M3.5.0,M10.5.0/3'),
          ('Canarias, Portugal','WET0WEST,M3.5.0/1,M10.5.0'),
          ('Reino Unido, Irlanda','GMT0BST,M3.5.0/1,M10.5.0'),
          ('Europa del este, Grecia','EET-2EEST,M3.5.0/3,M10.5.0/4'),
          ('México','CST6'),
          ('Colombia, Perú, Ecuador','<-05>5'),
          ('Venezuela, Bolivia','<-04>4'),
          ('Chile','<-04>4<-03>,M9.1.6/24,M4.1.6/24'),
          ('Argentina, Uruguay','<-03>3'),
          ('EE. UU. este (Nueva York)','EST5EDT,M3.2.0,M11.1.0'),
          ('EE. UU. pacífico (Los Ángeles)','PST8PDT,M3.2.0,M11.1.0'),
          ('UTC','UTC0'))
def tz_get():
    try:return (STATE/'tz').read_text().strip() or TZ_DEFAULT
    except OSError:return TZ_DEFAULT
def tz_name(tz=None):
    tz=tz or tz_get()
    return next((n for n,z in TZ_ZONES if z==tz),'Personalizada ('+tz+')')
def tz_set(i):
    i=int(i) if str(i).isdigit() else -1
    if not 0<=i<len(TZ_ZONES):raise ValueError('Zona horaria no válida')
    name,tz=TZ_ZONES[i]
    atomic(STATE/'tz',tz+'\n',0o644)
    os.environ['TZ']=tz;time.tzset()
    log('Zona horaria: '+name)
    return name

def ui_tz(arg):
    cur=tz_get();s=Screen('tz','Zona horaria').label('Hora: '+time.strftime('%H:%M'),'g')
    for i,(n,z) in enumerate(TZ_ZONES):s.button('tz.set:%d'%i,('> ' if z==cur else '')+n,'p' if z==cur else 'i')
    return s.small('El reloj de la pantalla, la web y los registros cambian al momento. El horario de verano es automático.','m')

DISPLAY_TIMES=((15,'15 segundos'),(60,'1 minuto'),(120,'2 minutos'),(300,'5 minutos'),(600,'10 minutos'),(0,'Siempre encendida'))
def display_timeout():
    t=load('display.json',{}).get('timeout',60)
    return t if t in dict(DISPLAY_TIMES) else 60
# backlight 0-255 (143 is what Android used); below 15 it is hard to see
BRIGHT_MIN=15
def display_brightness():
    b=load('display.json',{}).get('brightness',143)
    return b if type(b) is int and BRIGHT_MIN<=b<=255 else 143
# lock screen: once the screen goes off, a touch only shows the clock until
# the knob is slid across (on by default)
def display_lock():
    return load('display.json',{}).get('lock',True) is not False
# optional unlock code: only a salted PBKDF2 hash is kept; it needs the lock
# screen, so turning that off forgets the code
PIN_ITER=20000
# misses in a row are kept on disk (a reboot does not reset them): from the
# 5th one the screen waits 30 s, doubling; at PIN_MAX it stops taking codes
# until the web panel (admin password) unblocks it
PIN_MAX=10
PIN_FAIL={'n':0,'until':0.0}
def pin_wait(n):return 30*2**(n-5) if n>=5 else 0
def pin_fail_load():
    try:n=int(load('pin-fail.json',{}).get('n',0))
    except (TypeError,ValueError):n=0
    PIN_FAIL.update(n=n,until=time.monotonic()+pin_wait(n) if n<PIN_MAX else 0.0)   # after a reboot the wait starts again
def pin_fail_save(n):
    PIN_FAIL['n']=n
    if n:save('pin-fail.json',{'n':n})
    else:
        PIN_FAIL['until']=0.0
        try:(STATE/'pin-fail.json').unlink()
        except FileNotFoundError:pass
def pin_blocked():return display_pin() is not None and PIN_FAIL['n']>=PIN_MAX
def pin_unblock():
    pin_fail_save(0);log('Pantalla de bloqueo desbloqueada desde el panel web')
def display_pin():
    p=load('display.json',{}).get('pin')
    return p if isinstance(p,dict) and 'salt' in p and 'hash' in p else None
def pin_hash(pin,salt):return hashlib.pbkdf2_hmac('sha256',pin.encode(),bytes.fromhex(salt),PIN_ITER).hex()
def pin_set(pin,again):
    if not re.fullmatch(r'\d{4,8}',pin or ''):raise ValueError('El código debe tener de 4 a 8 cifras')
    if pin!=again:raise ValueError('Los dos códigos no coinciden')
    salt=secrets.token_hex(16);display_save(lock=True,pin={'salt':salt,'hash':pin_hash(pin,salt)});pin_fail_save(0);log('Código de la pantalla de bloqueo puesto')
def pin_clear():
    display_save(pin=None);pin_fail_save(0);log('Código de la pantalla de bloqueo quitado')
def pin_try(pin):
    """Checks a code typed on the lock screen (see PIN_MAX)."""
    p=display_pin()
    if not p:return
    if pin_blocked():raise ValueError('Pantalla bloqueada tras %d códigos erróneos. Desbloquéala desde el panel web.'%PIN_MAX)
    wait=PIN_FAIL['until']-time.monotonic()
    if wait>0:raise ValueError('Demasiados intentos: espera %d s'%(wait+1))
    if hmac.compare_digest(pin_hash(pin or '',p['salt']),p['hash']):pin_fail_save(0);return
    n=PIN_FAIL['n']+1;pin_fail_save(n)
    if n>=PIN_MAX:
        log('Pantalla de bloqueo: BLOQUEADA tras %d códigos erróneos'%n)
        raise ValueError('Pantalla bloqueada tras %d códigos erróneos. Desbloquéala desde el panel web.'%n)
    if n>=5:
        PIN_FAIL['until']=time.monotonic()+pin_wait(n)
        log('Pantalla de bloqueo: %d códigos erróneos seguidos'%n)
        raise ValueError('Código incorrecto. Espera %d s (quedan %d intentos)'%(pin_wait(n),PIN_MAX-n))
    raise ValueError('Código incorrecto')
def pin_need(f):
    # on the screen the current code is needed to remove it; misses count like
    # on the lock screen (the web panel can still remove it: forgotten code)
    if not f.get('pincur'):raise ValueError('Escribe el código actual')
    pin_try(f['pincur'])
def display_save(**kw):
    conf={'timeout':display_timeout(),'brightness':display_brightness(),'lock':display_lock(),'pin':display_pin()};conf.update(kw)
    if not conf['lock'] or not conf['pin']:conf.pop('pin')
    save('display.json',conf)

def ui_disp(arg):
    s=Screen('disp','Pantalla').label('Brillo:').slider('disp.bright',display_brightness(),BRIGHT_MIN,255)
    lk=display_lock();s.toggle('disp.lock:0' if lk else 'disp.lock:1','Pantalla de bloqueo',lk)
    s.small('Al apagarse, un toque solo enciende el reloj: hay que deslizar para usarla. Evita pulsaciones sin querer.','m')
    if lk and display_pin():
        s.label('Código de desbloqueo: activado','g').field('pincur','Código actual (para quitarlo o desactivar el bloqueo)','','q')
        s.button('disp.pinoff','Quitar el código','d')
    elif lk:
        s.field('pin','Código de desbloqueo (4 a 8 cifras, opcional)','','q').field('pin2','Repite el código','','q')
        s.button('disp.pin','Poner código','p')
        s.small('Si lo olvidas, quítalo desde el panel web (sección Pantalla de bloqueo).','m')
    cur=display_timeout();s.gap().label('Apagar la pantalla tras:')
    for t,n in DISPLAY_TIMES:s.button('disp.set:%d'%t,('> ' if t==cur else '')+n,'p' if t==cur else 'i')
    s.small('Se apaga al acabar el tiempo elegido. Los últimos segundos se atenúa: un toque ahí la usa directamente. Apagada, el primer toque solo la enciende.','m')
    return s.small('Siempre encendida: tras 1 min sin tocarla los datos se actualizan cada 30 s para no gastar CPU.','m')

# resources: deltas between two visits of the screen (no background sampling)
RES_PREV={}
def proc_sample():
    procs={}
    for pid in os.listdir('/proc'):
        if not pid.isdigit():continue
        try:
            st=Path('/proc/'+pid+'/stat').read_text();name=st[st.index('(')+1:st.rindex(')')]
            f=st[st.rindex(')')+2:].split()
            procs[pid]=(name,int(f[11])+int(f[12]),int(f[21])*4)  # utime+stime, rss pages -> KB
        except (OSError,ValueError,IndexError):pass
    cpu=[int(x) for x in Path('/proc/stat').read_text().split('\n',1)[0].split()[1:]]
    return {'t':sum(cpu),'idle':cpu[3]+cpu[4],'procs':procs,'when':time.monotonic()}

def net_bytes(dev):
    try:return sum(int((Path('/sys/class/net')/dev/'statistics'/k).read_text()) for k in ('rx_bytes','tx_bytes'))
    except OSError:return 0

# ---- battery: the fuel gauge counts the current (mA, + charging, - using the
# battery). Time left = charge left of the 1850 mAh the gauge also uses, over the
# mean current of the last minutes. Kernels without the counter fall back to
# how fast the charge (0.1 % steps) moves. One reading a minute from the worker.
BAT=Path('/sys/class/power_supply/battery')
FGU=Path('/sys/class/power_supply/sprdfgu/fgu_current')
BAT_MAH=1850
BAT_WH=BAT_MAH/1000*3.8
BAT_HIST=[]
def bat_read():
    rd=lambda n:(BAT/n).read_text().strip()
    try:
        b={'cap':int(rd('capacity')),'status':rd('status'),'v':int(rd('voltage_now'))/1e6,'temp':int(rd('temp'))/10}
        try:b['soc']=int(rd('batt_read_raw_soc'))/10
        except (OSError,ValueError):b['soc']=b['cap']
        if not 0<=b['soc']<=100:b['soc']=b['cap']
    except (OSError,ValueError):return None
    try:b['ma']=int(FGU.read_text().strip())
    except (OSError,ValueError):b['ma']=None
    if b['ma'] is not None and abs(b['ma'])<=1:b['ma']=None   # no counter: always 1
    if bat_paused():b['status']='Paused'
    return b
# ---- charge limit: at the limit the charger is paused (slate mode: the J1 runs
# on the battery with the cable plugged) and comes back BAT_RESUME points lower.
# j1-init turns it back on if web.py is not running.
BAT_LIMIT_MIN,BAT_LIMIT_MAX=50,95
BAT_RESUME=5
def bat_limits():
    c=load('battery.json',{})
    ok=lambda v:isinstance(v,int) and BAT_LIMIT_MIN<=v<=BAT_LIMIT_MAX
    return (c['limit'] if ok(c.get('limit')) else 0),(c['last'] if ok(c.get('last')) else 80)
def bat_limit():return bat_limits()[0]   # 0: no limit
def bat_limit_save(v):
    if v and not BAT_LIMIT_MIN<=v<=BAT_LIMIT_MAX:raise ValueError('El límite va del %d al %d %%'%(BAT_LIMIT_MIN,BAT_LIMIT_MAX))
    save('battery.json',{'limit':v,'last':v or bat_limits()[1]});bat_limit_apply()
def bat_paused():
    try:return (BAT/'batt_slate_mode').read_text().strip()=='1'
    except OSError:return False
def bat_pause(on):
    try:(BAT/'batt_slate_mode').write_text('1' if on else '0')
    except OSError:pass
def bat_limit_apply():
    b=bat_read();lim=bat_limit()
    if not b:return
    if b['status']=='Paused':
        if not lim or b['cap']<=lim-BAT_RESUME:bat_pause(False);log('Carga reanudada al %d%%'%b['cap'])
    elif lim and b['status'] in ('Charging','Full') and b['cap']>=lim:bat_pause(True);log('Carga en pausa: límite del %d%%'%lim)
def bat_sample():
    b=bat_read();now=time.monotonic()
    if not b:return
    if BAT_HIST and BAT_HIST[-1][2]!=b['status']:BAT_HIST.clear()
    BAT_HIST.append((now,b['soc'],b['status'],b['ma']))
    while now-BAT_HIST[0][0]>3600:BAT_HIST.pop(0)
def bat_rate():
    # % per hour (+ charging, - discharging); None while it cannot be told yet
    if len(BAT_HIST)<2:return None
    (t0,s0,*_),(t1,s1,*_)=BAT_HIST[0],BAT_HIST[-1]
    if t1-t0<600 or abs(s1-s0)<.5:return None
    return (s1-s0)*3600/(t1-t0)
def bat_mean_ma(b):
    # this reading and the last 10 minutes with the same charger state
    now=time.monotonic();m=[x[3] for x in BAT_HIST if x[2]==b['status'] and x[3] is not None and now-x[0]<=600]+[b['ma']]
    return sum(m)/len(m)
def duration(h):
    m=round(h*60)
    return '%d min'%m if m<60 else '%d h %02d min'%(m//60,m%60)
BAT_HEALTH={'Good':'buena','Overheat':'demasiado caliente','Cold':'demasiado fría','Dead':'agotada','Over voltage':'sobretensión'}
def bat_info():
    # [(name, value, colour)]: the Batería screen and the web panel's section
    b=bat_read()
    if not b:return []
    st=b['status'];t=b['temp'];ma=b['ma'];lim=bat_limit()
    paused='en pausa por el límite del %d%%; vuelve a cargar al %d%%'%(lim,lim-BAT_RESUME) if lim else 'en pausa'
    out=[('Carga','%d%%'%b['cap'],'r' if b['cap']<=15 else 'y' if b['cap']<=30 else 'g'),
         ('Estado',{'Charging':'cargando','Full':'cargada, con el cargador puesto','Discharging':'sin cargador, usando la batería','Paused':paused}.get(st,'cargador puesto, sin cargar'),'y' if st=='Discharging' else 'g'),
         ('Temperatura','%.1f °C'%t,'r' if t>=55 else 'y' if t>=45 else 'g'),('Voltaje','%.2f V'%b['v'],'y' if b['v']<3.6 else 'g')]
    if ma is not None:
        mean=bat_mean_ma(b)
        if st in ('Discharging','Paused') and ma<0:
            out.append(('Consumo','%d mA (%.2f W)'%(-ma,-ma*b['v']/1000),'y'))
            if st=='Discharging' and mean<0:out.append(('Tiempo restante','unas '+duration(b['soc']/100*BAT_MAH/-mean),'y'))
        elif st=='Charging' and ma>0:
            out.append(('Corriente de carga','%d mA'%ma,'g'))
            # last, constant-voltage stretch: the current keeps falling, no time from it
            if lim:
                if b['soc']<lim:out.append(('Llega al %d%% en'%lim,'unas '+duration((lim-b['soc'])/100*BAT_MAH/mean),'g'))
            elif mean<100 or b['v']>=4.3:out[1]=('Estado','cargando, casi llena','g')
            else:out.append(('Llena en','unas '+duration((100-b['soc'])/100*BAT_MAH/mean),'g'))
    elif st=='Discharging':
        r=bat_rate()
        if r and r<0:out+=[('Tiempo restante','unas '+duration(b['soc']/-r),'y'),('Consumo','aprox. %.1f W (%.1f %% por hora)'%(-r/100*BAT_WH,-r),'y')]
        elif len(BAT_HIST)>1 and BAT_HIST[-1][0]-BAT_HIST[0][0]>=3000:out.append(('Tiempo restante','más de 1 día (consumo muy bajo)','g'))
        else:out.append(('Tiempo restante','calculando (unos 10 min)','m'))
    elif st=='Charging':
        r=bat_rate()
        if r and r>0:out.append(('Llena en','unas '+duration((100-b['soc'])/r),'g'))
    try:h=(BAT/'health').read_text().strip();out.append(('Salud',BAT_HEALTH.get(h,'desconocida'),'g' if h=='Good' else 'r'))
    except OSError:pass
    return out
def bat_note():
    b=bat_read()
    if b and b['ma'] is not None:return 'Consumo medido por el chip de la batería. El tiempo restante usa la corriente media de los últimos 10 minutos y la capacidad de fábrica (%d mAh); con una batería gastada durará menos.'%BAT_MAH
    return 'Sin medida de corriente: el tiempo restante y el consumo se calculan por lo que baja la carga sin cargador (última hora).'
def ui_bat(arg):
    s=Screen('bat','Batería',refresh=30);info=bat_info()
    if not info:return s.label('No se puede leer la batería.','r')
    for n,v,c in info:s.label('%s: %s'%(n,v),c)
    s.small(bat_note(),'m')
    lim,last=bat_limits()
    s.gap().toggle('bat.limit:0' if lim else 'bat.limit:%d'%last,'Limitar la carga',lim)
    if lim:s.label('Cargar hasta:').slider('bat.limit',lim,BAT_LIMIT_MIN,BAT_LIMIT_MAX)
    return s.small(BAT_LIMIT_NOTE,'m')
BAT_LIMIT_NOTE='Tener la batería siempre al 100%% con el cargador puesto la desgasta. Con el límite, al llegar se pausa la carga (el J1 usa la batería con el cable puesto) y vuelve a cargar %d puntos por debajo.'%BAT_RESUME
def bat_section():
    info=bat_info();lim,last=bat_limits()
    return ('<section id=bat><h2>Batería</h2>'+(''.join('<p class=kv>'+('<span class="dot '+c+'"></span>' if c in 'gyr' else '')+'<span>'+esc(n)+': <b>'+esc(v)+'</b></span></p>' for n,v,c in info) if info else '<p>No se puede leer la batería.</p>')+
            '<p class=muted>'+esc(bat_note())+'</p><h3>Límite de carga</h3><form method=post>'+hidden()+'<input type=hidden name=action value=batlimit>'
            '<label><input type=checkbox name=on value=1'+(' checked' if lim else '')+'> Limitar la carga</label>'
            '<label>Cargar hasta (%%)<input type=number name=limit min=%d max=%d required value=%d></label>'%(BAT_LIMIT_MIN,BAT_LIMIT_MAX,lim or last)+
            '<small>'+esc(BAT_LIMIT_NOTE)+'</small><br><button>Guardar límite</button></form></section>')

def ui_res(arg):
    s=Screen('res','Recursos',refresh=3)
    now=proc_sample();now['wg']=net_bytes('wg0');prev=RES_PREV.get('s');RES_PREV['s']=now
    if not prev:s.label('Midiendo...','m')
    else:
        dt=max(1,now['t']-prev['t']);secs=max(.1,now['when']-prev['when'])
        s.label('CPU total: %d%%'%round(100*(dt-(now['idle']-prev['idle']))/dt),'g')
        s.label('WireGuard tráfico: %s/s'%size_h(max(0,now['wg']-prev['wg'])/secs))
        use={}
        for pid,(name,ticks,rss) in now['procs'].items():
            if pid in prev['procs'] and rss:
                u=use.setdefault(name,[0,0]);u[0]+=ticks-prev['procs'][pid][1];u[1]+=rss
        for name,(ticks,rss) in sorted(use.items(),key=lambda x:(-x[1][0],-x[1][1]))[:8]:
            s.add('P',name[:16],'CPU %.1f%%'%(100*ticks/dt),'RAM %.1f MB'%(rss/1024),'g' if name=='wireguard-go' else 'n')
        if 'wireguard-go' not in use:s.small('WireGuard en el kernel: su CPU va en "CPU total" (sin proceso propio).','g')
    try:
        mem={l.split(':')[0]:int(l.split()[1]) for l in Path('/proc/meminfo').read_text().splitlines() if l.split()[1:2]}
        s.label('RAM libre: %d de %d MB'%(mem.get('MemAvailable',mem['MemFree']+mem.get('Cached',0))//1024,mem['MemTotal']//1024))
        d=os.statvfs('/');s.label('Disco libre: %d MB'%(d.f_bavail*d.f_frsize//1048576))
    except (OSError,KeyError,ValueError):pass
    return s.small('% de CPU sobre el total de los 2 núcleos (el segundo solo se enciende con carga). Esta vista solo mide mientras está abierta.','m')

BRAND='J1 Open VPN · © 2026 Farweb'
REPO='github.com/Farwebsite/j1-open-vpn'
def ui_home():
    s=Screen('home','J1 · Servidor VPN','',3)
    ok=lambda t:'g' if re.search(r'\d+\.\d+\.\d+\.\d+',t) else 'y'
    wifi=readrun('wifi-summary','Wi-Fi: ?');s.label(wifi,ok(wifi))
    eth=readrun('eth-summary')
    if re.search(r'\d+\.\d+',eth):s.label(eth,'g')
    s.label(readrun('vpn-summary','WG: ?'),'g' if RUNTIME['vpn'].startswith('Activo') else 'y')
    s.label('DNS: '+RUNTIME['ddns'],'g' if RUNTIME['ddns'].startswith('Actualizado') else 'm')
    s.label('Red config: apagada' if (STATE/'ap-off').exists() else readrun('ap-name')+' · '+readrun('ap-password'),'m')
    for a,t in (('wifi','Wi-Fi'),('ap','Red de configuración'),('vpn','WireGuard'),('dns','Cloudflare DNS'),('usb','Cable USB'),
                ('speed','Velocidad'),('panel','Panel web'),('res','Recursos'),('bat','Batería'),('notify','Avisos'),('disp','Pantalla'),('tz','Zona horaria'),('logs:sys','Registros'),('sys','Sistema')):
        s.tile('nav:'+a,t,a.split(':')[0])
    return s.small(BRAND,'m').small(REPO,'m')

def ui_wifi(arg):
    on=not (STATE/'wifi-off').exists()
    s=Screen('wifi','Wi-Fi',refresh=5).label(readrun('wifi-summary','Wi-Fi: ?'))
    s.toggle('wifi.off' if on else 'wifi.on','Wi-Fi cliente',on)
    if 'IP fija' in readrun('wifi-summary') or (STATE/'ip-wlan0.conf').exists():s.small('IP manual activa','y')
    s.button('nav:ip:wlan0','IP de la Wi-Fi','i','ip')
    s.button('camqr.start:rear','Escanear QR de una red','i','cam')
    s.button('wifi.scan','Buscar redes','p','wifi').small(RUNTIME['scan'],'m')
    for n in RUNTIME['networks']:
        s.button('nav:wifinet:'+n['hex'],'%s  %d dBm%s'%(n['name'],n['signal'],'' if n['secure'] else ' · abierta'),'i','wifi')
    if client_wifi():s.button('nav:wifiqr:client','QR de la red guardada','i','qr')
    return s.button('nav:wifihidden','Red oculta','i','wifi')

def ui_wifinet(arg):
    n=next((n for n in RUNTIME['networks'] if n['hex']==arg),None)
    try:name=bytes.fromhex(arg).decode('utf8','replace')
    except ValueError:raise ValueError('Red no válida')
    s=Screen('wifinet:'+arg,'Conectar','nav:wifi').label(name,'g')
    if n and not n['secure']:return s.small('Red abierta, sin contraseña','y').button('wifi.joinopen:'+arg,'Conectar','p')
    return s.field('password','Contraseña Wi-Fi','','p').button('wifi.join:'+arg,'Conectar','p')

def ui_wifihidden(arg):
    return (Screen('wifihidden','Red oculta','nav:wifi').field('ssid','Nombre de la red (SSID)')
        .field('password','Contraseña (vacía = red abierta)','','p').button('wifi.hidden','Conectar','p'))

def ui_ap(arg):
    on=not (STATE/'ap-off').exists();go=readrun('ap-interface')
    s=Screen('ap','Red config',refresh=5).label(readrun('ap-name','AP'))
    up=on and go and Path('/sys/class/net/'+go).exists()
    s.label('Activa' if up else 'Apagada' if not on else 'Arrancando...','g' if up else 'y')
    s.toggle('ap.off' if on else 'ap.on','Red de configuración',on)
    if not on and (STATE/'wifi-off').exists():s.small('Wi-Fi cliente y red de configuración apagadas: solo USB y pantalla.','y')
    s.label(readrun('ap-password'),'m')
    try:leases=len((RUN/'dnsmasq.leases').read_text().splitlines())
    except OSError:leases=0
    s.small('Equipos con dirección asignada: %d'%leases,'m').gap()
    s.button('nav:wifiqr:ap','QR para conectarse','i','qr')
    s.field('password','Nueva clave (8 a 63 caracteres)','','p').button('ap.pass','Cambiar clave','p')
    return s.small(('El panel web tiene contraseña propia (Panel web). ' if panel_own_password() else 'Es también la contraseña del panel web mientras no le pongas una propia (Panel web). ')+'Los equipos conectados tendrán que volver a conectarse.','m')

def ui_ip(cls):
    if cls not in IP_CLASSES:raise ValueError('Interfaz no válida')
    conf=ip_load(cls);name=IP_CLASSES[cls]
    s=Screen('ip:'+cls,'IP · '+name,'nav:wifi' if cls=='wlan0' else 'nav:usb')
    s.label(readrun('wifi-summary' if cls=='wlan0' else 'eth-summary',name+': sin datos'))
    s.label('Modo: IP manual '+conf['ip'] if conf else 'Modo: automática (DHCP)','y' if conf else 'g')
    s.toggle('ip.need:'+cls if not conf else 'ip.auto:'+cls,'IP automática (DHCP)',not conf)
    if conf and ip_shared():s.small('Misma IP en Wi-Fi y cable: un solo puerto en el router. Usa el cable si tiene Internet; si no, la Wi-Fi.','g')
    elif conf:s.button('ip.share:'+cls,'Usar esta IP también en '+('el cable' if cls=='wlan0' else 'la Wi-Fi'),'i','ip')
    if not conf:
        # suggest the current DHCP values
        try:
            dev='wlan0' if cls=='wlan0' else next((d for d in sorted(os.listdir('/sys/class/net')) if d.startswith(('eth','usb'))),'')
            a=re.search(r'inet (\S+)',command(['ip','-4','-o','addr','show','dev',dev])) if dev else None
            r=re.search(r'default via (\S+) dev '+re.escape(dev)+r'\b',command(['ip','-4','route','show','default'])) if dev else None
            routes=command(['ip','-4','route','show','dev',dev]) if dev else ''
            net=next((x for x in re.findall(r'^(\d+\.\d+\.\d+\.\d+/\d+)',routes,re.M)),None)
            conf={'ip':a[1].split('/')[0] if a else '','prefix':net.split('/')[1] if net else '24','router':r[1] if r else ''}
        except (RuntimeError,OSError,subprocess.SubprocessError):conf={}
    else:
        conf=dict(conf,prefix=str(ipaddress.IPv4Network('0.0.0.0/'+conf.get('subnet','255.255.255.0')).prefixlen))
    s.field('ip','Dirección IP',conf.get('ip',''),'i').field('prefix','Prefijo (24 = 255.255.255.0)',conf.get('prefix','24'),'n')
    s.field('gw','Puerta de enlace',conf.get('router',''),'i').field('dns','DNS (separados por espacio)',conf.get('dns',''),'i')
    return s.button('ip.save:'+cls,'Guardar IP manual','p')

def ui_panel(arg):
    c=panel_conf();s=Screen('panel','Panel web',refresh=10)
    s.toggle('panel.off' if c['enabled'] else 'panel.on','Panel web',c['enabled'])
    if c['enabled']:
        s.toggle('panel.lan:0' if c['lan'] else 'panel.lan:1','Acceso desde la red local',c['lan'])
        s.toggle('panel.vpn:0' if c['vpn'] else 'panel.vpn:1','Acceso desde la VPN',c['vpn'])
        s.label('Direcciones:')
        s.small('Red del J1: '+('https' if c['https'] else 'http')+'://192.168.78.1','g').small('USB: '+('https' if c['https'] else 'http')+'://192.168.77.1','g')
        s.toggle('panel.https:0' if c['https'] else 'panel.https:1','Cifrado HTTPS',c['https'])
        sc='https' if c['https'] else 'http'
        if c['lan']:
            ips=lan_ips()
            for ip in ips:s.small('Red local: '+sc+'://'+ip,'g')
            if not ips:s.small('Red local: sin IP (conecta la Wi-Fi o el cable)','y')
            if not c['https']:s.small('En la red local el panel va sin cifrar (HTTP): activa HTTPS o úsalo solo en casa, y no abras el puerto 80 en el router.','y')
        if c['vpn']:s.small('VPN: '+sc+'://10.66.0.1 (cifrado por el túnel, desde cualquier sitio)','g')
        if c['https']:s.small('El navegador avisará la primera vez (certificado propio del J1). Comprueba que la huella SHA-256 empieza por '+https_fingerprint()[:23],'m')
    else:s.small('Puerto 80 cerrado. La pantalla sigue funcionando; sin panel no se descargan los .conf ni se gestiona el SSH.','m')
    own=panel_own_password() is not None
    s.gap().label('Contraseña del panel (usuario admin):').small('Propia' if own else 'La misma clave de la red de configuración','g' if own else 'm')
    s.field('pw','Nueva contraseña (8 a 64 caracteres)','','p').field('pw2','Repítela','','p').button('panel.pw','Cambiar contraseña del panel','p')
    if own:s.button('panel.pwreset','Volver a usar la clave de la red','i')
    s.gap().label('IP del J1 en la red local:')
    return s.button('nav:ip:wlan0','IP de la Wi-Fi (DHCP o fija)','i','ip').button('nav:ip:eth','IP del cable (DHCP o fija)','i','ip')

def ui_vpn(arg):
    v=ensure_vpn_state();peers=wg_peers()
    s=Screen('vpn','WireGuard',refresh=10).label(RUNTIME['vpn'],'g' if RUNTIME['vpn'].startswith('Activo') else 'y')
    s.field('port','Puerto UDP',v['port'],'n').field('endpoint','Dominio o IP (vacío = Cloudflare)',v.get('endpoint',''))
    s.button('vpn.save','Guardar puerto y dirección','p')
    up=load('upnp.json',{'enabled':True}).get('enabled',True)
    s.toggle('upnp.off' if up else 'upnp.on','Abrir puerto (UPnP)',up)
    s.small('Router: '+RUNTIME['upnp'],'g' if RUNTIME['upnp'].startswith('Abierto') and 'privada' not in RUNTIME['upnp'] else 'y' if up else 'm')
    s.gap().label('Clientes: %d'%len(v['clients']))
    for c in v['clients']:
        p=peers.get(c['public_key'],{})
        s.button('nav:client:'+c['id'],'%s · .%s · %s'%(c['name'],c['ip'],'en pausa' if c.get('paused') else ago(p.get('handshake',0))),'i','user')
    return s.field('name','Nombre del nuevo cliente').button('vpn.add','Crear cliente','p')

def ui_client(cid):
    v=ensure_vpn_state();c=next((c for c in v['clients'] if c['id']==cid),None)
    if c is None:raise ValueError('El cliente ya no existe')
    p=wg_peers().get(c['public_key'],{})
    s=Screen('client:'+cid,c['name'],'nav:vpn',10).label('IP en la VPN: 10.66.0.%s'%c['ip'])
    pa=c.get('paused')
    if pa:s.label('En pausa: no puede conectarse','y')
    else:
        s.label('Última conexión: '+ago(p.get('handshake',0)),'g' if p.get('handshake') and time.time()-p['handshake']<180 else 'm')
        if p.get('endpoint','(none)')!='(none)':s.small('Desde '+p['endpoint'],'m')
        s.small('Recibido %s · enviado %s'%(size_h(p.get('rx',0)),size_h(p.get('tx',0))),'m')
    s.toggle('vpn.pause:%s:%d'%(cid,0 if pa else 1),'Acceso a la VPN',not pa)
    s.button('nav:qr:'+cid,'Mostrar QR','p','qr')
    cf=load('cloudflare.json',{})
    if cf.get('enabled6') and cf.get('hostname6'):s.button('nav:qr6:'+cid,'QR por IPv6 (prueba)','i','qr')
    s.button('nav:del:'+cid,'Quitar cliente','d')
    return s.small('El QR contiene la clave privada del cliente: muéstralo solo para importarlo en la app WireGuard.','m')

def ui_qr(cid):
    v=ensure_vpn_state();c=next((c for c in v['clients'] if c['id']==cid),None)
    if c is None:raise ValueError('El cliente ya no existe')
    s=Screen('qr:'+cid,'QR · '+c['name'],'nav:client:'+cid)
    s.add('Q',','.join(qr_rows(client_profile(cid,local_ip()))))
    return s.small('App WireGuard: + > Escanear código QR','m')

def ui_qr6(cid):
    v=ensure_vpn_state();c=next((c for c in v['clients'] if c['id']==cid),None)
    if c is None:raise ValueError('El cliente ya no existe')
    host=load('cloudflare.json',{}).get('hostname6','')
    if not host:raise ValueError('Configura el nombre IPv6 en Cloudflare DNS')
    s=Screen('qr6:'+cid,'QR IPv6 · '+c['name'],'nav:client:'+cid)
    s.add('Q',','.join(qr_rows(client_profile(cid,local_ip(),host))))
    return (s.small('Conecta por '+host+' (IPv6). Solo funciona desde redes con IPv6 y con el puerto UDP abierto en el router.','m')
        .small('Impórtalo como túnel aparte para probar sin tocar el normal.','m'))

def ui_del(cid):
    v=ensure_vpn_state();c=next((c for c in v['clients'] if c['id']==cid),None)
    if c is None:raise ValueError('El cliente ya no existe')
    return (Screen('del:'+cid,'Quitar cliente','nav:client:'+cid).label('¿Quitar '+c['name']+'? Perderá el acceso a la VPN.','y')
        .button('vpn.del:'+cid,'Sí, quitar','d').button('nav:client:'+cid,'Cancelar'))

def ui_dns(arg):
    cf=load('cloudflare.json',{})
    s=Screen('dns','Cloudflare DNS',refresh=10).label(RUNTIME['ddns'],'g' if RUNTIME['ddns'].startswith('Actualizado') else 'm')
    s.toggle('dns.off' if cf.get('enabled') else 'dns.on','DNS automático',cf.get('enabled'))
    s.field('hostname','Nombre del registro',cf.get('hostname','')).field('zone_id','ID de zona',cf.get('zone_id',''))
    s.field('token','Token API'+(' (vacío = conservar)' if cf.get('token') else ''),'','p')
    s.gap().label('IPv6 (prueba)')
    s.label(RUNTIME['ddns6'],'g' if RUNTIME['ddns6'].startswith('Actualizado') else 'm')
    s.toggle('dns6.off' if cf.get('enabled6') else 'dns6.on','DNS IPv6',cf.get('enabled6'))
    s.field('hostname6','Nombre IPv6 (registro AAAA)',cf.get('hostname6',''))
    s.small('Esquiva el CG-NAT: el J1 tiene IPv6 pública propia. Hay que abrir el puerto UDP en el cortafuegos IPv6 del router.','m')
    return s.button('dns.save','Guardar Cloudflare','p','dns')

def ui_usb(arg):
    s=Screen('usb','Cable USB',refresh=3)
    if not (USB_PARAMS/'j1_boost').exists():return s.label('Este kernel no admite modo host USB.','y')
    s.label(readrun('eth-summary','Cable: sin adaptador'))
    s.label(('Modo host (adaptador)' if usb_param('j1_host_active')=='1' else 'Modo dispositivo (PC)')+' · '+
        ('el J1 da 5 V' if usb_param('j1_boost_on')=='1' else 'sin 5 V del J1'),'m')
    if usb_param('j1_boost_locked')=='1':s.small('5 V bloqueados hasta reconectar el OTG (%s intentos).'%(usb_param('j1_boost_tries') or '0'),'y')
    on=usb_param('j1_boost')=='1'
    s.toggle('usb.off' if on else 'usb.on','Alimentación automática 5 V',on)
    return s.button('nav:ip:eth','IP del cable','i','ip')

def ui_logs(kind):
    names={'sys':'Sistema','net':'Red','vpn':'VPN','kernel':'Kernel'}
    kind=kind if kind in names else 'sys'
    s=Screen('logs:'+kind,'Registro · '+names[kind],refresh=3)
    for k,n in names.items():
        if k!=kind:s.button('nav:logs:'+k,'Ver '+n,'i','logs')
    if kind=='sys':lines=tail(RUN/'appliance.log')
    elif kind=='kernel':lines=tail(LOGS/'kmsg.log')
    elif kind=='net':lines=tail(RUN/'udhcpc.log',30)+tail(RUN/'wpa-client.log',40)
    else:
        try:lines=command(['wg','show','wg0']).splitlines()
        except (RuntimeError,OSError,subprocess.SubprocessError):lines=['WireGuard no disponible']
        lines+=tail(RUN/'wireguard.log',30)
    for line in lines or ['(vacío)']:s.small(line)
    return s

def ui_sys(arg):
    s=Screen('sys','Sistema',refresh=5)
    try:
        up=float(Path('/proc/uptime').read_text().split()[0]);load=Path('/proc/loadavg').read_text().split()[:3]
        mem={l.split(':')[0]:int(l.split()[1]) for l in Path('/proc/meminfo').read_text().splitlines() if l.split()[1:2]}
        s.label('Encendido: %dd %dh %dmin'%(up//86400,up%86400//3600,up%3600//60)).label('Carga: '+' '.join(load))
        s.label('RAM libre: %d / %d MB'%(mem.get('MemAvailable',mem.get('MemFree',0))//1024,mem['MemTotal']//1024))
    except (OSError,KeyError,ValueError):pass
    s.label('Kernel '+os.uname().release,'m').small(BRAND,'m').small(REPO,'m')
    s.button('nav:update','Actualizar','i','update').small('Copia de seguridad: desde el panel web.','m')
    return s.button('nav:reboot','Reiniciar J1','d','power').button('nav:poweroff','Apagar J1','d','power')

# speed test through whatever link has the route (cable or Wi-Fi), in the background
SPEED={}
SPEED_URL='https://speed.cloudflare.com/'
def speed_link():
    try:m=re.search(r' dev (\S+)',command(['ip','route','get','1.1.1.1'],timeout=5))
    except RuntimeError:m=None
    dev=m.group(1) if m else '?'
    return dev,'Wi-Fi' if dev.startswith('wlan') else 'cable' if dev.startswith(('eth','usb')) else dev
def speed_mbit(n,t):return '%.1f Mbit/s'%(n*8/t/1e6) if t>0 else '?'
def speed_run():
    def step(k,v):
        with LOCK:SPEED[k]=v
    try:
        dev,name=speed_link();step('link','%s (%s)'%(name,dev))
        try:m=re.search(r'= [\d.]+/([\d.]+)/',command(['ping','-c','5','-q','1.1.1.1'],timeout=15))
        except RuntimeError:m=None
        step('ping',('%.0f ms'%float(m.group(1))) if m else 'sin respuesta')
        step('down','midiendo...');n=0;busy=0.0;fails=0
        # Cloudflare refuses big single downloads: 20 MB pieces for 10 s.
        # The first connection after a cable/Wi-Fi switch sometimes stalls: a failed piece is retried
        while busy<10 and fails<3:
            t1=time.monotonic()
            try:
                with urllib.request.urlopen(urllib.request.Request(SPEED_URL+'__down?bytes=20000000',headers={'User-Agent':'j1-vpn'}),timeout=6) as f:
                    while busy+time.monotonic()-t1<10:
                        b=f.read(65536)
                        if not b:break
                        n+=len(b)
                busy+=time.monotonic()-t1
            except OSError:
                fails+=1
                if not n and fails==3:raise
        if not n:raise OSError('la descarga no recibió datos; repítela en unos segundos')
        step('down',speed_mbit(n,busy))
        step('up','midiendo...');chunk=bytes(65536)
        for attempt in (1,2):
            sent=[0];t0=time.monotonic()
            def body():
                while time.monotonic()-t0<10 and sent[0]<100000000:
                    sent[0]+=len(chunk);yield chunk
            req=urllib.request.Request(SPEED_URL+'__up',data=body(),method='POST',headers={'Content-Type':'application/octet-stream','User-Agent':'j1-vpn'})
            try:
                with urllib.request.urlopen(req,timeout=15) as f:f.read()
                break
            except OSError:
                if attempt==2:raise
        step('up',speed_mbit(sent[0],time.monotonic()-t0))
        log('Prueba de velocidad por %s: bajada %s, subida %s, ping %s'%(SPEED['link'],SPEED['down'],SPEED['up'],SPEED['ping']))
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as e:
        step('error','Falló la prueba: %s'%(getattr(e,'reason',None) or e))
    finally:step('running',False)
def speed_start():
    with LOCK:
        if SPEED.get('running'):return
        SPEED.clear();SPEED['running']=True
    threading.Thread(target=speed_run,daemon=True).start()

def ui_speed(arg):
    with LOCK:sp=dict(SPEED)
    s=Screen('speed','Velocidad',refresh=1 if sp.get('running') else 0)
    if not sp:
        s.label('Mide la conexión a Internet por el enlace que esté usando el J1 (cable o Wi-Fi).')
        s.small('Tarda unos 25 s y gasta unos 100-200 MB de datos.','m')
        return s.button('speed.run','Empezar','p')
    for k,n in (('link','Por'),('ping','Ping'),('down','Bajada'),('up','Subida')):
        if k in sp:s.label('%s: %s'%(n,sp[k]),'y' if sp[k]=='midiendo...' else 'n')
    if sp.get('error'):s.label(sp['error'],'r')
    if sp.get('running'):return s.small('Midiendo...','m')
    s.small('Para la VPN cuenta sobre todo la subida: es lo que el J1 puede enviar a tus dispositivos fuera de casa.','m')
    return s.button('speed.run','Repetir','i')

def ui_reboot(arg):
    return (Screen('reboot','Reiniciar','nav:sys').label('¿Reiniciar el J1? La VPN se corta durante un minuto.','y')
        .button('sys.reboot','Sí, reiniciar','d').button('nav:sys','Cancelar'))

def ui_poweroff(arg):
    return (Screen('poweroff','Apagar','nav:sys').label('¿Apagar el J1? La VPN dejará de funcionar hasta que lo enciendas con el botón.','y')
        .small('Si está enchufado al cargador puede volver a encenderse solo.','m')
        .button('sys.poweroff','Sí, apagar','d').button('nav:sys','Cancelar'))

def ui_power(arg):
    # long press on the Power button: the tap on a button is the confirmation
    return (Screen('power','Apagar o reiniciar','nav:home').label('La VPN se corta mientras el J1 está apagado o reiniciándose.','y')
        .button('sys.poweroff','Apagar','d','power').button('sys.reboot','Reiniciar','d','power').button('nav:home','Cancelar'))

UI_SCREENS={'home':lambda a:ui_home(),'wifi':ui_wifi,'wifinet':ui_wifinet,'wifihidden':ui_wifihidden,'ap':ui_ap,
    'ip':ui_ip,'vpn':ui_vpn,'client':ui_client,'qr':ui_qr,'del':ui_del,'dns':ui_dns,'usb':ui_usb,'logs':ui_logs,
    'sys':ui_sys,'reboot':ui_reboot,'poweroff':ui_poweroff,'qr6':ui_qr6,'wifiqr':ui_wifiqr,'disp':ui_disp,'res':ui_res,'power':ui_power,'speed':ui_speed,'tz':ui_tz,'bat':ui_bat,'panel':ui_panel,'camqr':ui_camqr}

def ui_action(a, f):
    """Runs a screen action; returns (next screen, message)."""
    verb,_,arg=a.partition(':')
    if verb=='nav':return arg or 'home',None
    if verb in ('wifi.on','wifi.off'):wifi_enable(verb=='wifi.on');return 'wifi','Wi-Fi cliente '+('activada' if verb=='wifi.on' else 'apagada')
    if verb=='wifi.scan':scan_networks();return 'wifi',RUNTIME['scan']
    if verb=='wifi.join':wifi_save({'ssidhex':arg,'password':f.get('password','')});return 'wifi','Red guardada, conectando...'
    if verb=='wifi.joinopen':wifi_save({'ssidhex':arg,'open':'1'});return 'wifi','Red guardada, conectando...'
    if verb=='wifi.hidden':
        pw=f.get('password','');wifi_save({'ssid':f.get('ssid',''),'password':pw,'open':'' if pw else '1'})
        return 'wifi','Red guardada, conectando...'
    if verb=='camqr.start':camqr_start(arg);return 'camqr',None
    if verb=='camqr.switch':camqr_switch();return 'camqr',None
    if verb=='camqr.focus':camqr_focus();return 'camqr',None
    if verb=='camqr.set':camqr_set(arg);return 'camqr',None
    if verb=='camqr.close':camqr_stop();return 'wifi',None
    if verb in ('ap.on','ap.off'):ap_enable(verb=='ap.on');return 'ap','Red de configuración '+('activada' if verb=='ap.on' else 'apagada')
    if verb=='ap.pass':ap_password(f.get('password',''));return 'ap','Clave cambiada. Úsala también en la web.'
    if verb=='ip.need':return 'ip:'+cls_ok(arg),'IP manual: escribe la dirección, el prefijo y la puerta de enlace y pulsa Guardar IP manual'
    if verb=='ip.save':ip_save(arg,f);return 'ip:'+arg,'IP manual guardada'
    if verb=='ip.auto':ip_auto(arg);return 'ip:'+arg,'IP automática (DHCP)'
    if verb=='ip.share':ip_share(arg);return 'ip:'+arg,'IP compartida: el cable tiene prioridad y la Wi-Fi queda de reserva'
    if verb in ('upnp.on','upnp.off'):upnp_enable(verb=='upnp.on');return 'vpn','UPnP '+('activado: abriendo el puerto' if verb=='upnp.on' else 'desactivado: cerrando el puerto')
    if verb=='vpn.save':vpn_settings(f.get('port','0'),f.get('endpoint',''));return 'vpn','Guardado. Vuelve a importar los perfiles.'
    if verb=='vpn.add':c=client_create(f.get('name',''));return 'client:'+c['id'],'Cliente creado. Pulsa Mostrar QR.'
    if verb=='vpn.del':client_delete(arg);return 'vpn','Cliente quitado'
    if verb=='vpn.pause':
        cid,_,on=arg.partition(':')
        if on not in ('0','1'):raise ValueError('Opción no válida')
        client_pause(cid,on=='1');return 'client:'+cid,'Cliente '+('en pausa' if on=='1' else 'reanudado')
    if verb in ('dns.on','dns.off','dns.save','dns6.on','dns6.off'):
        cf=load('cloudflare.json',{})
        if verb=='dns.save':dns_settings(bool(cf.get('enabled')),f.get('hostname',''),f.get('zone_id',''),f.get('token',''),None,f.get('hostname6',cf.get('hostname6','')))
        elif verb.startswith('dns6'):dns_settings(bool(cf.get('enabled')),cf.get('hostname',''),cf.get('zone_id',''),'',verb=='dns6.on')
        else:dns_settings(verb=='dns.on',cf.get('hostname',''),cf.get('zone_id',''),'')
        return 'dns','Cloudflare guardado'
    if verb in ('panel.on','panel.off'):panel_set(enabled=verb=='panel.on');return 'panel','Panel web '+('activado' if verb=='panel.on' else 'desactivado')
    if verb=='panel.https':
        if arg not in ('0','1'):raise ValueError('Opción no válida')
        https_set(arg=='1');return 'panel','HTTPS '+('activado' if arg=='1' else 'desactivado')
    if verb=='panel.pw':panel_password_set(f.get('pw',''),f.get('pw2',''));return 'panel','Contraseña del panel cambiada'
    if verb=='panel.pwreset':panel_password_reset();return 'panel','El panel vuelve a usar la clave de la red'
    if verb in ('panel.lan','panel.vpn'):
        if arg not in ('0','1'):raise ValueError('Opción no válida')
        k=verb[6:];panel_set(**{k:arg=='1'})
        return 'panel','Acceso desde '+('la red local' if k=='lan' else 'la VPN')+' '+('activado' if arg=='1' else 'desactivado')
    if verb=='tz.set':return 'tz','Zona horaria: '+tz_set(arg)
    if verb=='disp.set':
        t=int(arg) if arg.isdigit() else -1
        if t not in dict(DISPLAY_TIMES):raise ValueError('Tiempo no válido')
        display_save(timeout=t);return 'disp','Guardado: '+dict(DISPLAY_TIMES)[t]
    if verb=='speed.run':speed_start();return 'speed',None
    if verb=='update.check':update_look();return 'update',None
    if verb=='update.run':update_start();return 'update',None
    if verb in ('notify.on','notify.off'):notify_save(enabled=verb=='notify.on');return 'notify','Avisos '+('activados' if verb=='notify.on' else 'desactivados')
    if verb=='notify.test':notify_test();return 'notify','Aviso de prueba enviado'
    if verb=='notify.topic':notify_save(new_topic=True);return 'notify','Tema nuevo: vuelve a suscribirte'
    if verb=='notify.ev':
        k,_,on=arg.partition(':');ev=notify_conf()['events']
        if k not in dict(NOTIFY_EVENTS) or on not in ('0','1'):raise ValueError('Opción no válida')
        notify_save(events=[e for e in ev if e!=k]+([k] if on=='1' else []));return 'notify',None
    if verb=='bat.limit':
        v=int(arg) if arg.isdigit() else -1
        bat_limit_save(v);return 'bat','Carga limitada al %d%%'%v if v else 'Sin límite de carga'
    if verb=='disp.lock':
        if arg not in ('0','1'):raise ValueError('Opción no válida')
        had=display_pin() is not None
        if had and arg=='0':pin_need(f)   # turning the lock off forgets the code
        display_save(lock=arg=='1');return 'disp','Pantalla de bloqueo '+('activada' if arg=='1' else 'desactivada'+(' y código quitado' if had else ''))
    if verb=='disp.pin':pin_set(f.get('pin',''),f.get('pin2',''));return 'disp','Código puesto: se pedirá al desbloquear'
    if verb=='disp.pinoff':pin_need(f);pin_clear();return 'disp','Código quitado'
    if verb=='lock.try':pin_try(f.get('pin',''));return 'home',None
    if verb=='lock.state':return 'home',None
    if verb=='disp.bright':
        b=int(arg) if arg.isdigit() else -1
        if not BRIGHT_MIN<=b<=255:raise ValueError('Brillo no válido')
        display_save(brightness=b);return 'disp',None
    if verb in ('usb.on','usb.off'):usb_set(verb=='usb.on');return 'usb','Alimentación USB guardada'
    if verb=='sys.reboot':
        log('Reinicio pedido desde la pantalla')
        subprocess.Popen(['/bin/busybox','sh','-c','sleep 2; sync; reboot -f'],start_new_session=True)
        return 'home','Reiniciando...'
    if verb=='sys.poweroff':
        log('Apagado pedido desde la pantalla')
        subprocess.Popen(['/bin/busybox','sh','-c','sleep 2; sync; poweroff -f'],start_new_session=True)
        return 'home','Apagando...'
    raise ValueError('Acción no válida')

def ui_request(raw):
    try:f={k:v[-1] for k,v in urllib.parse.parse_qs(raw.decode('ascii'),keep_blank_values=True,max_num_fields=40,encoding='cp437').items()}
    except (UnicodeDecodeError,ValueError):f={}
    fields={k[2:]:v for k,v in f.items() if k.startswith('f_')}
    msg=kind=None
    try:target,msg=ui_action(f.get('a','nav:home'),fields);kind='o'
    except (ValueError,RuntimeError) as e:target,msg,kind=f.get('s','home'),str(e),'e'
    except (OSError,subprocess.SubprocessError):target,msg,kind=f.get('s','home'),'No se pudo completar la operación','e'
    name,_,arg=target.partition(':')
    if name!='camqr' and CAMQR.get('running'):camqr_stop()   # left the camera (back, Home, Power...): off
    try:s=UI_SCREENS.get(name,UI_SCREENS['home'])(arg)
    except (ValueError,RuntimeError) as e:s=ui_home();msg,kind=str(e),'e'
    if msg:s.msg(msg,kind)
    with LOCK:busy=(SPEED.get('running') and name=='speed') or (CAMQR.get('running') and name=='camqr')
    s.rows.insert(1,['O','0' if busy else str(display_timeout())]);s.rows.insert(1,['V',str(display_brightness())])
    pin=display_lock() and display_pin() is not None
    s.rows.insert(1,['K','1' if display_lock() else '0','1' if pin else '0','1' if pin and pin_blocked() else '0'])
    return s.encode()

class UIHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(10);data=b''
        while len(data)<16384:
            b=self.request.recv(4096)
            if not b:break
            data+=b
        try:out=ui_request(data)
        except Exception as e:
            log('Pantalla: error '+type(e).__name__);out=Screen('home','J1').msg('Error interno','e').encode()
        self.wfile.write(out)

def ui_serve():
    path=RUN/'j1-ui.sock'
    while True:
        try:
            path.unlink(missing_ok=True)
            srv=socketserver.ThreadingUnixStreamServer(str(path),UIHandler);os.chmod(path,0o600)
            srv.daemon_threads=True;srv.serve_forever()
        except OSError:time.sleep(3)

# ---- UPnP: the J1 asks the home router to forward the WireGuard port ----
UPNP_SERVICES=('urn:schemas-upnp-org:service:WANIPConnection:2','urn:schemas-upnp-org:service:WANIPConnection:1',
               'urn:schemas-upnp-org:service:WANPPPConnection:1')
def uplink_ip():
    try:m=re.search(r'\bsrc (\S+)',command(['ip','-4','route','get','1.1.1.1']))
    except (RuntimeError,OSError,subprocess.SubprocessError):return ''
    return m[1] if m else ''

def upnp_find(local):
    """SSDP search for an Internet gateway; returns (control URL, service type) or None."""
    import socket
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.IPPROTO_IP,socket.IP_MULTICAST_IF,socket.inet_aton(local));s.bind((local,0));s.settimeout(0.5)
        for st in UPNP_SERVICES+('urn:schemas-upnp-org:device:InternetGatewayDevice:1',):
            s.sendto(('M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: 2\r\nST: %s\r\n\r\n'%st).encode(),('239.255.255.250',1900))
        locs=[];end=time.monotonic()+3
        while time.monotonic()<end:
            try:d,_=s.recvfrom(4096)
            except OSError:continue
            m=re.search(r'(?im)^location:\s*(\S+)',d.decode('latin1'))
            if m and m[1] not in locs:locs.append(m[1])
    finally:s.close()
    for loc in locs:
        try:x=urllib.request.urlopen(loc,timeout=5).read(65536).decode('latin1')
        except OSError:continue
        for svc,ctl in re.findall(r'<serviceType>\s*([^<]+?)\s*</serviceType>.*?<controlURL>\s*([^<]+?)\s*</controlURL>',x,re.S):
            if svc in UPNP_SERVICES:return urllib.parse.urljoin(loc,ctl),svc
    return None

def upnp_soap(ctl, svc, action, args):
    body=''.join('<%s>%s</%s>'%(k,html.escape(str(v)),k) for k,v in args)
    env=('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
         's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:%s xmlns:u="%s">%s</u:%s></s:Body></s:Envelope>'%(action,svc,body,action))
    req=urllib.request.Request(ctl,data=env.encode(),method='POST',headers={'Content-Type':'text/xml; charset="utf-8"','SOAPAction':'"%s#%s"'%(svc,action)})
    try:
        with urllib.request.urlopen(req,timeout=8) as r:return r.read(65536).decode('latin1')
    except urllib.error.HTTPError as e:
        code=re.search(r'<errorCode>(\d+)',e.read(4096).decode('latin1'))
        raise RuntimeError('UPnP %s: error %s'%(action,code[1] if code else e.code))

def upnp_sync():
    """Keeps exactly one UDP mapping (current WireGuard port → this J1) on the router."""
    want=load('upnp.json',{'enabled':True}).get('enabled',True)
    port=ensure_vpn_state()['port'];local=uplink_ip()
    try:old=json.loads((RUN/'upnp-state').read_text())
    except (OSError,ValueError):old={}
    if not local:RUNTIME['upnp']='Sin conexión';return
    gw=upnp_find(local)
    if not gw:
        RUNTIME['upnp']='El router no responde a UPnP: actívalo en el router o abre el puerto a mano' if want else 'Desactivado'
        return
    ctl,svc=gw
    if old.get('port') and (not want or old['port']!=port or old.get('client')!=local):
        try:upnp_soap(ctl,svc,'DeletePortMapping',[('NewRemoteHost',''),('NewExternalPort',old['port']),('NewProtocol','UDP')])
        except RuntimeError:pass
        (RUN/'upnp-state').unlink(missing_ok=True);log('UPnP: puerto %s cerrado'%old['port'])
    if not want:RUNTIME['upnp']='Desactivado';return
    args=[('NewRemoteHost',''),('NewExternalPort',port),('NewProtocol','UDP'),('NewInternalPort',port),('NewInternalClient',local),
          ('NewEnabled',1),('NewPortMappingDescription','J1 WireGuard'),('NewLeaseDuration',3600)]
    try:upnp_soap(ctl,svc,'AddPortMapping',args)
    except RuntimeError as e:
        if 'error 725' not in str(e):raise   # OnlyPermanentLeasesSupported
        upnp_soap(ctl,svc,'AddPortMapping',args[:-1]+[('NewLeaseDuration',0)])
    if old.get('port')!=port or old.get('client')!=local:log('UPnP: UDP %s abierto hacia %s'%(port,local))
    atomic(RUN/'upnp-state',json.dumps({'port':port,'client':local}))
    wan=''
    try:wan=(re.search(r'<NewExternalIPAddress>([^<]*)',upnp_soap(ctl,svc,'GetExternalIPAddress',[])) or [None,''])[1]
    except RuntimeError:pass
    note=''
    try:
        if wan and ipaddress.IPv4Address(wan).is_private:note=' · el router tiene IP privada (%s): hay otro router o CG-NAT delante'%wan
    except ValueError:pass
    RUNTIME['upnp']='Abierto UDP %s → %s%s'%(port,local,note)

# ---- notifications to the phone through an ntfy server (ntfy.sh or your own) on
# a secret topic: whoever knows the topic reads them, so the text carries no IPs,
# keys or passwords, only what happened. Sent in the background, never blocking.
NOTIFY_EVENTS=(('power','Corriente: se va o vuelve (cargador) y encendido'),('bat','Batería baja o caliente'),
               ('vpn','La VPN falla o vuelve a funcionar'),('ip','Cambia la IP pública de casa'),('client','Se conecta un cliente de la VPN'))
NOTIFY_SERVER='https://ntfy.sh'
def notify_conf():
    c=load('notify.json',{})
    if not isinstance(c.get('topic'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,64}',c['topic']):
        c['topic']='j1-'+secrets.token_hex(10);save('notify.json',c)
    c.setdefault('server',NOTIFY_SERVER);c.setdefault('events',[k for k,_ in NOTIFY_EVENTS]);c['enabled']=c.get('enabled') is True
    return c
def notify_save(enabled=None, server=None, events=None, new_topic=False):
    c=notify_conf()
    if enabled is not None:c['enabled']=bool(enabled)
    if server is not None:
        server=server.strip().rstrip('/') or NOTIFY_SERVER;u=urllib.parse.urlsplit(server)
        if u.scheme!='https' or not u.hostname or u.query or u.fragment:raise ValueError('El servidor de avisos debe empezar por https://')
        c['server']=server
    if events is not None:c['events']=[k for k,_ in NOTIFY_EVENTS if k in events]
    if new_topic:c['topic']='j1-'+secrets.token_hex(10)
    save('notify.json',c);log('Avisos: '+('activados' if c['enabled'] else 'desactivados'))
def notify_url(c=None):
    c=c or notify_conf();return c['server']+'/'+c['topic']
def notify_send(title, text, tags=(), prio=3):
    c=notify_conf()
    body=json.dumps({'topic':c['topic'],'title':title,'message':text,'tags':list(tags),'priority':prio}).encode()
    req=urllib.request.Request(c['server'],data=body,method='POST',headers={'Content-Type':'application/json','User-Agent':'j1-open-vpn'})
    with urllib.request.urlopen(req,timeout=15) as r:r.read(4096)
def notify(kind, title, text, tags=(), prio=3):
    c=notify_conf()
    if not c['enabled'] or kind not in c['events']:return False
    def run():
        try:notify_send(title,text,tags,prio)
        except Exception as e:log('Aviso no enviado: '+type(e).__name__)
    threading.Thread(target=run,daemon=True).start();return True
# what the last look saw (the worker looks once a minute); None = not known yet
WATCH={'power':None,'low':False,'hot':False,'vpn_err':None,'clients':None,'boot':None}
def notify_watch():
    b=bat_read()
    if b:
        plugged=b['status']!='Discharging'   # Paused: the cable is plugged, the limit stops the charge
        if WATCH['power'] is not None and plugged!=WATCH['power']:
            if plugged:notify('power','J1: vuelve la corriente','El cargador vuelve a dar corriente. Batería al %d%%.'%b['cap'],('electric_plug',))
            else:notify('power','J1: sin corriente','Se ha desconectado el cargador o se ha ido la luz. El J1 sigue con la batería (%d%%).'%b['cap'],('warning',),4)
        WATCH['power']=plugged
        if not plugged and b['cap']<=20 and not WATCH['low']:
            WATCH['low']=True;notify('bat','J1: batería baja','Queda un %d%%. Conecta el cargador o el J1 se apagará.'%b['cap'],('battery',),5)
        elif plugged or b['cap']>=25:WATCH['low']=False
        if b['temp']>=45 and not WATCH['hot']:
            WATCH['hot']=True;notify('bat','J1: batería caliente','La batería está a %.0f °C. Ponlo en un sitio más fresco.'%b['temp'],('fire',),4)
        elif b['temp']<40:WATCH['hot']=False
    err=RUNTIME['vpn'].startswith('Error')
    if WATCH['vpn_err'] is not None and err!=WATCH['vpn_err']:
        if err:notify('vpn','J1: la VPN no funciona','WireGuard ha dado un error. Mira Registros en el J1.',('x',),4)
        else:notify('vpn','J1: la VPN vuelve a funcionar','WireGuard funciona de nuevo.',('white_check_mark',))
    if not RUNTIME['vpn'].startswith('Iniciando'):WATCH['vpn_err']=err
    peers=wg_peers();now=time.time();on={}
    for c in ensure_vpn_state()['clients']:
        hs=peers.get(c['public_key'],{}).get('handshake',0)
        on[c['id']]=bool(hs) and now-hs<300 and not c.get('paused')
        if WATCH['clients'] is not None and on[c['id']] and not WATCH['clients'].get(c['id']):
            notify('client','J1: '+c['name']+' conectado','Se ha conectado a la VPN.',('closed_lock_with_key',),2)
    WATCH['clients']=on
    if WATCH['boot'] and has_uplink():
        WATCH['boot']=False;notify('power','J1: encendido','El J1 se ha encendido o reiniciado y ya tiene Internet.',('arrows_counterclockwise',))
def notify_ip(public):
    # public IPv4 of home, from the DNS update; only a change is told
    if RUNTIME.get('ip4') and RUNTIME['ip4']!=public:
        notify('ip','J1: nueva IP pública','Tu conexión de casa tiene otra IP pública. El DNS de Cloudflare ya se ha actualizado.',('globe_with_meridians',))
    RUNTIME['ip4']=public
def ui_notify(arg):
    c=notify_conf();s=Screen('notify','Avisos al móvil',refresh=10)
    s.toggle('notify.off' if c['enabled'] else 'notify.on','Avisos',c['enabled'])
    s.small('Llegan a la app ntfy (o al navegador) suscrita a tu tema secreto. Escanea el QR con el móvil para suscribirte.','m')
    s.add('Q',','.join(qr_rows(notify_url(c))))
    s.small(notify_url(c),'m')
    if c['enabled']:s.button('notify.test','Enviar aviso de prueba','p','notify')
    s.gap().label('Avisar cuando:')
    for k,n in NOTIFY_EVENTS:
        on=k in c['events'];s.toggle('notify.ev:%s:%d'%(k,0 if on else 1),n,on)
    s.gap().button('notify.topic','Cambiar el tema secreto','i')
    return s.small('Cambiar el tema deja de enviar avisos al anterior: vuelve a suscribirte. Los avisos no llevan IPs ni claves.','m')
def notify_section():
    c=notify_conf()
    return ('<section id=avisos><h2>Avisos al móvil</h2><p>'+('Activados.' if c['enabled'] else 'Desactivados.')+' Tema secreto: <code>'+esc(notify_url(c))+'</code></p>'
        '<p class=muted>Instala la app ntfy en el móvil y suscríbete a esa dirección (o ábrela en el navegador). Quien conozca el tema puede leer los avisos: por eso no llevan IPs, claves ni contraseñas.</p>'
        '<form method=post>'+hidden()+'<input type=hidden name=action value=notify>'
        '<label><input type=checkbox name=enabled value=1'+(' checked' if c['enabled'] else '')+'> Enviar avisos</label>'+
        ''.join('<label><input type=checkbox name=ev_'+k+' value=1'+(' checked' if k in c['events'] else '')+'> '+esc(n)+'</label>' for k,n in NOTIFY_EVENTS)+
        '<label>Servidor<input name=server value="'+esc(c['server'])+'" placeholder="'+NOTIFY_SERVER+'"></label>'
        '<small>Por defecto el servidor público ntfy.sh; puedes poner el tuyo.</small><br><button>Guardar avisos</button></form>'
        '<form method=post>'+hidden()+'<input type=hidden name=action value=notifytest><button class=sec>Enviar aviso de prueba</button></form>'
        '<form method=post>'+hidden()+'<input type=hidden name=action value=notifytopic><button class=sec>Cambiar el tema secreto</button><small>El tema anterior deja de recibir avisos: vuelve a suscribirte.</small></form></section>')
def notify_test():
    if not notify_conf()['enabled']:raise ValueError('Activa primero los avisos')
    try:notify_send('J1: aviso de prueba','Si lees esto, los avisos del J1 funcionan.',('wave',))
    except (OSError,ValueError) as e:raise RuntimeError('No se pudo enviar: '+type(e).__name__)

# ---- backup of the configuration: /etc/j1 and the SSH host keys in a tar,
# encrypted with a password (scrypt + AES-256-GCM from the system's libcrypto,
# the one Python's ssl module already loads). Files of this phone stay out.
DROPBEAR=Path(os.environ.get('J1_DROPBEAR','/etc/dropbear'))
BACKUP_SKIP={'random-seed','hostapd.entropy','mac.info'}
BACKUP_MAGIC=b'J1-OPEN-VPN-BACKUP-1\n'
BACKUP_MAX=1<<20
BACKUP_NAME=re.compile(r'(config|dropbear)/[A-Za-z0-9._-]{1,64}')
def libcrypto():
    for n in ('libcrypto.so.3',ctypes.util.find_library('crypto'),'libcrypto-3-x64.dll','libcrypto-3.dll'):
        if not n:continue
        try:return ctypes.CDLL(n)
        except OSError:pass
    raise RuntimeError('Falta libcrypto para cifrar')
def aes_gcm(key, nonce, aad, data, tag=None):
    # tag None: encrypts, returns ciphertext + 16-byte tag; else decrypts and checks the tag
    c=libcrypto();vp=ctypes.c_void_p;cp=ctypes.c_char_p;ip=ctypes.POINTER(ctypes.c_int)
    c.EVP_CIPHER_CTX_new.restype=vp;c.EVP_aes_256_gcm.restype=vp;c.EVP_CIPHER_CTX_free.argtypes=[vp]
    enc=tag is None
    init,upd,fin=((c.EVP_EncryptInit_ex,c.EVP_EncryptUpdate,c.EVP_EncryptFinal_ex) if enc else (c.EVP_DecryptInit_ex,c.EVP_DecryptUpdate,c.EVP_DecryptFinal_ex))
    init.argtypes=[vp,vp,vp,cp,cp];upd.argtypes=[vp,cp,ip,cp,ctypes.c_int];fin.argtypes=[vp,cp,ip];c.EVP_CIPHER_CTX_ctrl.argtypes=[vp,ctypes.c_int,ctypes.c_int,vp]
    ctx=c.EVP_CIPHER_CTX_new();n=ctypes.c_int(0);out=ctypes.create_string_buffer(len(data)+32);tb=ctypes.create_string_buffer(tag or 16)
    try:
        ok=init(ctx,c.EVP_aes_256_gcm(),None,key,nonce)==1 and upd(ctx,None,ctypes.byref(n),aad,len(aad))==1 and upd(ctx,out,ctypes.byref(n),data,len(data))==1
        size=n.value
        if not enc:ok=ok and c.EVP_CIPHER_CTX_ctrl(ctx,0x11,16,tb)==1   # EVP_CTRL_GCM_SET_TAG
        ok=ok and fin(ctx,ctypes.cast(ctypes.addressof(out)+size,cp),ctypes.byref(n))==1
        if enc:ok=ok and c.EVP_CIPHER_CTX_ctrl(ctx,0x10,16,tb)==1     # EVP_CTRL_GCM_GET_TAG
    finally:c.EVP_CIPHER_CTX_free(ctx)
    if not ok:raise ValueError('Contraseña incorrecta o copia dañada')
    return out.raw[:size]+(tb.raw[:16] if enc else b'')
def backup_key(pw, salt):return hashlib.scrypt(pw.encode(),salt=salt,n=1<<15,r=8,p=1,maxmem=64<<20,dklen=32)
def backup_files():
    out=[]
    for prefix,d in (('config',STATE),('dropbear',DROPBEAR)):
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.is_file() and not f.is_symlink() and f.name not in BACKUP_SKIP and BACKUP_NAME.fullmatch(prefix+'/'+f.name):out.append((prefix+'/'+f.name,f))
    return out
def backup_make(pw, again):
    if len(pw)<8:raise ValueError('La contraseña de la copia debe tener al menos 8 caracteres')
    if pw!=again:raise ValueError('Las dos contraseñas no coinciden')
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz') as t:
        for name,f in backup_files():
            data=f.read_bytes();i=tarfile.TarInfo(name);i.size=len(data);i.mode=0o600;i.mtime=int(f.stat().st_mtime)
            t.addfile(i,io.BytesIO(data))
    salt=secrets.token_bytes(16);nonce=secrets.token_bytes(12);head=BACKUP_MAGIC+salt+nonce
    log('Copia de seguridad descargada');return head+aes_gcm(backup_key(pw,salt),nonce,head,buf.getvalue())
def backup_open(blob, pw):
    # -> [(name, bytes)], checked: only plain files of config/ and dropbear/
    n=len(BACKUP_MAGIC)
    if len(blob)<n+28+16 or not blob.startswith(BACKUP_MAGIC):raise ValueError('Ese archivo no es una copia del J1')
    head=blob[:n+28];salt,nonce=blob[n:n+16],blob[n+16:n+28]
    plain=aes_gcm(backup_key(pw,salt),nonce,head,blob[n+28:-16],blob[-16:])
    files=[]
    with tarfile.open(fileobj=io.BytesIO(plain),mode='r:gz') as t:
        for m in t.getmembers():
            if not m.isfile() or not BACKUP_NAME.fullmatch(m.name) or m.size>BACKUP_MAX:raise ValueError('La copia contiene algo inesperado: no se restaura')
            if m.name.split('/')[1] in BACKUP_SKIP:continue
            files.append((m.name,t.extractfile(m).read()))
    if not any(n=='config/vpn.json' for n,_ in files):raise ValueError('La copia no tiene la configuración de la VPN')
    return files
def write_bytes(path, data, mode=0o600):
    tmp=path.with_name(path.name+'.new');fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,mode)
    with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
def backup_restore(blob, pw):
    files=backup_open(blob,pw)
    with LOCK:
        for name,data in files:
            prefix,fn=name.split('/');write_bytes((STATE if prefix=='config' else DROPBEAR)/fn,data)
    log('Copia de seguridad restaurada (%d archivos): reiniciando'%len(files))
    reboot_soon()
    return len(files)
def reboot_soon():
    subprocess.Popen(['/bin/busybox','sh','-c','sleep 3; sync; reboot -f'],start_new_session=True)
def backup_section():
    return ('<section id=copia><h2>Copia de seguridad</h2><p class=muted>Guarda la configuración (clientes de la VPN, Wi-Fi, Cloudflare, avisos, contraseñas y claves SSH) en un archivo cifrado con una contraseña. Sirve para reinstalar o pasar a otro J1 sin volver a configurar los clientes.</p>'
        '<form method=post>'+hidden()+'<input type=hidden name=action value=backup>'
        '<label>Contraseña de la copia (mínimo 8 caracteres)<input type=password name=pw autocomplete=new-password minlength=8 required></label><label>Repítela<input type=password name=pw2 autocomplete=new-password required></label>'
        '<small>Sin esta contraseña la copia no se puede abrir: apúntala. Guarda el archivo en un sitio seguro, contiene las claves de la VPN.</small><br><button>Descargar copia</button></form>'
        '<h3>Restaurar</h3><form method=post enctype=multipart/form-data>'+hidden()+'<input type=hidden name=action value=restore>'
        '<label>Archivo de la copia<input type=file name=file accept=".j1bak" required></label><label>Contraseña de la copia<input type=password name=pw autocomplete=off required></label>'
        '<small>Sustituye la configuración actual por la de la copia y reinicia el J1 (un minuto sin VPN).</small><br><button class=danger>Restaurar y reiniciar</button></form></section>')

# ---- updates from GitHub: the system (rootfs) of the latest release, checked with
# its SHA256SUMS, unpacked next to the running one and swapped in for the next
# boot; the old one stays as <root>.old. /etc/j1 and /etc/dropbear are not in
# it (own folders), and /var/lib/j1 (camera tables) is copied over. The boot
# image is not touched: if the release brings another kernel, the screen says so.
UPD_REPO='Farwebsite/j1-open-vpn'
UPD={'state':'','busy':False,'latest':None}
RELEASE_FILE=Path('/usr/share/j1/release')
KEEP_DIRS=('var/lib/j1',)
def release_current():
    try:m=re.search(r'j1-open-vpn (\d+\.\d+\.\d+)',RELEASE_FILE.read_text())
    except OSError:m=None
    return m[1] if m else ''
def vtuple(v):return tuple(int(x) for x in re.findall(r'\d+',v)[:3]) if v else (0,)
def http_get(url, limit, dest=None):
    req=urllib.request.Request(url,headers={'User-Agent':'j1-open-vpn','Accept':'application/octet-stream' if dest else 'application/vnd.github+json'})
    h=hashlib.sha256();n=0
    with urllib.request.urlopen(req,timeout=30) as r,(open(dest,'wb') if dest else io.BytesIO()) as f:
        while True:
            b=r.read(65536)
            if not b:break
            n+=len(b)
            if n>limit:raise RuntimeError('Descarga demasiado grande')
            h.update(b);f.write(b)
        data=None if dest else f.getvalue()
    return data,h.hexdigest()
def update_check():
    raw,_=http_get('https://api.github.com/repos/%s/releases/latest'%UPD_REPO,1<<20)
    j=json.loads(raw);assets={a['name']:a['browser_download_url'] for a in j.get('assets',[])}
    v=str(j.get('tag_name','')).lstrip('v')
    if not re.fullmatch(r'\d+\.\d+\.\d+',v) or 'j1-open-vpn-rootfs.tar.gz' not in assets or 'SHA256SUMS' not in assets:raise RuntimeError('La última versión de GitHub no trae el sistema')
    UPD['latest']={'version':v,'assets':assets};return UPD['latest']
def boot_kernel(blob):
    # kernel of an Android boot image (header v0), to compare by content
    if blob[:8]!=b'ANDROID!':return None
    k,_,_,_,_,_,_,page=struct.unpack_from('<8I',blob,8)
    return hashlib.sha256(blob[page:page+k]).hexdigest() if 0<k<len(blob) and page in (2048,4096) else None
def part_dev(name):
    for d in Path('/sys/class/block').glob('mmcblk0p*'):
        try:
            if 'PARTNAME='+name in (d/'uevent').read_text().split():return '/dev/'+d.name
        except OSError:pass
    return ''
def kernel_same(latest):
    # True / False, None if it cannot be told
    dev=part_dev('KERNEL')
    if not dev or 'j1-open-vpn-boot.img' not in latest['assets']:return None
    try:
        with open(dev,'rb') as f:mine=boot_kernel(f.read(16<<20))
        new,_=http_get(latest['assets']['j1-open-vpn-boot.img'],17<<20)
    except (OSError,RuntimeError):return None
    return mine is not None and mine==boot_kernel(new)
def root_paths():
    # (userdata partition, folder of / inside it) from /proc/self/mountinfo
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        f=line.split()
        if f[4]=='/' and f[3]!='/':
            src=f[f.index('-')+2]
            if src.startswith('/dev/'):return src,f[3].replace('\\040',' ')
    raise RuntimeError('No se sabe dónde está instalado el sistema')
def update_run():
    try:
        latest=UPD['latest'] or update_check();v=latest['version']
        UPD['state']='Descargando la versión %s...'%v
        sums,_=http_get(latest['assets']['SHA256SUMS'],65536)
        want=dict(reversed(l.split()) for l in sums.decode().splitlines() if len(l.split())==2).get('j1-open-vpn-rootfs.tar.gz')
        dev,root=root_paths();mnt=Path('/run/j1-data');mnt.mkdir(exist_ok=True)
        if subprocess.run(['mount','-t','ext4','-o','nosuid,nodev,noatime',dev,str(mnt)],capture_output=True,timeout=30).returncode:raise RuntimeError('No se pudo abrir la partición de datos')
        try:
            base=mnt/root.lstrip('/');new=base.with_name(base.name+'.new');old=base.with_name(base.name+'.old');tgz=base.with_name('update.tar.gz')
            if not (base/'sbin/j1-init').exists():raise RuntimeError('No se encuentra el sistema instalado')
            _,got=http_get(latest['assets']['j1-open-vpn-rootfs.tar.gz'],100<<20,tgz)
            if not want or got!=want:raise RuntimeError('La descarga no coincide con SHA256SUMS: no se instala')
            UPD['state']='Descomprimiendo (unos minutos)...'
            subprocess.run(['rm','-rf',str(new)],timeout=300);new.mkdir()
            if subprocess.run(['tar','-xzf',str(tgz),'-C',str(new)],capture_output=True,timeout=1800).returncode:raise RuntimeError('No se pudo descomprimir el sistema')
            if not (new/'usr/share/j1/release').is_file() or not (new/'sbin/j1-init').is_file():raise RuntimeError('El sistema descargado está incompleto')
            for d in KEEP_DIRS:
                if (base/d).is_dir():
                    (new/d).parent.mkdir(parents=True,exist_ok=True);subprocess.run(['cp','-a',str(base/d),str((new/d).parent)],timeout=120)
            UPD['state']='Instalando...'
            subprocess.run(['rm','-rf',str(old)],timeout=600);tgz.unlink()
            os.sync();os.rename(base,old);os.rename(new,base);os.sync()
        finally:subprocess.run(['umount',str(mnt)],capture_output=True,timeout=30)
        UPD['state']='Versión %s instalada: reiniciando...'%v;log('Actualizado a la versión %s: reiniciando'%v)
        reboot_soon()
    except Exception as e:
        UPD['state']='Error: '+str(e)[:120];log('Actualización: '+type(e).__name__+': '+str(e)[:200])
    finally:UPD['busy']=False
def update_start():
    with LOCK:
        if UPD['busy']:raise ValueError('Ya se está actualizando')
        if not UPD['latest'] or vtuple(UPD['latest']['version'])<=vtuple(release_current()):raise ValueError('Comprueba antes si hay una versión nueva')
        UPD['busy']=True;UPD['state']='Empezando...'
    threading.Thread(target=update_run,daemon=True).start()
def update_look():
    # check button: fills UPD and says what there is
    latest=update_check();cur=release_current()
    if vtuple(latest['version'])<=vtuple(cur):UPD['state']='Tienes la última versión (%s).'%cur;return
    same=kernel_same(latest)
    UPD['state']='Hay una versión nueva: %s.'%latest['version']+('' if same is not False else ' Trae otro kernel: el sistema se actualiza aquí; el kernel, solo reinstalando la imagen de arranque.')
def ui_update(arg):
    s=Screen('update','Actualizar','nav:sys',refresh=3 if UPD['busy'] else 0)
    s.label('Versión instalada: '+(release_current() or 'de desarrollo'))
    if UPD['state']:s.label(UPD['state'],'r' if UPD['state'].startswith('Error') else 'g' if 'nueva' in UPD['state'] or 'instalada' in UPD['state'] else 'm')
    if UPD['busy']:return s.small('No apagues el J1. Al terminar se reinicia solo.','y')
    s.button('update.check','Buscar actualizaciones','p','update')
    if UPD['latest'] and vtuple(UPD['latest']['version'])>vtuple(release_current()):s.button('update.run','Instalar la %s y reiniciar'%UPD['latest']['version'],'d','update')
    return s.small('Descarga el sistema de GitHub, comprueba su suma SHA-256 y lo instala junto al actual: la configuración se conserva. Un minuto sin VPN al reiniciar.','m')
def update_section():
    cur=release_current();new=UPD['latest'] and vtuple(UPD['latest']['version'])>vtuple(cur)
    return ('<section id=actualizar><h2>Actualizar</h2><p>Versión instalada: <b>'+esc(cur or 'de desarrollo')+'</b>'+('<br>'+esc(UPD['state']) if UPD['state'] else '')+'</p>'+
        ('' if UPD['busy'] else '<form method=post>'+hidden()+'<input type=hidden name=action value=updcheck><button class=sec>Buscar actualizaciones</button></form>'+
        ('<form method=post>'+hidden()+'<input type=hidden name=action value=updrun><button class=danger>Instalar la '+esc(UPD['latest']['version'])+' y reiniciar</button></form>' if new else ''))+
        '<p class=muted>Descarga el sistema de la última versión de GitHub, comprueba su suma SHA-256 y lo instala junto al actual. La configuración se conserva y el sistema anterior queda guardado. Un minuto sin VPN al reiniciar.</p></section>')

UI_SCREENS.update(notify=ui_notify,update=ui_update)   # defined after the table

def has_uplink():
    try:return bool(command(['ip','-4','route','show','default']))
    except (RuntimeError,OSError,subprocess.SubprocessError):return False

def worker():
    next_dns=0;next_vpn=0;next_upnp=0;next_bat=0
    while True:
        if time.monotonic()>=next_bat:
            bat_limit_apply();bat_sample()
            try:notify_watch()
            except Exception as e:log('Avisos: error '+type(e).__name__)
            next_bat=time.monotonic()+60
        if (time.monotonic()>=next_upnp or (RUN/'upnp-request').exists()) and has_uplink():
            (RUN/'upnp-request').unlink(missing_ok=True)
            try:upnp_sync();next_upnp=time.monotonic()+1800
            except Exception as e:
                RUNTIME['upnp']='Error UPnP: '+str(e)[:80];log('UPnP error: '+type(e).__name__+': '+str(e)[:200])
                next_upnp=time.monotonic()+300
        if time.monotonic()>=next_vpn:
            try:apply_vpn()
            except Exception:
                RUNTIME['vpn']='Error: revisa el registro WireGuard'
                atomic(RUN/'vpn-summary','WG: error de encaminamiento\n')
            next_vpn=time.monotonic()+30
        due=time.monotonic()>=next_dns or (RUN/'ddns-request').exists()
        # no uplink yet (boot, Wi-Fi reconnecting): wait quietly instead of logging errors
        if due and not has_uplink():
            if not RUNTIME['ddns'].startswith('Actualizado'):RUNTIME['ddns']='Esperando conexión a Internet'
            next_dns=time.monotonic()+5
        elif due:
            (RUN/'ddns-request').unlink(missing_ok=True)
            try:update_ddns();next_dns=time.monotonic()+300
            except Exception as e:
                RUNTIME['ddns']='No se pudo actualizar; comprueba Internet y los permisos del token'
                log('DNS VPN error: '+type(e).__name__+': '+str(e)[:200])
                # usually the uplink is still coming up (boot, cable/Wi-Fi change)
                next_dns=time.monotonic()+30
        time.sleep(2)

def main():
    os.umask(0o077);STATE.mkdir(parents=True,exist_ok=True);RUN.mkdir(parents=True,exist_ok=True)
    pin_fail_load()
    ensure_vpn_state();apply_usb()
    try:WATCH['boot']=float(Path('/proc/uptime').read_text().split()[0])<600   # booted now, not restarted
    except (OSError,ValueError):pass
    threading.Thread(target=worker,daemon=True).start()
    threading.Thread(target=ui_serve,daemon=True).start()
    threading.Thread(target=panel_serve,daemon=True).start()
    log('Web Wi-Fi / WireGuard disponible')
    while True:time.sleep(3600)
if __name__=='__main__':main()
