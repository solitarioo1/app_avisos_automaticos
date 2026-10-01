"""
CONFIG/imagenes.py - Validación/saneamiento de fotos subidas por usuarios
(agricultor sin login en /siniestro/reportar, e internos en /clasificar-cliente)
y extracción de su GPS/EXIF. Compartido entre ambos flujos para no duplicar
la defensa contra archivos maliciosos.
"""
import logging
import os
import re
from io import BytesIO

from PIL import Image, ExifTags

logger = logging.getLogger(__name__)

MAX_MEGAPIXELES = 50_000_000  # cubre fotos de celular de sobra; frena "bombas" de descompresión
FORMATOS_PERMITIDOS = {'JPEG', 'PNG', 'WEBP', 'HEIF'}

# OCR de respaldo: el formato del texto con la ubicación varía MUCHO según
# cómo llegó la foto — apps tipo "GPS Map Camera" ("Lat -15.44° Long -74.64°"),
# una captura de Google Maps (par decimal "-15.71857,-70.820965" en la barra
# de búsqueda, O grados/minutos/segundos "15°43'06.8"S 70°49'15.5"W" en el
# panel), etc. Se prueban varios patrones en orden, el primero que matchee gana.
_PATRONES_COORD = [
    # "Lat X° Long Y°" (GPS Map Camera y similares)
    re.compile(r'Lat[^\d\-]*(-?\d{1,2}\.\d{3,8})[^\d\-]*Long[^\d\-]*(-?\d{1,3}\.\d{3,8})', re.IGNORECASE),
    # Par decimal suelto "-15.718570,-70.820965" (ej. barra de busqueda de Maps)
    re.compile(r'(-\d{1,2}\.\d{4,8})\s*,\s*(-\d{2,3}\.\d{4,8})'),
]
# Grados/minutos/segundos con referencia cardinal (15°43'06.8"S / 70°49'15.5"W)
# — lat y lon se buscan POR SEPARADO (no una sola regex con las dos juntas):
# en capturas de Google Maps suelen quedar en líneas distintas con íconos/
# basura de OCR entre medio, una regex combinada con salto de línea no pega.
_REGEX_DMS_LAT = re.compile(r"(\d{1,2})\D{1,3}(\d{1,2})\D{1,3}(\d{1,2}(?:\.\d+)?)\D{0,2}([NS])")
_REGEX_DMS_LON = re.compile(r"(\d{1,3})\D{1,3}(\d{1,2})\D{1,3}(\d{1,2}(?:\.\d+)?)\D{0,2}([EW])")


def _dms_texto_a_decimal(grados, minutos, segundos, ref):
    decimal = float(grados) + float(minutos) / 60 + float(segundos) / 3600
    if ref.upper() in ('S', 'W'):
        decimal = -decimal
    return decimal
_TESSERACT_CMD_DEFAULT_WINDOWS = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
_TESSERACT_CMD = os.getenv('TESSERACT_CMD') or (
    _TESSERACT_CMD_DEFAULT_WINDOWS if os.name == 'nt' and os.path.exists(_TESSERACT_CMD_DEFAULT_WINDOWS) else ''
)
_ocr_disponible = None  # None = sin probar todavia; True/False luego de la 1ra foto


class FotoInvalida(Exception):
    pass


def _dms_a_decimal(valor_dms, referencia):
    """Convierte (grados, minutos, segundos) del EXIF a grados decimales."""
    grados, minutos, segundos = valor_dms
    decimal = float(grados) + float(minutos) / 60 + float(segundos) / 3600
    if referencia in ('S', 'W'):
        decimal = -decimal
    return decimal


def _leer_gps_de_exif(img):
    """Lee el GPS del EXIF ya abierto. Devuelve (lat, lon) o (None, None)."""
    exif = img.getexif()
    if not exif:
        return None, None
    gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
    if not gps_ifd:
        return None, None
    lat_dms = gps_ifd.get(2)
    lat_ref = gps_ifd.get(1)
    lon_dms = gps_ifd.get(4)
    lon_ref = gps_ifd.get(3)
    if not (lat_dms and lat_ref and lon_dms and lon_ref):
        return None, None
    lat = _dms_a_decimal(lat_dms, lat_ref)
    lon = _dms_a_decimal(lon_dms, lon_ref)
    return round(lat, 6), round(lon, 6)


