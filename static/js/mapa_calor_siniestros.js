// Mapa de Calor de Siniestros — SOLO burbujas (sin heat layer).
// Sin filtro de departamento -> vista NACIONAL: una burbuja por departamento
// (círculo = cantidad de casos indemnizados), sobre el contorno de deptos.
// Con un departamento elegido -> vista DEPARTAMENTAL: una burbuja por distrito,
// zoom a ese departamento. Mismo estilo que las imágenes de presentación
// (mapa_burbujas_*.png): fondo melón, burbuja cian, borde teal.
// El panel derecho y las 3 tablas de abajo se recalculan según el mismo filtro.

let mcsMapa, mcsCapaDeptosBase, mcsCapaDistritosBase, mcsCapaBurbujas;
let mcsGeojsonDeptosNacional = null;
let mcsGeojsonDistritosNacional = null;

const MCS_DEPARTAMENTOS = ['AMAZONAS','ANCASH','APURIMAC','AREQUIPA','AYACUCHO','CAJAMARCA','CALLAO',
    'CUSCO','HUANCAVELICA','HUANUCO','ICA','JUNIN','LA LIBERTAD','LAMBAYEQUE','LIMA','LORETO',
    'MADRE DE DIOS','MOQUEGUA','PASCO','PIURA','PUNO','SAN MARTIN','TACNA','TUMBES','UCAYALI'];

const MCS_BURBUJA_COLOR = '#7fe8e8';
const MCS_BURBUJA_BORDE = '#0d7377';

document.addEventListener('DOMContentLoaded', () => {
    mcsMapa = L.map('mcs-mapa', { preferCanvas: true }).setView([-9.2, -75.0], 5.5);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap',
        maxZoom: 18
    }).addTo(mcsMapa);

    const leyenda = L.control({ position: 'bottomright' });
    leyenda.onAdd = () => {
        const div = L.DomUtil.create('div', 'mcs-leyenda-mapa');
        div.innerHTML = `<div style="display:flex; align-items:center; gap:6px;">
            <span style="width:14px; height:14px; border-radius:50%; background:${MCS_BURBUJA_COLOR}; border:1.5px solid ${MCS_BURBUJA_BORDE}; display:inline-block;"></span>
            Tamaño = casos indemnizados</div>`;
        return div;
    };
    leyenda.addTo(mcsMapa);

    poblarSelectDepartamentos();
    cargarEventos();
    cargarTodo();

    document.getElementById('mcs-btn-filtrar').addEventListener('click', cargarTodo);
    document.getElementById('mcs-btn-limpiar').addEventListener('click', limpiarFiltros);
});

function limpiarFiltros() {
    document.getElementById('mcs-departamento').value = '';
    document.getElementById('mcs-anio-desde').value = '';
    document.getElementById('mcs-anio-hasta').value = '';
    document.getElementById('mcs-evento').value = '';
    cargarTodo();
}

function poblarSelectDepartamentos() {
    const sel = document.getElementById('mcs-departamento');
    MCS_DEPARTAMENTOS.forEach(d => {
        const opt = document.createElement('option');
        opt.value = d; opt.textContent = d.charAt(0) + d.slice(1).toLowerCase();
        sel.appendChild(opt);
    });
}

function paramsActuales(incluirDepto) {
    const p = new URLSearchParams();
    const desde = document.getElementById('mcs-anio-desde').value;
    const hasta = document.getElementById('mcs-anio-hasta').value;
    const evento = document.getElementById('mcs-evento').value;
    const depto = document.getElementById('mcs-departamento').value;
    if (desde) p.set('anio_desde', desde);
    if (hasta) p.set('anio_hasta', hasta);
    if (evento) p.set('evento', evento);
    if (incluirDepto && depto) p.set('departamento', depto);
    return p.toString();
}

function cargarEventos() {
    fetch('/mapa-calor-siniestros/api/eventos')
        .then(r => r.json())
        .then(eventos => {
            const sel = document.getElementById('mcs-evento');
            eventos.forEach(ev => {
                const opt = document.createElement('option');
                opt.value = ev; opt.textContent = titleCase(ev);
                sel.appendChild(opt);
            });
        });
}

function fmtMoneda(v) {
    return 'S/ ' + Number(v || 0).toLocaleString('es-PE', { maximumFractionDigits: 0 });
}

function titleCase(s) {
    if (!s) return '-';
    return s.toString().toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
}

