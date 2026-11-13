import importlib.util, tempfile, unittest, pathlib, io, json
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('j1web',pathlib.Path(__file__).resolve().parent.parent/'rootfs/overlay/usr/local/lib/j1/web.py');app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=(app.STATE,app.RUN);app.STATE=pathlib.Path(self.tmp.name)/'state';app.RUN=pathlib.Path(self.tmp.name)/'run';app.STATE.mkdir();app.RUN.mkdir()
  app.APPLIED.clear();app.WSTATE.update(net_bad=None,net_step=0,net_seen=False,last='',vpn_fail=False)
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
  s=app.client_profile('a','192.168.77.1');self.assertIn('CLIENT_A',s);self.assertNotIn('CLIENT_B',s);self.assertNotIn('SERVER_SECRET',s);self.assertIn('vpn.example.com:80',s);self.assertIn('MTU = 1420',s)
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
  # one rule for every link but the tunnel: also a cable or Wi-Fi that comes up later
  nat=[c[c.index('-o')-1:c.index('-o')+2] for c in calls if 'MASQUERADE' in c];self.assertEqual(nat,[['!','-o','wg0']])
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
   # own home tile, no longer in Sistema; back goes home
   self.assertIn(b'C\tnav:tz\tZona horaria\ttz\n',app.ui_request(b'a=nav%3Ahome'));self.assertNotIn(b'nav:tz',app.ui_request(b'a=nav%3Asys'))
   self.assertTrue(app.ui_request(b'a=nav%3Atz').startswith(b'T\ttz\tZona horaria\tnav:home\n'))
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
 def test_speed_keeps_screen_on(self):
  # while measuring, the Velocidad screen stays on (O 0) so the result is seen
  with app.LOCK:app.SPEED.clear();app.SPEED.update(running=True,link='Wi-Fi')
  self.assertIn(b'\nO\t0\n',app.ui_request(b'a=nav%3Aspeed'));self.assertIn(b'\nO\t60\n',app.ui_request(b'a=nav%3Ahome'))
  with app.LOCK:app.SPEED['running']=False
  self.assertIn(b'\nO\t60\n',app.ui_request(b'a=nav%3Aspeed'))
  with app.LOCK:app.SPEED.clear()
 def test_speed_screen(self):
  app.SPEED.clear();self.assertIn(b'speed.run\tEmpezar',app.ui_request(b'a=nav%3Aspeed'))
  app.SPEED.update(running=True,link='cable (eth0)',ping='9 ms',down='midiendo...')
  out=app.ui_request(b'a=nav%3Aspeed');self.assertIn(b'\nR\t1\n',out);self.assertIn(b'Bajada: midiendo...\ty',out)
  app.SPEED.update(running=False,down='80.0 Mbit/s',up='20.0 Mbit/s');out=app.ui_request(b'a=nav%3Aspeed')
  self.assertIn(b'Subida: 20.0 Mbit/s\tn',out);self.assertIn(b'speed.run\tRepetir',out);self.assertNotIn(b'\nR\t',out)
  self.assertEqual(app.speed_mbit(10**7,8),'10.0 Mbit/s');app.SPEED.clear()
  # only its home tile opens it
  self.assertTrue(app.ui_request(b'a=nav%3Aspeed').startswith(b'T\tspeed\tVelocidad\tnav:home\n'))
  self.assertNotIn(b'speed',app.ui_request(b'a=nav%3Asys'))
 def test_display_timeout_line_and_setting(self):
  self.assertIn(b'\nO\t60\n',app.ui_request(b'a=nav%3Ahome'))
  out=app.ui_request(b'a=disp.set%3A0&s=disp');self.assertIn(b'\nO\t0\n',out);self.assertIn(b'> Siempre encendida\tp',out)
  self.assertIn(b'\te\n',app.ui_request(b'a=disp.set%3A7&s=disp'));self.assertEqual(app.display_timeout(),0)
  self.assertIn(b'\nV\t143\n',out);out=app.ui_request(b'a=disp.bright%3A255&s=disp')
  self.assertIn(b'\nV\t255\n',out);self.assertIn(b'\nO\t0\n',out);self.assertIn(b'\nD\tdisp.bright\t255\t15\t255\n',out)
  self.assertIn(b'\te\n',app.ui_request(b'a=disp.bright%3A7&s=disp'));self.assertEqual(app.display_brightness(),255)
 def test_web_panel(self):
  self.assertEqual(app.panel_conf(),{'enabled':True,'lan':False,'vpn':False,'https':False})
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
   app.ui_request(b'a=panel.on&s=panel');self.assertEqual(app.panel_conf(),{'enabled':True,'lan':False,'vpn':True,'https':False})
  self.assertIn(b'C\tnav:panel\tPanel web\tpanel\n',app.ui_request(b'a=nav%3Ahome'))
 def test_panel_lan_fixed_ip(self):
  # a fixed IP is /32 on the interface; the subnet only shows in the routes
  out={('ip','-4','-o','addr','show'):'1: lo    inet 127.0.0.1/8 scope host lo\n3: wlan0    inet 10.10.1.40/32 scope global wlan0\n'
       '5: rndis0    inet 192.168.77.1/30 scope global rndis0\n6: wg0    inet 10.66.0.1/24 scope global wg0',
       ('ip','-4','route','show','scope','link'):'10.10.1.0/24 dev wlan0 scope link src 10.10.1.40 metric 100\n'
       '10.66.0.0/24 dev wg0 proto kernel scope link src 10.66.0.1\n192.168.77.0/30 dev rndis0 proto kernel scope link src 192.168.77.1'}
  with patch.object(app,'command',lambda a,*x,**k:out[tuple(a)]):
   self.assertEqual(app.lan_ips(),['10.10.1.40'])
   app.panel_set(lan=True);self.assertTrue(app.panel_allowed('10.10.1.7'));self.assertFalse(app.panel_allowed('10.10.2.7'))
   self.assertFalse(app.panel_allowed('10.66.0.3'))
 def test_panel_password(self):
  (app.STATE/'admin-password').write_text('ApKey12345\n')
  self.assertIsNone(app.panel_own_password());self.assertTrue(app.panel_password_ok('ApKey12345'));self.assertFalse(app.panel_password_ok('x'))
  self.assertIn(b'\te\n',app.ui_request(b'a=panel.pw&s=panel&f_pw=short&f_pw2=short'))
  self.assertIn(b'no coinciden',app.ui_request(b'a=panel.pw&s=panel&f_pw=Panel-Pass-1&f_pw2=Panel-Pass-2'))
  out=app.ui_request(b'a=panel.pw&s=panel&f_pw=Panel-Pass-1&f_pw2=Panel-Pass-1');self.assertIn(b'Propia',out);self.assertIn(b'panel.pwreset',out)
  self.assertTrue(app.panel_password_ok('Panel-Pass-1'));self.assertFalse(app.panel_password_ok('ApKey12345'))
  self.assertNotIn('Panel-Pass-1',app.json.dumps(app.load('panel.json',{})))
  app.ui_request(b'a=panel.vpn%3A1&s=panel');self.assertIsNotNone(app.panel_own_password())   # other settings keep it
  self.assertIn('Propia',app.pw_section())
  app.ui_request(b'a=panel.pwreset&s=panel');self.assertTrue(app.panel_password_ok('ApKey12345'));self.assertIsNone(app.panel_own_password())
 def test_panel_forms_for_codes(self):
  self.assertIn('action value=lockpin>',app.lock_section());self.assertIn('action value=appass>',app.ap_section())
  self.assertIn('name=current',app.ap_section());self.assertIn('Poner c',app.lock_section())
 def test_lock_code(self):
  app.PIN_FAIL.update(n=0,until=0.0)
  self.assertIn(b'\nK\t1\t0\t0\n',app.ui_request(b'a=nav%3Adisp'))
  self.assertIn(b'\te\n',app.ui_request(b'a=disp.pin&s=disp&f_pin=12&f_pin2=12'));self.assertIsNone(app.display_pin())
  self.assertIn(b'no coinciden',app.ui_request(b'a=disp.pin&s=disp&f_pin=1234&f_pin2=1235'))
  out=app.ui_request(b'a=disp.pin&s=disp&f_pin=2468&f_pin2=2468');self.assertIn(b'\nK\t1\t1\t0\n',out)
  self.assertNotIn('2468',app.json.dumps(app.load('display.json',{})))
  self.assertNotIn(b'\te\n',app.ui_request(b'a=lock.try&s=home&f_pin=2468'))
  for i in range(4):self.assertIn(b'incorrecto',app.ui_request(b'a=lock.try&s=home&f_pin=1111'))
  self.assertIn(b'Espera 30 s (quedan 5',app.ui_request(b'a=lock.try&s=home&f_pin=1111'))
  self.assertIn(b'Demasiados intentos',app.ui_request(b'a=lock.try&s=home&f_pin=2468'))   # even the right one waits
  self.assertEqual(app.load('pin-fail.json',{}),{'n':5})   # survives a reboot
  app.PIN_FAIL.update(n=0,until=0.0);app.pin_fail_load();self.assertEqual(app.PIN_FAIL['n'],5);self.assertGreater(app.PIN_FAIL['until'],0)
  for i in range(5):
   app.PIN_FAIL['until']=0.0;out=app.ui_request(b'a=lock.try&s=home&f_pin=1111')
  self.assertIn(b'Pantalla bloqueada tras 10',out);self.assertIn(b'\nK\t1\t1\t1\n',out);self.assertTrue(app.pin_blocked())
  app.PIN_FAIL['until']=0.0;self.assertIn(b'bloqueada',app.ui_request(b'a=lock.try&s=home&f_pin=2468'))   # not even the right one
  app.pin_fail_load();self.assertTrue(app.pin_blocked())
  self.assertIn('lockunblock',app.lock_section());app.pin_unblock();self.assertFalse(app.pin_blocked())
  self.assertNotIn(b'\te\n',app.ui_request(b'a=lock.try&s=home&f_pin=2468'));self.assertFalse((app.STATE/'pin-fail.json').exists())
  app.display_save(timeout=15);self.assertIsNotNone(app.display_pin())   # other settings keep the code
  self.assertIn('lockpinoff',app.lock_section())
  self.assertIn(b'F\tpincur\t',app.ui_request(b'a=nav%3Adisp'))
  self.assertIn(b'Escribe el c\xa2digo actual',app.ui_request(b'a=disp.lock%3A0&s=disp'));self.assertIsNotNone(app.display_pin())
  self.assertIn(b'incorrecto',app.ui_request(b'a=disp.lock%3A0&s=disp&f_pincur=1111'));self.assertTrue(app.display_lock())
  self.assertEqual(app.PIN_FAIL['n'],1)   # counts like the lock screen
  self.assertIn(b'y c\xa2digo quitado',app.ui_request(b'a=disp.lock%3A0&s=disp&f_pincur=2468'));self.assertIsNone(app.display_pin())
  app.ui_request(b'a=disp.lock%3A1&s=disp');app.ui_request(b'a=disp.pin&s=disp&f_pin=13579&f_pin2=13579')
  self.assertIn(b'Escribe el c\xa2digo actual',app.ui_request(b'a=disp.pinoff&s=disp'));self.assertIsNotNone(app.display_pin())
  self.assertIn(b'incorrecto',app.ui_request(b'a=disp.pinoff&s=disp&f_pincur=2468'));self.assertIsNotNone(app.display_pin())
  self.assertIn(b'\nK\t1\t0\t0\n',app.ui_request(b'a=disp.pinoff&s=disp&f_pincur=13579'));self.assertIsNone(app.display_pin())
 def test_lock_screen(self):
  out=app.ui_request(b'a=nav%3Adisp&s=home');self.assertTrue(app.display_lock());self.assertIn(b'\nK\t1\t0\t0\n',out)
  self.assertIn(b'\nS\tdisp.lock:0\tPantalla de bloqueo\t1\n',out)
  out=app.ui_request(b'a=disp.lock%3A0&s=disp');self.assertIn(b'\nK\t0\t0\t0\n',out);self.assertFalse(app.display_lock())
  self.assertIn(b'\te\n',app.ui_request(b'a=disp.lock%3A7&s=disp'));self.assertFalse(app.display_lock())
  app.display_save(timeout=15);self.assertFalse(app.display_lock());self.assertEqual(app.display_timeout(),15)
  self.assertIn('value=1><button class=sec>Activar',app.lock_section())
  app.display_save(lock=True);self.assertIn(b'\nK\t1\t0\t0\n',app.ui_request(b'a=nav%3Ahome&s=home'))

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
 def test_wifi_qr_parse(self):
  self.assertEqual(app.qr_wifi_parse(r'WIFI:T:WPA;S:Casa\;1;P:se\:creta123;H:true;;'),{'ssid':'Casa;1','password':'se:creta123'})
  self.assertEqual(app.qr_wifi_parse('wifi:S:Bar;T:nopass;P:;;'),{'ssid':'Bar','password':''})
  self.assertEqual(app.qr_wifi_parse(app.wifi_qr_text('Red "x"',r'cla\ve;123')),{'ssid':'Red "x"','password':r'cla\ve;123'})
  for bad in ('https://example.com','WIFI:T:WEP;S:Old;P:12345;;','WIFI:T:WPA;S:;P:secreta123;;','WIFI:T:WPA;S:Casa;P:corta;;'):
   with self.assertRaises(ValueError):app.qr_wifi_parse(bad)
 def test_wifi_from_camera_qr(self):
  class Proc:
   def __init__(self,rc,out):self.returncode=rc;self.out=out;self.signals=[]
   def communicate(self,timeout=None):return self.out,b''
   def terminate(self):self.signals.append('TERM')
   def send_signal(self,sig):self.signals.append(sig)
  def wait():
   for _ in range(200):
    if not app.CAMQR.get('running'):return
    app.time.sleep(0.01)
  app.CAMQR.clear()
  with patch.object(app.subprocess,'run'),patch.object(app.subprocess,'Popen',return_value=Proc(0,b'WIFI:T:WPA;S:Casa;P:secreta123;;')) as po:
   out=app.ui_request(b'a=camqr.start%3Arear');wait()
  self.assertIn(b'T\tcamqr\t',out);self.assertEqual(po.call_args.args[0][1:3],['qr','rear'])
  # read: saved and connecting at once, the password never on the screen
  self.assertIn('ssid='+b'Casa'.hex(),(app.STATE/'wifi.conf').read_text())
  out=app.ui_request(b'a=nav%3Acamqr');self.assertIn(b'T\twifi\t',out);self.assertIn(b'Red Casa guardada',out);self.assertNotIn(b'secreta123',out)
  self.assertIn(b'T\tcamqr\t',app.ui_request(b'a=nav%3Acamqr'))   # the message only once
  # running: full screen camera, tap focuses the rear one, the screen stays on
  app.CAMQR.clear();p=Proc(0,b'');app.CAMQR.update(running=True,cam='rear',gen=7,proc=p)
  out=app.ui_request(b'a=camqr.focus');self.assertIn(b'X\tcamqr.focus\tcamqr.switch\t',out);self.assertIn(b'\nO\t0\n',out);self.assertEqual(p.signals,[app.signal.SIGUSR1])
  # switching camera stops this one and starts the other
  with patch.object(app.threading,'Thread') as th:app.ui_request(b'a=camqr.switch')
  self.assertEqual(p.signals[-1],'TERM');self.assertEqual(app.CAMQR['cam'],'front');self.assertEqual(th.call_args.kwargs['args'],('front',8))
  # leaving the camera screen (Home) turns it off
  q=Proc(0,b'');app.CAMQR.update(proc=q);app.ui_request(b'a=nav%3Ahome');self.assertEqual(q.signals,['TERM'])
  # nothing seen: tap to try again; an older run cannot overwrite a newer one
  app.CAMQR.clear();app.CAMQR.update(running=True,cam='front',gen=3)
  with patch.object(app.subprocess,'run'),patch.object(app.subprocess,'Popen',return_value=Proc(1,b'')):app.camqr_run('front',2);self.assertTrue(app.CAMQR['running']);app.camqr_run('front',3)
  out=app.ui_request(b'a=nav%3Acamqr');self.assertIn(b'X\tcamqr.start:front\tcamqr.switch\tNo se ha visto',out)
  with patch.object(app.subprocess,'run'),patch.object(app.subprocess,'Popen',return_value=Proc(0,b'https://example.com')):
   app.CAMQR.update(running=True,gen=4);app.camqr_run('rear',4)
  self.assertIn(b'no es de una red Wi-Fi',app.ui_request(b'a=nav%3Acamqr'))
  self.assertIn(b'\te\n',app.ui_request(b'a=camqr.start%3Aside&s=camqr'))
 def test_camera_settings(self):
  ctl=str(app.STATE/'cam.ctl');level=str(app.STATE/'cam.level')
  with patch.object(app,'CAM_CTL',ctl),patch.object(app,'CAM_LEVEL',level),patch.dict(app.CAM_SET,{'b':'a','m':'s','c':'2','s':'1','f':'m'}):
   app.CAMQR.clear();app.CAMQR.update(running=True,cam='rear',gen=1,proc=None)
   # automatic: the screen shows the level j1-camera is using
   pathlib.Path(level).write_text('2\n')
   out=app.ui_request(b'a=nav%3Acamqr');self.assertIn(b'\nY\tcamqr.set\tb=a2 m=s c=2 s=1 f=m',out)
   # each control goes to j1-camera's control file
   app.ui_request(b'a=camqr.set%3Ab%3D6');app.ui_request(b'a=camqr.set%3Am%3Dc');out=app.ui_request(b'a=camqr.set%3Af%3Dn')
   self.assertEqual(pathlib.Path(ctl).read_text(),'b=6 m=c c=2 s=1 f=n\n');self.assertIn(b'Y\tcamqr.set\tb=6 m=c c=2 s=1 f=n',out)
   for bad in (b'b%3D9',b'c%3D5',b'x%3D1',b'm%3D',b's%3D11'):
    self.assertIn(b'\te\n',app.ui_request(b'a=camqr.set%3A'+bad+b'&s=camqr'))
   self.assertEqual(pathlib.Path(ctl).read_text(),'b=6 m=c c=2 s=1 f=n\n')
   # the front camera has no controls
   app.CAMQR.update(cam='front');self.assertNotIn(b'\nY\t',app.ui_request(b'a=nav%3Acamqr'))
   app.CAMQR.clear()
 def test_web_ap_switch(self):
  (app.RUN/'ap-name').write_text('AP: DIRECT-J1-VPN-TEST\n')
  s=app.ap_section();self.assertIn('Activada: <b>DIRECT-J1-VPN-TEST</b>',s);self.assertIn('name=action value=ap><input type=hidden name=on value=0>',s)
  app.ap_enable(False);s=app.ap_section();self.assertIn('Apagada.',s);self.assertIn('name=on value=1><button class=sec>Activar',s)
  self.assertTrue((app.STATE/'ap-off').exists());app.ap_enable(True);self.assertFalse((app.STATE/'ap-off').exists())
 def test_battery_estimate(self):
  bat=app.STATE/'bat';bat.mkdir()
  def put(**v):
   for k,x in dict(dict(capacity='80',status='Discharging',voltage_now='3900000',temp='275',batt_read_raw_soc='800'),**v).items():(bat/k).write_text(x+'\n')
  fgu=bat/'fgu_current'
  with patch.object(app,'BAT',bat),patch.object(app,'FGU',fgu),patch.object(app.time,'monotonic') as now:
   app.BAT_HIST.clear();put();now.return_value=1000;app.bat_sample()
   (bat/'health').write_text('Good\n')
   info=app.bat_info();self.assertEqual(info[:4],[('Carga','80%','g'),('Estado','sin cargador, usando la batería','y'),('Temperatura','27.5 °C','g'),('Voltaje','3.90 V','g')])
   self.assertEqual(info[4],('Tiempo restante','calculando (unos 10 min)','m'));self.assertEqual(info[-1],('Salud','buena','g'))
   # 2 % in 12 min = 10 %/h: 78 % left lasts 7 h 48 min, 10 % of 7.03 Wh
   put(batt_read_raw_soc='780',capacity='78');now.return_value=1720;app.bat_sample()
   self.assertEqual(app.bat_info()[4:6],[('Tiempo restante','unas 7 h 48 min','y'),('Consumo','aprox. 0.7 W (10.0 % por hora)','y')])
   out=app.ui_request(b'a=nav%3Abat').decode('cp437');self.assertIn('L\tTiempo restante: unas 7 h 48 min\ty',out);self.assertIn('Sin medida de corriente',out)
   self.assertIn('Consumo: <b>aprox. 0.7 W',app.bat_section())
   # counter that only says 1 (no measurement): still the estimate from the charge
   fgu.write_text('1\n');self.assertEqual(app.bat_info()[4][1],'unas 7 h 48 min')
   # measured current: shown at once; time left from the 10-minute mean, 78 % of 1850 mAh
   fgu.write_text('-200\n');now.return_value=1730;app.bat_sample()
   fgu.write_text('-244\n');info=app.bat_info()
   self.assertEqual(info[4:6],[('Consumo','244 mA (0.95 W)','y'),('Tiempo restante','unas 6 h 30 min','y')])
   self.assertIn('corriente media',app.bat_section())
   put(status='Charging',batt_read_raw_soc='900');fgu.write_text('370\n');now.return_value=1740
   self.assertEqual(app.bat_info()[4:6],[('Corriente de carga','370 mA','g'),('Llena en','unas 30 min','g')])
   def near_full():
    info=app.bat_info();self.assertEqual(info[1],('Estado','cargando, casi llena','g'));self.assertNotIn('Llena en',[n for n,v,c in info])
   fgu.write_text('60\n');near_full()
   # last stretch (constant voltage): the current falls, so no time from it
   fgu.write_text('300\n');put(status='Charging',voltage_now='4370000');near_full()
   fgu.unlink();put()
   # charger plugged: the discharge history no longer counts
   put(status='Charging');now.return_value=1780;app.bat_sample();self.assertEqual(len(app.BAT_HIST),1)
   self.assertEqual(app.bat_info()[1],('Estado','cargando','g'))
   put(status='Full',capacity='100',batt_read_raw_soc='1000');self.assertNotIn('Tiempo restante',[n for n,v,c in app.bat_info()])
   # its own tile and web section; not on the home status lines
   home=app.ui_request(b'a=nav%3Ahome');self.assertIn(b'C\tnav:bat\tBater',home);self.assertNotIn(b'Carga',home)
   self.assertIn('href="#bat"',app.home_html());self.assertNotIn('Tiempo restante',app.home_html())
   (bat/'capacity').unlink();self.assertEqual(app.bat_info(),[]);self.assertIn('No se puede leer',app.bat_section())
  app.BAT_HIST.clear()
 def test_battery_limit(self):
  bat=app.STATE/'bat2';bat.mkdir();slate=bat/'batt_slate_mode'
  def put(**v):
   for k,x in dict(dict(capacity='70',status='Charging',voltage_now='4000000',temp='280',batt_read_raw_soc='700',batt_slate_mode='0'),**v).items():(bat/k).write_text(x+'\n')
  fgu=bat/'fgu_current'
  with patch.object(app,'BAT',bat),patch.object(app,'FGU',fgu):
   put();fgu.write_text('370\n')
   # no limit: charges to 100 %, the screen offers the switch with 80 %
   self.assertEqual(app.bat_limit(),0);out=app.ui_request(b'a=nav%3Abat').decode('cp437')
   self.assertIn('S\tbat.limit:80\tLimitar la carga\t0',out);self.assertNotIn('bat.limit\t',out)
   self.assertIn('name=action value=batlimit',app.bat_section());self.assertIn('value=80>',app.bat_section())
   # 80 %: time to the limit, the slider shows it
   out=app.ui_request(b'a=bat.limit%3A80').decode('cp437');self.assertIn('Carga limitada al 80%',out);self.assertIn('D\tbat.limit\t80\t50\t95',out)
   self.assertIn(('Llega al 80% en','unas 30 min','g'),app.bat_info());self.assertEqual(slate.read_text(),'0\n')
   # reaches 80 %: charger paused, the J1 runs on the battery with the cable plugged
   put(capacity='80',batt_read_raw_soc='800');app.bat_limit_apply();self.assertEqual(slate.read_text(),'1')
   put(capacity='80',status='Discharging',batt_slate_mode='1');fgu.write_text('-110\n');info=app.bat_info()
   self.assertEqual(info[1],('Estado','en pausa por el límite del 80%; vuelve a cargar al 75%','g'))
   self.assertIn(('Consumo','110 mA (0.44 W)','y'),info);self.assertNotIn('Tiempo restante',[n for n,v,c in info])
   app.bat_limit_apply();self.assertEqual(slate.read_text(),'1\n')   # 80 %: still paused
   put(capacity='75',status='Discharging',batt_slate_mode='1');app.bat_limit_apply();self.assertEqual(slate.read_text(),'0')
   # custom value, kept when switched off and on again; out of range refused
   app.ui_action('bat.limit:65',{});self.assertEqual(app.bat_limit(),65)
   app.ui_action('bat.limit:0',{});self.assertEqual(app.bat_limit(),0);self.assertIn('S\tbat.limit:65\t',app.ui_request(b'a=nav%3Abat').decode('cp437'))
   for bad in ('49','96','x'):self.assertRaises(ValueError,app.ui_action,'bat.limit:'+bad,{})
   # limit off while paused: charging comes back at once
   app.bat_limit_save(90);put(capacity='92',status='Discharging',batt_slate_mode='1');app.bat_limit_save(0);self.assertEqual(slate.read_text(),'0')
  app.BAT_HIST.clear()
 def vpn0(self):app.save('vpn.json',{'port':53,'endpoint':'','private_key':'K','public_key':'P','clients':[]})   # page() without wg
 def test_client_pause_and_stats(self):
  app.save('vpn.json',{'port':53,'endpoint':'','private_key':'K','public_key':'P','clients':[
   {'id':'a'*16,'name':'Móvil','ip':2,'private_key':'x','public_key':'PUBA','psk':'S'},{'id':'b'*16,'name':'Portátil','ip':3,'private_key':'y','public_key':'PUBB','psk':'T'}]})
  peers={'PUBA':{'endpoint':'(none)','handshake':int(app.time.time())-60,'rx':2048,'tx':3*1048576}}
  with patch.object(app,'apply_vpn') as av,patch.object(app,'wg_peers',return_value=peers):
   s=app.page().decode();self.assertIn('hace 60 s · ↓3.0 MB ↑2.0 KB',s);self.assertIn('nunca',s);self.assertIn('value=pause',s)
   app.client_pause('a'*16,True);av.assert_called();self.assertTrue(app.load('vpn.json',{})['clients'][0]['paused'])
   self.assertIn('en pausa',app.page().decode());self.assertIn('Reanudar',app.page().decode())
   out=app.ui_request(b'a=nav%3Aclient%3A'+b'a'*16).decode('cp437');self.assertIn('En pausa: no puede conectarse',out);self.assertIn('S\tvpn.pause:'+'a'*16+':0\tAcceso a la VPN\t0',out)
   out=app.ui_request(b'a=vpn.pause%3A'+b'a'*16+b'%3A0').decode('cp437');self.assertIn('Cliente reanudado',out);self.assertFalse(app.load('vpn.json',{})['clients'][0]['paused'])
   self.assertRaises(ValueError,app.client_pause,'c'*16,True)
  # a paused client has no peer in WireGuard
  v=app.load('vpn.json',{});v['clients'][1]['paused']=True;app.save('vpn.json',v)
  with patch.object(app,'command',return_value='') as cmd,patch.object(app,'firewall',return_value=True),patch.object(app.Path,'exists',return_value=True):
   app.apply_vpn()
  conf=(app.RUN/'wg0.conf').read_text();self.assertIn('PUBA',conf);self.assertNotIn('PUBB',conf)
 def test_notifications(self):
  c=app.notify_conf();self.assertRegex(c['topic'],r'^j1-[0-9a-f]{20}$');self.assertFalse(c['enabled']);self.assertEqual(app.notify_url(),'https://ntfy.sh/'+c['topic'])
  sent=[]
  with patch.object(app,'notify_send',side_effect=lambda *a:sent.append(a)),patch.object(app.threading,'Thread') as T:
   T.side_effect=lambda target,daemon:type('T',(),{'start':lambda s:target()})()
   self.assertFalse(app.notify('power','t','x'))   # off: nothing
   app.notify_save(enabled=True,events=['power','client'])
   self.assertTrue(app.notify('power','t','x'));self.assertFalse(app.notify('bat','t','x'));self.assertEqual(len(sent),1)
   # watch: charger out and back, a client connecting; first look only learns the state
   bat={'cap':80,'status':'Charging','temp':30,'v':4.0,'soc':80,'ma':None}
   app.save('vpn.json',{'port':53,'endpoint':'','private_key':'K','public_key':'P','clients':[{'id':'a'*16,'name':'Móvil','ip':2,'private_key':'x','public_key':'PUBA','psk':'S'}]})
   peers={}
   app.WATCH.update({'power':None,'low':False,'hot':False,'vpn_err':None,'clients':None,'boot':None});sent.clear()
   with patch.object(app,'bat_read',side_effect=lambda:dict(bat)),patch.object(app,'wg_peers',side_effect=lambda:peers):
    app.notify_watch();self.assertEqual(sent,[])
    bat['status']='Discharging';app.notify_watch();self.assertEqual(sent[-1][0],'J1: sin corriente');self.assertIn('80%',sent[-1][1])
    bat['status']='Paused';app.notify_watch();self.assertEqual(sent[-1][0],'J1: vuelve la corriente')
    peers={'PUBA':{'handshake':int(app.time.time())-10}};app.notify_watch();self.assertEqual(sent[-1][0],'J1: Móvil conectado')
    n=len(sent);app.notify_watch();self.assertEqual(len(sent),n)   # still connected: once
    bat.update(status='Discharging',cap=15);app.notify_watch();self.assertNotIn('J1: batería baja',[x[0] for x in sent])   # 'bat' not chosen
   app.notify_save(events=['bat'])
   with patch.object(app,'bat_read',return_value=dict(bat,status='Discharging',cap=15)),patch.object(app,'wg_peers',return_value={}):
    app.WATCH['low']=False;app.notify_watch();self.assertEqual(sent[-1][0],'J1: batería baja')
  # no IPs, keys or the client's address in any text
  for t in sent:self.assertNotRegex(t[0]+t[1],r'\d+\.\d+\.\d+\.\d+')
  self.assertRaises(ValueError,app.notify_save,server='http://ntfy.sh')
  old=app.notify_conf()['topic'];app.notify_save(new_topic=True);self.assertNotEqual(app.notify_conf()['topic'],old)
  self.vpn0()
  with patch.object(app,'qr_rows',return_value=['101']):out=app.ui_request(b'a=nav%3Anotify').decode('cp437');self.assertIn('S\tnotify.off\tAvisos\t1',out);self.assertIn('\nQ\t',out)
  self.assertIn('C\tnav:notify\tAvisos\tnotify',app.ui_request(b'a=nav%3Ahome').decode('cp437'))
  self.assertIn('name=action value=notify>',app.page().decode())
 def test_notify_ip_change(self):
  app.RUNTIME.pop('ip4',None)
  with patch.object(app,'notify') as n:
   app.notify_ip('203.0.113.8');n.assert_not_called();app.notify_ip('203.0.113.8');n.assert_not_called()
   app.notify_ip('198.51.100.7');n.assert_called_once();self.assertNotIn('198.51',str(n.call_args))
 def test_backup_roundtrip(self):
  db=pathlib.Path(self.tmp.name)/'dropbear';db.mkdir();(db/'dropbear_ed25519_host_key').write_bytes(b'HOSTKEY')
  app.save('vpn.json',{'port':53,'clients':[]});(app.STATE/'wifi.conf').write_text('net');(app.STATE/'mac.info').write_text('MAC');(app.STATE/'random-seed').write_bytes(b'r')
  with patch.object(app,'DROPBEAR',db):
   self.assertRaises(ValueError,app.backup_make,'short','short');self.assertRaises(ValueError,app.backup_make,'longenough','different')
   blob=app.backup_make('correct horse','correct horse')
   self.assertTrue(blob.startswith(app.BACKUP_MAGIC))
   names=dict(app.backup_open(blob,'correct horse'))
   self.assertEqual(names['config/wifi.conf'],b'net');self.assertEqual(names['dropbear/dropbear_ed25519_host_key'],b'HOSTKEY')
   self.assertNotIn('config/mac.info',names);self.assertNotIn('config/random-seed',names)
   self.assertRaises(ValueError,app.backup_open,blob,'wrong password')
   bad=bytearray(blob);bad[-40]^=1;self.assertRaises(ValueError,app.backup_open,bytes(bad),'correct horse')
   self.assertRaises(ValueError,app.backup_open,b'not a backup','x')
   # restore writes the files back and reboots
   (app.STATE/'wifi.conf').write_text('changed');(db/'dropbear_ed25519_host_key').write_bytes(b'OTHER')
   with patch.object(app,'reboot_soon') as rb:self.assertEqual(app.backup_restore(blob,'correct horse'),3);rb.assert_called_once()
   self.assertEqual((app.STATE/'wifi.conf').read_text(),'net');self.assertEqual((db/'dropbear_ed25519_host_key').read_bytes(),b'HOSTKEY')
 def test_backup_rejects_paths(self):
  import tarfile
  buf=io.BytesIO()
  with tarfile.open(fileobj=buf,mode='w:gz') as t:
   for n in ('config/vpn.json','config/../../etc/passwd'):
    i=tarfile.TarInfo(n);i.size=2;t.addfile(i,io.BytesIO(b'{}'))
  salt=b's'*16;nonce=b'n'*12;head=app.BACKUP_MAGIC+salt+nonce
  blob=head+app.aes_gcm(app.backup_key('password1',salt),nonce,head,buf.getvalue())
  self.assertRaisesRegex(ValueError,'inesperado',app.backup_open,blob,'password1')
 def test_multipart_restore_form(self):
  body=(b'--X\r\nContent-Disposition: form-data; name="csrf"\r\n\r\nabc\r\n--X\r\nContent-Disposition: form-data; name="file"; filename="c.j1bak"\r\n'
        b'Content-Type: application/octet-stream\r\n\r\n\x00\x01BIN\r\n--X--\r\n')
  self.vpn0();f,files=app.multipart('multipart/form-data; boundary=X',body);self.assertEqual(f,{'csrf':'abc'});self.assertEqual(files,{'file':b'\x00\x01BIN'})
  s=app.page().decode();self.assertIn('enctype=multipart/form-data',s);self.assertIn('value=backup>',s)
 def test_update_check_and_screen(self):
  rel=pathlib.Path(self.tmp.name)/'release';rel.write_text('j1-open-vpn 1.4.4 (Alpine 3.24.4)\n')
  api=json.dumps({'tag_name':'v1.4.5','assets':[{'name':n,'browser_download_url':'https://example/'+n} for n in ('j1-open-vpn-rootfs.tar.gz','SHA256SUMS','j1-open-vpn-boot.img')]}).encode()
  app.UPD.update(state='',busy=False,latest=None);self.vpn0()
  with patch.object(app,'RELEASE_FILE',rel),patch.object(app,'http_get',return_value=(api,'')),patch.object(app,'kernel_same',return_value=False):
   self.assertEqual(app.release_current(),'1.4.4');self.assertRaises(ValueError,app.update_start)
   app.update_look();self.assertIn('Hay una versión nueva: 1.4.5',app.UPD['state']);self.assertIn('kernel',app.UPD['state'])
   out=app.ui_request(b'a=nav%3Aupdate').decode('cp437');self.assertIn('Versión instalada: 1.4.4',out);self.assertIn('B\tupdate.run\tInstalar la 1.4.5 y reiniciar',out)
   self.assertIn('Instalar la 1.4.5',app.page().decode())
   rel.write_text('j1-open-vpn 1.4.5 (Alpine 3.24.4)\n');app.update_look();self.assertIn('Tienes la última versión (1.4.5)',app.UPD['state'])
   self.assertRaises(ValueError,app.update_start)
  self.assertEqual(app.vtuple('1.10.0')>app.vtuple('1.9.9'),True)
  self.assertIn('B\tnav:update\tActualizar',app.ui_request(b'a=nav%3Asys').decode('cp437'))
  app.UPD.update(state='',busy=False,latest=None)
 def test_boot_kernel_compare(self):
  def img(k,r):
   h=bytearray(2048);h[:8]=b'ANDROID!';app.struct.pack_into('<8I',h,8,len(k),0,len(r),0,0,0,0,2048)
   return bytes(h)+k+bytes(-len(k)%2048)+r
  self.assertEqual(app.boot_kernel(img(b'K'*5000,b'R1')),app.boot_kernel(img(b'K'*5000,b'R2')))   # ramdisk ignored
  self.assertNotEqual(app.boot_kernel(img(b'K'*5000,b'R')),app.boot_kernel(img(b'J'*5000,b'R')))
  self.assertIsNone(app.boot_kernel(b'garbage'))
 def test_https_redirect_and_fingerprint(self):
  self.assertEqual(app.https_fingerprint(),'');self.vpn0()
  app.panel_set(https=True);self.assertTrue(app.panel_conf()['https'])
  class H:pass
  h=H();h.headers={'Host':'192.168.78.1:80'};h.connection=type('C',(),{'getsockname':lambda s:('192.168.77.1',80)})()
  sent=[];h.send_response=lambda c:sent.append(c);h.send_header=lambda k,v:sent.append((k,v));h.end_headers=lambda:None
  self.assertTrue(app.Handler.to_https(h));self.assertIn(('Location','https://192.168.78.1/'),sent)
  sent.clear();h.headers={'Host':'evil.com\r\nX: y'};app.Handler.to_https(h);self.assertIn(('Location','https://192.168.77.1/'),sent)
  app.panel_set(https=False);self.assertFalse(app.Handler.to_https(h))
  out=app.ui_request(b'a=nav%3Apanel').decode('cp437');self.assertIn('S\tpanel.https:1\tCifrado HTTPS\t0',out)
  self.assertIn('id=https',app.page().decode())
 @unittest.skipUnless(__import__('shutil').which('openssl'),'sin openssl')
 def test_https_certificate(self):
  app.https_cert();pem=(app.STATE/'https.pem').read_text();self.assertIn('PRIVATE KEY',pem);self.assertIn('CERTIFICATE',pem)
  self.assertRegex(app.https_fingerprint(),r'^([0-9A-F]{2}:){31}[0-9A-F]{2}$');self.assertEqual(list(app.RUN.glob('https-*')),[])
  import ssl;ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(app.cert_path())
 def test_notify_token(self):
  app.notify_save(token='tk_'+'a'*29);self.assertEqual(app.notify_conf()['token'],'tk_'+'a'*29)
  app.notify_save(token='');self.assertEqual(app.notify_conf()['token'],'tk_'+'a'*29)   # empty keeps it
  self.assertRaises(ValueError,app.notify_save,token='secret')
  self.vpn0();s=app.page().decode();self.assertNotIn('tk_'+'a'*29,s);self.assertIn('Guardado; vacío',s)
  seen={}
  class R:
   def __enter__(s):return s
   def __exit__(s,*a):pass
   def read(s,n):return b''
  def op(req,timeout):seen['auth']=req.get_header('Authorization');return R()
  with patch.object(app.urllib.request,'urlopen',side_effect=op):app.notify_send('t','x')
  self.assertEqual(seen['auth'],'Bearer tk_'+'a'*29)
  app.notify_save(token='-');self.assertNotIn('token',app.notify_conf())
 def test_notify_topic_typed(self):
  old=app.notify_conf()['topic']
  for bad in ('mi-tema','j1-con espacio','j1-'+'x'*62,'j1-ñ'):self.assertRaises(ValueError,app.notify_save,topic=bad)
  self.assertRaisesRegex(ValueError,'difícil de adivinar',app.notify_save,topic='j1-casa')   # public server, no token
  self.assertEqual(app.notify_conf()['topic'],old)
  app.notify_save(topic='j1-'+'k'*16);self.assertEqual(app.notify_conf()['topic'],'j1-'+'k'*16)
  app.notify_save(token='tk_'+'a'*29,topic='j1-casa');self.assertEqual(app.notify_conf()['topic'],'j1-casa')   # own server with token
  app.notify_save(topic='');self.assertEqual(app.notify_conf()['topic'],'j1-casa')   # empty keeps it
  self.vpn0();self.assertIn('name=topic value="j1-casa"',app.page().decode())
  with patch.object(app,'qr_rows',return_value=['1']):
   out=app.ui_request(b'a=notify.topicset&s=notify&f_topic=j1-salon').decode('cp437')
  self.assertIn('Tema guardado',out);self.assertIn('F	topic	Tema (empieza por j1-)	j1-salon',out);self.assertEqual(app.notify_conf()['topic'],'j1-salon')
 def test_ssh_network_rules(self):
  import ipaddress
  nets=[ipaddress.ip_interface('192.168.1.40/24'),ipaddress.ip_interface('192.168.1.41/24'),ipaddress.ip_interface('192.168.1.40/32')]
  self.assertEqual(app.ssh_conf(),{'enabled':True,'lan':False,'vpn':False})
  r=app.ssh_rules(app.ssh_conf(),nets);self.assertEqual(r[1],['-i','rndis0','-j','ACCEPT']);self.assertEqual(r[-1],['-j','DROP']);self.assertEqual(len(r),3)
  with patch.object(app,'apply_vpn'):
   out=app.ui_request(b'a=ssh.lan%3A1&s=panel').decode('cp437')
  self.assertIn('SSH desde la red local activado',out);self.assertIn('S\tssh.lan:0\tDesde la red local\t1',out)
  r=app.ssh_rules(app.ssh_conf(),nets)
  self.assertIn(['!','-i','wg0','-s','192.168.1.0/24','-j','ACCEPT'],r);self.assertEqual(len(r),4)   # one rule per network
  with patch.object(app,'apply_vpn'):app.ui_request(b'a=ssh.vpn%3A1&s=panel');app.ui_request(b'a=ssh.lan%3A0&s=panel')
  self.assertEqual(app.ssh_conf(),{'enabled':True,'lan':False,'vpn':True});self.assertIn(['-i','wg0','-s','10.66.0.0/24','-j','ACCEPT'],app.ssh_rules(app.ssh_conf(),nets))
  self.assertIn(b'\te\n',app.ui_request(b'a=ssh.lan%3A5&s=panel'))
  # firewall(): one NAT rule for any link but the tunnel, SSH chain rebuilt
  calls=[]
  class P:returncode=0
  def run(args,**k):calls.append(args[3:]);return P()
  with patch.object(app.subprocess,'run',run),patch.object(app,'command',return_value='default via 192.168.1.1 dev eth0'),patch.object(app,'Path') as path:
   self.assertTrue(app.firewall())
  self.assertIn(['-t','nat','-A','J1_NAT','-s','10.66.0.0/24','!','-o','wg0','-j','MASQUERADE'],calls)
  self.assertIn(['-A','J1_SSH','-i','wg0','-s','10.66.0.0/24','-j','ACCEPT'],calls);self.assertEqual(calls[-1],['-A','J1_SSH','-j','DROP'])
  self.vpn0()
  with patch.object(app,'lan_ips',return_value=['192.168.1.40']):self.assertIn('root@10.66.0.1</code> (VPN)',app.ssh_section())
 def test_watch_settings_screen_and_form(self):
  c=app.watch_conf();self.assertEqual((c['vpn'],c['net'],c['reboot'],c['min'],c['sched'],c['hour']),(True,True,True,10,0,4))
  out=app.ui_request(b'a=watch.min&s=watch').decode('cp437');self.assertIn('Sin Internet 15 min',out)
  app.ui_request(b'a=watch.reboot%3A0&s=watch');self.assertFalse(app.watch_conf()['reboot'])
  out=app.ui_request(b'a=watch.sched&s=watch').decode('cp437');self.assertIn('Cada día',out);self.assertIn('F\thour',out)
  self.assertIn('Hora guardada',app.ui_request(b'a=watch.hour&s=watch&f_hour=5').decode('cp437'));self.assertEqual(app.watch_conf()['hour'],5)
  self.assertIn(b'\te\n',app.ui_request(b'a=watch.hour&s=watch&f_hour=24'));self.assertIn(b'\te\n',app.ui_request(b'a=watch.vpn%3A2&s=watch'))
  self.assertRaises(ValueError,app.watch_save,min=7)
  self.vpn0();page=app.page().decode();self.assertIn('id=vigilantes',page);self.assertIn('href="#vigilantes"',page)
  self.assertIn('Vigilantes y reinicio',app.ui_request(b'a=nav:sys&s=sys').decode('cp437'))
 def test_net_watch_restarts_then_reboots_once(self):
  c=app.watch_conf();t=[1000.0];acts=[]
  with patch.object(app,'internet_ok',return_value=False),patch.object(app.time,'monotonic',lambda:t[0]),\
       patch.object(app,'net_configured',return_value=True),patch.object(app,'net_restart',lambda:acts.append('red')),\
       patch.object(app,'reboot_soon',lambda:acts.append('reinicio')),patch.object(app,'uptime',return_value=7200),patch.object(app,'notify'):
   app.net_watch(c);t[0]+=599;app.net_watch(c);self.assertEqual(acts,[])
   t[0]+=1;app.net_watch(c);self.assertEqual(acts,['red'])
   t[0]+=599;app.net_watch(c);self.assertEqual(acts,['red'])
   t[0]+=1;app.net_watch(app.watch_conf());self.assertEqual(acts,['red','reinicio'])
   self.assertIn('min sin Internet',app.load('watch.json',{})['note'])
   # restarted panel, same 6 h: no second reboot
   app.WSTATE.update(net_bad=None,net_step=0);t[0]+=10;app.net_watch(app.watch_conf());t[0]+=1300;app.net_watch(app.watch_conf());t[0]+=60;app.net_watch(app.watch_conf())
   self.assertEqual(acts,['red','reinicio','red'])
  with patch.object(app,'internet_ok',return_value=True),patch.object(app.time,'monotonic',lambda:t[0]),patch.object(app,'notify') as n:
   app.net_watch(c);self.assertEqual(app.WSTATE['net_step'],0);self.assertIn('Internet ha vuelto',app.WSTATE['last']);n.assert_called_once()
 def test_net_watch_waits_for_a_network(self):
  t=[0.0];acts=[]
  with patch.object(app,'internet_ok',return_value=False),patch.object(app.time,'monotonic',lambda:t[0]),\
       patch.object(app,'net_configured',return_value=False),patch.object(app,'net_restart',lambda:acts.append('red')):
   for _ in range(30):t[0]+=60;app.net_watch(app.watch_conf())
  self.assertEqual(acts,[])   # first setup: no Wi-Fi, no cable, never had Internet
 def test_vpn_watch_repairs_and_tells_once(self):
  seq=['no responde',None];calls=[]
  with patch.object(app,'vpn_problem',side_effect=lambda:seq.pop(0) if seq else None),patch.object(app,'apply_vpn',lambda:calls.append('apply')),\
       patch.object(app,'notify') as n,patch.object(app.subprocess,'run') as run:
   app.vpn_watch()
  self.assertEqual(calls,['apply']);run.assert_not_called();self.assertIn('reiniciado',app.WSTATE['last']);n.assert_called_once()
  with patch.object(app,'vpn_problem',return_value='no responde'),patch.object(app,'apply_vpn'),patch.object(app,'notify') as n,patch.object(app.subprocess,'run') as run:
   app.vpn_watch();app.vpn_watch()
  self.assertEqual(n.call_count,1);self.assertEqual(run.call_args.args[0],['ip','link','del','wg0'])
 def test_vpn_problem(self):
  app.save('vpn.json',{'port':51820,'endpoint':'','private_key':'K','public_key':'P','clients':[{'id':'a','ip':2,'public_key':'A','psk':'x'},{'id':'b','ip':3,'public_key':'B','psk':'y','paused':True}]})
  d=pathlib.Path(self.tmp.name)/'wg0';d.mkdir();(d/'flags').write_text('0x1091\n')
  real=app.Path
  with patch.object(app,'Path',lambda x,*a:d if x=='/sys/class/net/wg0' else real(x,*a)):
   with patch.object(app,'command',return_value='K\tP\t51820\toff\nA\tpsk\t1.2.3.4:5\t10.66.0.2/32\t0\t0\t0\toff'):self.assertIsNone(app.vpn_problem())
   with patch.object(app,'command',return_value='K\tP\t53\toff\nA\tpsk\t1.2.3.4:5\t10.66.0.2/32\t0\t0\t0\toff'):self.assertEqual(app.vpn_problem(),'puerto distinto')
   with patch.object(app,'command',return_value='K\tP\t51820\toff'):self.assertEqual(app.vpn_problem(),'clientes distintos')
   with patch.object(app,'command',side_effect=app.subprocess.TimeoutExpired('wg',5)):self.assertEqual(app.vpn_problem(),'no responde')
   (d/'flags').write_text('0x1090\n');self.assertEqual(app.vpn_problem(),'interfaz parada')
 def test_sched_reboot(self):
  app.watch_save(sched=7,hour=4);acts=[]
  sunday=app.time.struct_time((2026,11,15,4,3,0,6,319,0));monday=app.time.struct_time((2026,11,16,4,3,0,0,320,0))
  with patch.object(app,'reboot_soon',lambda:acts.append(1)),patch.object(app.time,'time',return_value=1.8e9):
   with patch.object(app.time,'localtime',return_value=monday),patch.object(app,'uptime',return_value=90000):app.sched_watch(app.watch_conf())
   self.assertEqual(acts,[])
   with patch.object(app.time,'localtime',return_value=sunday),patch.object(app,'uptime',return_value=600):app.sched_watch(app.watch_conf())
   self.assertEqual(acts,[])   # just rebooted
   with patch.object(app.time,'localtime',return_value=sunday),patch.object(app,'uptime',return_value=90000):app.sched_watch(app.watch_conf())
   self.assertEqual(acts,[1]);self.assertEqual(app.load('watch.json',{})['note'],'reinicio programado')
 def test_apply_unchanged_skips_iptables(self):
  calls=[]
  def run(cmd,**k):calls.append(cmd);return type('R',(),{'returncode':0})()
  with patch.object(app.subprocess,'run',side_effect=run),patch.object(app,'command',return_value='default via 10.0.0.1 dev eth0'),patch.object(app,'Path'):
   app.firewall();n=len(calls);self.assertGreater(n,5)
   app.firewall();self.assertEqual(len(calls),n)   # same rules: nothing run
   app.APPLIED['fw_at']-=app.REAPPLY+1;app.firewall();self.assertEqual(len(calls),2*n)   # written again after 5 min
 def test_ssh_screen_master_switch(self):
  self.assertIn('Acceso SSH',app.ui_request(b'a=nav:sys&s=sys').decode('cp437'))
  with patch.object(app,'lan_ips',return_value=['192.168.1.40']),patch.object(app,'apply_vpn'):
   out=app.ui_request(b'a=ssh.lan%3A1&s=ssh').decode('cp437')
   self.assertIn('T	ssh	Acceso SSH',out);self.assertIn('Red local: root@192.168.1.40',out);self.assertIn('Ninguna clave autorizada',out)
   out=app.ui_request(b'a=ssh.on%3A0&s=ssh').decode('cp437')
  self.assertIn('SSH desactivado',out);self.assertNotIn('ssh.lan',out);self.assertIn('S	ssh.on:1	SSH	0',out)
  self.assertEqual(app.ssh_rules(app.ssh_conf(),[]),[['-m','conntrack','--ctstate','ESTABLISHED,RELATED','-j','ACCEPT'],['-j','DROP']])
  self.assertTrue(app.ssh_conf()['lan'])   # kept for when it is switched on again
  self.vpn0();self.assertIn('Ahora desactivado',app.ssh_section())
  with patch.object(app,'apply_vpn'):app.ui_request(b'a=ssh.on%3A1&s=ssh')
  self.assertIn(['-i','rndis0','-j','ACCEPT'],app.ssh_rules(app.ssh_conf(),[]))
 def test_usb_ycable_option(self):
  params=pathlib.Path(self.tmp.name)/'params';params.mkdir();(params/'j1_boost').write_text('1\n')
  with patch.object(app,'USB_PARAMS',params):
   self.assertFalse(app.usb_ycable());self.assertIn('name=ycable value=1>',app.usb_section())
   out=app.ui_request(b'a=usb.y%3A1&s=usb').decode('cp437')
   self.assertIn('Cable en Y activado',out);self.assertIn('S\tusb.y:0\tCable en Y siempre conectado\t1',out)
   self.assertTrue((app.STATE/'usb-ycable').exists());self.assertIn('name=ycable value=1 checked',app.usb_section())
   app.usb_set(True,False);self.assertFalse((app.STATE/'usb-ycable').exists());self.assertEqual(app.load('usb.json',{}),{'boost':True,'ycable':False})
   self.assertEqual((params/'j1_boost').read_text(),'1\n')
   self.assertIn(b'\te\n',app.ui_request(b'a=usb.y%3A7&s=usb'))
if __name__=='__main__':unittest.main(verbosity=2)
