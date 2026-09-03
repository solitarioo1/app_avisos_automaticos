/* ============================================================================
   DECISIONES.JS - Centro de Decisiones con Leaflet + API
   Integracion de mapas geoespaciales con datos de clientes BD
   Sistema dinamico: Depto, Provincia, Distrito
   ============================================================================ */

let mapa = null;
let avisoActual = null;
let geojsonLayer = null;
let clientesLayer = null;
let capasRiesgoPoligonos = {};// nombre -> layer Leaflet de la ZONA de peligro en sí (polígono coloreado)
let capasRiesgoInfo = {};     // nombre -> {label, color, disponible, ...} desde /disponibles
let delimitacionesLayers = {};
let nivelSeleccionado = 'nacional';
let agregacionesData = {};
let filtroActual = { depto: null, provincia: null, distrito: null };
let filtroEntidadActual = null;  // id de la entidad seleccionada (null = todas)
let agregacionesDataOriginal = {};  // copia sin filtrar para restaurar
let modoPanel = 'avisos';  // 'avisos' | 'capas' — exclusivos, nunca los dos a la vez

document.addEventListener('DOMContentLoaded', function() {
    initializeDecisiones();
});

function initializeDecisiones() {
    console.log('🎯 Centro de Decisiones iniciado');
    inicializarMapa();
    cargarClientesMapa();   // todos los clientes, una sola vez
    cargarAvisos();
    cargarSelectorEntidades();  // independiente del aviso
    cargarSelectorCapasRiesgo();
}

// ============================================================================
// CAPAS DE RIESGO (independiente del aviso — cruce cliente x capa, multi-activo)
// Arquitectura: el cruce NO se recalcula en cada carga de página (las capas
// son fijas, lo que cambia es la data de clientes). Se calcula una vez con
// el botón "Actualizar Cruce" y queda guardado; acá solo se LEE.
// ============================================================================

function cargarSelectorCapasRiesgo() {
    fetch('/api/capas-riesgo/disponibles')
        .then(r => r.json())
        .then(capas => {
            const select = document.getElementById('filtro-capa-riesgo');
            const valorPrevio = select.value;
            select.innerHTML = '<option value="">-- Ninguna --</option>';
            let fechaMasReciente = null;

            capas.forEach(c => {
                capasRiesgoInfo[c.id] = c;
                const opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = c.disponible ? c.label : `${c.label} (pendiente)`;
                opt.disabled = !c.disponible;
                select.appendChild(opt);

                if (c.calculado_en && (!fechaMasReciente || c.calculado_en > fechaMasReciente)) {
                    fechaMasReciente = c.calculado_en;
                }
            });

            select.value = valorPrevio || '';
            actualizarFechaCruce(fechaMasReciente);
        })
        .catch(e => console.error('❌ Error cargando capas de riesgo:', e));
}

function actualizarFechaCruce(fechaISO) {
    const el = document.getElementById('capas-riesgo-fecha');
    if (!fechaISO) {
        el.textContent = '-- sin calcular --';
        return;
    }
    const f = new Date(fechaISO);
    el.textContent = 'Última actualización: ' + f.toLocaleString('es-PE', { dateStyle: 'medium', timeStyle: 'short' });
}

function actualizarCruce() {
    const btn = document.getElementById('btn-actualizar-cruce');
    btn.disabled = true;
    btn.textContent = 'Calculando...';

    fetch('/api/capas-riesgo/recalcular', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            console.log('✅ Cruce actualizado:', data);
            btn.disabled = false;
            btn.textContent = '↻ Actualizar Cruce';
            cargarSelectorCapasRiesgo();
            // Re-seleccionar la capa activa (cargarSelectorCapasRiesgo redibuja el select)
            if (capaRiesgoActiva) {
                const select = document.getElementById('filtro-capa-riesgo');
                if (select) select.value = capaRiesgoActiva;
                cargarPoligonoCapaRiesgo(capaRiesgoActiva);
                cargarCapaRiesgoEnMapa(capaRiesgoActiva);
                activarKPIsPorCapa(capaRiesgoActiva);
            }
        })
        .catch(e => {
            console.error('❌ Error actualizando cruce:', e);
            btn.disabled = false;
            btn.textContent = '↻ Actualizar Cruce';
        });
}

let capaRiesgoActiva = null;  // selección única: elegir una capa reemplaza los KPIs de arriba

// ============================================================================
// MODO DEL PANEL: Avisos <-> Capas de Riesgo — EXCLUSIVOS.
// Cambiar de modo es lo único que agrega/quita las capas del mapa; los
// checkboxes de abajo ya no tocan la capa de aviso directamente (evita el
// cruce de datos que se veía antes, con las dos capas encimadas).
// ============================================================================

function cambiarModoPanel(modo) {
    if (modo === modoPanel) return;
    modoPanel = modo;

    document.getElementById('tab-modo-avisos').classList.toggle('modo-tab-activo', modo === 'avisos');
    document.getElementById('tab-modo-capas').classList.toggle('modo-tab-activo', modo === 'capas');
    document.getElementById('modo-avisos').style.display = (modo === 'avisos') ? '' : 'none';
    document.getElementById('modo-capas').style.display = (modo === 'capas') ? '' : 'none';

    if (modo === 'avisos') {
        // Salir de modo capas: quitar la capa del mapa y limpiar el select.
        if (capaRiesgoActiva) {
            quitarCapaRiesgoDelMapa(capaRiesgoActiva);
            capaRiesgoActiva = null;
        }
        const select = document.getElementById('filtro-capa-riesgo');
        if (select) select.value = '';
        if (avisoActual) {
            cargarCapaGeoJSON(avisoActual);
            cargarKPIsNuevos(avisoActual);
            actualizarTablaZonas();
            actualizarTablaEntidades();
            actualizarTablaCultivos();
        }
    } else {
        // Entrar a modo capas: quitar el polígono del aviso del mapa y las
        // tablas de abajo (todavía sin capa elegida, no dejar datos del aviso).
        if (geojsonLayer) { mapa.removeLayer(geojsonLayer); geojsonLayer = null; }
        vaciarTablasCapaRiesgo();
    }
    actualizarEstadoBotonExportar();
}

// Selector único (dropdown, igual que Avisos): elegir una capa reemplaza
// la anterior automáticamente — no hace falta desmarcar nada a mano.
function cambiarCapaRiesgoSelect() {
    const nombre = document.getElementById('filtro-capa-riesgo').value;

    if (capaRiesgoActiva) {
        quitarCapaRiesgoDelMapa(capaRiesgoActiva);
        capaRiesgoActiva = null;
    }

    if (!nombre) {
        restaurarKPIsPorAviso();
        vaciarTablasCapaRiesgo();
        actualizarEstadoBotonExportar();
        return;
    }

    capaRiesgoActiva = nombre;
    cargarPoligonoCapaRiesgo(nombre);
    cargarCapaRiesgoEnMapa(nombre);
    activarKPIsPorCapa(nombre);  // única fuente de KPIs — ya no hay cuadrito duplicado abajo
    actualizarTablaZonasPorCapa(nombre);
    actualizarTablaEntidadesPorCapa(nombre);
    actualizarTablaCultivosPorCapa(nombre);
    actualizarEstadoBotonExportar();
}

function quitarCapaRiesgoDelMapa(nombre) {
    if (capasRiesgoPoligonos[nombre]) {
        mapa.removeLayer(capasRiesgoPoligonos[nombre]);
        delete capasRiesgoPoligonos[nombre];
    }
    restaurarColorClientesBase();
}

// Los KPIs de arriba (Agr. Afectados, % Afectación, Póliza/Hectáreas Afectadas)
// pasan a reflejar la capa de riesgo seleccionada en vez del aviso vigente.
// Los "Totales" (todo el libro de clientes) no cambian.
// Filtro "Niveles a combinar" (Muy Alto/Alto/Medio/Bajo) en la cabecera de
// Capas de Riesgo — pedido explícito: al desmarcar niveles, KPIs + mapa +
// las 3 tablas de abajo se recalculan solo con los niveles marcados.
function nivelesCapaSeleccionados() {
    const marcados = Array.from(document.querySelectorAll('#filtro-niveles-capa input:checked')).map(el => el.value);
    return marcados.join(',');
}

// Igual que qsNiveles() pero además manda depto/provincia/distrito/entidad —
// antes esos filtros no llegaban al backend en modo Capas, por eso el bloque
// "Estadísticas" del panel derecho se quedaba siempre en cero al filtrar.
function qsNiveles() {
    const p = new URLSearchParams();
    const niveles = nivelesCapaSeleccionados();
    if (niveles) p.set('niveles', niveles);
    if (filtroActual.depto)     p.set('depto', filtroActual.depto);
    if (filtroActual.provincia) p.set('provincia', filtroActual.provincia);
    if (filtroActual.distrito)  p.set('distrito', filtroActual.distrito);
    if (filtroEntidadActual)    p.set('entidad_id', filtroEntidadActual);
    const qs = p.toString();
    return qs ? `?${qs}` : '';
}

// Checkbox "Nivel de Riesgo" en modo Avisos (Rojo/Naranja/Amarillo — Verde no
// es seleccionable, por definición es "no expuesto"). Mismo patrón que
// nivelesCapaSeleccionados() en Capas de Riesgo.
function nivelesAvisoSeleccionados() {
    const marcados = Array.from(document.querySelectorAll('#filtro-niveles-aviso input:checked')).map(el => el.value);
    return marcados.join(',');
}