def _leer_gps_de_ocr(img):
    """Respaldo cuando no hay EXIF: busca el texto tipo 'Lat -15.44° Long
    -74.64°' que apps como GPS Map Camera queman en la imagen. Formato de
    foto variable (distintas apps, distintas posiciones/fuentes) — por eso
    se corre OCR sobre la imagen COMPLETA en vez de recortar una zona fija."""
    global _ocr_disponible
    if _ocr_disponible is False:
        return None, None
    try:
        import pytesseract
        if _TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = _TESSERACT_CMD
        texto = pytesseract.image_to_string(img)
        _ocr_disponible = True
    except Exception as e:
        _ocr_disponible = False
        logger.warning('OCR no disponible (Tesseract no instalado/configurado): %s', str(e))
        return None, None

    lat = lon = None
    for patron in _PATRONES_COORD:
        m = patron.search(texto)
        if not m:
            continue
        try:
            lat, lon = float(m.group(1)), float(m.group(2))
        except ValueError:
            lat = lon = None
            continue
        if -19.5 <= lat <= 0.5 and -82.0 <= lon <= -68.0:  # dentro de Perú
            break
        lat = lon = None

    if lat is None:
        # Respaldo: DMS con lat/lon buscados por separado (no en una sola regex).
        m_lat = _REGEX_DMS_LAT.search(texto)
        m_lon = _REGEX_DMS_LON.search(texto)
        if m_lat and m_lon:
            try:
                lat_c = _dms_texto_a_decimal(*m_lat.groups())
                lon_c = _dms_texto_a_decimal(*m_lon.groups())
                if -19.5 <= lat_c <= 0.5 and -82.0 <= lon_c <= -68.0:
                    lat, lon = lat_c, lon_c
            except (ValueError, TypeError):
                pass

    if lat is None:
        return None, None
    return round(lat, 6), round(lon, 6)


def validar_y_sanear(archivo_bytes, filename):
    """Defensa contra archivos maliciosos subidos como "foto": no basta con
    confiar en la extensión/content-type que manda el navegador (eso lo arma
    quien suba el archivo).

    1. Verifica que sea realmente una imagen decodificable (PIL.verify()) —
       descarta ejecutables, scripts, PDFs, polyglots, etc. disfrazados de .jpg.
    2. Rechaza formatos fuera de la lista blanca (nada de SVG/GIF/TIFF, que
       tienen historial de vulnerabilidades de parser o script embebido).
    3. Limita las dimensiones para frenar "bombas de descompresión" (archivo
       chico que se infla a gigas de RAM al decodificar).
    4. Re-codifica la imagen DESDE CERO (abre los píxeles reales y los vuelve
       a guardar como JPEG limpio) — cualquier payload escondido en bytes que
       no son píxeles de verdad se descarta acá.

    Devuelve (contenido_limpio_bytes, lat, lon). Lanza FotoInvalida si no pasa.
    """
    try:
        img = Image.open(BytesIO(archivo_bytes))
        img.verify()
    except Exception:
        raise FotoInvalida(f'{filename}: el archivo no es una imagen válida')

    try:
        # verify() deja la imagen inutilizable para seguir leyendo — reabrir.
        img = Image.open(BytesIO(archivo_bytes))
        formato = (img.format or '').upper()
        if formato not in FORMATOS_PERMITIDOS:
            raise FotoInvalida(f'{filename}: formato "{formato}" no permitido (solo fotos JPEG/PNG/WEBP/HEIC)')

        ancho, alto = img.size
        if ancho * alto > MAX_MEGAPIXELES:
            raise FotoInvalida(f'{filename}: imagen demasiado grande ({ancho}x{alto})')
        if ancho < 50 or alto < 50:
            raise FotoInvalida(f'{filename}: imagen demasiado pequeña, parece no ser una foto real')

        lat, lon = _leer_gps_de_exif(img)
        origen = 'exif'
        if lat is None:
            # Sin EXIF (típico de fotos reenviadas por WhatsApp) — intentar
            # leer el watermark de ubicación con OCR antes de rechazar.
            lat, lon = _leer_gps_de_ocr(img)
            origen = 'ocr' if lat is not None else None
        if lat is not None:
            logger.info('Ubicación de %s obtenida por %s: %s, %s', filename, origen, lat, lon)

        # Re-codificar: solo se guarda/envía el píxel real, nunca los bytes
        # originales de quien subió el archivo.
        limpio = img.convert('RGB')
        buf = BytesIO()
        limpio.save(buf, format='JPEG', quality=90)
        return buf.getvalue(), lat, lon
    except FotoInvalida:
        raise
    except Image.DecompressionBombError:
        raise FotoInvalida(f'{filename}: imagen sospechosa (demasiado grande al descomprimir)')
    except Exception as e:
        logger.warning('Foto rechazada (%s): %s', filename, str(e))
        raise FotoInvalida(f'{filename}: no se pudo procesar la imagen')
