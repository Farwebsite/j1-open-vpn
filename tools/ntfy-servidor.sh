#!/bin/bash
# Servidor ntfy propio para los avisos del J1: cualquier máquina Ubuntu 22.04/24.04
# con IP pública (por ejemplo la capa gratuita de Oracle Cloud), detrás del proxy
# de Cloudflare. Guía: docs/ntfy-propio.md. Léelo antes de ejecutarlo.
#
#   sudo bash ntfy-servidor.sh nombre.tudominio.com [puerto]
#
# Puerto: 8443 por defecto (deja libre el 443 si la máquina ya tiene otra web).
# Tiene que ser uno de los HTTPS que Cloudflare pasa con el proxy: 443, 2053,
# 2083, 2087, 2096 u 8443. El J1 y el móvil usan https://nombre:puerto.
#
# Qué hace:
#  1. Instala ntfy desde su repositorio oficial (archive.ntfy.sh).
#  2. Lo configura cerrado: sin acceso anónimo, sin registro, sin web, sin adjuntos,
#     HTTPS en ese puerto con el certificado de origen de Cloudflare.
#  3. Crea dos accesos para los temas j1-*:
#       j1    -> solo publicar (token tk_..., para el panel del J1)
#       movil -> solo leer (usuario y contraseña, para la app ntfy)
#  4. Cortafuegos: ese puerto solo acepta conexiones de Cloudflare (nadie llega
#     directo a la IP de la máquina). El SSH (22) queda como estaba.
# Los secretos se muestran SOLO al final en esta terminal: no se guardan en
# ningún archivo aparte de la base de usuarios de ntfy.
set -euo pipefail
HOST=${1:-}
PORT=${2:-8443}
[ "$(id -u)" = 0 ] || { echo "Ejecútalo con sudo"; exit 1; }
case "$PORT" in 443|2053|2083|2087|2096|8443) ;; *) echo "Puerto no válido: usa 8443 (o 2053, 2083, 2087, 2096, 443)"; exit 1;; esac
# another program on that port (not an ntfy of an earlier run): choose another one
if ss -ltnpH "sport = :$PORT" 2>/dev/null | grep -v '"ntfy"' | grep -q .; then
  echo "El puerto $PORT ya lo usa otro programa:"; ss -ltnpH "sport = :$PORT"; echo "Elige otro, por ejemplo: sudo bash $0 $HOST 2053"; exit 1
fi
URL="https://$HOST"; [ "$PORT" = 443 ] || URL="$URL:$PORT"
[[ "$HOST" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$ ]] || { echo "Uso: sudo bash $0 nombre.tudominio.com"; exit 1; }
CERT=/root/origin.pem KEY=/root/origin.key
[ -s "$CERT" ] && [ -s "$KEY" ] || { echo "Falta el certificado de origen de Cloudflare en $CERT y $KEY (docs/ntfy-propio.md, paso 3)"; exit 1; }
grep -q 'BEGIN CERTIFICATE' "$CERT" && grep -q 'PRIVATE KEY' "$KEY" || { echo "$CERT o $KEY no tienen el formato PEM esperado"; exit 1; }

echo "== Paquetes"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q curl gnupg openssl iptables netfilter-persistent iptables-persistent
install -d -m 755 /etc/apt/keyrings
curl -fsSL https://archive.ntfy.sh/apt/keyring.gpg -o /tmp/ntfy-keyring
# the key may come armored or binary: apt wants it binary
if grep -q 'BEGIN PGP' /tmp/ntfy-keyring; then gpg --dearmor </tmp/ntfy-keyring >/etc/apt/keyrings/archive.ntfy.sh.gpg
else install -m 644 /tmp/ntfy-keyring /etc/apt/keyrings/archive.ntfy.sh.gpg; fi
rm -f /tmp/ntfy-keyring
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/archive.ntfy.sh.gpg] https://archive.ntfy.sh/apt stable main" >/etc/apt/sources.list.d/archive.ntfy.sh.list
apt-get update -q
apt-get install -y -q ntfy
id ntfy >/dev/null 2>&1 || { echo "El paquete ntfy no creó su usuario"; exit 1; }