// Igual patrón que qsNiveles() pero para modo Avisos — usada por el KPI
// superior, las 3 tablas de abajo (Zonas/Entidades/Cultivos), el panel de
// Estadísticas y el export CSV: antes ignoraban depto/provincia/distrito/
// entidad por completo y siempre mostraban el resumen de TODO el aviso
// (Verde incluido), sin importar el filtro puesto en pantalla.
function qsFiltroZona() {
    const p = new URLSearchParams();
    if (filtroActual.depto)     p.set('depto', filtroActual.depto);
    if (filtroActual.provincia) p.set('provincia', filtroActual.provincia);
    if (filtroActual.distrito)  p.set('distrito', filtroActual.distrito);
    if (filtroEntidadActual)    p.set('entidad_id', filtroEntidadActual);
    // Siempre se manda (aunque estén los 3 tildados) para no depender de un
    // default del backend — si el usuario destilda todo, debe dar 0, no "todos".
    p.set('colores', nivelesAvisoSeleccionados());
    const qs = p.toString();
    return qs ? `?${qs}` : '';
}

function cambiarNivelesCapaRiesgo() {
    if (!capaRiesgoActiva) return;
    activarKPIsPorCapa(capaRiesgoActiva);
    cargarCapaRiesgoEnMapa(capaRiesgoActiva);
    actualizarTablaZonasPorCapa(capaRiesgoActiva);
    actualizarTablaEntidadesPorCapa(capaRiesgoActiva);
    actualizarTablaCultivosPorCapa(capaRiesgoActiva);
}

function activarKPIsPorCapa(nombre) {
    fetch(`/api/capas-riesgo/${nombre}/kpis${qsNiveles()}`)
        .then(r => r.json())
        .then(data => {
            if (modoPanel !== 'capas' || capaRiesgoActiva !== nombre) return;  // llegó tarde
            if (data.error) { console.warn('⚠️', data.error); return; }
            const elem = (id) => document.getElementById(id);
            // Totales vienen directo del endpoint de la capa (ya no dependen de
            // que se haya cargado un aviso antes — ese era el bug: entrar
            // directo a "Capas de Riesgo" dejaba Agr./Hectáreas/Póliza Totales en "-").
            const totalClientes = data.agricultores_totales || 0;
            const pct = totalClientes > 0 ? (data.total_expuestos / totalClientes * 100).toFixed(1) : 0;

            if (elem('kpi-agr-totales')) elem('kpi-agr-totales').textContent = totalClientes.toLocaleString('es-ES');
            if (elem('kpi-hectareas-totales')) elem('kpi-hectareas-totales').textContent = `${data.hectareas_totales.toLocaleString('es-ES', {minimumFractionDigits: 2, maximumFractionDigits: 2})} ha`;
            if (elem('kpi-poliza-total')) elem('kpi-poliza-total').textContent = `S/ ${data.poliza_total.toLocaleString('es-ES', {maximumFractionDigits: 0})}`;

            if (elem('kpi-agr-afectados')) elem('kpi-agr-afectados').textContent = data.total_expuestos.toLocaleString('es-ES');
            if (elem('kpi-porcentaje-afectacion')) elem('kpi-porcentaje-afectacion').textContent = `${pct}%`;
            if (elem('kpi-poliza-afectados')) elem('kpi-poliza-afectados').textContent = `S/ ${data.monto_expuesto.toLocaleString('es-ES', {maximumFractionDigits: 0})}`;
            if (elem('kpi-hectareas-afectadas')) elem('kpi-hectareas-afectadas').textContent = `${data.hectareas_expuestas.toLocaleString('es-ES', {minimumFractionDigits: 2, maximumFractionDigits: 2})} ha`;

            // Bloque "Estadísticas" del panel derecho (antes se quedaba en cero
            // en modo Capas: nada lo refrescaba al cambiar depto/provincia/distrito).
            if (elem('stat-agricultores')) elem('stat-agricultores').textContent = data.total_expuestos.toLocaleString('es-ES');
            if (elem('stat-poliza')) elem('stat-poliza').textContent = `S/ ${data.monto_expuesto.toLocaleString('es-ES', {maximumFractionDigits: 0})}`;
            if (elem('stat-hectareas')) elem('stat-hectareas').textContent = `${data.hectareas_expuestas.toLocaleString('es-ES', {minimumFractionDigits: 2, maximumFractionDigits: 2})} ha`;
            const nivelBadge = elem('stat-nivel');
            if (nivelBadge) {
                const niveles = nivelesCapaSeleccionados().split(',').filter(Boolean);
                nivelBadge.textContent = niveles.length === 4 || niveles.length === 0 ? 'TODOS' : niveles.join(' + ').toUpperCase();
                nivelBadge.className = 'badge-nivel ' + (
                    niveles.includes('Muy Alto') ? 'badge-rojo' :
                    niveles.includes('Alto') ? 'badge-naranja' :
                    niveles.includes('Medio') ? 'badge-amarillo' : 'badge-verde'
                );
            }
        })
        .catch(e => console.error('❌ Error activando KPIs por capa:', e));
}

function restaurarKPIsPorAviso() {
    if (avisoActual) cargarKPIsNuevos(avisoActual);
}

// Sin capa seleccionada (pero todavía en la pestaña "Capas de Riesgo"):
// las tablas no deben quedar con datos de la última capa vista.
function vaciarTablasCapaRiesgo() {
    const ph = (cols) => `<tr><td colspan="${cols}" class="text-center text-muted">Selecciona una capa</td></tr>`;
    const zonas = document.getElementById('tabla-zonas-body');
    const entidades = document.getElementById('tabla-entidades-body');
    const cultivos = document.getElementById('tabla-cultivos-body');
    if (zonas) zonas.innerHTML = ph(4);
    if (entidades) entidades.innerHTML = ph(5);
    if (cultivos) cultivos.innerHTML = ph(7);
}

// La ZONA de peligro en sí (polígono coloreado verde->rojo por severidad).
function cargarPoligonoCapaRiesgo(nombre) {
    if (capasRiesgoPoligonos[nombre]) {
        mapa.removeLayer(capasRiesgoPoligonos[nombre]);
        delete capasRiesgoPoligonos[nombre];
    }
    fetch(`/api/capas-riesgo/${nombre}/geometria`)
        .then(r => r.json())
        .then(geojson => {
            if (modoPanel !== 'capas' || capaRiesgoActiva !== nombre) return;  // llegó tarde
            if (geojson.error || !geojson.features) return;
            const layer = L.geoJSON(geojson, {
                style: (feature) => ({
                    fillColor: feature.properties.color_display || '#999',
                    fillOpacity: 0.5,
                    color: '#555',
                    weight: 0.3,
                    opacity: 0.4
                })
            }).bindTooltip(l => l.feature.properties.nivel_display || '', { sticky: true }).addTo(mapa);
            capasRiesgoPoligonos[nombre] = layer;
            // Puntos y aviso siempre encima del polígono de peligro
            if (clientesLayer) clientesLayer.bringToFront();
            if (geojsonLayer) geojsonLayer.bringToFront();
        })
        .catch(e => console.error(`❌ Error polígono capa ${nombre}:`, e));
}

// Nivel de cada cliente AFECTADO por la capa activa (id -> nivel), o null si
// no hay capa seleccionada. Se usa para repintar clientesLayer EN SU LUGAR
// (azul = afectado, plomo = no afectado) — pedido explícito, en vez de dibujar
// una capa de puntos aparte encima.
let clientesRiesgoCapaMap = null;

function cargarCapaRiesgoEnMapa(nombre) {
    fetch(`/api/capas-riesgo/${nombre}/clientes-geojson${qsNiveles()}`)
        .then(r => r.json())
        .then(geojson => {
            if (modoPanel !== 'capas' || capaRiesgoActiva !== nombre) return;  // llegó tarde
            clientesRiesgoCapaMap = new Map(
                (geojson.features || []).map(f => [f.properties.id, f.properties.nivel])
            );
            pintarClientesPorCapa();
        })
        .catch(e => console.error(`❌ Error geojson capa ${nombre}:`, e));
}

function pintarClientesPorCapa() {
    if (!clientesLayer || !clientesRiesgoCapaMap) return;
    // OJO: nunca llamar layer.bringToFront() dentro de este loop — con miles
    // de marcadores afectados (ej. Sequía = 5795) reordena el canvas esa
    // misma cantidad de veces seguidas y congela la pestaña ("página no
    // responde"). Un solo bringToFront() del layer completo al final alcanza.
    clientesLayer.eachLayer((layer) => {
        const id = layer.feature?.properties?.id;
        const nivel = clientesRiesgoCapaMap.get(id);
        if (nivel !== undefined) {
            pintarMarcadorCliente(layer, {
                radius: 6, fillColor: '#0066FF', color: '#003399',
                weight: 1.2, opacity: 1, fillOpacity: 0.9
            });
            layer.bindPopup(`<b>${layer.feature.properties.nombre || ''}</b><br>Nivel: ${nivel || '-'}`);
        } else {
            pintarMarcadorCliente(layer, {
                radius: 2, fillColor: '#999999', color: '#777777',
                weight: 0.3, opacity: 0.3, fillOpacity: 0.2
            });
            layer.unbindPopup();
        }
    });
    clientesLayer.bringToFront();
}

// Aplica un estilo Y lo guarda como "base" del marcador — el hover
// (mouseover/mouseout, ver cargarClientesMapa) lo lee para saber a qué
// volver al sacar el mouse, en vez de un tamaño fijo que borraba el color
// azul/plomo de afectado/no-afectado apenas se pasaba el mouse por encima.
function pintarMarcadorCliente(layer, estilo) {
    layer._estiloBase = estilo;
    layer.setStyle(estilo);
}

// Vuelve clientesLayer a su estado normal (todos azules) al salir de modo capas.
function restaurarColorClientesBase() {
    clientesRiesgoCapaMap = null;
    if (!clientesLayer) return;
    clientesLayer.eachLayer((layer) => {
        pintarMarcadorCliente(layer, {
            radius: 3, fillColor: '#0066FF', color: '#003399',
            weight: 0.5, opacity: 0.8, fillOpacity: 0.6
        });
        layer.unbindPopup();
    });
}

