#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0
"""Demo server for the touch screen: runs the screens of web.py with invented
data (network, password, clients) so screenshots show no real configuration.
Nothing touches the network: every external command is blocked except
qrencode. Serves on /tmp/j1demo/run/j1-ui.sock; build a j1-display that uses
that socket (see tools/capturas.sh).
usage: demo-pantalla.py path/to/web.py"""
import importlib.util, json, os, pathlib, sys, time

BASE = pathlib.Path('/tmp/j1demo')
os.environ['J1_STATE'] = str(BASE / 'state')
os.environ['J1_RUN'] = str(BASE / 'run')
for d in ('state', 'run'):
    (BASE / d).mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location('j1web', sys.argv[1])
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

now = int(time.time())
KEY = 'kDemoDemoDemoDemoDemoDemoDemoDemoDemoDemo%s='
clients = [{'id': '%016x' % (i + 1), 'name': n, 'ip': i + 2, 'private_key': KEY % i,
            'public_key': KEY % (i + 10), 'psk': KEY % (i + 20)}
           for i, n in enumerate(('movil', 'portatil', 'tablet'))]
json.dump({'port': 51820, 'endpoint': '', 'private_key': KEY % 99, 'public_key': KEY % 98,
           'clients': clients}, open(BASE / 'state/vpn.json', 'w'))
json.dump({'enabled': True, 'hostname': 'vpn.ejemplo.com', 'zone_id': '0' * 32, 'token': 'x'},
          open(BASE / 'state/cloudflare.json', 'w'))
json.dump({'timeout': 60, 'brightness': 143}, open(BASE / 'state/display.json', 'w'))
(BASE / 'state/admin-password').write_text('7KQ2M9XR4TPA\n')
for name, text in {'wifi-summary': 'Wi-Fi: 192.168.1.40 (IP fija)', 'eth-summary': 'Cable: sin adaptador',
                   'vpn-summary': 'WG: UDP 51820 / 3 clientes', 'ap-name': 'AP: DIRECT-J1-VPN-71D9',
                   'ap-password': 'Clave: 7KQ2M9XR4TPA', 'ap-interface': 'p2p-wlan0-0'}.items():
    (BASE / 'run' / name).write_text(text + '\n')
app.RUNTIME.update(vpn='Activo: UDP 51820', ddns='Actualizado: vpn.ejemplo.com',
                   upnp='Abierto UDP 51820 → 192.168.1.40', scan='5 redes encontradas',
                   networks=[{'hex': n.encode().hex(), 'name': n, 'signal': s, 'secure': True}
                             for n, s in (('MiCasa', -41), ('MiCasa_5G', -55), ('Vecino_2.4', -72),
                                          ('Biblioteca', -80), ('Wifi-Invitados', -84))])
app.SPEED.update(link='cable (eth0)', ping='9 ms', down='56.8 Mbit/s', up='43.2 Mbit/s', running=False)

dump = ['priv\tpub\t51820\toff'] + [
    '%s\tpsk\t%s\t10.66.0.%d/32\t%d\t%d\t%d\toff' % (c['public_key'], ep, c['ip'], hs, rx, tx)
    for c, ep, hs, rx, tx in zip(clients, ('85.48.12.7:41622', '(none)', '(none)'),
                                 (now - 40, now - 7200, 0), (52_400_000, 8_100_000, 0),
                                 (1_310_000_000, 96_000_000, 0))]
def command(args, data=None, timeout=15):
    if args[:4] == ['wg', 'show', 'wg0', 'dump']:
        return '\n'.join(dump)
    raise RuntimeError('demo: ' + args[0] + ' bloqueado')
app.command = command
app.log = lambda *a: None
print('demo en', BASE / 'run/j1-ui.sock', flush=True)
app.ui_serve()
