import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
from PIL import Image
import os
import sys
import geopandas as gpd
import contextily as ctx
from matplotlib_scalebar.scalebar import ScaleBar
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# ============================================================================
# CONFIGURACIÓN DE ESTILOS Y COLORES
# ============================================================================
class Estilos:
    """Configuración centralizada de colores, tamaños de fuente, etc."""
    
    # Colores de niveles
    COLOR_MUY_ALTO = '#FF0000'  # Rojo
    COLOR_ALTO = '#FF8C00'      # Naranja
    COLOR_MEDIO = '#FFFF00'     # Amarillo
    
    # Tamaños de fuente
    FONT_TITULO_PRINCIPAL = 13
    FONT_SUBTITULO = 11
    FONT_FECHA_EVENTO = 9
    FONT_LEYENDA = 10
    FONT_FECHAS_INFO = 9
    FONT_LP_FUENTE = 10
    FONT_RECOMENDACIONES = 9
    
    # Colores de texto
    COLOR_TEXTO_PRINCIPAL = 'black'
    COLOR_TEXTO_ITALICO = '#333333'
    # Fuente elegante y universal
    FUENTE_ELEGANTE = 'DejaVu Sans'
    
    # Grosores de línea
    GROSOR_MARCO_HOJA = 3
    GROSOR_BLOQUES = 2
    GROSOR_SEPARADORES = 1.5
    
    # Ruta del logo
    RUTA_LOGO = 'LOGO/logo.png'

# ============================================================================
# 1. DIMENSIONES DE LA HOJA
# ============================================================================
TOTAL_W, TOTAL_H = 1080, 1920
MARGEN_HOJA = 20  # Margen desde el borde de la hoja al marco general

# MARCO GENERAL (dentro de la hoja)
MARCO_X1 = MARGEN_HOJA
MARCO_X2 = TOTAL_W - MARGEN_HOJA
MARCO_Y1 = MARGEN_HOJA
MARCO_Y2 = TOTAL_H - MARGEN_HOJA
MARCO_ANCHO = MARCO_X2 - MARCO_X1
MARCO_ALTURA = MARCO_Y2 - MARCO_Y1

# ============================================================================
# 2. TRES BLOQUES DENTRO DEL MARCO GENERAL (CON ESPACIO)
# ============================================================================
ESPACIO_BLOQUES = 15

BLOQUE_HEADER_ALTURA = 200
BLOQUE_MAPA_ALTURA = 1000
BLOQUE_FOOTER_ALTURA = MARCO_ALTURA - BLOQUE_HEADER_ALTURA - BLOQUE_MAPA_ALTURA - 2*ESPACIO_BLOQUES

# Posiciones de los bloques DENTRO del marco
BLOQUE_HEADER_Y2 = MARCO_Y2
BLOQUE_HEADER_Y1 = BLOQUE_HEADER_Y2 - BLOQUE_HEADER_ALTURA

BLOQUE_MAPA_Y2 = BLOQUE_HEADER_Y1 - ESPACIO_BLOQUES
BLOQUE_MAPA_Y1 = BLOQUE_MAPA_Y2 - BLOQUE_MAPA_ALTURA

BLOQUE_FOOTER_Y2 = BLOQUE_MAPA_Y1 - ESPACIO_BLOQUES
BLOQUE_FOOTER_Y1 = BLOQUE_FOOTER_Y2 - BLOQUE_FOOTER_ALTURA

# ============================================================================
# 3. SUBDIVISIONES DEL FOOTER
# ============================================================================
LOGO_ANCHO = 250
SEP_VERTICAL_X = MARCO_X1 + LOGO_ANCHO

FILA1_ALTURA = 200
FILA1_Y2 = BLOQUE_FOOTER_Y2
FILA1_Y1 = FILA1_Y2 - FILA1_ALTURA

FILA2_ALTURA = 80
FILA2_Y2 = FILA1_Y1
FILA2_Y1 = FILA2_Y2 - FILA2_ALTURA

FILA3_Y2 = FILA2_Y1
FILA3_Y1 = BLOQUE_FOOTER_Y1
FILA3_ALTURA = FILA3_Y2 - FILA3_Y1

# Leyenda
LEYENDA_ANCHO = 250
LEYENDA_ALTURA = 140
LEYENDA_X1 = MARCO_X2 - 60 - LEYENDA_ANCHO
LEYENDA_Y1 = BLOQUE_MAPA_Y1 + 60

# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def texto_multilinea(ax, x, y, texto, max_ancho_chars, fontsize, **kwargs):
    """
    Divide texto largo en múltiples líneas
    
    Args:
        ax: axes de matplotlib
        x, y: coordenadas
        texto: string a dividir
        max_ancho_chars: máximo de caracteres por línea
        fontsize: tamaño de fuente
        **kwargs: otros argumentos para ax.text()
    """
    palabras = texto.split()
    lineas = []
    linea_actual = []
    
    for palabra in palabras:
        linea_test = ' '.join(linea_actual + [palabra])
        if len(linea_test) <= max_ancho_chars:
            linea_actual.append(palabra)
        else:
            if linea_actual:
                lineas.append(' '.join(linea_actual))
            linea_actual = [palabra]
    
    if linea_actual:
        lineas.append(' '.join(linea_actual))
    
    texto_final = '\n'.join(lineas)
    ax.text(x, y, texto_final, fontsize=fontsize, **kwargs)


def cargar_logo(ax, ruta_logo, x1, y1, ancho, altura):
    """
    Carga y muestra el logo en el mapa
    
    Args:
        ax: axes de matplotlib
        ruta_logo: ruta al archivo de imagen
        x1, y1: esquina inferior izquierda
        ancho, altura: dimensiones del área del logo
    """
    if os.path.exists(ruta_logo):
        try:
            img = Image.open(ruta_logo)
            # Calcular aspecto para no deformar
            img_ratio = img.width / img.height
            area_ratio = ancho / altura
            
            if img_ratio > area_ratio:
                # Imagen más ancha, ajustar por ancho
                nuevo_ancho = ancho * 0.9  # 90% del espacio
                nuevo_altura = nuevo_ancho / img_ratio
            else:
                # Imagen más alta, ajustar por altura
                nuevo_altura = altura * 0.9
                nuevo_ancho = nuevo_altura * img_ratio
            
            # Centrar en el área
            x_centro = x1 + ancho/2
            y_centro = y1 + altura/2
            extent = [
                x_centro - nuevo_ancho/2,
                x_centro + nuevo_ancho/2,
                y_centro - nuevo_altura/2,
                y_centro + nuevo_altura/2
            ]
            
            ax.imshow(img, extent=extent, aspect='auto', zorder=10)
        except Exception as e:
            # Si falla, mostrar texto "LOGO"
            ax.text(x1 + ancho/2, y1 + altura/2, 'LOGO', 
                   fontsize=16, ha='center', va='center', 
                   fontweight='bold', color='gray')
    else:
        # Si no existe el archivo, mostrar texto "LOGO"
        ax.text(x1 + ancho/2, y1 + altura/2, 'LOGO', 
               fontsize=16, ha='center', va='center', 
               fontweight='bold', color='gray')


def dibujar_leyenda(ax, x1, y1, ancho, altura):
    """
    Dibuja la leyenda con círculos de colores
    
    Args:
        ax: axes de matplotlib
        x1, y1: esquina inferior izquierda
        ancho, altura: dimensiones
    """
    # Borde de leyenda con zorder alto para quedar encima
    leyenda_rect = Rectangle((x1, y1), ancho, altura,
                             fill=True, facecolor='white', alpha=0.95,
                             edgecolor='black', linewidth=1.5, zorder=100)
    ax.add_patch(leyenda_rect)
    
    # Items de la leyenda
    niveles = [
        ('MUY ALTO', Estilos.COLOR_MUY_ALTO),
        ('ALTO', Estilos.COLOR_ALTO),
        ('MEDIO', Estilos.COLOR_MEDIO)
    ]
    
    radio_circulo = 12
    espacio_vertical = altura / 4
    x_circulo = x1 + 40
    x_texto = x_circulo + 30
    
    for i, (texto, color) in enumerate(niveles):
        y_pos = y1 + altura - espacio_vertical * (i + 1)
        
        # Círculo de color con zorder alto
        circulo = Circle((x_circulo, y_pos), radio_circulo, 
                        color=color, zorder=101)
        ax.add_patch(circulo)
        
        # Texto con zorder alto
        ax.text(x_texto, y_pos, texto, 
               fontsize=Estilos.FONT_LEYENDA, 
               va='center', ha='left',
               fontweight='bold',
               color=Estilos.COLOR_TEXTO_PRINCIPAL,
               zorder=101)


# ============================================================================
# 4. CREAR FIGURA
# ============================================================================