// Botón único al final del dashboard: descarga según el modo activo (aviso o
// capa) y aplica los MISMOS filtros que están puestos en pantalla (depto/
// provincia/distrito/entidad) — pedido explícito, no solo el cruce crudo.
function exportarCsvActual() {
    let url;
    if (modoPanel === 'avisos' && avisoActual) {
        url = `/api/avisos/${avisoActual}/exportar-csv`;
    } else if (modoPanel === 'capas' && capaRiesgoActiva) {
        url = `/api/capas-riesgo/${capaRiesgoActiva}/exportar-csv`;
    } else {
        alert('Selecciona un aviso o una capa de riesgo antes de descargar.');
        return;
    }

    const params = [];
    if (filtroActual.depto)     params.push(`depto=${encodeURIComponent(filtroActual.depto)}`);
    if (filtroActual.provincia) params.push(`provincia=${encodeURIComponent(filtroActual.provincia)}`);
    if (filtroActual.distrito)  params.push(`distrito=${encodeURIComponent(filtroActual.distrito)}`);
    if (filtroEntidadActual)    params.push(`entidad_id=${encodeURIComponent(filtroEntidadActual)}`);
    if (modoPanel === 'capas') {
        const niveles = nivelesCapaSeleccionados();
        if (niveles) params.push(`niveles=${encodeURIComponent(niveles)}`);
    } else if (modoPanel === 'avisos') {
        params.push(`colores=${encodeURIComponent(nivelesAvisoSeleccionados())}`);
    }
    if (params.length) url += '?' + params.join('&');

    window.location.href = url;
}

function actualizarEstadoBotonExportar() {
    const btn = document.getElementById('btn-exportar-csv-general');
    const hint = document.getElementById('exportar-csv-hint');
    if (!btn) return;
    const activo = (modoPanel === 'avisos' && !!avisoActual) || (modoPanel === 'capas' && !!capaRiesgoActiva);
    btn.disabled = !activo;
    if (hint) {
        hint.textContent = activo
            ? 'Se descargan los clientes con los filtros actuales (departamento/provincia/distrito/entidad si aplican).'
            : 'Selecciona un aviso o una capa de riesgo para poder descargar.';
    }
}

// ============================================================================
// MAPA LEAFLET
// ============================================================================

function inicializarMapa() {
    // Crear mapa centrado en Perú
    // preferCanvas: con ~12,342 puntos de clientes + capas de departamentos/
    // provincias/distritos, el renderer SVG por defecto crea un nodo DOM por
    // cada uno — cambiar depto/provincia/distrito recorre TODOS con setStyle()
    // y el navegador se traba. Canvas dibuja todo en un solo bitmap: mismo
    // código, mucho más rápido al re-pintar miles de marcadores.
    mapa = L.map('mapa-leaflet', { preferCanvas: true }).setView([-9.189, -75.0152], 5.5);
    
    // Igualar altura del mapa al panel derecho dinámicamente
    const panelDerecho = document.querySelector('.panel-derecho');
    const mapaDiv = document.getElementById('mapa-leaflet');

    function igualarAlturaMapa() {
        const panelH = panelDerecho ? panelDerecho.offsetHeight : 0;
        const nuevaAltura = Math.max(panelH, 600);
        mapaDiv.style.height = nuevaAltura + 'px';
        mapa.invalidateSize();
    }

    // Ejecutar al cargar y cuando el panel cambie de tamaño
    setTimeout(igualarAlturaMapa, 300);
    if (window.ResizeObserver && panelDerecho) {
        new ResizeObserver(igualarAlturaMapa).observe(panelDerecho);
    }
    mapa.invalidateSize();
    
    // Capa base
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap',
        maxZoom: 19
    }).addTo(mapa);
    
    // Cargar delimitaciones
    cargarCapasDelimitaciones();

    console.log('✅ Mapa inicializado');
}

function cargarCapaGeoJSON(numero) {
    if (modoPanel !== 'avisos') return;  // llegó tarde (carga en curso al cambiar de pestaña): ignorar
    if (geojsonLayer) {
        mapa.removeLayer(geojsonLayer);
    }

    console.log(`🗺️ Cargando SHP del aviso ${numero}`);

    fetch(`/api/avisos/${numero}/shp-geojson`)
        .then(r => r.json())
        .then(geojson => {
            if (modoPanel !== 'avisos') return;  // se cambió de pestaña mientras cargaba
            console.log(`✅ GeoJSON: ${geojson.features.length} features`);

            if (!geojson.features || geojson.features.length === 0) {
                console.warn('⚠️ No hay features');
                return;
            }
            
            // Filtrar verde (Nivel 1) = no renderizar
            const featuresFiltrados = geojson.features.filter(f => 
                f.properties.color !== '#90EE90'
            );
            
            console.log(`📊 Features después de filtro: ${featuresFiltrados.length}`);
            
            geojsonLayer = L.geoJSON({
                type: 'FeatureCollection',
                features: featuresFiltrados
            }, {
                style: (feature) => ({
                    fillColor: feature.properties.color,
                    fillOpacity: 0.55,
                    color: '#555',
                    weight: 0.4,
                    opacity: 0.6
                })
            }).addTo(mapa);
            
            if (geojsonLayer.getLayers().length > 0) {
                mapa.fitBounds(geojsonLayer.getBounds());
            }
            // Mantener orden: SHP encima de tiles, puntos encima del SHP
            if (clientesLayer) clientesLayer.bringToFront();
            console.log('✅ SHP renderizado:', featuresFiltrados.length, 'features');
        })
        .catch(e => console.error('❌ Error SHP:', e));
}

function cargarClientesMapa(numero) {
    if (clientesLayer) {
        mapa.removeLayer(clientesLayer);
    }
    
    // Cargar TODOS los clientes de la BD (no filtrar por aviso)
    console.log('👥 Cargando todos los clientes de la BD');
    
    fetch('/api/clientes/todos-geojson')
        .then(r => r.json())
        .then(geojson => {
            console.log(`✅ ${geojson.total} clientes totales en mapa`);
            
            clientesLayer = L.geoJSON(geojson, {
                pointToLayer: (feature, latlng) => {
                    const estiloBase = {
                        radius: 3, fillColor: '#0066FF', color: '#003399',
                        weight: 0.5, opacity: 0.8, fillOpacity: 0.6
                    };
                    const marker = L.circleMarker(latlng, estiloBase);
                    marker._estiloBase = estiloBase;

                    // El hover tiene que agrandar/resaltar el estilo ACTUAL del
                    // punto (afectado/no afectado según filtro), no un tamaño
                    // fijo — si no, al sacar el mouse se pierde el color/tamaño
                    // que le puso el filtro de aviso o capa.
                    marker.on('mouseover', function() {
                        const base = this._estiloBase || estiloBase;
                        this.setStyle({ ...base, radius: base.radius + 2, fillOpacity: 0.95 });
                    });

                    marker.on('mouseout', function() {
                        this.setStyle(this._estiloBase || estiloBase);
                    });

                    return marker;
                }
            }).addTo(mapa);
            
            // Mantener puntos siempre arriba
            clientesLayer.bringToFront();
            
            console.log('✅ Clientes renderizados en mapa');
        })
        .catch(e => console.error('❌ Error clientes:', e));
}

function cargarCapasDelimitaciones() {
    console.log('📍 Cargando delimitaciones ESTÁTICAS (departamentos + provincias)');
    
    // 1. Cargar DEPARTAMENTOS - ESTÁTICO (contorno grueso)
    fetch('/api/delimitaciones/departamentos')
        .then(r => r.json())
        .then(geojson => {
            const deptoLayer = L.geoJSON(geojson, {
                style: {
                    fillColor: 'transparent',
                    fillOpacity: 0,
                    color: '#333',
                    weight: 1.5,
                    opacity: 0.8
                },
                onEachFeature: (feature, layer) => {
                    const depto = (feature.properties.DEPARTAMEN || feature.properties.NAME || '').toUpperCase();
                    layer.deptoNombre = depto;
                    
                    layer.on('mouseover', () => {
                        layer.setStyle({color: '#FF6B6B', weight: 2.5});
                    });
                    layer.on('mouseout', () => {
                        layer.setStyle({color: '#333', weight: 1.5});
                    });
                    layer.on('click', () => {
                        // Seleccionar departamento en el filtro y aplicar zoom
                        const selectorDepto = document.getElementById('filtro-depto');
                        if (selectorDepto) {
                            selectorDepto.value = depto;
                            cambiarDepartamento();
                        }
                    });
                }
            }).addTo(mapa);
            
            delimitacionesLayers['departamentos'] = deptoLayer;
            
            // DEBUG: Listar todos los nombres asignados
            let nombresAsignados = [];
            deptoLayer.eachLayer((layer) => {
                nombresAsignados.push(layer.deptoNombre || 'SIN-NOMBRE');
            });
            console.log('✅ Departamentos cargados:', geojson.features?.length || 0);
            console.log('📋 Nombres en capa:', nombresAsignados.join(', '));
        })
        .catch(e => console.error('❌ Error depto:', e));
    
    // 2. Cargar PROVINCIAS - ESTÁTICO (contorno visible)
    fetch('/api/delimitaciones/provincias')
        .then(r => r.json())
        .then(geojson => {
            delimitacionesLayers['provinciasData'] = geojson; // Guardar data para zoom
            
            const provLayer = L.geoJSON(geojson, {
                style: {
                    fillColor: 'transparent',
                    fillOpacity: 0,
                    color: '#888',
                    weight: 1,
                    opacity: 0.7
                },
                onEachFeature: (feature, layer) => {
                    const prov = (feature.properties.PROVINCIA || '').toUpperCase();
                    const depto = (feature.properties.DEPARTAMEN || '').toUpperCase();
                    layer.provNombre = prov;
                    layer.deptoNombre = depto;
                    layer.on('mouseover', () => {
                        layer.setStyle({color: '#0066FF', weight: 2.5});
                    });
                    layer.on('mouseout', () => {
                        layer.setStyle({color: '#888', weight: 1});
                    });
                    layer.on('click', () => {
                        const selectorProv = document.getElementById('filtro-provincia');
                        if (selectorProv) {
                            selectorProv.value = prov;
                            cambiarProvincia();
                        }
                    });
                }
            });
            
            delimitacionesLayers['provincias'] = provLayer;
            console.log('✅ Provincias cargadas (NO visibles por defecto):', geojson.features?.length || 0);
        })
        .catch(e => console.error('❌ Error provincias:', e));
    
    // 3. Distritos - Solo guardar data para zoom (muy pesado para mostrar siempre)
    delimitacionesLayers['distritosData'] = null;
}

