/* ============================================================================
   DECISIONES.JS - Centro de Decisiones con Leaflet + API
   Integracion de mapas geoespaciales con datos de clientes BD
   Sistema dinamico: Depto, Provincia, Distrito
   ============================================================================ */

let mapa = null;
let avisoActual = null;
let geojsonLayer = null;
let clientesLayer = null;
let delimitacionesLayers = {};
let nivelSeleccionado = 'nacional';
let agregacionesData = {};
let filtroActual = { depto: null, provincia: null, distrito: null };
let filtroEntidadActual = null;  // id de la entidad seleccionada (null = todas)
let agregacionesDataOriginal = {};  // copia sin filtrar para restaurar

document.addEventListener('DOMContentLoaded', function() {
    initializeDecisiones();
});

function initializeDecisiones() {
    console.log('🎯 Centro de Decisiones iniciado');
    inicializarMapa();
    cargarClientesMapa();   // todos los clientes, una sola vez
    cargarAvisos();
    cargarSelectorEntidades();  // independiente del aviso
}

// ============================================================================
// MAPA LEAFLET
// ============================================================================

function inicializarMapa() {
    // Crear mapa centrado en Perú
    mapa = L.map('mapa-leaflet').setView([-9.189, -75.0152], 5.5);
    
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
    if (geojsonLayer) {
        mapa.removeLayer(geojsonLayer);
    }
    
    console.log(`🗺️ Cargando SHP del aviso ${numero}`);
    
    fetch(`/api/avisos/${numero}/shp-geojson`)
        .then(r => r.json())
        .then(geojson => {
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
                    const marker = L.circleMarker(latlng, {
                        radius: 3,
                        fillColor: '#0066FF',
                        color: '#003399',
                        weight: 0.5,
                        opacity: 0.8,
                        fillOpacity: 0.6
                    });
                    
                    marker.on('mouseover', function() {
                        this.setStyle({radius: 5, fillOpacity: 0.9});
                    });
                    
                    marker.on('mouseout', function() {
                        this.setStyle({radius: 3, fillOpacity: 0.6});
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

    // Resetear selector entidad (solo el valor, no deshabilitar)
    const selEnt = document.getElementById('filtro-entidad');
    if (selEnt) { selEnt.value = ''; }
    
    console.log(`📊 Cargando aviso ${numero}`);
    
    // Cargar datos en paralelo
    Promise.all([
        fetch(`/api/avisos/${numero}/clientes-afectados`).then(r => r.json()).catch(e => {console.error('Error clientes:', e); return {};}),
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
    if (!avisoActual) return;
    
    console.log('📊 Actualizando datos:', filtroActual);
    
    // Construir URL con filtros
    let url = `/api/avisos/${avisoActual}/clientes-afectados`;
    const params = [];
    
    if (filtroActual.depto)     params.push(`depto=${encodeURIComponent(filtroActual.depto)}`);
    if (filtroActual.provincia) params.push(`provincia=${encodeURIComponent(filtroActual.provincia)}`);
    if (filtroActual.distrito)  params.push(`distrito=${encodeURIComponent(filtroActual.distrito)}`);
    if (filtroEntidadActual)    params.push(`entidad_id=${encodeURIComponent(filtroEntidadActual)}`);
    
    if (params.length > 0) {
        url += '?' + params.join('&');
    }
    
    fetch(url)
        .then(r => r.json())
        .then(data => {
            // SOLO actualizar estadísticas dinámicas (panel derecho)
            // Los KPIs superiores son ESTÁTICOS (todo el aviso)
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

    clientesLayer.eachLayer((layer) => {
        const props = layer.feature?.properties || {};
        const pDepto = (props.departamento || '').toUpperCase().trim();
        const pProv  = (props.provincia   || '').toUpperCase().trim();
        const pDist  = (props.distrito    || '').toUpperCase().trim();
        const pEnt   = String(props.entidad_id ?? '');

        if (!hayFiltro && !filtroEntidadActual) {
            // Sin filtro: todos iguales azul
            layer.setStyle({
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
            layer.setStyle({
                radius: 7, fillColor: '#0066FF', color: '#003399',
                weight: 1.5, opacity: 1, fillOpacity: 0.95
            });
            layer.bringToFront();
        } else {
            layer.setStyle({
                radius: 2, fillColor: '#BBBBBB', color: '#999999',
                weight: 0.3, opacity: 0.25, fillOpacity: 0.15
            });
        }
    });

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
    console.log(`📊 Cargando KPIs para aviso ${numero}`);
    
    fetch(`/api/avisos/${numero}/kpis`)
        .then(r => r.json())
        .then(data => {
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

function actualizarTablaZonas() {
    if (!avisoActual) return;
    
    console.log('📊 Actualizando Tabla Zonas para aviso:', avisoActual);
    
    // Usar los datos del endpoint KPI (más reciente y correcto)
    fetch(`/api/avisos/${avisoActual}/kpis`)
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                console.error('Error:', data.error);
                return;
            }
            
            const tbody = document.getElementById('tabla-zonas-body');
            if (!tbody) return;
            
            let html = '';
            const zonas_por_color = data.zonas_por_color || {};
            const iconos = { 'Rojo': '🔴', 'Naranja': '🟠', 'Amarillo': '🟡', 'Verde': '🟢' };
            const colores = ['Rojo', 'Naranja', 'Amarillo', 'Verde'];
            
            for (const color of colores) {
                const zona = zonas_por_color[color];
                if (!zona) continue;
                
                const agr_total = zona.agricultores || 0;
                const ha_total = zona.hectareas || 0;
                const poliza_total = zona.poliza || 0;
                
                const fila_class = `zona-${color.toLowerCase()}`;
                
                html += `
                    <tr class="${fila_class}">
                        <td>${iconos[color]} ${color}</td>
                        <td><strong>${agr_total}</strong></td>
                        <td>${ha_total.toLocaleString('es-ES', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                        <td>S/ ${poliza_total.toLocaleString('es-ES', {maximumFractionDigits: 0})}</td>
                    </tr>
                `;
            }
            
            tbody.innerHTML = html;
            console.log('✅ Tabla Zonas actualizada con datos KPI');
        })
        .catch(e => console.error('Error actualizando tabla zonas:', e));
}

function actualizarTablaEntidades() {
    if (!avisoActual) return;
    
    console.log('📊 Actualizando Tabla Entidades para aviso:', avisoActual);
    
    // Usar el nuevo endpoint KPI Entidades
    fetch(`/api/avisos/${avisoActual}/kpis-entidades`)
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                console.error('Error:', data.error);
                return;
            }
            
            const tbody = document.getElementById('tabla-entidades-body');
            if (!tbody) return;
            
            const entidades = data.entidades || [];
            
            let html = '';
            for (const ent of entidades) {
                const agr_afect  = ent.agricultores  || 0;
                const total_ent  = ent.total_entidad || 0;
                const ha_afect   = ent.hectareas     || 0;
                const monto_afect = ent.monto        || 0;
                const pct        = ent.pct_damage    || 0;

                // color del badge según % daño
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
            
            if (html === '') {
                html = '<tr><td colspan="5" class="text-center text-muted">Sin datos de entidades afectadas</td></tr>';
            }
            
            tbody.innerHTML = html;
            console.log('✅ Tabla Entidades actualizada');
        })
        .catch(e => console.error('Error actualizando tabla entidades:', e));
}

function actualizarTablaCultivos() {
    if (!avisoActual) return;
    
    console.log('🌾 Actualizando Tabla Cultivos para aviso:', avisoActual);
    
    // Usar el nuevo endpoint KPI Cultivos
    fetch(`/api/avisos/${avisoActual}/kpis-cultivos`)
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                console.error('Error:', data.error);
                return;
            }
            
            const tbody = document.getElementById('tabla-cultivos-body');
            if (!tbody) return;
            
            const cultivos = data.cultivos || [];

            const medals = ['🥇','🥈','🥉'];
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
            
            if (html === '') {
                html = '<tr><td colspan="7" class="text-center text-muted">Sin datos de cultivos afectados</td></tr>';
            }
            
            tbody.innerHTML = html;
            console.log('✅ Tabla Cultivos actualizada con', cultivos.length, 'registros');
        })
        .catch(e => console.error('Error actualizando tabla cultivos:', e));
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