fig, ax = plt.subplots(figsize=(TOTAL_W/100, TOTAL_H/100), dpi=100)
ax.set_xlim(0, TOTAL_W)
ax.set_ylim(0, TOTAL_H)
ax.set_aspect('equal')
ax.axis('off')
# Fondo naranja suave para toda la hoja
fondo_hoja = Rectangle((0, 0), TOTAL_W, TOTAL_H, facecolor='#FFF3E0', edgecolor='none', zorder=-100)
ax.add_patch(fondo_hoja)

# ============================================================================
# 5. DIBUJAR MARCO GENERAL (borde de la hoja)
# ============================================================================
borde_hoja = Rectangle((0, 0), TOTAL_W, TOTAL_H,
                       fill=False, edgecolor='black', 
                       linewidth=Estilos.GROSOR_MARCO_HOJA)
ax.add_patch(borde_hoja)

# ============================================================================
# 6. DIBUJAR 3 BLOQUES INDEPENDIENTES
# ============================================================================

# BLOQUE 1: HEADER
header = Rectangle((MARCO_X1, BLOQUE_HEADER_Y1),
                   MARCO_ANCHO, BLOQUE_HEADER_ALTURA,
                   fill=False, edgecolor='black', 
                   linewidth=Estilos.GROSOR_BLOQUES)
ax.add_patch(header)

# BLOQUE 2: MAPA (solo borde)
mapa = Rectangle(
    (MARCO_X1, BLOQUE_MAPA_Y1),
    MARCO_ANCHO, BLOQUE_MAPA_ALTURA,
    fill=False, edgecolor='black',
    linewidth=Estilos.GROSOR_BLOQUES,
    zorder=1
)
ax.add_patch(mapa)

# BLOQUE 3: FOOTER
footer = Rectangle((MARCO_X1, BLOQUE_FOOTER_Y1),
                   MARCO_ANCHO, BLOQUE_FOOTER_ALTURA,
                   fill=False, edgecolor='black', 
                   linewidth=Estilos.GROSOR_BLOQUES)
ax.add_patch(footer)

# ============================================================================
# 7. LÍNEAS INTERNAS DEL FOOTER
# ============================================================================
# Línea vertical única
ax.plot([SEP_VERTICAL_X, SEP_VERTICAL_X], 
        [FILA2_Y1, FILA1_Y2], 'k-', 
        linewidth=Estilos.GROSOR_SEPARADORES)

# Líneas horizontales
ax.plot([MARCO_X1, MARCO_X2], [FILA1_Y1, FILA1_Y1], 'k-', 
        linewidth=Estilos.GROSOR_SEPARADORES)
ax.plot([MARCO_X1, MARCO_X2], [FILA2_Y1, FILA2_Y1], 'k-', 
        linewidth=Estilos.GROSOR_SEPARADORES)

# ============================================================================
# 8. CONTENIDO - HEADER
# ============================================================================
padding_header = 20


# ================== ARGUMENTOS DINÁMICOS =====================
if __name__ == "__main__":
    if len(sys.argv) < 11:
        print("Uso: python MAPAS.py <DEPARTAMENTO> <NUM_AVISO> <DURACION_HRS> <TITULO> <NIVEL> <COLOR> <FECHA_EMISION> <FECHA_INICIO> <FECHA_FIN> <DESCRIPCION>")
        sys.exit(1)
    (
        DEPARTAMENTO_OBJETIVO,
        numero_aviso,
        duracion_horas,
        titulo,
        nivel,
        color,
        fecha_emision,
        fecha_inicio,
        fecha_fin,
        descripcion
    ) = sys.argv[1:11]
else:
    # Valores por defecto para pruebas
    DEPARTAMENTO_OBJETIVO = "CAJAMARCA"
    numero_aviso = "000"
    duracion_horas = "00"
    titulo = "TITULO DE PRUEBA"
    nivel = "NARANJA"
    color = "naranja"
    fecha_emision = "2025-12-14"
    fecha_inicio = "2025-12-16 18:00:00"
    fecha_fin = "2025-12-18 23:59:00"
    descripcion = "Descripción de prueba para el aviso."

# Título principal (centrado, más grande y elegante)
texto_multilinea(
    ax,
    MARCO_X1 + MARCO_ANCHO/2,
    BLOQUE_HEADER_Y1 + BLOQUE_HEADER_ALTURA - 30,
    titulo,
    max_ancho_chars=50,
    fontsize=20,  # más grande
    fontweight='bold',
    va='top',
    ha='center',
    color=Estilos.COLOR_TEXTO_PRINCIPAL,
    fontfamily=Estilos.FUENTE_ELEGANTE
)

