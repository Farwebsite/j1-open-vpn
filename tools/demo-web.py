#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0
"""Writes the web panel page with invented data (like demo-pantalla.py for the
screen), to look at its design in a browser without a J1.
usage: demo-web.py path/to/web.py out.html [message] [error]"""
import importlib.util, json, os, pathlib, sys, tempfile, time

base = pathlib.Path(tempfile.mkdtemp(prefix='j1web'))
os.environ['J1_STATE'] = str(base / 'state')
os.environ['J1_RUN'] = str(base / 'run')
for d in ('state', 'run'):
    (base / d).mkdir()
spec = importlib.util.spec_from_file_location('j1web', sys.argv[1])
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

KEY = 'kDemoDemoDemoDemoDemoDemoDemoDemoDemoDemo%s='
clients = [{'id': '%016x' % (i + 1), 'name': n, 'ip': i + 2, 'private_key': KEY % i,
            'public_key': KEY % (i + 10), 'psk': KEY % (i + 20)} for i, n in enumerate(('movil', 'portatil'))]
json.dump({'port': 51820, 'endpoint': '', 'private_key': KEY % 99, 'public_key': KEY % 98, 'clients': clients},
          open(base / 'state/vpn.json', 'w'))
json.dump({'enabled': True, 'hostname': 'vpn.ejemplo.com', 'zone_id': '0' * 32, 'token': 'x'},
          open(base / 'state/cloudflare.json', 'w'))
(base / 'state/admin-password').write_text('7KQ2M9XR4TPA\n')
for name, text in {'wifi-summary': 'Wi-Fi: 192.168.1.40 (IP fija)', 'eth-summary': 'Cable: sin adaptador',
                   'ap-name': 'AP: DIRECT-J1-VPN-71D9'}.items():
    (base / 'run' / name).write_text(text + '\n')
app.RUNTIME.update(vpn='Activo: UDP 51820', ddns='Actualizado: vpn.ejemplo.com', scan='3 redes encontradas',
                   networks=[{'hex': n.encode().hex(), 'name': n, 'signal': s, 'secure': True}
                             for n, s in (('MiCasa', -41), ('MiCasa_5G', -55), ('Vecino_2.4', -72))])
def command(args, data=None, timeout=15):
    if args[:4] == ['wg', 'show', 'wg0', 'dump']: return 'priv\tpub\t51820\toff'
    raise RuntimeError('demo')
app.command = command
app.log = lambda *a: None
msg = sys.argv[3] if len(sys.argv) > 3 else ''
try: body = app.page(msg, len(sys.argv) > 4)
except TypeError: body = app.page(msg)
pathlib.Path(sys.argv[2]).write_bytes(body)
