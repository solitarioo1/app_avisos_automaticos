l# Plan de Implementación — Módulo de Difusión

**Fecha:** 21 de febrero de 2026  
**Proyecto:** APP MAPAS AVISOS SENAMHI  
**Estado:** BD lista ✅ — Backend pendiente ⏳

---

## 1. ¿Qué hace el módulo de difusión?

Permite enviar alertas meteorológicas a clientes afectados por un aviso SENAMHI a través de tres canales:

| Canal | Flujo |
|-------|-------|
| **WhatsApp** | n8n genera mensaje → guarda en BD → Flask previsualiza → n8n despacha |
| **Email** | n8n genera mensaje → guarda en BD → Flask previsualiza → n8n despacha |
| **SMS** | Solo exporta CSV con datos del cliente (no hay workflow n8n aún) |

---

## 2. Arquitectura general

```
[Flask UI] → [n8n: generar mensajes con IA]
                ↓
        [BD: clientes_envios]  ← guarda mensaje_texto generado
                ↓
[Flask: previsualizar muestra de 4 mensajes]
                ↓
[Flask: confirmar envío] → [n8n: despachar uno a uno]
                ↓
        [BD: actualizar estado por registro]
```

**n8n es el orquestador.** Flask solo coordina y muestra resultados.  
**El agente IA de n8n genera los mensajes** de forma dinámica (no son plantillas fijas).

---

## 3. Tabla de envíos: `clientes_envios` ✅ YA EXISTE Y MIGRADA

No se creó tabla nueva. Se usa `clientes_envios` con migración aplicada (`configurar_difusion.sql` ejecutado).

### Columnas clave

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | SERIAL PK | |
| `cliente_id` | INT FK | → clientes |
| `numero_aviso` | INT FK | → avisos_completos |
| `canal_enviado` | VARCHAR(20) | `whatsapp` / `sms` / `email` |
| `estado` | VARCHAR(20) | `pendiente → enviando → enviado / fallido / entregado / leído` |
| `mensaje_texto` | TEXT | ✅ Nuevo — generado por agente IA de n8n |
| `fecha_envio` | TIMESTAMP | |
| `intentos` | INT | reintentos |
| `mensaje_error` | TEXT | detalle si falló |
| `id_mensaje_externo` | VARCHAR(100) | tracking WhatsApp API / n8n |
| `nivel_filtro` | VARCHAR(20) | nivel al momento del envío |
| `entidad_filtro` | VARCHAR(100) | entidad al momento del envío |

### UNIQUE corregido ✅
```sql
-- ANTES: bloqueaba enviar al mismo cliente por 2 canales
UNIQUE(cliente_id, numero_aviso)
-- AHORA: permite WhatsApp + Email al mismo cliente/aviso
UNIQUE(cliente_id, numero_aviso, canal_enviado)
```

### `mapa_url` — viene por JOIN ✅
No es columna. Se obtiene desde `imagenes_avisos.ruta_web` uniendo por `numero_aviso` + `departamento` del cliente.

---

## 4. Vistas disponibles ✅ RECREADAS

| Vista | Uso |
|-------|-----|
| `v_historial_envios` | Tabla principal del historial (17 campos) |
| `v_resumen_envios_por_aviso` | Panel izquierdo — totales por aviso |
| `v_resumen_envios_por_canal` | Panel derecho — WhatsApp / SMS / Email × estado |

**Campos de `v_historial_envios`:**  
`id, numero_aviso, canal_enviado, estado, nivel_filtro, entidad_filtro, mensaje_texto, fecha_envio, intentos, mensaje_error, nombre, apellido, telefono, correo, departamento, aviso_titulo, mapa_url`

---