function filtrarYZoom(valor, layer) {
    // Zoom a la zona
    mapa.fitBounds(layer.getBounds());
    
    // Filtrar datos dinámicamente
    filtroActual.depto = valor;
    filtroActual.provincia = null;
    filtroActual.distrito = null;
    nivelSeleccionado = 'depto';
    
    actualizarDatos();
}

// ============================================================================
// AVISOS SELECTOR
// ============================================================================

function cargarAvisos() {
    console.log('🔍 Iniciando cargarAvisos()');
    
    fetch('/api/avisos')
        .then(response => {
            console.log('Status:', response.status);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return response.json();
        })
        .then(response => {
            console.log('Response:', response);
            const avisos = response.avisos || [];
            const selector = document.getElementById('filtro-aviso');
            
            if (!selector) {
                console.error('❌ Selector no encontrado');
                return;
            }
            
            if (!avisos || avisos.length === 0) {
                selector.innerHTML = '<option>-- Sin avisos --</option>';
                return;
            }
            
            console.log(`📊 Total de avisos cargados: ${avisos.length}`);
            
            // Solo avisos con SHP generado (mapa disponible)
            const conMapa = avisos.filter(a => a.tiene_shp === true);
            const totalAvisos = conMapa.length;
            console.log(`🗺️ Avisos con SHP disponible: ${totalAvisos}`);
            
            if (totalAvisos === 0) {
                selector.innerHTML = '<option value="">-- Sin avisos con mapa --</option>';
                return;
            }
            
            selector.innerHTML = '<option value="">-- Seleccionar Aviso --</option>' + 
                conMapa.map(a => 
                    `<option value="${a.numero}">Aviso ${a.numero} — ${a.titulo || a.color || ''}</option>`
                ).join('');
            
            // Mensaje de scroll si hay muchos
            if (totalAvisos > 100) {
                selector.title = `${totalAvisos} avisos disponibles - usa scroll para navegar`;
                console.log(`📊 ${totalAvisos} avisos. INSTRUCCIÓN: Usa scroll en el selector.`);
            } else {
                console.log(`📊 ${totalAvisos} avisos cargados`);
            }
            
            // ✅ CARGAR PRIMER AVISO AUTOMÁTICAMENTE
            if (conMapa.length > 0) {
                selector.value = conMapa[0].numero;
                console.log(`✅ Auto-cargando aviso ${conMapa[0].numero}`);
                cargarAviso();
            }
        })
        .catch(e => console.error('Error:', e));
}

function cargarAviso() {
    const selector = document.getElementById('filtro-aviso');
    if (!selector) {
        console.error('❌ Selector no encontrado');
        return;
    }
    
    const numero = selector.value;
    if (!numero) return;
    
    avisoActual = numero;

    // Resetear filtros
    filtroActual = { depto: null, provincia: null, distrito: null };
    filtroEntidadActual = null;
    nivelSeleccionado = 'nacional';
    actualizarEstadoBotonExportar();

    // Resetear selector entidad (solo el valor, no deshabilitar)
    const selEnt = document.getElementById('filtro-entidad');
    if (selEnt) { selEnt.value = ''; }

    // Resetear checkbox "Nivel de Riesgo" a los 3 tildados (Rojo+Naranja+Amarillo)
    document.querySelectorAll('#filtro-niveles-aviso input').forEach(el => { el.checked = true; });

    console.log(`📊 Cargando aviso ${numero}`);

    // Cargar datos en paralelo
    Promise.all([
        fetch(`/api/avisos/${numero}/clientes-afectados${qsFiltroZona()}`).then(r => r.json()).catch(e => {console.error('Error clientes:', e); return {};}),
        fetch(`/api/avisos/${numero}/estadisticas`).then(r => r.json()).catch(e => {console.error('Error stats:', e); return {};}),
        fetch(`/api/avisos/${numero}/shp-geojson`).then(r => r.json()).catch(e => {console.error('Error shp:', e); return {};}),
        fetch(`/api/avisos/${numero}/agregaciones`).then(r => r.json()).catch(e => {console.error('Error agregaciones:', e); return {};})
    ])
    .then(([clientesResp, statsResp, shpResp, agregacionesResp]) => {
        const clientes = clientesResp.clientes || clientesResp;
        const stats = statsResp;
        agregacionesData = agregacionesResp.agregaciones || {};
        agregacionesDataOriginal = agregacionesData;  // guardar copia original
        
        console.log('📋 Clientes cargados:', clientes);
        console.log('📊 Stats:', stats);
        console.log('📈 Agregaciones:', agregacionesData);
        
        // ✅ CARGAR KPIs (desde v_estadisticas_aviso)
        cargarKPIsNuevos(numero);
        
        actualizarEstadisticas(stats);
        
        // Actualizar TABLAS
        actualizarTablaZonas();
        actualizarTablaEntidades();
        actualizarTablaCultivos();
        
        // Poblar selector de departamentos con datos de agregaciones
        poblarSelectorDepartamentos();

        // Cargar selector de entidades (ya cargado en init, no repetir)
        // cargarSelectorEntidades();
        
        // Renderizar capa SHP del aviso
        cargarCapaGeoJSON(numero);
        // (los puntos de clientes ya están cargados desde el init)
        
        console.log('✅ Aviso cargado completamente');
    })
    .catch(e => console.error('❌ Error fatal:', e));
}

// ============================================================================
// ACTUALIZACIÓN DINÁMICA DE DATOS Y KPIs
// ============================================================================

function actualizarDatos() {
    // Modo "Capas de Riesgo": los 9 puntos que llaman actualizarDatos() (cambiar
    // depto/provincia/distrito/entidad) antes solo cubrían modo Avisos — en
    // Capas de Riesgo el bloque "Estadísticas" (panel derecho) se quedaba
    // siempre en cero porque nada lo refrescaba al filtrar. Bug real, no cosmético.
    if (modoPanel === 'capas' && capaRiesgoActiva) {
        cambiarNivelesCapaRiesgo();  // reusa el mismo refresco (KPIs+mapa+3 tablas) con los filtros actuales
    }

    if (!avisoActual) return;

    console.log('📊 Actualizando datos:', filtroActual);

    // Construir URL con filtros (incluye depto/provincia/distrito/entidad/colores)
    const url = `/api/avisos/${avisoActual}/clientes-afectados${qsFiltroZona()}`;

    // KPI superior: depto/prov/dist siguen sin afectarlo (estático por diseño,
    // es "todo el aviso"), pero el checkbox de colores sí lo recalcula.
    cargarKPIsNuevos(avisoActual);

    fetch(url)
        .then(r => r.json())
        .then(data => {
            // Estadísticas dinámicas del panel derecho (sí responden a TODOS
            // los filtros: depto/provincia/distrito/entidad/colores)
            actualizarEstadisticasDinamicas(data.clientes || {});
            actualizarTituloPanel();

            // FILTRAR PUNTOS EN MAPA según selección actual
            filtrarPuntosEnMapa(filtroActual.depto, filtroActual.provincia, filtroActual.distrito);
            
            // ACTUALIZAR TABLAS
            actualizarTablaZonas();
            actualizarTablaEntidades();
            actualizarTablaCultivos();
        })
        .catch(e => console.error('Error actualizando datos:', e));
}

/**
 * Filtra visualmente los puntos del mapa según el filtro activo.
 * Coincidentes: naranja grande | No coincidentes: gris tenue | Sin filtro: azul normal
 */
function filtrarPuntosEnMapa(depto, provincia, distrito) {
    if (!clientesLayer) return;

    const hayFiltro = depto || provincia || distrito;

    // OJO: nunca layer.bringToFront() dentro de este loop — con miles de
    // marcadores coincidentes reordena el canvas esa misma cantidad de veces
    // seguidas y congela la pestaña ("página no responde"). Un solo
    // bringToFront() del layer completo al final alcanza.
    clientesLayer.eachLayer((layer) => {
        const props = layer.feature?.properties || {};
        const pDepto = (props.departamento || '').toUpperCase().trim();
        const pProv  = (props.provincia   || '').toUpperCase().trim();
        const pDist  = (props.distrito    || '').toUpperCase().trim();
        const pEnt   = String(props.entidad_id ?? '');

        if (!hayFiltro && !filtroEntidadActual) {
            // Sin filtro: todos iguales azul
            pintarMarcadorCliente(layer, {
                radius: 3, fillColor: '#0066FF', color: '#003399',
                weight: 0.5, opacity: 0.8, fillOpacity: 0.6
            });
            return;
        }

        const matchEnt      = !filtroEntidadActual || String(filtroEntidadActual) === pEnt;
        const matchDepto    = !depto    || depto.toUpperCase().trim()    === pDepto;
        const matchProvincia = !provincia || provincia.toUpperCase().trim() === pProv;
        const matchDistrito  = !distrito  || distrito.toUpperCase().trim()  === pDist;
        const match = matchEnt && matchDepto && matchProvincia && matchDistrito;

        if (match) {
            pintarMarcadorCliente(layer, {
                radius: 7, fillColor: '#0066FF', color: '#003399',
                weight: 1.5, opacity: 1, fillOpacity: 0.95
            });
        } else {
            pintarMarcadorCliente(layer, {
                radius: 2, fillColor: '#BBBBBB', color: '#999999',
                weight: 0.3, opacity: 0.25, fillOpacity: 0.15
            });
        }
    });
    clientesLayer.bringToFront();

    console.log(`🎯 Puntos filtrados en mapa: depto=${depto} prov=${provincia} dist=${distrito}`);
}

