# SPDX-License-Identifier: GPL-2.0
# J1 Open VPN - instalador para Windows (Heimdall).
# Uso: doble clic en instalar-windows.bat, o en PowerShell:
#   powershell -ExecutionPolicy Bypass -File instalar-windows.ps1
# Necesita en la misma carpeta: j1-open-vpn-boot.img, j1-open-vpn-rootfs.tar.gz, SHA256SUMS
# 'Continue': stderr of heimdall.exe must not stop Windows PowerShell 5.1;
# every step is checked explicitly
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Paso($t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan }
function Fallo($t) { Write-Host ""; Write-Host "ERROR: $t" -ForegroundColor Red; Read-Host "Pulsa Enter para salir"; exit 1 }
function Hash($f) { (Get-FileHash -Algorithm SHA256 $f).Hash.ToLower() }

Write-Host "J1 Open VPN - instalación en Samsung Galaxy J1 SM-J100H" -ForegroundColor Green
Write-Host "Se escribirán las particiones KERNEL y HIDDEN. Android dejará de arrancar"
Write-Host "(tus datos no se borran). Guía completa: docs/instalacion.md"

Paso "1/5 Comprobando los archivos descargados"
$files = 'j1-open-vpn-boot.img', 'j1-open-vpn-rootfs.tar.gz'
if (-not (Test-Path SHA256SUMS)) { Fallo "Falta SHA256SUMS en $here" }
$sums = @{}
foreach ($line in Get-Content SHA256SUMS) { $p = $line -split '\s+\*?'; if ($p.Count -ge 2) { $sums[$p[1]] = $p[0].ToLower() } }
foreach ($f in $files) {
  if (-not (Test-Path $f)) { Fallo "Falta $f en $here" }
  if ((Hash $f) -ne $sums[$f]) { Fallo "$f está dañado (la suma SHA-256 no coincide). Descárgalo otra vez." }
  Write-Host "  $f correcto"
}

Paso "2/5 Heimdall 1.4.2"
$hd = Join-Path $here 'heimdall'
$exe = Join-Path $hd 'heimdall.exe'
if (-not (Test-Path $exe)) {
  New-Item -ItemType Directory -Force $hd | Out-Null
  # versiones fijadas: el Heimdall 1.4.0 oficial falla con el J1
  $zips = @{
    'heimdall.windows.zip' = '0df75584145fab182a243331a7a00a840e453a5976e3d2741f3c90b4af2fab2a'
    'dlls.zip'             = 'ea23d62d6dad653aed5ef4d14a572ea3acd447a58a56997d1672bd6b7005770b'
  }
  foreach ($z in $zips.Keys) {
    $dest = Join-Path $hd $z
    Write-Host "  Descargando $z"
    try { Invoke-WebRequest -UseBasicParsing "https://github.com/amo13/Heimdall/releases/download/v1.4.2/$z" -OutFile $dest -ErrorAction Stop }
    catch { Fallo "No se pudo descargar $z. Comprueba la conexión a Internet." }
    if ((Hash $dest) -ne $zips[$z]) { Fallo "La descarga de $z no es la esperada" }
    try { Expand-Archive -Force $dest $hd -ErrorAction Stop } catch { Fallo "No se pudo descomprimir $z" }
    Remove-Item $dest
  }
}
if (-not (Test-Path $exe)) { Fallo "No se encontró heimdall.exe en $hd" }
Write-Host "  Heimdall listo en $hd"

Paso "3/5 Teléfono en modo Download"
Write-Host "  1. Apaga el J1 (batería cargada al menos al 50 %)."
Write-Host "  2. Mantén Volumen abajo + Home + Encendido hasta que salga un aviso."
Write-Host "  3. Pulsa Volumen arriba y conéctalo al PC con el cable USB."
while ($true) {
  Read-Host "  Pulsa Enter cuando esté en modo Download y conectado"
  $out = & $exe detect 2>&1 | Out-String
  if ($out -match 'Device detected') { Write-Host "  Teléfono detectado" -ForegroundColor Green; break }
  Write-Host ""
  Write-Host "  No se detecta. Si es la primera vez, falta el driver WinUSB:" -ForegroundColor Yellow
  Write-Host "   - Abre Zadig (https://zadig.akeo.ie), menú Options > List All Devices."
  Write-Host "   - Elige el dispositivo con USB ID 04E8 685D, driver WinUSB, 'Replace Driver'."
  Write-Host "  Después vuelve a pulsar Enter. (Ctrl+C para salir.)"
}

Paso "4/5 Confirmación"
Write-Host "  Se escribirá:"
Write-Host "    KERNEL  <- j1-open-vpn-boot.img"
Write-Host "    HIDDEN  <- j1-open-vpn-rootfs.tar.gz"
Write-Host "  No desconectes el cable mientras se escribe." -ForegroundColor Yellow
if ((Read-Host "  Escribe SI para continuar") -ne 'SI') { Write-Host "Cancelado: no se ha escrito nada."; exit 0 }

Paso "5/5 Flasheando (alrededor de 1 minuto)"
& $exe flash --KERNEL j1-open-vpn-boot.img --HIDDEN j1-open-vpn-rootfs.tar.gz
if ($LASTEXITCODE -ne 0) {
  Fallo "Heimdall terminó con error $LASTEXITCODE. Vuelve a poner el teléfono en modo Download y repite. Ver docs/recuperacion.md"
}

Write-Host ""
Write-Host "Listo." -ForegroundColor Green
Write-Host "El J1 se reinicia y se instala solo: la pantalla estará en negro unos 30 segundos."
Write-Host "Después muestra 'AP: DIRECT-J1-VPN-XXXX - Clave: ...': apunta la clave."
Write-Host "Siguiente paso: docs/instalacion.md, apartado 6 (conectarlo a tu Wi-Fi)."
Read-Host "Pulsa Enter para salir"
