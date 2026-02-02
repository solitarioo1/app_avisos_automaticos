# 📋 EXAMEN ACTUAL: HTML, CSS, JS - decisiones.html

## 1. ESTRUCTURA HTML ACTUAL (decisiones.html)

### ✅ **ELEMENTOS EXISTENTES:**

#### 1.1 Header Card
- **Ubicación**: Línea 12-28
- **Contenido**: Título "Centro de Decisiones Estratégicas" + gradiente rojo (#e53935 → #c62828)
- **Componentes**: Badge "ALERTAS ACTIVAS", fecha actual
- **Estado**: Funcional (clase `.decisiones-container`, max-width: 1200px)

#### 1.2 Tarjetas de Estado (KPI Cards)
- **Ubicación**: Línea 30-59
- **Elementos**: 
  - CRÍTICO (bg-danger red)
  - ALTO RIESGO (bg-warning yellow)
  - AGRICULTORES (bg-info cyan)
  - PÓLIZAS (bg-success green)
- **Datos**: Valores hardcodeados (3 deptos, 7 deptos, 15,847 agr., S/ 245M)
- **Problema**: Estático, no se conecta a BD

#### 1.3 Mapa Interactivo (col-lg-8)
- **Ubicación**: Línea 61-151
- **ID Contenedor**: `mapa-peru-decisiones`
- **Dimensiones**: height: 400px
- **Fondo**: Gradiente verde (e8f5e8 → c8e6c9) - SERÁ REEMPLAZADO
- **Elementos Mapa**:
  - 3 departamentos simulados (Piura, Lima, Arequipa)
  - Posicionamiento absoluto hardcodeado
  - CSS inline (no clean)
  - Colores hardcodeados (rgba values)
  - Leyenda estática en esquina inferior izquierda
  - Tooltip hover en `#dept-tooltip-decisiones`

#### 1.4 Panel de Control (col-lg-4)
- **Ubicación**: Línea 153-168
- **Contenido**:
  - `#dept-detail-decisiones`: Panel de detalles (actualiza con click)
  - Sección "Protocolos de Emergencia":
    - Botón "Activar Brigadas" → función activarBrigadas()
    - Botón "Notificar Autoridades" → función notificarAutoridades()

#### 1.5 Análisis de Cultivos (col-12)
- **Ubicación**: Línea 170-207
- **Contenido**:
  - Canvas para gráfico (id: `cultivosChart`) - NO INICIALIZADO
  - Tabla hardcodeada: Arroz (12,450 ha), Maíz (8,890 ha), Papa (15,670 ha)
  - Valores estáticos sin conexión a BD

#### 1.6 Acciones Estratégicas (col-md-6 × 2)
- **Ubicación**: Línea 209-261
- **COLUMNA IZQUIERDA - Acciones Inmediatas**:
  - Botón: Enviar Alerta WhatsApp → enviarAlertaWhatsApp()
  - Botón: Activar Equipos Técnicos → activarEquiposTecnicos()
  - Botón: Generar Reporte PDF → generarReporteCompleto()

- **COLUMNA DERECHA - Historial de Decisiones**:
  - Timeline div con 3 items hardcodeados
  - Badges de hora (14:30, 13:45, 13:20)
  - Textos estáticos sin conexión a historial real

---

## 2. ESTRUCTURA CSS ACTUAL (inline en decisiones.html)

### **CSS Embebido**:
```css
.decisiones-container {
    max-width: 1200px;
    margin: 0 auto;
}
```

### **Problemas de CSS**:
1. **Muy poco CSS**: Solo 1 regla para contenedor
2. **Estilos inline HTML**: Mapa departamentos tiene style="" con posiciones hardcodeadas
3. **Colores hardcodeados en HTML**: rgba(244, 67, 54, 0.8), rgba(255, 193, 7, 0.8)
4. **Sin Leaflet**: No hay referencias a libería Leaflet
5. **Estilos Bootstrap**: Depende 100% de clases Bootstrap

---

## 3. ESTRUCTURA JS ACTUAL (decisiones.js)

### ✅ **Funciones Existentes**:

| Función | Línea | Propósito | Estado |
|---------|-------|----------|--------|
| `initializeDecisiones()` | 8-11 | Inicialización general | ✅ Funcional |
| `setupDepartamentoInteractivity()` | 13-38 | Setup de eventos mouseover/mouseout/click | ✅ Funcional |
| `mostrarDetallesDepto()` | 40-57 | Actualiza panel derecho con detalles | ✅ Funcional |
| `resetMapaDecisiones()` | 59-65 | Resetea panel de detalles | ✅ Funcional |
| `toggleProvinciasDecisiones()` | 67-69 | Alerta "en desarrollo" | ❌ No implementado |
| `exportarMapaDecisiones()` | 71-73 | Alerta "en desarrollo" | ❌ No implementado |
| `activarBrigadas()` | 75-77 | Muestra modal success | ✅ Funcional |
| `notificarAutoridades()` | 79-81 | Muestra modal info | ✅ Funcional |
| `enviarAlertaWhatsApp()` | 83-85 | Muestra modal success | ✅ Funcional |
| `activarEquiposTecnicos()` | 87-89 | Muestra modal success | ✅ Funcional |
| `generarReporteCompleto()` | 91-93 | Muestra modal success | ✅ Funcional |
| `updateFecha()` | 95-104 | Actualiza fecha en header | ✅ Funcional |

### **Problemas JS**:
1. **No hay conexión BD**: Todo es hardcodeado
2. **No hay fetch a API**: No llama `/api/avisos/...`
3. **No hay Leaflet**: Sin código para mapas geoespaciales
4. **Función `mostrarModal()` no definida**: Se llama pero no existe en decisiones.js
5. **Canvas Chart vacío**: El `cultivosChart` nunca se inicializa (Chart.js falta)

---

## 4. STACK ACTUAL DE TECNOLOGÍAS

### **HTML**:
- Bootstrap 5.3.2
- Bootstrap Icons 1.11.0
- Jinja2 templating
- Inline styles (PROBLEMA)

### **CSS**:
- Bootstrap 5 utilities
- Minimal custom CSS (1 regla)
- Inline styles HTML

### **JS**:
- Vanilla JavaScript (NO frameworks)
- Llamadas a `mostrarModal()` sin definición
- Event listeners sobre elementos HTML
- NO Leaflet
- NO Chart.js (aunque usa canvas)
- NO Axios/Fetch API para BD

### **Backend (app.py)**:
- Blueprint `/decisiones` (rutas)
- NO hay endpoints `/api/avisos/{numero}/clientes-afectados`
- NO hay integración con tabla `clientes` de BD

---

## 5. PROBLEMAS CRÍTICOS IDENTIFICADOS

### 🔴 **CRÍTICOS**:
1. **Sin Leaflet**: Para mapas geoespaciales necesitamos Leaflet + GeoJSON
2. **Sin conexión BD**: Todos los datos son hardcodeados
3. **Sin CSV parsing**: No lee CSV de `OUTPUT/aviso_{numero}/`
4. **Sin estadísticas dinámicas**: Números fijos en KPI cards

### 🟠 **ALTOS**:
5. **Sección eliminable existente**: Historial, Protocolo, Acciones (TODO ESTO DEBE IRSE)
6. **Layout incorrecto**: Necesita 2 columnas (50-50) no el actual
7. **Sin cascada depto→provincia→distrito**: Interactividad mapa incompleta

### 🟡 **MEDIOS**:
8. **CSS desordenado**: Estilos inline + Bootstrap + inline style=""
9. **JS functions sin implementar**: toggle, exportar, mostrarModal
10. **No hay leyenda dinámica**: Depende de rojo/naranja en CSV

---

## 6. ESTRUCTURA ESPERADA vs ACTUAL

### **ACTUAL (Columnas Desfavorables)**:
```
┌─────────────────────────────────────────────────┐
│              HEADER DECISIONES                   │
├─────────────────────────────────────────────────┤
│    CRÍTICO│ALTO RIESGO│AGRICULTORES│PÓLIZAS    │
├───────────────────────┬─────────────────────────┤
│                       │                         │
│   MAPA (col-lg-8)    │  PANEL CONTROL (col-4)  │
│                       │                         │
│  Departamentos        │  Detalles Depto         │
│  Hardcodeados         │  Protocolos             │
│                       │  Brigadas/Notificaciones│
├───────────────────────┴─────────────────────────┤
│        ANÁLISIS DE CULTIVOS (col-12)           │
│        Canvas + Tabla Estática                  │
├─────────────────────────────────────────────────┤
│ ACCIONES INMEDIATAS │ HISTORIAL DE DECISIONES  │
│ WhatsApp/PDF/Equipos│ Timeline Hardcodeado     │
└─────────────────────────────────────────────────┘
```

### **ESPERADO (Nuevo Diseño)**:
```
┌──────────────────────────────────────────────────────┐
│              HEADER + KPI CARDS                      │
├────────────────────┬────────────────────────────────┤
│                    │                                │
│   MAPA LEAFLET     │   FILTRO AVISO                 │
│   (50% ancho)      │   (50% ancho - derecha)        │
│                    │                                │
│   Perú shapefile   │   Nivel: 🔴 CRÍTICO           │
│   Coloreado        │   Alto Riesgo: 🟠 NARANJA     │
│   SHP layers       │                                │
│   Geoespacial      │   ESTADÍSTICAS DINÁMICAS       │
│   Hover interactivo│   • Agricultores: 1,247       │
│                    │   • Póliza: S/ 245M            │
│                    │   • Hectáreas: 12,450         │
│                    │                                │
│   Leyenda          │   PANEL HOVER DINÁMICO         │
│   (rojo/naranja)   │   [Actualiza con mouse]        │
│                    │                                │
└────────────────────┴────────────────────────────────┘
```

---

## 7. RESUMEN COMPARATIVO

| Aspecto | ACTUAL | NECESARIO |
|---------|--------|-----------|
| **Mapa** | Posiciones hardcodeadas | Leaflet + SHP GeoJSON |
| **Datos** | Estáticos en HTML | Dinámicos desde BD |
| **Columnas** | 8-4 (mapa-panel) | 50-50 (izq-der) |
| **Panel Derecho** | Protocolos/Brigadas | Filtro + Estadísticas |
| **Interactividad** | Hover básico | Cascada depto→provincia→distrito |
| **CSS** | Inline HTML | Separado + clean |
| **JS** | Funciones vacías | Fetch API + Leaflet |
| **Historial** | Sección completa | ❌ ELIMINAR |
| **PDF Export** | Botón funcional | ❌ ELIMINAR |

---

## 8. ARCHIVOS INVOLUCRADOS

### **Frontend**:
- ✅ [decisiones.html](templates/decisiones.html) - **SERÁ REEMPLAZADO 80%**
- 📝 [decisiones.js](static/js/decisiones.js) - **SERÁ REEMPLAZADO 95%**
- ✅ [style.css](static/css/style.css) - **AGREGAR ESTILOS NUEVOS**
- ✅ [base.html](templates/base.html) - **SIN CAMBIOS (usar como está)**

### **Backend**:
- 🔴 [routes/decisiones.py](routes/decisiones.py) - **REVISAR/CREAR ENDPOINT**
- 📦 requirements.txt - **REVISAR Leaflet CDN**

### **Datos**:
- ✅ [DELIMITACIONES/DEPARTAMENTOS/DEPARTAMENTOS.shp](DELIMITACIONES/DEPARTAMENTOS/) - Ya coloreado
- ✅ [OUTPUT/aviso_{numero}/](OUTPUT/) - CSVs existentes
- 🗄️ BD PostgreSQL - tabla `clientes` (1000 registros)

---

## 9. CONCLUSIÓN PRE-IMPLEMENTACIÓN

### **Cambios Principales Requeridos**:

1. ✂️ **ELIMINAR**: 
   - Sección "Historial de Decisiones" completa
   - Sección "Acciones Inmediatas" (Enviar WhatsApp, PDF)
   - Sección "Protocolos de Emergencia"
   - Mapa simulado hardcodeado

2. 🆕 **AGREGAR**:
   - Leaflet.js + L.GeoJSON
   - Fetch API para clientes BD + CSV avisos
   - Panel derecho con filtro dinámico
   - Cascada interactiva: depto → provincia → distrito
   - Estadísticas calculadas en tiempo real
   - Hover panel update en JavaScript

3. 🎨 **CAMBIAR**:
   - Layout: 2 columnas 50-50
   - Colores: usar #a67676 (rojo), #b8956a (naranja)
   - Estructura CSS: mover inline → separado
   - Datos: hardcoded → dinámicos

4. ✅ **MANTENER**:
   - Header con KPI cards (pero dinámico)
   - Base.html estructura
   - Color palette existente
   - Bootstrap 5

---

**LISTA CHECKPOINTS**:
- [x] HTML examinado (364 líneas)
- [x] CSS examinado (inline minimal)
- [x] JS examinado (104 líneas)
- [x] Problemas identificados (10+)
- [x] Estructura esperada definida
- [x] Archivos involucrados listados
- [x] Pronto: Implementación fase 1 (Backend)