function actualizarTituloPanel() {
    const panelTitle = document.querySelector('.estadisticas-card h5');
    if (!panelTitle) return;
    
    const niveles = {
        'nacional': 'INFORMACIÓN NACIONAL',
        'depto': `DEPARTAMENTO: ${filtroActual.depto}`,
        'provincia': `PROVINCIA: ${filtroActual.provincia}`,
        'distrito': `DISTRITO: ${filtroActual.distrito}`
    };
    
    panelTitle.textContent = niveles[nivelSeleccionado];
}

// ============================================================================
// ACTUALIZAR UI
// ============================================================================

function cargarKPIsNuevos(numero) {
    /**
     * Carga KPIs desde el nuevo endpoint /api/avisos/<numero>/kpis
     * Actualiza la sección superior con los nuevos campos
     */
    if (modoPanel !== 'avisos') return;  // llegó tarde (carga en curso al cambiar de pestaña): ignorar
    console.log(`📊 Cargando KPIs para aviso ${numero}`);

    fetch(`/api/avisos/${numero}/kpis${qsFiltroZona()}`)
        .then(r => r.json())
        .then(data => {
            if (modoPanel !== 'avisos') return;  // se cambió de pestaña mientras cargaba
            console.log('✅ KPIs recibidos:', data);
            
            const elem = (id) => document.getElementById(id);
            
            // Agricultores
            if (elem('kpi-agr-totales')) {
                elem('kpi-agr-totales').textContent = data.agricultores_totales.toLocaleString('es-ES');
            }
            if (elem('kpi-agr-afectados')) {
                elem('kpi-agr-afectados').textContent = data.agricultores_afectados.toLocaleString('es-ES');
            }
            
            // Porcentaje
            if (elem('kpi-porcentaje-afectacion')) {
                elem('kpi-porcentaje-afectacion').textContent = `${data.porcentaje_afectacion}%`;
            }
            
            // Pólizas
            if (elem('kpi-poliza-total')) {
                const polizaTotal = `S/ ${(data.poliza_total).toLocaleString('es-ES', {maximumFractionDigits: 0})}`;
                elem('kpi-poliza-total').textContent = polizaTotal;
            }
            if (elem('kpi-poliza-afectados')) {
                const polizaAfectados = `S/ ${(data.poliza_afectados).toLocaleString('es-ES', {maximumFractionDigits: 0})}`;
                elem('kpi-poliza-afectados').textContent = polizaAfectados;
            }
            
            // Hectáreas
            if (elem('kpi-hectareas-totales')) {
                elem('kpi-hectareas-totales').textContent = `${data.hectareas_totales.toLocaleString('es-ES', {minimumFractionDigits: 2, maximumFractionDigits: 2})} ha`;
            }
            if (elem('kpi-hectareas-afectadas')) {
                elem('kpi-hectareas-afectadas').textContent = `${data.hectareas_afectadas.toLocaleString('es-ES', {minimumFractionDigits: 2, maximumFractionDigits: 2})} ha`;
            }
            
            // Guardar datos de zonas por color para usar en tablas
            if (data.zonas_por_color) {
                window.zonasColorData = data.zonas_por_color;
            }
            
            console.log('✅ KPIs nuevos renderizados');
        })
        .catch(e => {
            console.error('❌ Error cargando KPIs:', e);
            // Mostrar valores por defecto
            const elem = (id) => document.getElementById(id);
            ['kpi-agr-totales', 'kpi-agr-afectados', 'kpi-porcentaje-afectacion', 
             'kpi-poliza-total', 'kpi-poliza-afectados', 'kpi-hectareas-totales', 
             'kpi-hectareas-afectadas'].forEach(id => {
                if (elem(id)) elem(id).textContent = '-';
            });
        });
}

function actualizarEstadisticas(stats) {
    const elem = (id) => document.getElementById(id);
    if (!stats) {
        console.warn('⚠️ Stats vacío');
        return;
    }
    
    // Nivel badge
    const nivelBadge = elem('stat-nivel');
    if (nivelBadge) {
        const color = stats.color?.toLowerCase() || 'sin_color';
        if (color === 'rojo') {
            nivelBadge.textContent = 'RIESGO EXTREMO';
            nivelBadge.className = 'badge-nivel badge-rojo';
        } else if (color === 'naranja') {
            nivelBadge.textContent = 'RIESGO ALTO';
            nivelBadge.className = 'badge-nivel badge-naranja';
        } else if (color === 'amarillo') {
            nivelBadge.textContent = 'RIESGO MEDIO';
            nivelBadge.className = 'badge-nivel badge-amarillo';
        } else if (color === 'verde') {
            nivelBadge.textContent = 'RIESGO BAJO';
            nivelBadge.className = 'badge-nivel badge-verde';
        } else {
            nivelBadge.textContent = 'SIN CLASIFICAR';
            nivelBadge.className = 'badge-nivel badge-sin-nivel';
        }
    }
    
    // Estadísticas de la tarjeta derecha
    const agr = stats.agricultores_total || 0;
    const pol = stats.poliza_total || 0;
    const ha = stats.hectareas_total || 0;
    
    if (elem('stat-agricultores')) {
        elem('stat-agricultores').textContent = agr > 0 ? agr.toLocaleString('es-ES') : '0';
    }
    if (elem('stat-poliza')) {
        elem('stat-poliza').textContent = pol > 0 ? `S/ ${pol.toLocaleString('es-ES', {maximumFractionDigits: 0})}` : 'S/ 0';
    }
    if (elem('stat-hectareas')) {
        elem('stat-hectareas').textContent = ha > 0 ? ha.toLocaleString('es-ES') : '0';
    }
    
    console.log('✅ Estadísticas actualizadas');
}

/**
 * ESTADÍSTICAS DINÁMICAS - Se actualizan con filtros (panel derecho)
 * Los KPIs superiores son ESTÁTICOS (todo el aviso)
 */
function actualizarEstadisticasDinamicas(clientes) {
    const elem = (id) => document.getElementById(id);
    
    // Valores dinámicos del filtro actual
    const agr = clientes.total_agricultores || 0;
    const pol = clientes.total_monto_asegurado || 0;
    const ha = clientes.total_hectareas || 0;
    
    // DEBUG: Ver valor exacto de póliza
    console.log(`💰 Póliza RAW: ${pol}, Tipo: ${typeof pol}, Dividido entre 1M: ${pol/1e6}`);
    
    // Solo actualizar panel derecho (estadísticas dinámicas)
    if (elem('stat-agricultores')) {
        elem('stat-agricultores').textContent = agr > 0 ? agr.toLocaleString('es-ES') : '0';
    }
    if (elem('stat-poliza')) {
        elem('stat-poliza').textContent = pol > 0 ? `S/ ${pol.toLocaleString('es-ES', {maximumFractionDigits: 2})}` : 'S/ 0';
    }
    if (elem('stat-hectareas')) {
        elem('stat-hectareas').textContent = ha > 0 ? ha.toLocaleString('es-ES') : '0';
    }
    
    console.log('📊 Estadísticas DINÁMICAS actualizadas:', {agr, ha, pol: (pol/1e6).toFixed(2) + 'M'});
}

function mostrarInfoHover(depto, provincia, distrito) {
    // Ejemplo de función para mostrar info al pasar mouse en zonas
    const infoDiv = document.getElementById('info-hover');
    const infoContent = document.getElementById('info-hover-content');
    
    const html = `
        <div style="font-size: 12px;">
            <div><strong>${depto}</strong></div>
            <div>${provincia} → ${distrito}</div>
            <div style="margin-top: 0.5rem; padding-top: 0.5rem; border-top: 1px solid #ddd;">
                <small>Agricultores: <strong>N/A</strong></small><br>
                <small>Hectáreas: <strong>N/A</strong></small>
            </div>
        </div>
    `;
    
    infoContent.innerHTML = html;
    infoDiv.style.display = 'block';
}

function ocultarInfoHover() {
    const infoDiv = document.getElementById('info-hover');
    infoDiv.style.display = 'none';
}

// Renderer compartido: recibe un dict {nivel: {agricultores,hectareas,poliza|monto}}
// y el orden/iconos a usar — lo llaman tanto Avisos como Capas de Riesgo.
function renderTablaZonas(zonasDict, ordenNiveles, iconos, claseFilaFn) {
    const tbody = document.getElementById('tabla-zonas-body');
    if (!tbody) return;

    let html = '';
    for (const nivel of ordenNiveles) {
        const zona = zonasDict[nivel];
        if (!zona) continue;
        const agr_total = zona.agricultores || 0;
        const ha_total = zona.hectareas || 0;
        const poliza_total = zona.poliza ?? zona.monto ?? 0;
        const fila_class = claseFilaFn ? claseFilaFn(nivel) : '';

        html += `
            <tr class="${fila_class}">
                <td>${iconos[nivel] || ''} ${nivel}</td>
                <td><strong>${agr_total}</strong></td>
                <td>${ha_total.toLocaleString('es-ES', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                <td>S/ ${poliza_total.toLocaleString('es-ES', {maximumFractionDigits: 0})}</td>
            </tr>
        `;
    }
    tbody.innerHTML = html || '<tr><td colspan="4" class="text-center text-muted">Sin datos</td></tr>';
}

