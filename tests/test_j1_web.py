import importlib.util, tempfile, unittest, pathlib, io, json
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('j1web',pathlib.Path(__file__).resolve().parent.parent/'rootfs/overlay/usr/local/lib/j1/web.py');app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=(app.STATE,app.RUN);app.STATE=pathlib.Path(self.tmp.name)/'state';app.RUN=pathlib.Path(self.tmp.name)/'run';app.STATE.mkdir();app.RUN.mkdir()
 def tearDown(self):app.STATE,app.RUN=self.old;self.tmp.cleanup()
 def test_wifi_config_escapes_and_persists(self):
  app.wifi_save({'ssid':'a"b\\c','password':'safe"pass\\word'})
  s=(app.STATE/'wifi.conf').read_text();self.assertIn('ssid=6122625c63',s);self.assertIn('psk="safe\\"pass\\\\word"',s);self.assertNotIn('p2p_disabled',s);self.assertTrue((app.RUN/'wifi-reconfigure').exists())
 def test_ddns_disabled_makes_no_request(self):
  with patch.object(app.urllib.request,'urlopen') as request:app.update_ddns();request.assert_not_called()
 def test_ddns_create_scoped_and_unproxied(self):
  app.save('cloudflare.json',{'enabled':True,'hostname':'vpn.example.com','zone_id':'a'*32,'token':'private-token'})
  response=io.BytesIO(b'ip=203.0.113.8\n')
  with patch.object(app.urllib.request,'urlopen',return_value=response),patch.object(app,'cf_request',side_effect=[[],{}]) as req:
   app.update_ddns();args=req.call_args_list;self.assertEqual(args[1].args[1],'/zones/'+'a'*32+'/dns_records');self.assertEqual(args[1].args[2],'POST');self.assertFalse(args[1].args[3]['proxied']);self.assertEqual(args[1].args[3]['name'],'vpn.example.com')
 def test_ambiguous_record_not_modified(self):
  app.save('cloudflare.json',{'enabled':True,'hostname':'vpn.example.com','zone_id':'a'*32,'token':'t'})
  with patch.object(app.urllib.request,'urlopen',return_value=io.BytesIO(b'ip=203.0.113.8\n')),patch.object(app,'cf_request',return_value=[{},{}]) as req:
   with self.assertRaises(RuntimeError):app.update_ddns()
   self.assertEqual(req.call_count,1)
 def test_dns_name_rejects_url_and_paths(self):
  for x in ['https://vpn.example.com','vpn.example.com/path','evil\n.example.com']:
   with self.assertRaises(ValueError):app.hostname(x)
 def test_private_values_not_in_page(self):
  app.save('vpn.json',{'port':80,'endpoint':'','private_key':'SERVER_SECRET','public_key':'pub','clients':[]})
  app.save('cloudflare.json',{'token':'API_SECRET'})
  s=app.page().decode();self.assertNotIn('SERVER_SECRET',s);self.assertNotIn('API_SECRET',s);self.assertIn('Buscar redes',s)
 def test_profile_contains_only_chosen_client(self):
  app.save('vpn.json',{'port':80,'endpoint':'vpn.example.com','private_key':'SERVER_SECRET','public_key':'serverpub','clients':[{'id':'a','ip':2,'private_key':'CLIENT_A','psk':'PSK_A'},{'id':'b','ip':3,'private_key':'CLIENT_B','psk':'PSK_B'}]})
  s=app.client_profile('a','192.168.77.1');self.assertIn('CLIENT_A',s);self.assertNotIn('CLIENT_B',s);self.assertNotIn('SERVER_SECRET',s);self.assertIn('vpn.example.com:80',s)
 def test_usb_boost_kernel_default_kept_and_choice_persisted(self):
  p=pathlib.Path(self.tmp.name)/'params';p.mkdir();(p/'j1_boost').write_text('1\n');(p/'j1_host_active').write_text('1\n');(p/'j1_boost_on').write_text('0\n')
  with patch.object(app,'USB_PARAMS',p):
   app.apply_usb();self.assertEqual((p/'j1_boost').read_text(),'1\n')
   app.save('usb.json',{'boost':False});app.apply_usb();self.assertEqual((p/'j1_boost').read_text(),'0\n')
   app.save('usb.json',{'boost':True});app.apply_usb();self.assertEqual((p/'j1_boost').read_text(),'1\n')
   (app.RUN/'eth-summary').write_text('Cable: 10.10.1.36\n');s=app.usb_section();self.assertIn('Cable: 10.10.1.36',s);self.assertIn('Modo host',s);self.assertIn(' checked',s);self.assertNotIn('bloqueados',s)
   (p/'j1_boost_locked').write_text('1\n');(p/'j1_boost_tries').write_text('3\n');self.assertIn('bloqueados',app.usb_section())
 def test_usb_section_without_host_kernel(self):
  with patch.object(app,'USB_PARAMS',pathlib.Path(self.tmp.name)/'missing'):
   self.assertIn('no admite modo host',app.usb_section());app.apply_usb()
 def test_nat_on_every_uplink(self):
  calls=[]
  def run(cmd,**k):calls.append(cmd);return type('R',(),{'returncode':0})()
  routes='default via 10.10.1.1 dev eth0 metric 50 \ndefault via 10.10.1.1 dev wlan0 metric 100 \n'
  with patch.object(app.subprocess,'run',side_effect=run),patch.object(app,'command',return_value=routes),patch.object(app,'Path') as P:
   self.assertTrue(app.firewall())
  nat=[c[c.index('-o')+1] for c in calls if 'MASQUERADE' in c];self.assertEqual(nat,['eth0','wlan0'])
 def test_ui_home_cp437_and_buttons(self):
  (app.RUN/'wifi-summary').write_text('Wi-Fi: 10.10.1.24\n')
  out=app.ui_request(b'a=nav%3Ahome')
  self.assertTrue(out.startswith(b'T\thome\t'));self.assertIn(b'C\tnav:wifi\tWi-Fi\twifi\n',out);self.assertIn(b'C\tnav:logs:sys\tRegistros\tlogs\n',out);self.assertIn(b'l\tgithub.com/Farwebsite/j1-open-vpn\tm\n',out);self.assertIn(b'L\tWi-Fi: 10.10.1.24\tg',out)
  self.assertIn('Red de configuración'.encode('cp437'),out)
 def test_ui_error_stays_on_screen(self):
  with patch.object(app,'command',side_effect=RuntimeError('x')):
   out=app.ui_request(b'a=ip.save%3Awlan0&s=ip%3Awlan0&f_ip=nope').decode('cp437')
  self.assertTrue(out.startswith('T\tip:wlan0\t'));self.assertRegex(out,r'\nM\t[^\n]*no válidos[^\n]*\te\n')
 def test_ui_field_decoding(self):
  got={}
  with patch.object(app,'client_create',side_effect=lambda n:got.update(name=n) or {'id':'0'*16}),patch.dict(app.UI_SCREENS,{'client':lambda a:app.Screen('client','c')}):
   out=app.ui_request(b'a=vpn.add&f_name=M%A2vil+1')
  self.assertEqual(got['name'],'Móvil 1');self.assertIn(b'M\tCliente creado',out)
 def test_ip_manual_and_auto(self):
  app.ip_save('wlan0',{'ip':'10.10.1.50','prefix':'24','gw':'10.10.1.1','dns':'1.1.1.1, 8.8.8.8'})
  self.assertEqual((app.STATE/'ip-wlan0.conf').read_text(),"ip=10.10.1.50\nsubnet=255.255.255.0\nrouter=10.10.1.1\ndns='1.1.1.1 8.8.8.8'\n")
  self.assertEqual(app.ip_load('wlan0')['dns'],'1.1.1.1 8.8.8.8');self.assertTrue((app.RUN/'ip-reconfigure').exists())
  for bad in ({'ip':'10.10.1.50','prefix':'24','gw':'10.10.2.1'},{'ip':'10.10.1.0','prefix':'24','gw':'10.10.1.1'},{'ip':'10.10.1.5','prefix':'24','gw':'10.10.1.1','dns':'x'}):
   with self.assertRaises(ValueError):app.ip_save('eth',bad)
  self.assertFalse(app.ip_shared());app.ip_share('wlan0')
  self.assertEqual((app.STATE/'ip-eth.conf').read_text(),(app.STATE/'ip-wlan0.conf').read_text());self.assertTrue(app.ip_shared())
  app.ip_auto('wlan0');self.assertEqual(app.ip_load('wlan0'),{});self.assertFalse(app.ip_shared())
  with self.assertRaises(ValueError):app.ip_share('wlan0')
 def test_ap_password_updates_files_and_group(self):
  (app.STATE/'p2p.conf').write_text('network={\n    ssid="DIRECT-J1"\n    psk="oldpassword"\n    mode=3\n}\n');(app.RUN/'ap-interface').write_text('lo\n')
  calls=[]
  def wpa(*a):calls.append(a);return 'network id / ssid / bssid / flags\n0\tDIRECT-J1\tany\t[DISABLED][P2P-PERSISTENT]' if a[0]=='list_networks' else 'OK'
  with patch.object(app,'wpa',side_effect=wpa):app.ap_password('Nueva-clave1')
  self.assertIn('    psk="Nueva-clave1"\n',(app.STATE/'p2p.conf').read_text());self.assertEqual((app.STATE/'admin-password').read_text(),'Nueva-clave1\n')
  self.assertIn(('set_network','0','psk','"Nueva-clave1"'),calls);self.assertIn(('p2p_group_remove','lo'),calls)
  for bad in ('corta','con espacio1','comi"llas12'):
   with self.assertRaises(ValueError):app.ap_password(bad)
 def test_wifi_toggle_and_save_reenables(self):
  app.wifi_enable(False);self.assertTrue((app.STATE/'wifi-off').exists())
  app.wifi_save({'ssid':'red','password':'12345678'});self.assertFalse((app.STATE/'wifi-off').exists())
 def test_qr_rows(self):
  r=type('P',(),{'returncode':0,'stdout':'##  ##\n  ##\n'})()
  with patch.object(app.subprocess,'run',return_value=r):self.assertEqual(app.qr_rows('x'),['101','010'])
 def test_wifi_qr_text_and_saved_network(self):
  self.assertEqual(app.wifi_qr_text('Mi;Red','a"b\\c:d'),'WIFI:T:WPA;S:Mi\\;Red;P:a\\"b\\\\c\\:d;;')
  self.assertEqual(app.wifi_qr_text('Libre',''),'WIFI:T:nopass;S:Libre;;')
  app.wifi_save({'ssid':'Casa ñ','password':'safe"pass\\word'});self.assertEqual(app.client_wifi(),('Casa ñ','safe"pass\\word'))
 def test_time_zone(self):
  import os,time
  old=os.environ.get('TZ')
  try:
   self.assertEqual(app.tz_get(),app.TZ_DEFAULT);self.assertEqual(app.tz_name(),'España, Europa central')
   self.assertIn(b'nav:tz\tZona horaria: Espa',app.ui_request(b'a=nav%3Asys'))
   for bad in (b'tz.set%3A99',b'tz.set%3A-1',b'tz.set%3Ax'):self.assertIn(b'\te\n',app.ui_request(b'a='+bad+b'&s=tz'))
   out=app.ui_request(b'a=tz.set%3A1&s=tz');self.assertIn(b'> Canarias, Portugal\tp',out)
   self.assertEqual((app.STATE/'tz').read_text(),'WET0WEST,M3.5.0/1,M10.5.0\n');self.assertEqual(os.environ['TZ'],'WET0WEST,M3.5.0/1,M10.5.0')
   self.assertEqual(time.strftime('%z'),'+0000' if not time.localtime().tm_isdst else '+0100')
   (app.STATE/'tz').write_text('<+0545>-5:45\n');self.assertEqual(app.tz_name(),'Personalizada (<+0545>-5:45)')
   app.save('vpn.json',{'port':51820,'endpoint':'','private_key':'S','public_key':'P','clients':[]})
   page=app.page();self.assertIn(b'id=hora',page);self.assertIn(b'<option value=11>UTC</option>',page)
  finally:
   if old is None:os.environ.pop('TZ',None)
   else:os.environ['TZ']=old
   time.tzset()
 def test_ssh_keys(self):
  self.assertEqual(app.ssh_keys(),[]);self.assertIn('Desactivado',app.ssh_section())
  for bad in ('','hola','ssh-ed25519','ssh-ed25519 AAAA\nssh-rsa BBBB','ssh-dss AAAAB3'):
   self.assertRaises(ValueError,app.ssh_add,bad)
  key='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIK0wmN/Cr3JXqmLW7u+g9pTh+4ZqHt7ZgLGbjJz0x8k4 yo@pc'
  app.ssh_add(key+'\n');app.ssh_add('  '+key);self.assertEqual(app.ssh_keys(),[key])
  self.assertEqual(oct((app.STATE/'authorized_keys').stat().st_mode&0o777),'0o600')
  self.assertIn('Activo: 1 clave autorizada',app.ssh_section());self.assertIn('sshoff',app.ssh_section())
  app.save('vpn.json',{'port':51820,'endpoint':'','private_key':'S','public_key':'P','clients':[]})
  self.assertIn(b'id=ssh',app.page());app.ssh_disable();app.ssh_disable();self.assertEqual(app.ssh_keys(),[])
 def test_speed_screen(self):
  app.SPEED.clear();self.assertIn(b'speed.run\tEmpezar',app.ui_request(b'a=nav%3Aspeed'))
  app.SPEED.update(running=True,link='cable (eth0)',ping='9 ms',down='midiendo...')
  out=app.ui_request(b'a=nav%3Aspeed');self.assertIn(b'\nR\t1\n',out);self.assertIn(b'Bajada: midiendo...\ty',out)
  app.SPEED.update(running=False,down='80.0 Mbit/s',up='20.0 Mbit/s');out=app.ui_request(b'a=nav%3Aspeed')
  self.assertIn(b'Subida: 20.0 Mbit/s\tn',out);self.assertIn(b'speed.run\tRepetir',out);self.assertNotIn(b'\nR\t',out)
  self.assertEqual(app.speed_mbit(10**7,8),'10.0 Mbit/s');app.SPEED.clear()
 def test_display_timeout_line_and_setting(self):
  self.assertIn(b'\nO\t60\n',app.ui_request(b'a=nav%3Ahome'))
  out=app.ui_request(b'a=disp.set%3A0&s=disp');self.assertIn(b'\nO\t0\n',out);self.assertIn(b'> Siempre encendida\tp',out)
  self.assertIn(b'\te\n',app.ui_request(b'a=disp.set%3A7&s=disp'));self.assertEqual(app.display_timeout(),0)
  self.assertIn(b'\nV\t143\n',out);out=app.ui_request(b'a=disp.bright%3A255&s=disp')
  self.assertIn(b'\nV\t255\n',out);self.assertIn(b'\nO\t0\n',out);self.assertIn(b'\nD\tdisp.bright\t255\t15\t255\n',out)
  self.assertIn(b'\te\n',app.ui_request(b'a=disp.bright%3A7&s=disp'));self.assertEqual(app.display_brightness(),255)
 def test_web_panel(self):
  self.assertEqual(app.panel_conf(),{'enabled':True,'lan':False,'vpn':False})
  lan=lambda:[app.ipaddress.ip_interface('10.10.1.40/24')]
  with patch.object(app,'lan_nets',lan):
   # peers: AP client, USB PC, home PC, VPN client, Internet
   ok=lambda:[app.panel_allowed(p) for p in ('192.168.78.23','192.168.77.2','10.10.1.7','10.66.0.2','85.1.2.3')]
   self.assertEqual(ok(),[True,True,False,False,False])
   out=app.ui_request(b'a=panel.lan%3A1&s=panel');self.assertIn(b'Red local: http://10.10.1.40',out)
   self.assertEqual(ok(),[True,True,True,False,False])
   out=app.ui_request(b'a=panel.vpn%3A1&s=panel');self.assertIn(b'VPN: http://10.66.0.1',out)
   self.assertEqual(ok(),[True,True,True,True,False])
   app.ui_request(b'a=panel.lan%3A0&s=panel');self.assertEqual(ok(),[True,True,False,True,False])
   self.assertIn(b'\te\n',app.ui_request(b'a=panel.lan%3A7&s=panel'))
   self.assertIn(b'\te\n',app.ui_request(b'a=panel.vpn%3Ax&s=panel'))
   out=app.ui_request(b'a=panel.off&s=panel');self.assertIn(b'S\tpanel.on\tPanel web\t0',out)
   self.assertEqual(ok(),[False]*5);self.assertFalse(app.panel_allowed('nonsense'))
   app.ui_request(b'a=panel.on&s=panel');self.assertEqual(app.panel_conf(),{'enabled':True,'lan':False,'vpn':True})
  self.assertIn(b'C\tnav:panel\tPanel web\tpanel\n',app.ui_request(b'a=nav%3Ahome'))
 def test_lock_code(self):
  app.PIN_FAIL.update(n=0,until=0.0)
  self.assertIn(b'\nK\t1\t0\n',app.ui_request(b'a=nav%3Adisp'))
  self.assertIn(b'\te\n',app.ui_request(b'a=disp.pin&s=disp&f_pin=12&f_pin2=12'));self.assertIsNone(app.display_pin())
  self.assertIn(b'no coinciden',app.ui_request(b'a=disp.pin&s=disp&f_pin=1234&f_pin2=1235'))
  out=app.ui_request(b'a=disp.pin&s=disp&f_pin=2468&f_pin2=2468');self.assertIn(b'\nK\t1\t1\n',out)
  self.assertNotIn('2468',app.json.dumps(app.load('display.json',{})))
  self.assertNotIn(b'\te\n',app.ui_request(b'a=lock.try&s=home&f_pin=2468'))
  for i in range(4):self.assertIn(b'incorrecto',app.ui_request(b'a=lock.try&s=home&f_pin=1111'))
  self.assertIn(b'Espera 30 s',app.ui_request(b'a=lock.try&s=home&f_pin=1111'))
  self.assertIn(b'Demasiados intentos',app.ui_request(b'a=lock.try&s=home&f_pin=2468'))   # even the right one waits
  app.PIN_FAIL['until']=0.0;self.assertNotIn(b'\te\n',app.ui_request(b'a=lock.try&s=home&f_pin=2468'))
  app.display_save(timeout=15);self.assertIsNotNone(app.display_pin())   # other settings keep the code
  self.assertIn('lockpinoff',app.lock_section())
  self.assertIn(b'y c\xa2digo quitado',app.ui_request(b'a=disp.lock%3A0&s=disp'));self.assertIsNone(app.display_pin())
  app.ui_request(b'a=disp.lock%3A1&s=disp');app.ui_request(b'a=disp.pin&s=disp&f_pin=13579&f_pin2=13579')
  self.assertIn(b'\nK\t1\t0\n',app.ui_request(b'a=disp.pinoff&s=disp'));self.assertIsNone(app.display_pin())
 def test_lock_screen(self):
  out=app.ui_request(b'a=nav%3Adisp&s=home');self.assertTrue(app.display_lock());self.assertIn(b'\nK\t1\t0\n',out)
  self.assertIn(b'\nS\tdisp.lock:0\tPantalla de bloqueo\t1\n',out)
  out=app.ui_request(b'a=disp.lock%3A0&s=disp');self.assertIn(b'\nK\t0\t0\n',out);self.assertFalse(app.display_lock())
  self.assertIn(b'\te\n',app.ui_request(b'a=disp.lock%3A7&s=disp'));self.assertFalse(app.display_lock())
  app.display_save(timeout=15);self.assertFalse(app.display_lock());self.assertEqual(app.display_timeout(),15)
  self.assertIn('value=1><button>Activar',app.lock_section())
  app.display_save(lock=True);self.assertIn(b'\nK\t1\t0\n',app.ui_request(b'a=nav%3Ahome&s=home'))

 def test_resources_screen_measures_between_visits(self):
  app.RES_PREV.clear();first=app.ui_request(b'a=nav%3Ares');self.assertIn(b'Midiendo',first)
  second=app.ui_request(b'a=nav%3Ares').decode('cp437');self.assertIn('CPU total:',second);self.assertIn('RAM libre',second)
 def test_poweroff_needs_confirmation_and_runs_poweroff(self):
  self.assertIn(b'B\tsys.poweroff\t',app.ui_request(b'a=nav%3Apoweroff'))
  self.assertIn(b'B\tnav:poweroff\tApagar J1\td',app.ui_request(b'a=nav%3Asys'))
  with patch.object(app.subprocess,'Popen') as p:out=app.ui_request(b'a=sys.poweroff&s=poweroff')
  self.assertIn('poweroff -f',p.call_args.args[0][-1]);self.assertIn(b'M\tApagando',out)
  home=app.ui_request(b'a=nav%3Ahome')
  self.assertIn(b'l\tJ1 Open VPN \xfa (c) 2026 Farweb\t',home);self.assertNotIn(b'appliance',home)
  menu=app.ui_request(b'a=nav%3Apower')
  for act in (b'sys.poweroff',b'sys.reboot',b'nav:home'):self.assertIn(b'B\t'+act+b'\t',menu)
 def test_ddns_ipv6_test_name_and_ipv4_kept(self):
  app.save('cloudflare.json',{'enabled':True,'hostname':'vpn.example.com','zone_id':'a'*32,'token':'t','enabled6':True,'hostname6':'vpn6.example.com'})
  traces=[io.BytesIO(b'ip=2a0c:5a87:5700:b000::1\n'),io.BytesIO(b'ip=203.0.113.8\n')]
  with patch.object(app.urllib.request,'urlopen',side_effect=traces),patch.object(app,'cf_request',side_effect=[[],{},[],{}]) as req:
   app.update_ddns()
  posts=[c.args[3] for c in req.call_args_list if len(c.args)>2 and c.args[2]=='POST']
  self.assertEqual([(p['type'],p['name'],p['content'],p['proxied']) for p in posts],[('AAAA','vpn6.example.com','2a0c:5a87:5700:b000::1',False),('A','vpn.example.com','203.0.113.8',False)])
  # IPv6 failure must not stop the IPv4 update
  with patch.object(app.urllib.request,'urlopen',side_effect=[OSError('no v6'),io.BytesIO(b'ip=203.0.113.9\n')]),patch.object(app,'cf_request',side_effect=[[{'id':'x','content':'203.0.113.8'}],{}]):
   app.update_ddns()
  self.assertEqual(app.RUNTIME['ddns'],'Actualizado: 203.0.113.9');self.assertIn('No se pudo',app.RUNTIME['ddns6'])
 def test_ipv6_settings_and_qr(self):
  app.save('cloudflare.json',{'enabled':True,'hostname':'vpn.example.com','zone_id':'a'*32,'token':'t'})
  with self.assertRaises(ValueError):app.dns_settings(True,'vpn.example.com','a'*32,'',True,'vpn.example.com')
  app.dns_settings(True,'vpn.example.com','a'*32,'',True,'vpn6.example.com')
  cf=app.load('cloudflare.json',{});self.assertEqual((cf['enabled6'],cf['hostname6'],cf['token']),(True,'vpn6.example.com','t'))
  app.dns_settings(True,'vpn.example.com','a'*32,'')   # web form: keeps the IPv6 settings
  self.assertTrue(app.load('cloudflare.json',{})['enabled6'])
  app.save('vpn.json',{'port':80,'endpoint':'','private_key':'S','public_key':'P','clients':[{'id':'a'*16,'name':'m','ip':2,'private_key':'C','public_key':'CP','psk':'K'}]})
  self.assertIn('Endpoint = vpn6.example.com:80',app.client_profile('a'*16,'x','vpn6.example.com'))
  self.assertIn('Endpoint = vpn.example.com:80',app.client_profile('a'*16,'x'))
  with patch.object(app,'wg_peers',return_value={}):self.assertIn(b'nav:qr6:'+b'a'*16,app.ui_request(b'a=nav%3Aclient%3A'+b'a'*16))
 def test_upnp_follows_port_and_switch(self):
  app.save('vpn.json',{'port':443,'endpoint':'','private_key':'S','public_key':'P','clients':[]})
  calls=[];wan=['79.1.2.3']
  def soap(ctl,svc,action,args):
   calls.append((action,dict(args)))
   if action=='AddPortMapping' and dict(args)['NewLeaseDuration']==3600 and wan[0]=='permanent':raise RuntimeError('UPnP AddPortMapping: error 725')
   return '<NewExternalIPAddress>%s</NewExternalIPAddress>'%('79.1.2.3' if wan[0]=='permanent' else wan[0])
  adds=lambda:[(a['NewExternalPort'],a['NewInternalClient'],a['NewProtocol'],a['NewLeaseDuration']) for n,a in calls if n=='AddPortMapping']
  dels=lambda:[a['NewExternalPort'] for n,a in calls if n=='DeletePortMapping']
  with patch.object(app,'upnp_find',return_value=('http://r/ctl','urn:schemas-upnp-org:service:WANIPConnection:1')),patch.object(app,'uplink_ip',return_value='10.10.1.24'),patch.object(app,'upnp_soap',side_effect=soap):
   app.upnp_sync();self.assertEqual(adds(),[(443,'10.10.1.24','UDP',3600)]);self.assertEqual(app.RUNTIME['upnp'],'Abierto UDP 443 → 10.10.1.24')
   calls.clear();app.save('vpn.json',dict(app.load('vpn.json',{}),port=51821));app.upnp_sync()
   self.assertEqual(dels(),[443]);self.assertEqual(adds(),[(51821,'10.10.1.24','UDP',3600)])
   calls.clear();wan[0]='permanent';app.upnp_sync();self.assertEqual(adds(),[(51821,'10.10.1.24','UDP',3600),(51821,'10.10.1.24','UDP',0)])
   calls.clear();wan[0]='192.168.1.33';app.upnp_sync();self.assertIn('IP privada',app.RUNTIME['upnp'])
   calls.clear();app.upnp_enable(False);app.upnp_sync();self.assertEqual(dels(),[51821]);self.assertEqual(adds(),[]);self.assertEqual(app.RUNTIME['upnp'],'Desactivado')
  with patch.object(app,'upnp_find',return_value=None),patch.object(app,'uplink_ip',return_value='10.10.1.24'):
   app.upnp_enable(True);app.upnp_sync();self.assertIn('no responde a UPnP',app.RUNTIME['upnp'])
if __name__=='__main__':unittest.main(verbosity=2)
