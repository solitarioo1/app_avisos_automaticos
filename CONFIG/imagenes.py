"""
CONFIG/imagenes.py - Validación/saneamiento de fotos subidas por usuarios
(agricultor sin login en /siniestro/reportar, e internos en /clasificar-cliente)
y extracción de su GPS/EXIF. Compartido entre ambos flujos para no duplicar
la defensa contra archivos maliciosos.
"""
import base64
import logging
import os
import re
from io import BytesIO

import requests
from PIL import Image, ExifTags, ImageOps

logger = logging.getLogger(__name__)

N8N_WEBHOOK_OCR_IA = os.getenv('N8N_WEBHOOK_OCR_IA', '')

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
# Decimal con letra cardinal pegada, sin coma, par separado por espacio —
# formato real distinto del par con coma de Maps y del DMS (sin minutos/
# segundos): "12.1455S 76.8324W" (visto en fotos de siniestros reales con
# marca de agua tipo app de reporte de campo).
_REGEX_DECIMAL_LETRA = re.compile(
    r'(\d{1,2}\.\d{2,8})\s*([NS])\D{0,3}(\d{1,3}\.\d{2,8})\s*([EW])', re.IGNORECASE)

# Grados/minutos/segundos con referencia cardinal (15°43'06.8"S / 70°49'15.5"W)
# — lat y lon se buscan POR SEPARADO (no una sola regex con las dos juntas):
# en capturas de Google Maps suelen quedar en líneas distintas con íconos/
# basura de OCR entre medio, una regex combinada con salto de línea no pega.
_REGEX_DMS_LAT = re.compile(r"(\d{1,2})\D{1,3}(\d{1,2})\D{1,3}(\d{1,2}(?:\.\d+)?)\D{0,2}([NS])")
_REGEX_DMS_LON = re.compile(r"(\d{1,3})\D{1,3}(\d{1,2})\D{1,3}(\d{1,2}(?:\.\d+)?)\D{0,2}([EW])")

# UTM (otro SISTEMA de coordenadas, no solo otro formato de las mismas lat/lon
# — apps tipo GPS Map Camera a veces queman esto en vez de decimal/DMS, ej.
# "18L 0234567mE 8976543mN"). Perú cae en zonas 17-19 sur. Se convierte a
# WGS84 con pyproj (EPSG:327<zona> = UTM sur de esa zona), no se descarta.
_REGEX_UTM = re.compile(
    r'\b(1[789])\s*([A-Za-z])?\D{0,6}(\d{5,7})\s*m?E\D{1,6}(\d{6,8})\s*m?N\b', re.IGNORECASE)


def _utm_a_decimal(zona, easting, northing):
    from pyproj import Transformer
    transformer = Transformer.from_crs(f'EPSG:327{int(zona):02d}', 'EPSG:4326', always_xy=True)
    lon, lat = transformer.transform(float(easting), float(northing))
    return round(lat, 6), round(lon, 6)


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
_ocr_lang = None  # se detecta en el primer uso -- 'eng+spa' si el traineddata de
                   # español está instalado (Docker/prod lo trae), si no 'eng' solo
                   # (ej. instalación local de Windows sin el paquete spa).


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


def _umbral_otsu(img_gris):
    """Punto de corte óptimo para binarizar ESTA imagen en particular (método
    de Otsu: maximiza la separación entre las dos 'nubes' de brillo del
    histograma), en vez de un valor fijo. Hace falta porque un umbral fijo
    no generaliza: probado con 2 fotos reales, threshold=200 fijo lee
    perfecto un watermark blanco sobre fondo oscuro (cielo/rocas) pero deja
    el texto totalmente negro/invisible en otra con fondo más claro (tierra
    de chacra al sol) — y viceversa, un umbral más bajo sirve para la
    segunda pero no la primera. Sin numpy serían ~256 pasadas en Python
    puro por imagen; con numpy es instantáneo."""
    import numpy as np
    arr = np.asarray(img_gris, dtype=np.int64)
    hist, _ = np.histogram(arr, bins=256, range=(0, 256))
    total = arr.size
    suma_total = float(np.dot(np.arange(256), hist))
    peso_fondo = np.cumsum(hist).astype(np.float64)
    suma_fondo = np.cumsum(np.arange(256) * hist).astype(np.float64)
    peso_frente = total - peso_fondo
    with np.errstate(divide='ignore', invalid='ignore'):
        media_fondo = np.where(peso_fondo > 0, suma_fondo / peso_fondo, 0)
        media_frente = np.where(peso_frente > 0, (suma_total - suma_fondo) / peso_frente, 0)
        var_entre = peso_fondo * peso_frente * (media_fondo - media_frente) ** 2
    var_entre[(peso_fondo == 0) | (peso_frente == 0)] = -1  # umbrales inválidos (todo de un lado)
    return int(np.argmax(var_entre))