function actualizarTablaZonas() {
    if (!avisoActual) return;
    console.log('📊 Actualizando Tabla Zonas para aviso:', avisoActual);

    // /zonas (no /kpis) — /kpis es el KPI superior, deliberadamente estático
    // para todo el aviso; esta tabla sí debe respetar el filtro de pantalla.
    fetch(`/api/avisos/${avisoActual}/zonas${qsFiltroZona()}`)
        .then(r => r.json())
        .then(data => {
            if (modoPanel !== 'avisos') return;
            if (data.error) { console.error('Error:', data.error); return; }
            renderTablaZonas(
                data.zonas_por_color || {},
                ['Rojo', 'Naranja', 'Amarillo', 'Verde'],
                { 'Rojo': '🔴', 'Naranja': '🟠', 'Amarillo': '🟡', 'Verde': '🟢' },
                (nivel) => `zona-${nivel.toLowerCase()}`
            );
            console.log('✅ Tabla Zonas actualizada con datos KPI');
        })
        .catch(e => console.error('Error actualizando tabla zonas:', e));
}

function actualizarTablaZonasPorCapa(nombre) {
    fetch(`/api/capas-riesgo/${nombre}/zonas${qsNiveles()}`)
        .then(r => r.json())
        .then(data => {
            if (modoPanel !== 'capas' || capaRiesgoActiva !== nombre) return;
            if (data.error) { console.error('Error:', data.error); return; }
            renderTablaZonas(
                // Niveles estandarizados (ver routes/capas_riesgo.py::_nivel_estandar) — siempre
                // Muy Alto/Alto/Medio/Bajo; "Expuesto" queda de fallback para capas sin categoría.
                data.zonas || {},
                ['Muy Alto', 'Alto', 'Medio', 'Bajo', 'Expuesto'],
                { 'Muy Alto': '🔴', 'Alto': '🟠', 'Medio': '🟡', 'Bajo': '🟢', 'Expuesto': '🔵' }
            );
        })
        .catch(e => console.error(`Error tabla zonas capa ${nombre}:`, e));
}

function renderTablaEntidades(entidades) {
    const tbody = document.getElementById('tabla-entidades-body');
    if (!tbody) return;

    let html = '';
    for (const ent of entidades) {
        const agr_afect  = ent.agricultores  || 0;
        const total_ent  = ent.total_entidad || 0;
        const ha_afect   = ent.hectareas     || 0;
        const monto_afect = ent.monto        || 0;
        const pct        = ent.pct_damage    || 0;

        let badgeColor = '#28a745';       // verde < 20%
        if      (pct >= 50) badgeColor = '#dc3545';   // rojo
        else if (pct >= 30) badgeColor = '#fd7e14';   // naranja
        else if (pct >= 20) badgeColor = '#ffc107';   // amarillo

        html += `
            <tr>
                <td><strong>${ent.nombre}</strong></td>
                <td>${agr_afect}</td>
                <td>${ha_afect.toLocaleString('es-ES', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                <td>S/ ${monto_afect.toLocaleString('es-ES', {maximumFractionDigits: 0})}</td>
                <td>
                    <span class="badge"
                          style="background-color:${badgeColor}; color:#fff; cursor:default;"
                          title="${agr_afect} afectados de ${total_ent} clientes totales de esta entidad">
                        ${pct}%
                    </span>
                </td>
            </tr>
        `;
    }
    tbody.innerHTML = html || '<tr><td colspan="5" class="text-center text-muted">Sin datos de entidades afectadas</td></tr>';
}

function actualizarTablaEntidades() {
    if (!avisoActual) return;
    console.log('📊 Actualizando Tabla Entidades para aviso:', avisoActual);

    fetch(`/api/avisos/${avisoActual}/kpis-entidades${qsFiltroZona()}`)
        .then(r => r.json())
        .then(data => {
            if (modoPanel !== 'avisos') return;
            if (data.error) { console.error('Error:', data.error); return; }
            renderTablaEntidades(data.entidades || []);
            console.log('✅ Tabla Entidades actualizada');
        })
        .catch(e => console.error('Error actualizando tabla entidades:', e));
}

function actualizarTablaEntidadesPorCapa(nombre) {
    fetch(`/api/capas-riesgo/${nombre}/entidades${qsNiveles()}`)
        .then(r => r.json())
        .then(data => {
            if (modoPanel !== 'capas' || capaRiesgoActiva !== nombre) return;
            if (data.error) { console.error('Error:', data.error); return; }
            renderTablaEntidades(data.entidades || []);
        })
        .catch(e => console.error(`Error tabla entidades capa ${nombre}:`, e));
}

function renderTablaCultivos(cultivos) {
    const tbody = document.getElementById('tabla-cultivos-body');
    if (!tbody) return;

    let html = '';
    cultivos.forEach((cult, i) => {
                const agr       = cult.agricultores  || 0;
                const total     = cult.total_cultivo || 0;
                const ha        = cult.hectareas     || 0;
                const monto     = cult.monto         || 0;
                const pct       = cult.pct_damage    || 0;
                const nombre    = cult.cultivo_nombre || 'SIN CULTIVO';
                const deptos    = cult.departamentos  || '-';
                const rank      = i + 1;  // solo número

                let barColor = '#28a745';
                if      (pct >= 50) barColor = '#dc3545';
                else if (pct >= 30) barColor = '#fd7e14';
                else if (pct >= 20) barColor = '#ffc107';

                html += `
                    <tr>
                        <td class="text-center fw-bold">${rank}</td>
                        <td><strong>${nombre}</strong></td>
                        <td class="text-center">${agr}</td>
                        <td>
                            <div class="d-flex align-items-center gap-1">
                                <div style="flex:1; background:#e9ecef; border-radius:4px; height:8px; min-width:50px;">
                                    <div style="width:${Math.min(pct,100)}%; background:${barColor}; height:8px; border-radius:4px;"></div>
                                </div>
                                <span class="badge" style="background:${barColor}; color:#fff; min-width:46px;"
                                      title="${agr} afectados de ${total} agricultores con este cultivo">${pct}%</span>
                            </div>
                        </td>
                        <td class="text-end">${ha.toLocaleString('es-ES', {minimumFractionDigits: 2, maximumFractionDigits: 2})} ha</td>
                        <td class="text-end">S/ ${monto.toLocaleString('es-ES', {maximumFractionDigits: 0})}</td>
                        <td style="font-size:11px; color:#555;">${deptos}</td>
                    </tr>
                `;
    });
    tbody.innerHTML = html || '<tr><td colspan="7" class="text-center text-muted">Sin datos de cultivos afectados</td></tr>';
}

function actualizarTablaCultivos() {
    if (!avisoActual) return;
    console.log('🌾 Actualizando Tabla Cultivos para aviso:', avisoActual);

    fetch(`/api/avisos/${avisoActual}/kpis-cultivos${qsFiltroZona()}`)
        .then(r => r.json())
        .then(data => {
            if (modoPanel !== 'avisos') return;
            if (data.error) { console.error('Error:', data.error); return; }
            renderTablaCultivos(data.cultivos || []);
            console.log('✅ Tabla Cultivos actualizada con', (data.cultivos || []).length, 'registros');
        })
        .catch(e => console.error('Error actualizando tabla cultivos:', e));
}

function actualizarTablaCultivosPorCapa(nombre) {
    fetch(`/api/capas-riesgo/${nombre}/cultivos${qsNiveles()}`)
        .then(r => r.json())
        .then(data => {
            if (modoPanel !== 'capas' || capaRiesgoActiva !== nombre) return;
            if (data.error) { console.error('Error:', data.error); return; }
            renderTablaCultivos(data.cultivos || []);
        })
        .catch(e => console.error(`Error tabla cultivos capa ${nombre}:`, e));
}

// ============================================================================
// FUNCIONES DE VISUALIZACIÓN DE CAPAS
// ============================================================================

function mostrarDistritosDelimitacion(depto, provincia) {
    console.log(`🗺️ Mostrando distritos de ${provincia}/${depto}`);
    
    const distritosData = delimitacionesLayers['distritosData'];
    if (!distritosData) return;
    
    // Filtrar distritos de la provincia
    const distritosFiltered = {
        type: 'FeatureCollection',
        features: distritosData.features.filter(f => 
            (f.properties?.PROVINCIA || '').toUpperCase() === provincia.toUpperCase() &&
            (f.properties?.DEPARTAMEN || '').toUpperCase() === depto.toUpperCase()
        )
    };
    
    // Limpiar distritos anteriores si existen
    if (delimitacionesLayers['distritosDelimitacion']) {
        mapa.removeLayer(delimitacionesLayers['distritosDelimitacion']);
    }
    
    // Crear capa de distritos
    const distritosLayer = L.geoJSON(distritosFiltered, {
        style: {
            fillColor: 'transparent',
            fillOpacity: 0,
            color: '#FFFFFF',
            weight: 1.5,
            opacity: 0.8
        },
        onEachFeature: (feature, layer) => {
            const dist = (feature.properties.DISTRITO || '').toUpperCase();
            layer.distNombre = dist;
            
            layer.on('mouseover', () => {
                layer.setStyle({color: '#FFFFFF', weight: 2.5, fillOpacity: 0});
            });
            layer.on('mouseout', () => {
                layer.setStyle({color: '#FFFFFF', weight: 1.5, fillOpacity: 0});
            });
            layer.on('click', () => {
                const selectorDist = document.getElementById('filtro-distrito');
                if (selectorDist) {
                    selectorDist.value = dist;
                    cambiarDistrito();
                }
            });
        }
    }).addTo(mapa);
    
    delimitacionesLayers['distritosDelimitacion'] = distritosLayer;
    console.log(`✅ Distritos mostrados: ${distritosFiltered.features.length}`);
}

// ============================================================================
// SELECCIÓN JERÁRQUICA: DEPTO → PROVINCIA → DISTRITO
// ============================================================================

function cargarSelectorEntidades() {
    const sel = document.getElementById('filtro-entidad');
    if (!sel) return;
    fetch('/api/entidades')
        .then(r => r.json())
        .then(data => {
            // el endpoint devuelve {data:[...], success:true}
            const entidades = Array.isArray(data) ? data : (data.data || data.entidades || []);
            sel.innerHTML = '<option value="">-- Todas las Entidades --</option>' +
                entidades.map(e => `<option value="${e.id}">${e.nombre}</option>`).join('');
            sel.disabled = false;
            console.log(`🏦 Selector entidades poblado: ${entidades.length} entidades`);
        })
        .catch(e => console.error('Error cargando entidades:', e));
}