# Subtítulo: solo el nombre del departamento (más grande y elegante)
ax.text(
    MARCO_X1 + MARCO_ANCHO/2,
    BLOQUE_HEADER_Y1 + 90,
    DEPARTAMENTO_OBJETIVO,
    fontsize=16,  # más grande
    ha='center', va='center',
    fontweight='bold',
    color=Estilos.COLOR_TEXTO_PRINCIPAL,
    fontfamily=Estilos.FUENTE_ELEGANTE
)

# Fecha del evento (inicio y fin, más grande y elegante)
ax.text(
    MARCO_X1 + MARCO_ANCHO/2,
    BLOQUE_HEADER_Y1 + 30,
    f'Evento: {fecha_inicio} a {fecha_fin}',
    fontsize=14,  # más grande
    ha='center', va='center',
    style='italic',
    color=Estilos.COLOR_TEXTO_ITALICO,
    fontfamily=Estilos.FUENTE_ELEGANTE
)

# ============================================================================
# 9. CONTENIDO - MAPA (GENERADO DENTRO DEL CUADRANTE)
# ============================================================================

# Validar argumento de departamento
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python MAPAS.py <NOMBRE_DEPARTAMENTO>")
        sys.exit(1)
    DEPARTAMENTO_OBJETIVO = sys.argv[1]
else:
    DEPARTAMENTO_OBJETIVO = "CAJAMARCA"  # Valor por defecto si se importa

# Cargar shapefiles
shp_deptos = gpd.read_file('DELIMITACIONES/DEPARTAMENTOS/DEPARTAMENTOS.shp')
shp_provincias = gpd.read_file('DELIMITACIONES/PROVINCIAS/PROVINCIAS.shp')

# Cargar SHP de riesgo desde variable de entorno o parámetro
shp_riesgo_path = os.getenv('SHP_RIESGO_PATH', 'DESCARGADOS_DB/aviso_452_3/view_aviso.shp')
if not os.path.exists(shp_riesgo_path):
    print(f"❌ Error: SHP de riesgo no encontrado en {shp_riesgo_path}")
    sys.exit(1)
shp_riesgo = gpd.read_file(shp_riesgo_path)

if DEPARTAMENTO_OBJETIVO not in shp_deptos['DPTONOM02'].values:
    print(f"El departamento '{DEPARTAMENTO_OBJETIVO}' no se encuentra en los datos.")
    sys.exit(1)

departamento = DEPARTAMENTO_OBJETIVO
gdf_depto = shp_deptos[shp_deptos['DPTONOM02'] == departamento].to_crs('EPSG:3857')
gdf_provincias = shp_provincias[shp_provincias['DEPARTAMEN'] == departamento].to_crs('EPSG:3857')
shp_riesgo_wm = shp_riesgo.to_crs('EPSG:3857')

# Crear axes para el mapa usando inset_axes
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

ax_mapa = inset_axes(ax, 
                     width="100%", 
                     height="100%",
                     bbox_to_anchor=(MARCO_X1, BLOQUE_MAPA_Y1, 
                                    MARCO_ANCHO, BLOQUE_MAPA_ALTURA),
                     bbox_transform=ax.transData,
                     loc='lower left',
                     borderpad=0)

ax_mapa.set_aspect('equal')
ax_mapa.axis('off')

# Calcular el bounding box del departamento
bounds = gdf_depto.total_bounds
x_min_depto, y_min_depto, x_max_depto, y_max_depto = bounds

# Calcular centro del departamento
centro_x_depto = (x_min_depto + x_max_depto) / 2
centro_y_depto = (y_min_depto + y_max_depto) / 2

# Calcular aspecto del cuadrante
aspecto_cuadrante = MARCO_ANCHO / BLOQUE_MAPA_ALTURA

# Calcular dimensiones del departamento
ancho_depto = x_max_depto - x_min_depto
alto_depto = y_max_depto - y_min_depto

# Expandir desde el centro del departamento para llenar el cuadrante
# Agregar 5% extra para contexto mínimo alrededor del departamento
factor_expansion = 1.05
ancho_depto_expandido = ancho_depto * factor_expansion
alto_depto_expandido = alto_depto * factor_expansion

