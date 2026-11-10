#!/usr/bin/python3
"""Personal J1 appliance controller. SPDX-License-Identifier: GPL-2.0"""
import base64, hashlib, hmac, html, http.server, ipaddress, json, os, re, secrets
import socketserver, subprocess, threading, time, unicodedata, urllib.error, urllib.parse, urllib.request
from pathlib import Path
STATE = Path(os.environ.get('J1_STATE', '/etc/j1'))
RUN = Path(os.environ.get('J1_RUN', '/run'))
LOCK = threading.RLock()
CSRF = secrets.token_hex(32)
RUNTIME = {'vpn': 'Iniciando', 'ddns': 'Sin configurar', 'ddns6': 'Desactivado', 'upnp': 'Comprobando...', 'scan': 'Pulsa Buscar redes', 'networks': []}
CSS = '''body{font:16px system-ui;background:#0b1420;color:#edf4fa;max-width:880px;margin:24px auto;padding:16px}nav{display:flex;gap:20px;flex-wrap:wrap}a{color:#9aefc1}section{background:#142133;border:1px solid #304158;border-radius:12px;padding:22px;margin:20px 0}label{display:block;margin:14px 0 5px}input,select,button{box-sizing:border-box;max-width:100%;padding:11px;border-radius:7px;border:1px solid #637387;font:inherit}input:not([type=checkbox]),select{width:100%}button{background:#9aefc1;color:#10251c;margin-top:16px;cursor:pointer}.danger{background:#f4b4b4}small,.muted{color:#b7c7d8}p{line-height:1.5}table{width:100%;border-collapse:collapse}td,th{text-align:left;border-bottom:1px solid #40516a;padding:10px 5px}.notice{padding:12px;background:#263e3c}code{overflow-wrap:anywhere}h1,h2{line-height:1.2}'''
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
            lines += ['','[Peer]','PublicKey = '+c['public_key'],'PresharedKey = '+c['psk'],
                      'AllowedIPs = 10.66.0.%s/32, fd66:6a31::%x/128' % (c['ip'],c['ip'])]
        atomic(RUN/'wg0.conf', '\n'.join(lines)+'\n')
        command(['wg','syncconf','wg0',str(RUN/'wg0.conf')])
        command(['ip','address','replace','10.66.0.1/24','dev','wg0'])
        command(['ip','-6','address','replace','fd66:6a31::1/64','dev','wg0'])
        command(['ip','link','set','wg0','mtu','1280','up'])
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