## 5. Endpoints a crear en `routes/difusion.py`

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/difusion` | Sirve el template HTML |
| `GET` | `/api/difusion/clientes/<aviso>` | Estadísticas de clientes por nivel para el sidebar |
| `GET` | `/api/difusion/clientes/export/<aviso>` | Descarga CSV (usado por canal SMS) |
| `POST` | `/api/difusion/generar` | Dispara n8n para generar mensajes → guarda en `clientes_envios` |
| `GET` | `/api/difusion/preview/<aviso>` | Lee 4 mensajes de muestra desde `clientes_envios` |
| `POST` | `/api/difusion/enviar/<aviso>` | Dispara n8n para despachar todos los mensajes pendientes |
| `POST` | `/api/difusion/reanudar/<aviso>` | Re-dispara n8n solo para los que tienen `estado='pendiente'` |
| `GET` | `/api/difusion/historial` | Resumen agrupado por aviso + canal para la tabla de historial |

---

## 6. Flujo paso a paso en la UI

```
1. Seleccionar aviso
2. Filtrar por nivel (rojo/naranja/amarillo/todos)
3. Filtrar por entidad (opcional)
4. Seleccionar canal (WhatsApp / Email / SMS)
5. [Botón] "Generar mensajes"  → POST /api/difusion/generar
        ↓ n8n genera y guarda en clientes_envios (estado=pendiente)
6. [Botón] "Ver preview"       → GET /api/difusion/preview/<aviso>
        ↓ muestra 4 tarjetas estilo WhatsApp
7. [Botón] "Confirmar y enviar" → POST /api/difusion/enviar/<aviso>
        ↓ n8n despacha uno a uno actualizando estado
8. Si se interrumpe:
   [Botón] "Reanudar envío"    → POST /api/difusion/reanudar/<aviso>
        ↓ n8n solo procesa los que siguen en 'pendiente'
```

---

## 7. Historial — diseño de la página

### Panel izquierdo — alimentado por `v_resumen_envios_por_aviso`

| Aviso | Total | Pendientes | Enviando | Enviados | Fallidos | Canales |
|-------|-------|------------|----------|----------|----------|---------|
| #44 | 630 | 0 | 0 | 630 | 0 | 3 |
| #43 | 285 | 0 | 0 | 280 | 5 | 2 |

### Panel derecho — alimentado por `v_resumen_envios_por_canal`

| Aviso | Canal | Total | Enviados | Fallidos | Tasa % |
|-------|-------|-------|----------|----------|--------|
| #44 | whatsapp | 100 | 100 | 0 | 100% |
| #44 | sms | 30 | 30 | 0 | 100% |
| #44 | email | 500 | 500 | 0 | 100% |

---

## 8. Recuperación ante interrupciones

| Situación | Acción |
|-----------|--------|
| Se cayó el servidor a mitad del envío | Mensajes enviados tienen `estado='enviado'`, los demás siguen en `pendiente` |
| n8n falló en un mensaje | Ese registro queda en `estado='fallido'` con `error_msg` |
| Quiero reintentar fallidos | Cambiar `estado='fallido'` → `'pendiente'` y usar "Reanudar envío" |
| Quiero ver qué falló | Consultar `clientes_envios WHERE estado='fallido'` |

---

## 9. Cambios en archivos existentes

### `app.py`
Agregar al bloque de blueprints:
```python
from routes.difusion import difusion_bp
app.register_blueprint(difusion_bp)
```

### `templates/difusion.html`
Actualizar flujo de botones:
- Reemplazar "Previsualizar" → "Generar mensajes" + "Ver preview"
- Agregar sección "Historial" con tabla principal + panel derecho de resumen
- El modal de preview mostrará 4 tarjetas con estilo WhatsApp

---

## 10. Checklist de implementación

- [x] Migrar `clientes_envios`: agregar `mensaje_texto`
- [x] Corregir UNIQUE a 3 columnas
- [x] Recrear `v_historial_envios` (17 campos)
- [x] Recrear `v_resumen_envios_por_aviso`
- [x] Recrear `v_resumen_envios_por_canal`
- [ ] Crear `routes/difusion.py` con todos los endpoints
- [ ] Registrar `difusion_bp` en `app.py`
- [ ] Actualizar `templates/difusion.html`:
  - [ ] Botón "Generar mensajes" (reemplaza "Previsualizar")
  - [ ] Modal de preview con 4 tarjetas y `mensaje_texto` real
  - [ ] Sección historial: tabla izquierda + panel derecho canal×estado
- [ ] Workflows n8n (usuario los construye por separado)

---

*Actualizado tras ejecutar `configurar_difusion.sql` en TablePlus.*