echo "== Configuración"
install -d -m 750 -o root -g ntfy /etc/ntfy/tls
install -m 640 -o root -g ntfy "$CERT" /etc/ntfy/tls/origin.pem
install -m 640 -o root -g ntfy "$KEY" /etc/ntfy/tls/origin.key
install -d -m 750 -o ntfy -g ntfy /var/lib/ntfy
cat >/etc/ntfy/server.yml <<EOF
# Servidor privado de avisos del J1 (instalar-ntfy.sh)
base-url: "$URL"
listen-http: "127.0.0.1:2586"
listen-https: ":$PORT"
cert-file: /etc/ntfy/tls/origin.pem
key-file: /etc/ntfy/tls/origin.key
behind-proxy: true
auth-file: /var/lib/ntfy/user.db
auth-default-access: deny-all
cache-file: /var/lib/ntfy/cache.db
cache-duration: "24h"
enable-signup: false
enable-login: false
enable-reservations: false
web-root: disable
EOF
chmod 644 /etc/ntfy/server.yml
# ports below 1024 (443) as the ntfy user
install -d /etc/systemd/system/ntfy.service.d
printf '[Service]\nAmbientCapabilities=CAP_NET_BIND_SERVICE\n' >/etc/systemd/system/ntfy.service.d/puerto.conf
systemctl daemon-reload
systemctl enable ntfy >/dev/null
systemctl restart ntfy
sleep 3
systemctl is-active --quiet ntfy || { journalctl -u ntfy -n 30 --no-pager; echo "ntfy no arranca"; exit 1; }

echo "== Accesos"
# runuser keeps the environment (sudo would drop NTFY_PASSWORD and ntfy would
# ask for it); no terminal input, so nothing can stop to ask anything
nt() { runuser -u ntfy -- env NTFY_AUTH_FILE=/var/lib/ntfy/user.db ntfy "$@" </dev/null; }
J1PW=$(openssl rand -hex 24)
MOVPW=$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 20)
nt user del j1 >/dev/null 2>&1 || true
nt user del movil >/dev/null 2>&1 || true
NTFY_PASSWORD="$J1PW" nt user add j1 >/dev/null
NTFY_PASSWORD="$MOVPW" nt user add movil >/dev/null
nt access j1 'j1-*' write-only >/dev/null
nt access movil 'j1-*' read-only >/dev/null
TOKEN=$(nt token add j1 2>&1 | grep -o 'tk_[A-Za-z0-9]*' | head -1)
[ -n "$TOKEN" ] || { echo "No se pudo crear el token del J1"; exit 1; }
unset J1PW

echo "== Cortafuegos: $PORT solo desde Cloudflare"
iptables -N J1_CF 2>/dev/null || iptables -F J1_CF
n=0
for r in $(curl -fsSL https://www.cloudflare.com/ips-v4); do
  [[ "$r" =~ ^[0-9.]+/[0-9]+$ ]] || continue
  iptables -A J1_CF -s "$r" -p tcp --dport "$PORT" -j ACCEPT; n=$((n+1))
done
[ "$n" -gt 5 ] || { echo "No se pudo leer la lista de IPs de Cloudflare"; exit 1; }
# before Oracle's final REJECT rule (its images block everything but SSH)
if ! iptables -C INPUT -p tcp --dport "$PORT" -j J1_CF 2>/dev/null; then
  pos=$(iptables -L INPUT --line-numbers -n | awk '$2=="REJECT"{print $1; exit}')
  if [ -n "$pos" ]; then iptables -I INPUT "$pos" -p tcp --dport "$PORT" -j J1_CF
  else iptables -A INPUT -p tcp --dport "$PORT" -j J1_CF; fi
fi
netfilter-persistent save >/dev/null

cat <<EOF

================================================================
 Listo. Copia estos datos AHORA (no se vuelven a mostrar) y
 cierra la terminal después. No los pegues en ningún chat.

 Panel del J1 -> Avisos al móvil:
   Servidor:          $URL
   Token de acceso:   $TOKEN

 App ntfy del móvil -> Ajustes -> Usuarios -> Añadir:
   Servidor:          $URL
   Usuario:           movil
   Contraseña:        $MOVPW
================================================================
EOF
