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

document.addEventListener('DOMContentLoaded', function() {
    initializeDecisiones();
});

function initializeDecisiones() {
    console.log('🎯 Centro de Decisiones iniciado');
    inicializarMapa();
    cargarAvisos();
}

// ============================================================================
// MAPA LEAFLET
// ============================================================================

function inicializarMapa() {
    // Crear mapa centrado en Perú
    mapa = L.map('mapa-leaflet').setView([-9.189, -75.0152], 5);
    
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
                    fillOpacity: 0.4,
                    color: 'none',
                    weight: 0,
                    opacity: 0
                })
            }).addTo(mapa);
            
            if (geojsonLayer.getLayers().length > 0) {
                mapa.fitBounds(geojsonLayer.getBounds());
            }
            console.log('✅ SHP renderizado');
        })
        .catch(e => console.error('❌ Error SHP:', e));
}

function cargarClientesMapa(numero) {
    if (clientesLayer) {
        mapa.removeLayer(clientesLayer);
    }
    
    console.log(`👥 Cargando clientes del aviso ${numero}`);
    
    fetch(`/api/avisos/${numero}/clientes-geojson`)
        .then(r => r.json())
        .then(geojson => {
            console.log(`✅ ${geojson.total} clientes cargados`);
            
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
                }
            }).addTo(mapa);
            
            delimitacionesLayers['provincias'] = provLayer;
            console.log('✅ Provincias cargadas y visibles:', geojson.features?.length || 0);
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
            
            // Usar todos los avisos
            const totalAvisos = avisos.length;
            
            selector.innerHTML = '<option value="">-- Seleccionar Aviso --</option>' + 
                avisos.map(a => 
                    `<option value="${a.numero}">Aviso ${a.numero} - ${a.color || ''}</option>`
                ).join('');
            
            // Mensaje de scroll si hay muchos
            if (totalAvisos > 100) {
                selector.title = `${totalAvisos} avisos disponibles - usa scroll para navegar`;
                console.log(`📊 ${totalAvisos} avisos. INSTRUCCIÓN: Usa scroll en el selector.`);
            } else {
                console.log(`📊 ${totalAvisos} avisos cargados`);
            }
            
            // ✅ CARGAR PRIMER AVISO AUTOMÁTICAMENTE
            if (avisos.length > 0) {
                selector.value = avisos[0].numero;
                console.log(`✅ Auto-cargando aviso ${avisos[0].numero}`);
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
    nivelSeleccionado = 'nacional';
    
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
        
        console.log('📋 Clientes cargados:', clientes);
        console.log('📊 Stats:', stats);
        console.log('📈 Agregaciones:', agregacionesData);
        
        // Actualizar KPIs y estadísticas
        actualizarKPIs(stats, clientes);
        actualizarEstadisticas(stats);
        
        // Poblar selector de departamentos con datos de agregaciones
        poblarSelectorDepartamentos();
        
        // Renderizar capas
        cargarCapaGeoJSON(numero);
        cargarClientesMapa(numero);
        
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
    
    if (filtroActual.depto) params.push(`depto=${encodeURIComponent(filtroActual.depto)}`);
    if (filtroActual.provincia) params.push(`provincia=${encodeURIComponent(filtroActual.provincia)}`);
    if (filtroActual.distrito) params.push(`distrito=${encodeURIComponent(filtroActual.distrito)}`);
    
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
        })
        .catch(e => console.error('Error actualizando datos:', e));
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