# Ajustar para que llene el cuadrante respetando el aspecto
if ancho_depto_expandido / alto_depto_expandido > aspecto_cuadrante:
    # Más ancho - ajustar por ancho
    ancho_final = ancho_depto_expandido
    alto_final = ancho_final / aspecto_cuadrante
else:
    # Más alto - ajustar por altura
    alto_final = alto_depto_expandido
    ancho_final = alto_final * aspecto_cuadrante

# FORZAR llenado horizontal completo (eliminar espacios en blanco)
ancho_minimo = ancho_depto * 1.15  # Mínimo 15% más que el departamento
if ancho_final < ancho_minimo:
    ancho_final = ancho_minimo
    alto_final = ancho_final / aspecto_cuadrante

# Calcular límites finales centrados en el departamento
x_min_final = centro_x_depto - ancho_final / 2
x_max_final = centro_x_depto + ancho_final / 2
y_min_final = centro_y_depto - alto_final / 2
y_max_final = centro_y_depto + alto_final / 2

# Establecer límites ANTES del basemap
ax_mapa.set_xlim(x_min_final, x_max_final)
ax_mapa.set_ylim(y_min_final, y_max_final)

# Forzar que matplotlib respete estos límites
ax_mapa.set_autoscale_on(False)

# Zoom dinámico según tamaño del departamento (más zoom = más cercano)
area = (x_max_depto - x_min_depto) * (y_max_depto - y_min_depto)
if area < 2e9:
    zoom = 11  # Muy cercano
elif area < 5e9:
    zoom = 10  # Cercano 
else:
    zoom = 9   # Medio

# Agregar mapa base CON reset_extent=False y extent forzado
try:
    # Calcular extent explícito para el basemap
    extent = [x_min_final, x_max_final, y_min_final, y_max_final]
    
    ctx.add_basemap(ax_mapa, 
                   source=ctx.providers.OpenStreetMap.Mapnik, 
                   zoom=zoom, 
                   crs='EPSG:3857', 
                   reset_extent=False)
    
    # Restablecer límites después del basemap para asegurar
    ax_mapa.set_xlim(x_min_final, x_max_final)
    ax_mapa.set_ylim(y_min_final, y_max_final)
except Exception as e:
    print(f"Advertencia: No se pudo cargar mapa base: {e}")

# Plotear departamento y provincias (sin leyenda automática)
gdf_depto.plot(ax=ax_mapa, facecolor='none', edgecolor='black', 
              linewidth=2, zorder=2)
gdf_provincias.plot(ax=ax_mapa, facecolor='none', edgecolor='gray', 
                   linewidth=1, zorder=2)

# Plotear zonas de riesgo (sin leyenda automática)
colores = {'Nivel 2': 'yellow', 'Nivel 3': 'orange', 'Nivel 4': 'red'}
for nivel, color in colores.items():
    sel = shp_riesgo_wm[shp_riesgo_wm['nivel'] == nivel]
    if not sel.empty:
        sel.plot(ax=ax_mapa, color=color, alpha=0.5, zorder=3)

# Agregar escala y grid
scalebar = ScaleBar(1, units="m", location='lower left', box_alpha=0.3)
ax_mapa.add_artist(scalebar)
ax_mapa.grid(True, which='both', color='gray', alpha=0.2, linestyle='--', zorder=1)

# ============================================================================
# DIBUJAR LEYENDA DENTRO DEL ax_mapa (para que quede encima)
# ============================================================================
# Convertir coordenadas del axes principal a coordenadas del mapa
# La leyenda debe dibujarse en ax_mapa para quedar visible
leyenda_x1_mapa = x_min_final + (LEYENDA_X1 - MARCO_X1) * (x_max_final - x_min_final) / MARCO_ANCHO
leyenda_y1_mapa = y_min_final + (LEYENDA_Y1 - BLOQUE_MAPA_Y1) * (y_max_final - y_min_final) / BLOQUE_MAPA_ALTURA
leyenda_ancho_mapa = LEYENDA_ANCHO * (x_max_final - x_min_final) / MARCO_ANCHO
leyenda_altura_mapa = LEYENDA_ALTURA * (y_max_final - y_min_final) / BLOQUE_MAPA_ALTURA

# Dibujar leyenda en ax_mapa
from matplotlib.patches import Rectangle, Circle
leyenda_rect = Rectangle((leyenda_x1_mapa, leyenda_y1_mapa), 
                         leyenda_ancho_mapa, leyenda_altura_mapa,
                         fill=True, facecolor='white', alpha=0.95,
                         edgecolor='black', linewidth=1.5, zorder=200)