def client_profile(cid, fallback, endpoint=None):
    v=ensure_vpn_state();c=next((c for c in v['clients'] if c['id']==cid),None)
    if c is None:raise ValueError('Cliente no encontrado')
    cf=load('cloudflare.json',{})
    endpoint=endpoint or v.get('endpoint') or (cf.get('hostname') if cf.get('enabled') else '') or fallback
    return f'''[Interface]
PrivateKey = {c['private_key']}
Address = 10.66.0.{c['ip']}/32, fd66:6a31::{c['ip']:x}/128
DNS = 1.1.1.1
MTU = 1280

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
    # the AP passphrase is also the web password (user admin)
    if not 8<=len(pw)<=63 or any(not 33<=ord(c)<=126 or c in '"\\' for c in pw):
        raise ValueError('Clave: 8 a 63 caracteres, sin espacios, comillas ni \\')
    with LOCK:
        conf=(STATE/'p2p.conf').read_text()
        new,n=re.subn(r'(?m)^(\s*psk=).*$',lambda m:m[1]+'"'+pw+'"',conf,count=1)
        if n!=1:raise RuntimeError('No se encontró la clave de la red de configuración')
        atomic(STATE/'p2p.conf',new);atomic(STATE/'admin-password',pw+'\n')
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
    on=display_lock()
    return ('<section id=pantalla><h2>Pantalla de bloqueo</h2><p>'+('Activada' if on else 'Desactivada')+'</p><p class=muted>Activada: cuando la pantalla del J1 se apaga, tocarla solo enciende el reloj y hay que deslizar para usarla, así no se pulsa nada sin querer.</p><form method=post>'+hidden()+
        '<input type=hidden name=action value=lock><input type=hidden name=on value='+('0' if on else '1')+'><button>'+('Desactivar' if on else 'Activar')+' pantalla de bloqueo</button></form></section>')
def tz_section():
    cur=tz_get()
    opts=''.join('<option value=%d%s>%s</option>'%(i,' selected' if z==cur else '',esc(n)) for i,(n,z) in enumerate(TZ_ZONES))
    return ('<section id=hora><h2>Zona horaria</h2><p>'+esc(tz_name(cur))+' · ahora '+time.strftime('%H:%M')+'</p><form method=post>'+hidden()+
        '<input type=hidden name=action value=tz><select name=zone>'+opts+'</select><button>Guardar zona horaria</button></form></section>')
def ssh_section():
    n=len(ssh_keys())
    state='Activo: %d clave%s autorizada%s.'%(n,'' if n==1 else 's','' if n==1 else 's') if n else 'Desactivado (ninguna clave autorizada).'
    return lock_section()+tz_section()+('<section id=ssh><h2>Acceso SSH por USB</h2><p>'+state+'</p><p class=muted>Opcional, para usuarios avanzados. Solo funciona con el J1 conectado al PC por USB: <code>ssh -i clave root@192.168.77.1</code>. Nunca desde la Wi-Fi ni desde Internet, y solo con clave (sin contraseña).</p>'
        '<form method=post>'+hidden()+'<input type=hidden name=action value=sshgen><button>Generar una clave y descargarla</button><small>Guarda el archivo descargado: es la llave para entrar y no se puede volver a descargar.</small></form>'
        '<form method=post>'+hidden()+'<input type=hidden name=action value=sshadd><label>O pega tu clave pública (id_ed25519.pub)<textarea name=key rows=3 maxlength=1000></textarea></label><button>Añadir clave pública</button></form>'
        +('<form method=post>'+hidden()+'<input type=hidden name=action value=sshoff><button class=danger>Desactivar SSH (borrar todas las claves)</button></form>' if n else '')+'</section>')

def hidden():return '<input type="hidden" name="csrf" value="'+CSRF+'">'
def page(message=''):
    v=ensure_vpn_state();cf=load('cloudflare.json',{})
    try:wifi=(RUN/'wifi-summary').read_text().strip()
    except FileNotFoundError:wifi='Sin configurar'
    out=['<!doctype html><html lang=es><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>J1 VPN</title><style>'+CSS+'</style><h1>J1 · Servidor VPN</h1><nav><a href="#wifi">Wi-Fi</a><a href="#usb">Cable</a><a href="#vpn">WireGuard</a><a href="#dns">Cloudflare</a><a href="#pantalla">Pantalla</a><a href="#hora">Hora</a><a href="#ssh">SSH</a></nav>']
    if message:out.append('<p class=notice role=status>'+esc(message)+'</p>')
    out+=['<section id=wifi><h2>Conexión Wi-Fi</h2><p>'+esc(wifi)+'</p><form method=post>'+hidden()+'<input type=hidden name=action value=scan><button>Buscar redes</button></form><p class=muted>'+esc(RUNTIME['scan'])+'</p><form method=post>'+hidden()+'<input type=hidden name=action value=wifi><label for=net>Redes encontradas</label><select name=ssidhex id=net><option value="">Selecciona una red</option>']
    for n in RUNTIME['networks']:out.append('<option value="'+n['hex']+'">'+esc(n['name'])+' · '+str(n['signal'])+' dBm'+('' if n['secure'] else ' · abierta')+'</option>')
    out+=['</select><details><summary>Red oculta o nombre manual</summary><label>Nombre de la red<input name=ssid maxlength=32 autocomplete=off></label></details><label>Contraseña Wi-Fi<input type=password name=password maxlength=63 autocomplete=new-password></label><label><input type=checkbox name=open value=1> Red abierta, sin contraseña</label><button>Guardar y conectar</button></form><p><small>La red de configuración se mantiene disponible.</small></p></section>',usb_section()]
    out+=['<section id=vpn><h2>WireGuard</h2><p>'+esc(RUNTIME['vpn'])+'</p><form method=post>'+hidden()+'<input type=hidden name=action value=vpn><label>Puerto UDP<input type=number name=port min=1 max=65535 required value="'+str(v['port'])+'"></label><label>Dominio o IP de conexión<input name=endpoint value="'+esc(v.get('endpoint',''))+'" placeholder="vpn2.tudominio.com"></label><small>Vacío: usa el dominio de Cloudflare o la IP de acceso actual. Web en TCP 80; VPN en UDP. Si cambias el puerto o dominio, descarga otra vez los perfiles.</small><br><button>Guardar puerto y dirección</button></form><h3>Clientes</h3><table><tr><th>Nombre</th><th>Dirección</th><th>Acciones</th></tr>']
    for c in v['clients']:
        out.append('<tr><td>'+esc(c['name'])+'</td><td>10.66.0.'+str(c['ip'])+'</td><td><a href="/client/'+c['id']+'.conf">Descargar .conf</a><form method=post>'+hidden()+'<input type=hidden name=action value=delete><input type=hidden name=id value="'+c['id']+'"><button class=danger>Quitar cliente</button></form></td></tr>')
    out+=['</table><form method=post>'+hidden()+'<input type=hidden name=action value=client><label>Nombre del nuevo cliente<input name=name maxlength=64 required placeholder="Mi móvil"></label><button>Crear cliente</button></form><p><small>El perfil contiene claves privadas. Al quitar un cliente, su acceso se revoca en el servidor.</small></p></section>']
    checked=' checked' if cf.get('enabled') else ''
    out+=['<section id=dns><h2>Cloudflare · DNS dinámico</h2><p>'+esc(RUNTIME['ddns'])+'</p><form method=post>'+hidden()+'<input type=hidden name=action value=dns><label><input type=checkbox name=enabled value=1'+checked+'> Actualizar automáticamente el registro DNS</label><label>Nombre completo del registro<input name=hostname value="'+esc(cf.get('hostname',''))+'" placeholder="vpn2.tudominio.com"></label><label>ID de zona de Cloudflare<input name=zone_id value="'+esc(cf.get('zone_id',''))+'" maxlength=32></label><label>Token API<input type=password name=token autocomplete=new-password placeholder="'+('Guardado; deja vacío para conservarlo' if cf.get('token') else 'Token con permiso DNS:Editar en esta zona')+'"></label><small>El registro A se crea o actualiza en modo Solo DNS, sin proxy naranja. Revisión cada 5 minutos. No se conecta a Cloudflare hasta que actives esta opción.</small><br><button>Guardar Cloudflare</button></form></section>'+ssh_section()+'<footer><small>Acceso externo: el router debe redirigir el puerto UDP al J1. El DNS dinámico no elimina CG-NAT. La VPN proporciona salida IPv4; el perfil dirige IPv6 al túnel para evitar salida directa.</small><p><small>'+BRAND+' · <a href="https://'+REPO+'">'+REPO+'</a></small></footer></html>']
    return ''.join(out).encode()

# ---- web panel: on/off and who may reach it (set from the screen) ----
# Decided by who connects, not by the address used: a VPN client sends
# everything through the tunnel, so it could also reach 192.168.78.1.
PANEL_FIXED=('192.168.77.1','192.168.78.1')   # USB and the J1's own network
PANEL_NETS=tuple(ipaddress.ip_network(n) for n in ('192.168.77.0/30','192.168.78.0/24'))
VPN_NET=ipaddress.ip_network('10.66.0.0/24')
PANEL_CHANGED=threading.Event()
def panel_conf():
    c=load('panel.json',{})
    return {'enabled':c.get('enabled',True) is not False,'lan':c.get('lan') is True,'vpn':c.get('vpn') is True}
def panel_set(**kw):
    c=panel_conf();c.update(kw);save('panel.json',c);PANEL_CHANGED.set()
    extra=[n for n,k in (('red local','lan'),('VPN','vpn')) if c[k]]
    log('Panel web: '+('activado' if c['enabled'] else 'desactivado')+(' (también desde '+' y '.join(extra)+')' if c['enabled'] and extra else ''))
def lan_nets():
    """The J1's networks at home (Wi-Fi / cable), fixed or from DHCP."""
    try:out=command(['ip','-4','-o','addr','show'])
    except (RuntimeError,OSError,subprocess.SubprocessError):return []
    nets=[]
    for cidr in re.findall(r'\binet (\d+\.\d+\.\d+\.\d+/\d+)',out):
        n=ipaddress.ip_interface(cidr)
        if str(n.ip) not in PANEL_FIXED and not n.ip.is_loopback and n.ip not in VPN_NET:nets.append(n)
    return nets
def lan_ips():return [str(n.ip) for n in lan_nets()]
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
def panel_serve():
    srv=None
    while True:
        on=panel_conf()['enabled']
        if on and not srv:
            try:srv=PanelServer(('0.0.0.0',80),Handler);threading.Thread(target=srv.serve_forever,daemon=True).start()
            except OSError:srv=None
        elif srv and not on:srv.shutdown();srv.server_close();srv=None   # port 80 closed
        PANEL_CHANGED.wait(3);PANEL_CHANGED.clear()

class Handler(http.server.BaseHTTPRequestHandler):
    server_version='J1-VPN'
    def log_message(self,*args):pass
    def auth(self):
        try: password=(STATE/'admin-password').read_text().strip()
        except FileNotFoundError:
            self.respond(b'Configuracion aun no disponible',503,'text/plain');return False
        expected='Basic '+base64.b64encode(('admin:'+password).encode()).decode()
        if hmac.compare_digest(self.headers.get('Authorization',''),expected):return True
        self.send_response(401);self.send_header('WWW-Authenticate','Basic realm="J1 VPN"');self.send_header('Content-Length','0');self.end_headers();return False
    def respond(self, body, code=200, content='text/html; charset=utf-8', filename=None):
        self.send_response(code);self.send_header('Content-Type',content);self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        if filename:self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if not self.auth():return
        try:
            m=re.fullmatch(r'/client/([0-9a-f]{16})\.conf',urllib.parse.urlsplit(self.path).path)
            if m:
                self.respond(client_profile(m[1],self.server.server_address[0]).encode(),content='application/x-wireguard-profile',filename='j1-'+m[1]+'.conf');return
            if urllib.parse.urlsplit(self.path).path not in ('/','/cgi-bin/config.cgi'):
                self.respond(b'No encontrado',404,'text/plain');return
            with LOCK:body=page()
            self.respond(body)
        except ValueError as e:self.respond(str(e).encode(),404,'text/plain; charset=utf-8')
    def do_POST(self):
        if not self.auth():return
        try:
            size=int(self.headers.get('Content-Length','0'))
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
            elif action=='vpn':
                vpn_settings(f.get('port','0'),f.get('endpoint',''))
                message='Puerto y dirección guardados. Descarga perfiles actualizados.'
            elif action=='sshgen':
                key=ssh_generate()
                self.respond(key,content='application/octet-stream',filename='j1-open-vpn-ssh-key');return
            elif action=='sshadd':ssh_add(f.get('key',''));message='Clave añadida. Ya puedes entrar por USB: ssh root@192.168.77.1'
            elif action=='lock':display_save(lock=f.get('on')=='1');message='Pantalla de bloqueo '+('activada.' if display_lock() else 'desactivada.')
            elif action=='tz':message='Zona horaria: '+tz_set(f.get('zone',''))
            elif action=='sshoff':ssh_disable();message='SSH desactivado.'
            elif action=='dns':
                dns_settings(f.get('enabled')=='1',f.get('hostname',''),f.get('zone_id',''),f.get('token',''))
                message='Cloudflare guardado.'
            else:raise ValueError('Acción no válida')
            with LOCK:body=page(message)
            self.respond(body)
        except (ValueError,RuntimeError,subprocess.SubprocessError) as e:
            with LOCK:body=page(str(e) if isinstance(e,(ValueError,RuntimeError)) else 'No se pudo completar la operación')
            self.respond(body,400)

# ---- Touch screen (j1-display) over /run/j1-ui.sock ----
# Request: urlencoded a=<action>&s=<screen>&f_<field>=<value>, cp437 bytes.
# Reply: one widget per line, tab separated, cp437 (the screen font):
#  T id title back | R seconds | M text kind(o/e) | L text color | l small-text color
#  B action text style(n/p/d/i) | S action text 0/1 | F name label value kind(t/p/n/i)
#  Q row,row,... (QR, 1 = dark) | G (gap) | C action text icon (home tile, two per row)
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
    cur=tz_get();s=Screen('tz','Zona horaria','nav:sys').label('Hora: '+time.strftime('%H:%M'),'g')
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
def display_save(**kw):
    conf={'timeout':display_timeout(),'brightness':display_brightness(),'lock':display_lock()};conf.update(kw);save('display.json',conf)

def ui_disp(arg):
    s=Screen('disp','Pantalla').label('Brillo:').slider('disp.bright',display_brightness(),BRIGHT_MIN,255)
    lk=display_lock();s.toggle('disp.lock:0' if lk else 'disp.lock:1','Pantalla de bloqueo',lk)
    s.small('Al apagarse, un toque solo enciende el reloj: hay que deslizar para usarla. Evita pulsaciones sin querer.','m')
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
        s.label('Batería: %.1f °C'%(int(Path('/sys/class/power_supply/battery/temp').read_text())/10),'m')
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
                ('speed','Velocidad'),('panel','Panel web'),('res','Recursos'),('disp','Pantalla'),('logs:sys','Registros'),('sys','Sistema')):
        s.tile('nav:'+a,t,a.split(':')[0])
    return s.small(BRAND,'m').small(REPO,'m')

def ui_wifi(arg):
    on=not (STATE/'wifi-off').exists()
    s=Screen('wifi','Wi-Fi',refresh=5).label(readrun('wifi-summary','Wi-Fi: ?'))
    s.toggle('wifi.off' if on else 'wifi.on','Wi-Fi cliente',on)
    if 'IP fija' in readrun('wifi-summary') or (STATE/'ip-wlan0.conf').exists():s.small('IP manual activa','y')
    s.button('nav:ip:wlan0','IP de la Wi-Fi','i','ip')
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
    return s.small('Es también la clave de la web (usuario admin). Los equipos conectados tendrán que volver a conectarse.','m')

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
        s.small('Red del J1: http://192.168.78.1','g').small('USB: http://192.168.77.1','g')
        if c['lan']:
            ips=lan_ips()
            for ip in ips:s.small('Red local: http://'+ip,'g')
            if not ips:s.small('Red local: sin IP (conecta la Wi-Fi o el cable)','y')
            s.small('En la red local el panel va sin cifrar (HTTP): úsalo solo en casa y no abras el puerto 80 en el router.','y')
        if c['vpn']:s.small('VPN: http://10.66.0.1 (cifrado por el túnel, desde cualquier sitio)','g')
        s.small('Usuario admin; contraseña: la clave de la red de configuración.','m')
    else:s.small('Puerto 80 cerrado. La pantalla sigue funcionando; sin panel no se descargan los .conf ni se gestiona el SSH.','m')
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
        s.button('nav:client:'+c['id'],'%s · .%s · %s'%(c['name'],c['ip'],ago(p.get('handshake',0))),'i','user')
    return s.field('name','Nombre del nuevo cliente').button('vpn.add','Crear cliente','p')

def ui_client(cid):
    v=ensure_vpn_state();c=next((c for c in v['clients'] if c['id']==cid),None)
    if c is None:raise ValueError('El cliente ya no existe')
    p=wg_peers().get(c['public_key'],{})
    s=Screen('client:'+cid,c['name'],'nav:vpn',10).label('IP en la VPN: 10.66.0.%s'%c['ip'])
    s.label('Última conexión: '+ago(p.get('handshake',0)),'g' if p.get('handshake') and time.time()-p['handshake']<180 else 'm')
    if p.get('endpoint','(none)')!='(none)':s.small('Desde '+p['endpoint'],'m')
    s.small('Recibido %s · enviado %s'%(size_h(p.get('rx',0)),size_h(p.get('tx',0))),'m')
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
    s.button('nav:tz','Zona horaria: '+tz_name(),'i')
    s.button('nav:speed','Prueba de velocidad','i')
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
    s=Screen('speed','Velocidad','nav:sys',refresh=1 if sp.get('running') else 0)
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
    'sys':ui_sys,'reboot':ui_reboot,'poweroff':ui_poweroff,'qr6':ui_qr6,'wifiqr':ui_wifiqr,'disp':ui_disp,'res':ui_res,'power':ui_power,'speed':ui_speed,'tz':ui_tz,'panel':ui_panel}

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
    if verb in ('dns.on','dns.off','dns.save','dns6.on','dns6.off'):
        cf=load('cloudflare.json',{})
        if verb=='dns.save':dns_settings(bool(cf.get('enabled')),f.get('hostname',''),f.get('zone_id',''),f.get('token',''),None,f.get('hostname6',cf.get('hostname6','')))
        elif verb.startswith('dns6'):dns_settings(bool(cf.get('enabled')),cf.get('hostname',''),cf.get('zone_id',''),'',verb=='dns6.on')
        else:dns_settings(verb=='dns.on',cf.get('hostname',''),cf.get('zone_id',''),'')
        return 'dns','Cloudflare guardado'
    if verb in ('panel.on','panel.off'):panel_set(enabled=verb=='panel.on');return 'panel','Panel web '+('activado' if verb=='panel.on' else 'desactivado')
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
    if verb=='disp.lock':
        if arg not in ('0','1'):raise ValueError('Opción no válida')
        display_save(lock=arg=='1');return 'disp','Pantalla de bloqueo '+('activada' if arg=='1' else 'desactivada')
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
    try:s=UI_SCREENS.get(name,UI_SCREENS['home'])(arg)
    except (ValueError,RuntimeError) as e:s=ui_home();msg,kind=str(e),'e'
    if msg:s.msg(msg,kind)
    s.rows.insert(1,['O',str(display_timeout())]);s.rows.insert(1,['V',str(display_brightness())])
    s.rows.insert(1,['K','1' if display_lock() else '0'])
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

def has_uplink():
    try:return bool(command(['ip','-4','route','show','default']))
    except (RuntimeError,OSError,subprocess.SubprocessError):return False

def worker():
    next_dns=0;next_vpn=0;next_upnp=0
    while True:
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
    ensure_vpn_state();apply_usb();threading.Thread(target=worker,daemon=True).start()
    threading.Thread(target=ui_serve,daemon=True).start()
    threading.Thread(target=panel_serve,daemon=True).start()
    log('Web Wi-Fi / WireGuard disponible')
    while True:time.sleep(3600)
if __name__=='__main__':main()
