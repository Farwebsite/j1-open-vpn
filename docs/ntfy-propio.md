# Servidor de avisos propio (ntfy)

Por defecto, los avisos del J1 pasan por el servidor público `ntfy.sh` en un tema secreto. Es cómodo, pero:

- quien conozca el tema puede **leer** los avisos y **mandarte avisos falsos**;
- el servidor los ve en claro, porque ntfy no cifra de extremo a extremo.

Con un servidor ntfy propio y cerrado, solo el J1 puede publicar (con un token) y solo tu móvil puede leer (con usuario y contraseña). El J1 nunca recibe nada del servidor: solo envía.

## Cómo queda

```
J1 --HTTPS + token (solo publicar)--> Cloudflare (proxy) --HTTPS--> tu máquina: ntfy
móvil <--HTTPS + usuario (solo leer)-- Cloudflare (proxy) <------------'
```

- **Cerrado por defecto** (`deny-all`): sin token o usuario no se puede leer ni publicar.
- **Nombre fuera de los registros públicos:** se usa el certificado de origen de Cloudflare, no uno de Let's Encrypt, así que el nombre no aparece en los registros públicos de certificados. Aun así, elige un subdominio poco evidente.
- **IP oculta:** la máquina queda detrás de Cloudflare y su cortafuegos solo acepta el puerto de ntfy desde Cloudflare.

Se necesita:

- una máquina Ubuntu 22.04/24.04 con IP pública (la capa gratuita de Oracle Cloud basta);
- un dominio gestionado en Cloudflare.

## Pasos

1. **Máquina:** Ubuntu con tu clave SSH.
   - En Oracle Cloud: *Compute → Instances → Create instance*, forma «Always Free».
   - Abre el puerto **TCP 8443** en el cortafuegos del proveedor. En Oracle: *Networking → Virtual Cloud Networks → Security Lists → Add Ingress Rule*, origen `0.0.0.0/0`.
2. **DNS en Cloudflare:** registro `A` con un nombre poco evidente y la IP de la máquina, en modo **Proxied (nube naranja)**.
3. **Certificado de origen:**
   - Cloudflare → *SSL/TLS → Origin Server → Create Certificate*, solo para ese nombre.
   - En la máquina, guarda el certificado en `/root/origin.pem` y la clave en `/root/origin.key`.
   - Cloudflare → *Rules → Configuration Rules*: para ese nombre de host, **SSL: Full (strict)**. Así no cambias el resto del dominio.
4. **Instalar:** copia [`tools/ntfy-servidor.sh`](../tools/ntfy-servidor.sh) a la máquina, léelo y ejecútalo:
   ```
   sudo bash ntfy-servidor.sh avisos.example.com
   ```
   - Usa el puerto **8443**, así no choca con otra web en el 443. Otro puerto como segundo dato: 2053, 2083, 2087, 2096 o 443.
   - Instala ntfy desde su repositorio oficial y lo deja cerrado (sin web, sin registro, sin adjuntos).
   - Crea un token **solo para publicar** (el J1) y un usuario `movil` **solo para leer**, para los temas `j1-*`.
   - Limita el puerto a las IPs de Cloudflare.
   - Al final muestra el token y la contraseña **una sola vez**. Cópialos y no los pegues en ningún chat.
5. **J1:** panel web → *Avisos al móvil*.
   - Servidor: `https://avisos.example.com:8443`, **con el puerto**.
   - Token de acceso: el `tk_...`.
   - *Guardar avisos* → *Enviar aviso de prueba*.
   - El token no se vuelve a mostrar: el campo vacío lo conserva y `-` lo quita.
6. **Móvil:** app ntfy.
   - *Ajustes → Gestionar usuarios → Añadir*: el servidor, el usuario `movil` y su contraseña.
   - *+ Suscribirse*: marca «usar otro servidor», pon el tuyo y el tema que muestra el J1 (`j1-...`, también como QR en la pantalla *Avisos*).
   - Con un servidor propio la app mantiene su propia conexión y no usa los servicios de Google.

## Comprobar que está cerrado

Sin credenciales:

```
curl -s -o /dev/null -w "%{http_code}\n" -d prueba https://avisos.example.com:8443/j1-x
curl -s -o /dev/null -w "%{http_code}\n" "https://avisos.example.com:8443/j1-x/json?poll=1"
curl -m 5 -k https://IP-DE-LA-MAQUINA:8443
```

- Las dos primeras deben dar **403**.
- La tercera debe agotar el tiempo: solo entra Cloudflare.
- La dirección sin puerto (`https://avisos.example.com`) puede dar un error de Cloudflare (por ejemplo 525) si en el 443 de la máquina hay otra web: es normal, usa siempre `:8443`.

## Mantenimiento

- **ntfy** se actualiza con `sudo apt update && sudo apt upgrade`.
- **Accesos nuevos:** vuelve a ejecutar el script. Anula el token y la contraseña anteriores y crea otros; luego cámbialos en el J1 y en el móvil.
- **Limpieza:** borra `/root/origin.key` cuando acabes, porque ntfy usa su copia en `/etc/ntfy/tls/`. Y haz una copia de seguridad nueva del J1: el token va dentro, cifrado.