ax_mapa.add_patch(leyenda_rect)

# Items de la leyenda
niveles = [
    ('MUY ALTO', Estilos.COLOR_MUY_ALTO),
    ('ALTO', Estilos.COLOR_ALTO),
    ('MEDIO', Estilos.COLOR_MEDIO)
]

radio_circulo_mapa = 12 * (x_max_final - x_min_final) / MARCO_ANCHO
espacio_vertical_mapa = leyenda_altura_mapa / 4
x_circulo_mapa = leyenda_x1_mapa + 40 * (x_max_final - x_min_final) / MARCO_ANCHO
x_texto_mapa = x_circulo_mapa + 30 * (x_max_final - x_min_final) / MARCO_ANCHO

for i, (texto, color) in enumerate(niveles):
    y_pos_mapa = leyenda_y1_mapa + leyenda_altura_mapa - espacio_vertical_mapa * (i + 1)
    
    # Círculo de color
    circulo = Circle((x_circulo_mapa, y_pos_mapa), radio_circulo_mapa, 
                    color=color, zorder=201)
    ax_mapa.add_patch(circulo)
    
    # Texto
    ax_mapa.text(x_texto_mapa, y_pos_mapa, texto, 
           fontsize=Estilos.FONT_LEYENDA, 
           va='center', ha='left',
           fontweight='bold',
           color=Estilos.COLOR_TEXTO_PRINCIPAL,
           zorder=201)

# ============================================================================
# 11. CONTENIDO - FOOTER
# ============================================================================

# LOGO
cargar_logo(ax, Estilos.RUTA_LOGO, 
           MARCO_X1, FILA1_Y1, LOGO_ANCHO, FILA1_ALTURA)


# Fechas (INFO, más grande y elegante)
padding_info = 15
fechas_texto = f"""fecha de elaboración: {fecha_emision}\nInicio del evento: {fecha_inicio}\nFin del evento: {fecha_fin}"""
ax.text(
    SEP_VERTICAL_X + (MARCO_X2 - SEP_VERTICAL_X)/2,
    FILA1_Y1 + FILA1_ALTURA/2,
    fechas_texto,
    fontsize=14,  # más grande
    va='center', ha='center',
    style='italic',
    color=Estilos.COLOR_TEXTO_ITALICO,
    linespacing=1.6,
    fontfamily=Estilos.FUENTE_ELEGANTE
)

# LP-seguro agrario (elegante)
ax.text(
    MARCO_X1 + LOGO_ANCHO/2, FILA2_Y1 + FILA2_ALTURA/2,
    'LP-SEGURO AGRARIO',
    fontsize=Estilos.FONT_LP_FUENTE,
    ha='center', va='center',
    fontweight='bold',
    color=Estilos.COLOR_TEXTO_PRINCIPAL,
    fontfamily=Estilos.FUENTE_ELEGANTE
)

# FUENTE (centrado, más grande y elegante)
ax.text(
    SEP_VERTICAL_X + (MARCO_X2 - SEP_VERTICAL_X)/2,
    FILA2_Y1 + FILA2_ALTURA/2,
    'FUENTE: SENAMHI',
    fontsize=13,  # más grande
    va='center', ha='center',
    fontweight='bold',
    color=Estilos.COLOR_TEXTO_PRINCIPAL,
    fontfamily=Estilos.FUENTE_ELEGANTE
)

# RECOMENDACIONES (usa la descripción del aviso, más grande, centrado y elegante)
texto_multilinea(
    ax,
    MARCO_X1 + MARCO_ANCHO/2,
    FILA3_Y1 + FILA3_ALTURA/2 + 20,
    descripcion,
    max_ancho_chars=80,
    fontsize=14,  # más grande
    va='center',
    ha='center',
    color=Estilos.COLOR_TEXTO_PRINCIPAL,
    fontfamily=Estilos.FUENTE_ELEGANTE
)

# ============================================================================
# 12. GUARDAR
# ============================================================================
plt.savefig(f'mapa_tematico_{departamento}.png', dpi=300, 
            bbox_inches='tight', pad_inches=0, facecolor='white')
plt.close()

print(f"✅ 'mapa_tematico_{departamento}.png' GENERADO")
print(f"   • Logo: {Estilos.RUTA_LOGO}")
print(f"   • Departamento: {departamento}")
print(f"   • Colores leyenda: Rojo, Naranja, Amarillo")