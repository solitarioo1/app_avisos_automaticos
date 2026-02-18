# 📋 ESTRUCTURA DEL MAPA TEMÁTICO - SENAMHI

## 🔍 Análisis de Layout Actual (MAPAS.py)

### **Dimensiones Totales**
- **Ancho**: 1080 px
- **Alto**: 1920 px
- **Margen**: 20 px desde el borde

---

## 📐 **DIVISIÓN EN 3 BLOQUES PRINCIPALES**

### **1️⃣ BLOQUE HEADER (Superior)**
- **Altura**: 200 px
- **Contenido**:
  - ✅ Título principal (CENTRADO, fuente 20px, negrita)
  - ✅ Departamento (fuente 16px, negrita)
  - ✅ Rango de fechas (fuente 14px, itálica)
  
**Ejemplo**:
```
┌─────────────────────────────────────┐
│                                     │
│   ALERTA POR HELADAS EN CAJAMARCA   │
│                                     │
│            CAJAMARCA                │
│                                     │
│  Evento: 2025-12-16 18:00 a         │
│          2025-12-18 23:59           │
│                                     │
└─────────────────────────────────────┘
```

**Ubicación en código**: Líneas 300-330

---

### **2️⃣ BLOQUE MAPA (Centro - Principal)**
- **Altura**: 1000 px (el bloque más grande)
- **Espacios**: 15 px arriba y abajo

**Componentes del Mapa**:

#### **🗺️ Capa Base**
- **Proveedor**: OpenStreetMap.Mapnik (fallback: CartoDB Positron)
- **Zoom dinámico**: 9-11 según tamaño del departamento
- **CRS**: EPSG:3857 (Web Mercator)

#### **🖼️ Capas Vectoriales**
1. **Límite del Departamento**
   - Borde negro grueso (4px)
   - Sin relleno (transparente)
   - Z-order: 3

2. **Provincias**
   - Línea gris oscura (2.5px)
   - Z-order: 2.5

3. **Zonas de Riesgo** (Shapefile de SENAMHI)
   - Nivel 4 (Rojo): `Color = #FF0000` con 50% transparencia
   - Nivel 3 (Naranja): `Color = #FF8C00` con 50% transparencia
   - Nivel 2 (Amarillo): `Color = #FFFF00` con 50% transparencia
   - Z-order: 3

#### **📊 Elementos Complementarios**
- **Escala**: Posición inferior izquierda, semitransparente
- **Grilla**: Líneas punteadas gris claro (Z-order: 1)
- **Leyenda**: Esquina inferior derecha del mapa
  - Rectángulo blanco (95% opacidad)
  - 3 círculos de color (Rojo, Naranja, Amarillo)
  - Texto en fuente 10px negrita

**ubicación en código**: Líneas 400-700

---

### **3️⃣ BLOQUE FOOTER (Inferior)**
- **Altura**: ~520 px
- **División**: 3 FILAS INTERNAS

#### **Fila 1 (Superior - 200px)**
- **Lado Izquierdo (250px ancho)**:
  - 🏛️ **LOGO** (de SENAMHI)
  - Ajustado automáticamente sin deformación
  
- **Lado Derecho** (Resto):
  - 📅 **FECHAS**:
    - Fecha de elaboración
    - Inicio del evento
    - Fin del evento
  - Fuente 14px itálica

#### **Fila 2 (Media - 80px)**
- **Lado Izquierdo**:
  - Texto: "LP-SEGURO AGRARIO"
  - Fuente 10px negrita

- **Lado Derecho**:
  - Texto: "FUENTE: SENAMHI"
  - Fuente 13px negrita

#### **Fila 3 (Inferior - ~240px)**
- **Ancho completo**:
  - 📝 **RECOMENDACIONES** (descripción del aviso)
  - Texto multilinea automático
  - Fuente 14px
  - Centrado horizontalmente
  - Máximo 80 caracteres por línea

---

## 🎨 **ESQUEMA VISUAL COMPLETO**