def _extraer_coordenada_de_texto(texto):
    """Prueba los 5 formatos conocidos de watermark GPS sobre un texto YA
    extraído por OCR, en orden. Separado de _leer_gps_de_ocr para poder
    probarlo contra el mismo texto con distintos preprocesados de imagen
    (ver _leer_gps_de_ocr) sin repetir esta cascada entera cada vez."""
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
        # Respaldo: decimal con letra cardinal pegada ("12.1455S 76.8324W"),
        # sin coma y sin grados/minutos/segundos — formato real distinto
        # de los dos anteriores.
        m = _REGEX_DECIMAL_LETRA.search(texto)
        if m:
            try:
                lat_c = float(m.group(1)) * (-1 if m.group(2).upper() == 'S' else 1)
                lon_c = float(m.group(3)) * (-1 if m.group(4).upper() == 'W' else 1)
                if -19.5 <= lat_c <= 0.5 and -82.0 <= lon_c <= -68.0:
                    lat, lon = lat_c, lon_c
            except (ValueError, TypeError):
                pass

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
        # Respaldo: UTM (otro sistema de coordenadas, no solo otro formato) —
        # se convierte, no se descarta como "ilegible".
        m_utm = _REGEX_UTM.search(texto)
        if m_utm:
            try:
                zona, _letra, easting, northing = m_utm.groups()
                lat_c, lon_c = _utm_a_decimal(zona, easting, northing)
                if -19.5 <= lat_c <= 0.5 and -82.0 <= lon_c <= -68.0:
                    lat, lon = lat_c, lon_c
            except (ValueError, TypeError, ImportError):
                pass

    if lat is None:
        return None, None
    return round(lat, 6), round(lon, 6)


def _leer_gps_de_ocr(img):
    """Respaldo cuando no hay EXIF: busca el texto tipo 'Lat -15.44° Long
    -74.64°' que apps como GPS Map Camera queman en la imagen. Formato de
    foto variable (distintas apps, distintas posiciones/fuentes) — por eso
    se corre OCR sobre la imagen COMPLETA en vez de recortar una zona fija.

    La imagen de celular real (12+ MP) se achica y se binariza (blanco/negro
    puro, no solo escala de grises) ANTES de correr Tesseract, con --psm 6
    (bloque de texto uniforme). El umbral es lo que de verdad importa, pero
    NINGÚN valor fijo generaliza a todas las apps/fondos — medido con 2
    fotos reales de siniestros: threshold=200 lee perfecto un watermark
    blanco sobre fondo oscuro (cielo/rocas) pero deja el texto invisible
    sobre un fondo más claro (tierra de chacra al sol); con Otsu (umbral
    automático por imagen) pasa lo inverso en algún caso puntual. Por eso se
    prueban los DOS en cascada -- 200 fijo primero (más barato, ya probado
    en la mayoría de fotos), Otsu como segundo intento -- y se usa el primero
    que logre extraer una coordenada real, no uno solo "universal"."""
    global _ocr_disponible, _ocr_lang
    if _ocr_disponible is False:
        return None, None
    try:
        import pytesseract
        if _TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = _TESSERACT_CMD
        if _ocr_lang is None:
            try:
                disponibles = set(pytesseract.get_languages(config=''))
                _ocr_lang = 'eng+spa' if 'spa' in disponibles else 'eng'
            except Exception:
                _ocr_lang = 'eng'
        copia = img.copy()
        copia.thumbnail((1800, 1800))
        gris = ImageOps.grayscale(copia)
    except Exception as e:
        _ocr_disponible = False
        logger.warning('OCR no disponible (Tesseract no instalado/configurado): %s', str(e))
        return None, None

    umbrales = [200]
    try:
        umbrales.append(_umbral_otsu(gris))
    except Exception:
        pass  # si numpy fallara por algún motivo, seguir solo con el fijo

    for umbral in umbrales:
        try:
            binaria = gris.point(lambda p, u=umbral: 255 if p > u else 0)
            texto = pytesseract.image_to_string(binaria, lang=_ocr_lang, config='--psm 6')
            _ocr_disponible = True
        except Exception as e:
            _ocr_disponible = False
            logger.warning('OCR no disponible (Tesseract no instalado/configurado): %s', str(e))
            return None, None
        lat, lon = _extraer_coordenada_de_texto(texto)
        if lat is not None:
            return lat, lon

    return None, None