function cargarTodo() {
    const depto = document.getElementById('mcs-departamento').value;
    const qsConDepto = paramsActuales(true);

    cargarKpis(qsConDepto);
    cargarResumen(qsConDepto, depto);

    if (depto) {
        document.getElementById('mcs-panel-titulo').textContent = 'Vista: ' + titleCase(depto);
        cargarBurbujasDistrito(depto, paramsActuales(false));
    } else {
        document.getElementById('mcs-panel-titulo').textContent = 'Vista Nacional';
        if (mcsCapaDistritosBase) { mcsMapa.removeLayer(mcsCapaDistritosBase); mcsCapaDistritosBase = null; }
        cargarBurbujasNacional(qsConDepto);
        mcsMapa.setView([-9.2, -75.0], 5.5);
    }
}

// ============================================================================
// KPIs
// ============================================================================
function cargarKpis(qs) {
    fetch(`/mapa-calor-siniestros/api/kpis?${qs}`)
        .then(r => r.json())
        .then(k => {
            document.getElementById('mcs-kpi-total').textContent = Number(k.total).toLocaleString('es-PE');
            document.getElementById('mcs-kpi-rango').textContent = k.fecha_min && k.fecha_max
                ? `${k.fecha_min.slice(0,4)} - ${k.fecha_max.slice(0,4)}` : '-';
            document.getElementById('mcs-kpi-pct').textContent = k.pct_indemnizado != null ? `${k.pct_indemnizado}%` : '-';
            document.getElementById('mcs-kpi-detalle').textContent = `${Number(k.indemnizados).toLocaleString('es-PE')} pagados / ${Number(k.no_indemnizados).toLocaleString('es-PE')} no pagados`;
            document.getElementById('mcs-kpi-monto').textContent = fmtMoneda(k.monto_total);
            document.getElementById('mcs-kpi-sindato').textContent = Number(k.sin_dato).toLocaleString('es-PE');
        });
}

// ============================================================================
// Panel derecho (top 1) + 3 tablas de abajo
// ============================================================================
function cargarResumen(qs, depto) {
    fetch(`/mapa-calor-siniestros/api/resumen?${qs}`)
        .then(r => r.json())
        .then(d => {
            document.getElementById('mcs-stat-distrito-top').textContent = d.distritos[0] ? `${titleCase(d.distritos[0].distrito)} (${d.distritos[0].indemnizados})` : '-';
            document.getElementById('mcs-stat-evento-top').textContent = d.eventos[0] ? `${titleCase(d.eventos[0].evento)} (${d.eventos[0].indemnizados})` : '-';
            document.getElementById('mcs-stat-cultivo-top').textContent = d.cultivos[0] ? `${titleCase(d.cultivos[0].cultivo)} (${d.cultivos[0].indemnizados})` : '-';

            document.getElementById('mcs-th-distritos').textContent = depto ? `Distritos más afectados — ${titleCase(depto)}` : 'Distritos más afectados (nacional)';

            pintarTablaSimple('mcs-body-distritos', d.distritos, f => `
                <tr><td>${titleCase(f.distrito)}</td><td class="num">${Number(f.indemnizados).toLocaleString('es-PE')}</td><td class="num">${fmtMoneda(f.monto_total)}</td></tr>
            `);
            pintarTablaSimple('mcs-body-eventos', d.eventos, f => `
                <tr><td>${titleCase(f.evento)}</td><td class="num">${Number(f.indemnizados).toLocaleString('es-PE')}</td><td class="num">${Number(f.total).toLocaleString('es-PE')}</td></tr>
            `);
            pintarTablaSimple('mcs-body-cultivos', d.cultivos, f => `
                <tr><td>${titleCase(f.cultivo)}</td><td class="num">${Number(f.indemnizados).toLocaleString('es-PE')}</td><td class="num">${fmtMoneda(f.monto_total)}</td></tr>
            `);
        });
}

function pintarTablaSimple(idTbody, filas, filaHtml) {
    const tbody = document.getElementById(idTbody);
    if (!filas.length) {
        tbody.innerHTML = '<tr><td colspan="3" style="text-align:center; color:#999; padding:1rem;">Sin datos.</td></tr>';
        return;
    }
    tbody.innerHTML = filas.map(filaHtml).join('');
}