function actualizarKPIs(stats, clientes) {
    // Valores por defecto
    let critico = 0;
    let alto = 0;
    let agr = 0;
    let pol = 0;
    let ha = 0;
    
    // Extraer valores correctamente (backend devuelve 'count' no 'cantidad')
    if (stats && stats.critico && stats.critico.count) {
        critico = stats.critico.count;
    }
    if (stats && stats.alto_riesgo && stats.alto_riesgo.count) {
        alto = stats.alto_riesgo.count;
    }
    if (clientes && clientes.total_agricultores) {
        agr = clientes.total_agricultores;
    }
    if (clientes && clientes.total_monto_asegurado) {
        pol = clientes.total_monto_asegurado;
    }
    if (clientes && clientes.total_hectareas) {
        ha = clientes.total_hectareas;
    }
    
    // Actualizar tarjetas KPI
    const elem = (id) => document.getElementById(id);
    
    if (elem('kpi-critico')) elem('kpi-critico').textContent = critico > 0 ? `${critico}` : '-';
    if (elem('kpi-alto')) elem('kpi-alto').textContent = alto > 0 ? `${alto}` : '-';
    if (elem('kpi-agr')) elem('kpi-agr').textContent = agr > 0 ? agr.toLocaleString('es-ES') : '0';
    if (elem('kpi-pol')) elem('kpi-pol').textContent = pol > 0 ? `S/ ${(pol/1e6).toFixed(1)}M` : '-';
    if (elem('kpi-ha')) elem('kpi-ha').textContent = ha > 0 ? ha.toLocaleString('es-ES') : '0';
    
    console.log('✅ KPIs actualizados:', {critico, alto, agr, pol, ha});
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
            nivelBadge.textContent = '🔴 CRÍTICO';
            nivelBadge.className = 'badge-nivel badge-rojo';
        } else if (color === 'naranja') {
            nivelBadge.textContent = '🟠 ALTO RIESGO';
            nivelBadge.className = 'badge-nivel badge-naranja';
        } else {
            nivelBadge.textContent = '⚪ SIN NIVEL';
            nivelBadge.className = 'badge-nivel';
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
        elem('stat-poliza').textContent = pol > 0 ? (pol / 1e6).toFixed(2) : '0.00';
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
    
    // Solo actualizar panel derecho (estadísticas dinámicas)
    if (elem('stat-agricultores')) {
        elem('stat-agricultores').textContent = agr > 0 ? agr.toLocaleString('es-ES') : '0';
    }
    if (elem('stat-poliza')) {
        elem('stat-poliza').textContent = pol > 0 ? (pol / 1e6).toFixed(2) : '0.00';
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

// ============================================================================
// SELECCIÓN JERÁRQUICA: DEPTO → PROVINCIA → DISTRITO
// ============================================================================

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
    
    // Zoom al distrito en el mapa
    if (distSeleccionado && filtroActual.depto && filtroActual.provincia) {
        zoomADistrito(filtroActual.depto, filtroActual.provincia, distSeleccionado);
    }
    
    actualizarDatos();
}

function limpiarFiltros() {
    // Resetear filtros
    filtroActual = { depto: null, provincia: null, distrito: null };
    nivelSeleccionado = 'nacional';
    
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
    
    // Volver a vista nacional
    if (mapa) {
        mapa.setView([-9.189, -75.0152], 5);
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
    
    capas.forEach((layer) => {
        const nombre = (layer.deptoNombre || '').toUpperCase().trim();
        
        if (nombre === buscado) {
            console.log(`✅ MATCH: "${nombre}" === "${buscado}"`);
            const bounds = layer.getBounds();
            console.log(`📍 Bounds SW:`, bounds.getSouthWest(), `NE:`, bounds.getNorthEast());
            
            mapa.fitBounds(bounds, { padding: [30, 30], animate: true });
            
            // Resaltar
            layer.setStyle({color: '#FF0000', weight: 4, fillOpacity: 0.2, fillColor: '#FF0000'});
            setTimeout(() => {
                layer.setStyle({color: '#333', weight: 1.5, fillOpacity: 0});
            }, 2000);
            
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
            layer.setStyle({color: '#0066FF', weight: 3, fillOpacity: 0.2, fillColor: '#0066FF'});
            setTimeout(() => {
                layer.setStyle({color: '#888', weight: 1, fillOpacity: 0});
            }, 2000);
            
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
            style: { fillColor: '#28a745', fillOpacity: 0.25, color: '#28a745', weight: 2 }
        }).addTo(mapa);
        
        mapa.fitBounds(tempLayer.getBounds(), { padding: [50, 50] });
        setTimeout(() => mapa.removeLayer(tempLayer), 2000);
        
        console.log(`✅ Zoom completado: ${distrito}`);
    } else {
        console.warn(`⚠️ Distrito ${distrito} no encontrado`);
        zoomAProvincia(depto, provincia);
    }
}