function cambiarEntidad() {
    const sel = document.getElementById('filtro-entidad');
    const entidadId = sel ? (sel.value || null) : null;
    filtroEntidadActual = entidadId;

    // Resetear filtros de zona
    filtroActual = { depto: null, provincia: null, distrito: null };
    nivelSeleccionado = 'nacional';
    const selectorDepto = document.getElementById('filtro-depto');
    const selectorProv  = document.getElementById('filtro-provincia');
    const selectorDist  = document.getElementById('filtro-distrito');
    if (selectorDist) { selectorDist.innerHTML = '<option value="">-- Selecciona Provincia --</option>'; selectorDist.disabled = true; }
    if (selectorProv)  { selectorProv.innerHTML  = '<option value="">-- Selecciona Departamento --</option>'; selectorProv.disabled = true; }

    if (!entidadId) {
        // Volver a mostrar todos los deptos de la agregacion original
        poblarSelectorDepartamentos();
        filtrarPuntosEnMapa(null, null, null);
        actualizarDatos();
        return;
    }

    // Filtrar deptos/provincias/distritos disponibles para esta entidad
    // usando las propiedades de los features ya cargados en clientesLayer
    const deptos = {};
    if (clientesLayer) {
        clientesLayer.eachLayer((layer) => {
            const p = layer.feature?.properties || {};
            if (String(p.entidad_id) !== String(entidadId)) return;
            const dep = (p.departamento || '').toUpperCase().trim();
            const pro = (p.provincia   || '').toUpperCase().trim();
            const dis = (p.distrito    || '').toUpperCase().trim();
            if (!dep) return;
            if (!deptos[dep]) deptos[dep] = { provincias: {} };
            if (pro) {
                if (!deptos[dep].provincias[pro]) deptos[dep].provincias[pro] = { distritos: {} };
                if (dis) deptos[dep].provincias[pro].distritos[dis] = true;
            }
        });
    }

    // Poblar selector depto filtrado por entidad
    if (selectorDepto) {
        const listaDeptos = Object.keys(deptos).sort();
        selectorDepto.innerHTML = '<option value="">-- Todos los Departamentos --</option>' +
            listaDeptos.map(d => `<option value="${d}">${d}</option>`).join('');
    }

    // Guardar data filtrada para que cambiarDepartamento use
    agregacionesData = deptos;

    filtrarPuntosEnMapa(null, null, null);
    actualizarDatos();
    console.log(`🏦 Entidad seleccionada: ${sel.options[sel.selectedIndex]?.text} (id=${entidadId})`);
}

function poblarSelectorDepartamentos() {
    const selector = document.getElementById('filtro-depto');
    if (!selector) return;
    
    // Obtener departamentos de agregacionesData
    const deptos = Object.keys(agregacionesData).sort();
    
    selector.innerHTML = '<option value="">-- Todos los Departamentos --</option>' +
        deptos.map(d => `<option value="${d}">${d}</option>`).join('');
    
    console.log(`📍 Selector departamentos poblado: ${deptos.length} opciones`);
}

function cambiarDepartamento() {
    const selectorDepto = document.getElementById('filtro-depto');
    const selectorProv = document.getElementById('filtro-provincia');
    const selectorDist = document.getElementById('filtro-distrito');
    
    const deptoSeleccionado = selectorDepto.value;
    
    // Resetear filtros inferiores
    filtroActual.depto = deptoSeleccionado || null;
    filtroActual.provincia = null;
    filtroActual.distrito = null;
    
    // Resetear selectores inferiores
    selectorDist.innerHTML = '<option value="">-- Primero seleccione Provincia --</option>';
    selectorDist.disabled = true;
    
    if (!deptoSeleccionado) {
        // Volver a nacional
        nivelSeleccionado = 'nacional';
        selectorProv.innerHTML = '<option value="">-- Primero seleccione Departamento --</option>';
        selectorProv.disabled = true;
        actualizarDatos();
        return;
    }
    
    // Poblar provincias del departamento seleccionado
    const provincias = Object.keys(agregacionesData[deptoSeleccionado]?.provincias || {}).sort();
    
    selectorProv.innerHTML = '<option value="">-- Todas las Provincias --</option>' +
        provincias.map(p => `<option value="${p}">${p}</option>`).join('');
    selectorProv.disabled = false;
    
    nivelSeleccionado = 'depto';
    console.log(`📍 Depto seleccionado: ${deptoSeleccionado}, ${provincias.length} provincias disponibles`);
    
    // MANTENER departamentos VISIBLES pero resaltar el seleccionado
    const deptoLayer = delimitacionesLayers['departamentos'];
    if (deptoLayer) {
        const buscado = deptoSeleccionado.toUpperCase().trim();
        deptoLayer.eachLayer((layer) => {
            const nombre = (layer.deptoNombre || '').toUpperCase().trim();
            if (nombre === buscado) {
                // Resaltar depto seleccionado - SIN RESTAURAR ANTES
                layer.setStyle({color: '#FF0000', weight: 3, fillOpacity: 0.1});
                delimitacionesLayers['deptoDestacado'] = layer;
            } else {
                // Deptos no seleccionados: muy tenue
                layer.setStyle({color: '#CCCCCC', weight: 0.5, fillOpacity: 0});
            }
        });
    }
    
    // MOSTRAR provincias
    if (delimitacionesLayers['provincias']) {
        mapa.addLayer(delimitacionesLayers['provincias']);
    }
    
    // Asegurar SHP atrás
    if (geojsonLayer) {
        geojsonLayer.bringToBack();
    }
    
    // MANTENER puntos GPS siempre arriba (después de agregar provincias)
    if (clientesLayer) {
        clientesLayer.bringToFront();
    }
    
    // Zoom al departamento en el mapa
    zoomADepartamento(deptoSeleccionado);
    
    actualizarDatos();
}

function cambiarProvincia() {
    const selectorDepto = document.getElementById('filtro-depto');
    const selectorProv = document.getElementById('filtro-provincia');
    const selectorDist = document.getElementById('filtro-distrito');
    
    const deptoSeleccionado = selectorDepto.value;
    const provSeleccionada = selectorProv.value;
    
    // Actualizar filtros
    filtroActual.provincia = provSeleccionada || null;
    filtroActual.distrito = null;
    
    if (!provSeleccionada) {
        // Volver a nivel depto
        nivelSeleccionado = 'depto';
        selectorDist.innerHTML = '<option value="">-- Primero seleccione Provincia --</option>';
        selectorDist.disabled = true;
        actualizarDatos();
        return;
    }
    
    // Poblar distritos de la provincia seleccionada
    const distritos = Object.keys(
        agregacionesData[deptoSeleccionado]?.provincias[provSeleccionada]?.distritos || {}
    ).sort();
    
    selectorDist.innerHTML = '<option value="">-- Todos los Distritos --</option>' +
        distritos.map(d => `<option value="${d}">${d}</option>`).join('');
    selectorDist.disabled = false;
    
    nivelSeleccionado = 'provincia';
    console.log(`📍 Provincia seleccionada: ${provSeleccionada}, ${distritos.length} distritos disponibles`);
    
    // MANTENER depto resaltado - OCULTAR otras provincias - MOSTRAR distritos
    if (delimitacionesLayers['provincias']) {
        const buscadoProv = provSeleccionada.toUpperCase().trim();
        const buscadoDepto = deptoSeleccionado.toUpperCase().trim();
        
        delimitacionesLayers['provincias'].eachLayer((layer) => {
            const nombreProv = (layer.provNombre || '').toUpperCase().trim();
            const nombreDepto = (layer.deptoNombre || '').toUpperCase().trim();
            
            if (nombreProv === buscadoProv && nombreDepto === buscadoDepto) {
                // Resaltar provincia seleccionada - SIN RELLENO
                layer.setStyle({color: '#0066FF', weight: 3, fillOpacity: 0});
                delimitacionesLayers['provinciaDestacada'] = layer;
            } else {
                // Otras provincias: muy tenue
                layer.setStyle({color: '#DDDDDD', weight: 0.5, fillOpacity: 0});
            }
        });
    }
    
    // Cargar y mostrar distritos de la provincia
    if (!delimitacionesLayers['distritosData']) {
        fetch('/api/delimitaciones/distritos')
            .then(r => r.json())
            .then(geojson => {
                delimitacionesLayers['distritosData'] = geojson;
                mostrarDistritosDelimitacion(deptoSeleccionado, provSeleccionada);
                // Mantener puntos arriba después de cargar distritos
                if (geojsonLayer) {
                    geojsonLayer.bringToBack();
                }
                if (clientesLayer) {
                    clientesLayer.bringToFront();
                }
            })
            .catch(e => console.error('Error distritos:', e));
    } else {
        mostrarDistritosDelimitacion(deptoSeleccionado, provSeleccionada);
        // Mantener puntos arriba después de mostrar distritos
        if (geojsonLayer) {
            geojsonLayer.bringToBack();
        }
        if (clientesLayer) {
            clientesLayer.bringToFront();
        }
    }
    
    // Asegurar SHP atrás
    if (geojsonLayer) {
        geojsonLayer.bringToBack();
    }
    
    // Zoom a la provincia en el mapa
    zoomAProvincia(deptoSeleccionado, provSeleccionada);
    
    actualizarDatos();
}

