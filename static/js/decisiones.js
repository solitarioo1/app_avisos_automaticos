/* ============================================================================
   DECISIONES.JS - Centro de Decisiones con Leaflet + API
   Integración de mapas geoespaciales con datos de clientes BD
   ============================================================================ */

let mapa = null;
let avisoActual = null;
let geojsonLayer = null;

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
    
    console.log('✅ Mapa inicializado');
}

function cargarCapaGeoJSON(numero) {
    // Eliminar capa anterior
    if (geojsonLayer) {
        mapa.removeLayer(geojsonLayer);
    }
    
    // Cargar zonas afectadas del CSV
    fetch(`/api/avisos/${numero}/zonas`)
        .then(r => r.json())
        .then(data => {
            console.log('📍 Zonas cargadas:', data.zonas);
            
            // Por ahora, solo mostramos feedback
            // En futuro: cargar SHP files como GeoJSON
            const totalZonas = data.total_zonas;
            console.log(`Total de zonas afectadas: ${totalZonas}`);
        })
        .catch(e => console.error('Error cargando zonas:', e));
}

// ============================================================================
// AVISOS SELECTOR
// ============================================================================

function cargarAvisos() {
    fetch('/api/avisos')
        .then(r => r.json())
        .then(avisos => {
            const selector = document.getElementById('filtro-aviso');
            
            // Filtrar solo rojo/naranja
            const avisosFiltrados = avisos.filter(a => 
                a.color && (a.color.toLowerCase() === 'rojo' || a.color.toLowerCase() === 'naranja')
            );
            
            selector.innerHTML = '<option value="">-- Seleccionar aviso --</option>' + 
                avisosFiltrados.map(a => 
                    `<option value="${a.numero}" data-color="${a.color}">
                        Aviso ${a.numero} - ${a.titulo} (${a.color.toUpperCase()})
                    </option>`
                ).join('');
            
            // Si hay avisos, cargar el primero por defecto
            if (avisosFiltrados.length > 0) {
                selector.value = avisosFiltrados[0].numero;
                cargarAviso();
            }
        })
        .catch(e => console.error('Error cargando avisos:', e));
}

function cargarAviso() {
    const numero = document.getElementById('filtro-aviso').value;
    if (!numero) return;
    
    avisoActual = numero;
    console.log(`📊 Cargando aviso ${numero}`);
    
    // Fetch de clientes y estadísticas
    Promise.all([
        fetch(`/api/avisos/${numero}/clientes-afectados`).then(r => r.json()),
        fetch(`/api/avisos/${numero}/estadisticas`).then(r => r.json())
    ])
    .then(([clientes, stats]) => {
        actualizarKPIs(stats);
        actualizarEstadisticas(stats);
        cargarCapaGeoJSON(numero);
    })
    .catch(e => console.error('Error cargando datos:', e));
}

// ============================================================================
// ACTUALIZAR UI
// ============================================================================

function actualizarKPIs(stats) {
    const critico = stats.critico?.count || 0;
    const alto = stats.alto_riesgo?.count || 0;
    const agr = stats.agricultores_total || 0;
    const pol = stats.poliza_total || 0;
    const ha = stats.hectareas_total || 0;
    
    document.getElementById('kpi-critico').textContent = critico > 0 ? `${critico}` : '-';
    document.getElementById('kpi-alto').textContent = alto > 0 ? `${alto}` : '-';
    document.getElementById('kpi-agr').textContent = agr.toLocaleString('es-ES');
    document.getElementById('kpi-pol').textContent = pol > 0 ? `S/ ${(pol/1e6).toFixed(1)}M` : '-';
    document.getElementById('kpi-ha').textContent = ha.toLocaleString('es-ES');
}

function actualizarEstadisticas(stats) {
    // Nivel badge
    const nivelBadge = document.getElementById('stat-nivel');
    const color = stats.color?.toLowerCase();
    
    if (color === 'rojo') {
        nivelBadge.textContent = '🔴 CRÍTICO';
        nivelBadge.className = 'badge-nivel badge-rojo';
    } else if (color === 'naranja') {
        nivelBadge.textContent = '🟠 ALTO RIESGO';
        nivelBadge.className = 'badge-nivel badge-naranja';
    } else {
        nivelBadge.textContent = 'SIN NIVEL';
        nivelBadge.className = 'badge-nivel';
    }
    
    // Estadísticas
    document.getElementById('stat-agricultores').textContent = 
        stats.agricultores_total.toLocaleString('es-ES');
    
    document.getElementById('stat-poliza').textContent = 
        stats.poliza_total > 0 ? (stats.poliza_total / 1e6).toFixed(2) : '0.00';
    
    document.getElementById('stat-hectareas').textContent = 
        stats.hectareas_total.toLocaleString('es-ES');
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