def _leer_gps_de_ia(archivo_bytes, filename):
    """ÚLTIMO respaldo, solo si EXIF Y el OCR local (Tesseract + los 5
    patrones de arriba) ya fallaron los dos: manda la foto a un flujo n8n
    (n8n/07_ocr_foto_ia.json) que le pide a Gemini que busque la coordenada
    en CUALQUIER formato, no solo los que el regex local ya sabe reconocer.

    A propósito NO es el primer intento — Tesseract es gratis/instantáneo/
    local y resuelve la mayoría de los casos; esto cuesta latencia (llamada
    de red + inferencia de un modelo) y solo vale la pena para la minoría
    que además falla con el OCR local. Si N8N_WEBHOOK_OCR_IA no está
    configurado (no se importó/activó el flujo en n8n todavía), no hace
    nada — mismo comportamiento que hoy, no rompe nada por default."""
    if not N8N_WEBHOOK_OCR_IA:
        return None, None
    try:
        payload = {
            'filename': filename,
            'foto_base64': base64.b64encode(archivo_bytes).decode('ascii'),
        }
        resp = requests.post(N8N_WEBHOOK_OCR_IA, json=payload, timeout=25)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning('OCR con IA no disponible para %s: %s', filename, str(e))
        return None, None

    if not data.get('encontrado'):
        return None, None
    try:
        lat, lon = float(data['lat']), float(data['lon'])
    except (TypeError, ValueError, KeyError):
        return None, None
    if not (-19.5 <= lat <= 0.5 and -82.0 <= lon <= -68.0):
        return None, None
    logger.info('Ubicación de %s obtenida por IA: %s, %s (texto: %r)',
                filename, lat, lon, data.get('texto_original'))
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

    Devuelve (contenido_limpio_bytes, lat, lon, origen). `origen` es
    'exif'/'ocr'/'ia'/None (de dónde salió la ubicación, para mostrarlo en
    pantalla — la IA es más lenta/cuesta dinero, vale avisar cuándo se usó).
    Lanza FotoInvalida si no pasa.
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
        limpio_bytes = buf.getvalue()

        if lat is None:
            # Último respaldo: EXIF y OCR local ya fallaron los dos — intentar
            # con IA (no-op si N8N_WEBHOOK_OCR_IA no está configurado). Se
            # manda la foto YA re-codificada/saneada, nunca los bytes
            # originales que subió el usuario.
            lat, lon = _leer_gps_de_ia(limpio_bytes, filename)
            origen = 'ia' if lat is not None else None

        return limpio_bytes, lat, lon, origen
    except FotoInvalida:
        raise
    except Image.DecompressionBombError:
        raise FotoInvalida(f'{filename}: imagen sospechosa (demasiado grande al descomprimir)')
    except Exception as e:
        logger.warning('Foto rechazada (%s): %s', filename, str(e))
        raise FotoInvalida(f'{filename}: no se pudo procesar la imagen')