function cambiarDistrito() {
    const selectorDepto = document.getElementById('filtro-depto');
    const selectorProv = document.getElementById('filtro-provincia');
    const selectorDist = document.getElementById('filtro-distrito');
    const distSeleccionado = selectorDist.value;
    
    filtroActual.distrito = distSeleccionado || null;
    nivelSeleccionado = distSeleccionado ? 'distrito' : 'provincia';
    
    console.log(`📍 Distrito seleccionado: ${distSeleccionado || 'ninguno'}`);
    
    // MANTENER provincia resaltada - MOSTRAR/OCULTAR distritos
    if (distSeleccionado && filtroActual.depto && filtroActual.provincia) {
        // Resaltar el distrito seleccionado
        if (delimitacionesLayers['distritosDelimitacion']) {
            const buscadoDist = distSeleccionado.toUpperCase().trim();
            delimitacionesLayers['distritosDelimitacion'].eachLayer((layer) => {
                const nombreDist = (layer.distNombre || '').toUpperCase().trim();
                if (nombreDist === buscadoDist) {
                    // Resaltar SOLO CON LÍNEA BLANCA - SIN RELLENO
                    layer.setStyle({color: '#FFFFFF', weight: 2.5, fillOpacity: 0});
                    delimitacionesLayers['distritoDestacado'] = layer;
                } else {
                    layer.setStyle({color: '#DDDDDD', weight: 0.5, fillOpacity: 0});
                }
            });
        }
        
        // Asegurar SHP y puntos en orden correcto
        if (geojsonLayer) {
            geojsonLayer.bringToBack();
        }
        if (clientesLayer) {
            clientesLayer.bringToFront();
        }
        
        zoomADistrito(filtroActual.depto, filtroActual.provincia, distSeleccionado);
    } else {
        // Resetear distritos a estilo normal
        if (delimitacionesLayers['distritosDelimitacion']) {
            delimitacionesLayers['distritosDelimitacion'].eachLayer((layer) => {
                layer.setStyle({color: '#FFFFFF', weight: 1.5, fillOpacity: 0});
            });
        }
    }
    
    actualizarDatos();
}

function limpiarFiltros() {
    // Resetear filtros
    filtroActual = { depto: null, provincia: null, distrito: null };
    filtroEntidadActual = null;
    nivelSeleccionado = 'nacional';

    // Resetear selector entidad
    const selEnt = document.getElementById('filtro-entidad');
    if (selEnt) selEnt.value = '';

    // Restaurar agregaciones originales (sin filtro de entidad)
    agregacionesData = agregacionesDataOriginal;
    poblarSelectorDepartamentos();
    
    // Resetear estilos de delimitaciones
    if (delimitacionesLayers['departamentos']) {
        delimitacionesLayers['departamentos'].eachLayer(l => {
            l.setStyle({color: '#333', weight: 1.5, fillOpacity: 0});
        });
        mapa.addLayer(delimitacionesLayers['departamentos']);
    }
    if (delimitacionesLayers['provincias']) {
        delimitacionesLayers['provincias'].eachLayer(l => {
            l.setStyle({color: '#888', weight: 1, fillOpacity: 0});
        });
        mapa.removeLayer(delimitacionesLayers['provincias']);
    }
    if (delimitacionesLayers['distritosDelimitacion']) {
        mapa.removeLayer(delimitacionesLayers['distritosDelimitacion']);
        delimitacionesLayers['distritosDelimitacion'] = null;
    }
    if (delimitacionesLayers['distritoActual']) {
        mapa.removeLayer(delimitacionesLayers['distritoActual']);
        delimitacionesLayers['distritoActual'] = null;
    }
    
    // Resetear selectores
    const selectorDepto = document.getElementById('filtro-depto');
    const selectorProv = document.getElementById('filtro-provincia');
    const selectorDist = document.getElementById('filtro-distrito');
    
    if (selectorDepto) selectorDepto.value = '';
    if (selectorProv) {
        selectorProv.innerHTML = '<option value="">-- Primero seleccione Departamento --</option>';
        selectorProv.disabled = true;
    }
    if (selectorDist) {
        selectorDist.innerHTML = '<option value="">-- Primero seleccione Provincia --</option>';
        selectorDist.disabled = true;
    }
    
    console.log('🔄 Filtros limpiados');

    // Restaurar todos los puntos a azul normal
    filtrarPuntosEnMapa(null, null, null);

    // Asegurar orden correcto: SHP atrás, puntos arriba
    if (geojsonLayer) {
        geojsonLayer.bringToBack();
    }
    if (clientesLayer) {
        clientesLayer.bringToFront();
    }

    // Volver a vista nacional
    if (mapa) {
        mapa.setView([-9.189, -75.0152], 6);
    }

    actualizarDatos();
}

function zoomADepartamento(depto) {
    console.log(`🔍 ZOOM DEPARTAMENTO INICIADO: "${depto}"`);
    
    const deptoLayer = delimitacionesLayers['departamentos'];
    if (!deptoLayer) {
        console.error('❌ ERROR: Capa de departamentos NO disponible');
        return;
    }
    
    const capas = deptoLayer.getLayers();
    console.log(`📊 Buscando en ${capas.length} capas...`);
    
    // DEBUG: Mostrar todos los nombres disponibles
    const nombresDisponibles = capas.map(l => l.deptoNombre || 'NULL').slice(0, 5);
    console.log(`📋 Primeros 5 nombres: [${nombresDisponibles.join(', ')}]`);
    
    let encontrado = false;
    const buscado = depto.toUpperCase().trim();
    
    // Restaurar TODOS los deptos a estilo normal primero
    capas.forEach(l => {
        l.setStyle({color: '#333', weight: 1.5, fillOpacity: 0});
    });
    
    capas.forEach((layer) => {
        const nombre = (layer.deptoNombre || '').toUpperCase().trim();
        
        if (nombre === buscado) {
            console.log(`✅ MATCH: "${nombre}" === "${buscado}"`);
            const bounds = layer.getBounds();
            console.log(`📍 Bounds SW:`, bounds.getSouthWest(), `NE:`, bounds.getNorthEast());
            
            mapa.fitBounds(bounds, { padding: [30, 30], animate: true });
            
            // Resaltar
            layer.setStyle({color: '#FF0000', weight: 4, fillOpacity: 0.1, fillColor: '#FF0000'});
            // setTimeout(() => {
            //     layer.setStyle({color: '#333', weight: 1.5, fillOpacity: 0});
            // }, 2000);
            
            encontrado = true;
        }
    });
    
    if (!encontrado) {
        console.error(`❌ NO ENCONTRADO: "${depto}" - Verificar nombres en SHP`);
        // Listar primeros 5 nombres disponibles para debug
        let nombres = [];
        deptoLayer.eachLayer((layer) => {
            if (nombres.length < 5) nombres.push(layer.deptoNombre);
        });
        console.log(`📋 Nombres disponibles (primeros 5): ${nombres.join(', ')}`);
    }
}

function zoomAProvincia(depto, provincia) {
    console.log(`🔍 ZOOM PROVINCIA INICIADO: ${provincia} en ${depto}`);
    
    const provLayer = delimitacionesLayers['provincias'];
    if (!provLayer) {
        console.error('❌ ERROR: Capa de provincias NO disponible');
        zoomADepartamento(depto);
        return;
    }
    
    console.log(`📊 Buscando en ${provLayer.getLayers().length} provincias...`);
    
    // Restaurar TODAS las provincias a estilo normal primero
    provLayer.eachLayer(l => {
        l.setStyle({color: '#888', weight: 1, fillOpacity: 0});
    });
    
    let encontrado = false;
    provLayer.eachLayer((layer) => {
        const nombreProv = (layer.provNombre || '').toUpperCase().trim();
        const nombreDepto = (layer.deptoNombre || '').toUpperCase().trim();
        const buscadoProv = provincia.toUpperCase().trim();
        const buscadoDepto = depto.toUpperCase().trim();
        
        if (nombreProv === buscadoProv && nombreDepto === buscadoDepto) {
            console.log(`✅ ENCONTRADO: ${nombreProv} en ${nombreDepto}`);
            
            mapa.fitBounds(layer.getBounds(), { padding: [40, 40], animate: true });
            
            // Resaltar
            layer.setStyle({color: '#0066FF', weight: 3, fillOpacity: 0.1, fillColor: '#0066FF'});
            // setTimeout(() => {
            //     layer.setStyle({color: '#888', weight: 1, fillOpacity: 0});
            // }, 2000);
            
            encontrado = true;
        }
    });
    
    if (!encontrado) {
        console.error(`❌ NO ENCONTRADO: "${provincia}" en "${depto}"`);
        zoomADepartamento(depto);
    }
}

async function zoomADistrito(depto, provincia, distrito) {
    console.log(`🔍 Zoom a distrito: ${distrito}`);
    
    // Cargar distritos bajo demanda
    if (!delimitacionesLayers['distritosData']) {
        console.log('📥 Cargando distritos...');
        try {
            const response = await fetch('/api/delimitaciones/distritos');
            delimitacionesLayers['distritosData'] = await response.json();
        } catch (e) {
            console.error('❌ Error:', e);
            zoomAProvincia(depto, provincia);
            return;
        }
    }
    
    const distritosData = delimitacionesLayers['distritosData'];
    const feature = distritosData.features?.find(f => {
        return (f.properties?.DISTRITO || '').toUpperCase() === distrito.toUpperCase() && 
               (f.properties?.PROVINCIA || '').toUpperCase() === provincia.toUpperCase() && 
               (f.properties?.DEPARTAMEN || '').toUpperCase() === depto.toUpperCase();
    });
    
    if (feature) {
        const tempLayer = L.geoJSON(feature, {
            style: { fillColor: 'transparent', fillOpacity: 0, color: '#FFFFFF', weight: 2 }
        }).addTo(mapa);
        
        mapa.fitBounds(tempLayer.getBounds(), { padding: [50, 50] });
        // Guardar referencia para poder limpiarla después
        delimitacionesLayers['distritoActual'] = tempLayer;
        
        // Asegurar orden correcto
        if (geojsonLayer) {
            geojsonLayer.bringToBack();
        }
        if (clientesLayer) {
            clientesLayer.bringToFront();
        }
        
        console.log(`✅ Zoom completado: ${distrito}`);
    } else {
        console.warn(`⚠️ Distrito ${distrito} no encontrado`);
        zoomAProvincia(depto, provincia);
    }
}