// ============================================================================
// Burbujas — helper compartido: dibuja un círculo por feature de un GeoJSON,
// centrado en su centroide, radio = sqrt(valor) (área proporcional).
// ============================================================================
function dibujarBurbujas(features, propNombre, statsPorNombre, tooltipFn) {
    if (mcsCapaBurbujas) mcsMapa.removeLayer(mcsCapaBurbujas);
    const marcadores = [];
    const valores = Object.values(statsPorNombre).map(f => f.indemnizados || 0).filter(v => v > 0);
    const max = valores.length ? Math.max(...valores) : 1;

    features.forEach(feature => {
        const nombre = (feature.properties[propNombre] || '').toUpperCase();
        const stats = statsPorNombre[nombre];
        if (!stats || !stats.indemnizados) return;
        const capa = L.geoJSON(feature);
        const centro = capa.getBounds().getCenter();
        const radio = 4 + Math.sqrt(stats.indemnizados / max) * 22;
        const marker = L.circleMarker(centro, {
            radius: radio, color: MCS_BURBUJA_BORDE, weight: 1.5,
            fillColor: MCS_BURBUJA_COLOR, fillOpacity: 0.65
        }).bindTooltip(tooltipFn(nombre, stats), { sticky: true });
        marcadores.push(marker);
    });
    mcsCapaBurbujas = L.layerGroup(marcadores).addTo(mcsMapa);
    return marcadores.length;
}

function tooltipStats(titulo, stats) {
    return `<b>${titleCase(titulo)}</b><br>Indemnizados: ${stats.indemnizados}<br>No indemnizados: ${stats.no_indemnizados}<br>% Indemnizado: ${stats.pct_indemnizado != null ? stats.pct_indemnizado + '%' : '-'}<br>Monto: ${fmtMoneda(stats.monto_total)}`;
}

// ============================================================================
// MODO NACIONAL — burbuja por departamento
// ============================================================================
function cargarBurbujasNacional(qs) {
    fetch(`/mapa-calor-siniestros/api/departamentos?${qs}`)
        .then(r => r.json())
        .then(filas => {
            const statsPorDepto = {};
            filas.forEach(f => { statsPorDepto[f.departamento] = f; });

            const activar = geojson => {
                mcsGeojsonDeptosNacional = geojson;
                if (mcsCapaDeptosBase) mcsMapa.removeLayer(mcsCapaDeptosBase);
                mcsCapaDeptosBase = L.geoJSON(geojson, {
                    style: () => ({ color: '#999', weight: 0.8, fillColor: '#fbdcc4', fillOpacity: 0.45 }),
                    onEachFeature: (feature, layer) => {
                        layer.on('click', () => {
                            document.getElementById('mcs-departamento').value = (feature.properties.nombre || '').toUpperCase();
                            cargarTodo();
                        });
                    }
                }).addTo(mcsMapa);

                const propsPorNombre = {};
                geojson.features.forEach(f => { propsPorNombre[(f.properties.nombre || '').toUpperCase()] = f.properties.nombre; });
                // dibujarBurbujas espera la propiedad tal cual viene en el feature (aquí 'nombre')
                dibujarBurbujas(geojson.features, 'nombre', statsPorDepto, tooltipStats);
            };

            if (mcsGeojsonDeptosNacional) activar(mcsGeojsonDeptosNacional);
            else fetch('/api/delimitaciones/departamentos').then(r => r.json()).then(activar);
        });
}

// ============================================================================
// MODO DEPARTAMENTAL — burbuja por distrito
// ============================================================================
function cargarBurbujasDistrito(depto, qs) {
    const qsDistritos = qs + (qs ? '&' : '') + `departamentos=${depto}`;
    fetch(`/mapa-calor-siniestros/api/distritos?${qsDistritos}`)
        .then(r => r.json())
        .then(filas => {
            const statsPorDistrito = {};
            filas.forEach(f => { statsPorDistrito[f.distrito] = f; });

            const activar = geojson => {
                mcsGeojsonDistritosNacional = geojson;
                const filtradas = geojson.features.filter(f => (f.properties.DEPARTAMEN || '').toUpperCase() === depto);

                if (mcsCapaDistritosBase) mcsMapa.removeLayer(mcsCapaDistritosBase);
                mcsCapaDistritosBase = L.geoJSON({ type: 'FeatureCollection', features: filtradas }, {
                    style: () => ({ color: '#999', weight: 0.6, fillColor: '#fbdcc4', fillOpacity: 0.5 })
                }).addTo(mcsMapa);

                dibujarBurbujas(filtradas, 'DISTRITO', statsPorDistrito, tooltipStats);

                if (filtradas.length) mcsMapa.fitBounds(mcsCapaDistritosBase.getBounds(), { padding: [20, 20] });
            };

            if (mcsGeojsonDistritosNacional) activar(mcsGeojsonDistritosNacional);
            else fetch('/api/delimitaciones/distritos').then(r => r.json()).then(activar);
        });
}