```
╔═══════════════════════════════════════════╗
║  MARCO GENERAL (1080 x 1920 px)          ║
║  ┌────────────────────────────────────┐  ║
║  │  HEADER (200px)                   │  ║
║  │  ┌──────────────────────────────┐ │  ║
║  │  │ TITULO: ALERTA POR HELADAS   │ │  ║
║  │  │ DEPARTAMENTO: CAJAMARCA      │ │  ║
║  │  │ FECHAS: 2025-12-16 a 2025... │ │  ║
║  │  └──────────────────────────────┘ │  ║
║  ├────────────────────────────────────┤  ║
║  │  MAPA (1000px)                    │  ║
║  │  ┌──────────────────────────────┐ │  ║
║  │  │    🗺️  MAPA INTERACTIVO      │ │  ║
║  │  │  (OpenStreetMap + Shapefiles)│ │  ║
║  │  │  ┌─ OSM Basemap              │ │  ║
║  │  │  ├─ Límites (Depto/Provinc) │ │  ║
║  │  │  ├─ Zonas de Riesgo (RGB)   │ │  ║
║  │  │  ├─ Escala (inferior izq)   │ │  ║
║  │  │  ├─ Grid                    │ │  ║
║  │  │  └─ Leyenda (inferior dcha) │ │  ║
║  │  └──────────────────────────────┘ │  ║
║  ├────────────────────────────────────┤  ║
║  │  FOOTER (520px)                   │  ║
║  │  ┌─────────────┬────────────────┐ │  ║
║  │  │ LOGO        │ FECHAS (14px)  │ │  ║  Fila 1 (200px)
║  │  │ (250px)     │ 📅📅📅         │ │  ║
║  │  ├─────────────┼────────────────┤ │  ║
║  │  │LP-SEG AGRIO │ FUENTE SENAMHI │ │  ║  Fila 2 (80px)
║  │  ├─────────────────────────────┐ │  ║
║  │  │   RECOMENDACIONES (texto    │ │  ║  Fila 3 (240px)
║  │  │   multilinea, 14px)         │ │  ║
║  │  └─────────────────────────────┘ │  ║
║  └────────────────────────────────────┘  ║
╚═══════════════════════════════════════════╝
```

---

## 🎯 **VARIABLES IMPORTANTES (En MAPAS.py)**

| Variable | Valor | Descripción |
|----------|-------|-------------|
| `TOTAL_W x TOTAL_H` | 1080 x 1920 | Dimensión total del mapa |
| `MARGEN_HOJA` | 20 | Margen desde el borde |
| `BLOQUE_HEADER_ALTURA` | 200 | Alto del encabezado |
| `BLOQUE_MAPA_ALTURA` | 1000 | Alto del mapa (principal) |
| `BLOQUE_FOOTER_ALTURA` | ~520 | Alto del pie de página |
| `ESPACIO_BLOQUES` | 15 | Espacio entre bloques |
| `LOGO_ANCHO` | 250 | Ancho reservado para logo |

---

## 🖌️ **COLORES Y ESTILOS**

### **Colores de Niveles**
```python
COLOR_MUY_ALTO = '#FF0000'  # Rojo (Nivel 4)
COLOR_ALTO = '#FF8C00'      # Naranja (Nivel 3)
COLOR_MEDIO = '#FFFF00'     # Amarillo (Nivel 2)
```

### **Tamaños de Fuente**
- Título Principal: **20px**
- Departamento: **16px**
- Fechas (Header): **14px**
- Recomendaciones: **14px**
- Subtítulos: **13px**
- Leyenda: **10px**

### **Fuente**
- Familia: **DejaVu Sans**
- Disponible en Windows/Linux/Mac

---

## 📌 **ARGUMENTOS DE ENTRADA**

El script recibe 10 parámetros:

```bash
python MAPAS.py <DEPARTAMENTO> <NUM_AVISO> <DURACION_HRS> <TITULO> \
                  <NIVEL> <COLOR> <FECHA_EMISION> <FECHA_INICIO> \
                  <FECHA_FIN> <DESCRIPCION>
```

**Ejemplo**:
```bash
python MAPAS.py "CAJAMARCA" "447" "48" "ALERTA POR HELADAS" \
                 "NARANJA" "naranja" "2025-12-14" \
                 "2025-12-16 18:00:00" "2025-12-18 23:59:00" \
                 "Se espera descenso de temperaturas..."
```

---

## 📤 **SALIDA**

**Fichero generado**:
```
mapa_tematico_{DEPARTAMENTO}.png
```

**Especificaciones**:
- Formato: PNG
- Resolución: 300 DPI
- Tamaño aproximado: 3240 x 5760 px (a 300 DPI)
- Fondo: Blanco (#FFFFFF)

---

## ✅ **ELEMENTOS VERIFICADOS**

- [x] Título centrado y grande
- [x] Departamento destacado
- [x] Fechas con formato limpio
- [x] Mapa con zoom automático
- [x] Leyenda visible
- [x] Logo escalado sin deformación
- [x] Escala cartográfica
- [x] Grid de referencia
- [x] Texto de recomendaciones automáticamente distribuido
- [x] Fuente elegante y legible

---

**¿Qué deseas modificar?**
