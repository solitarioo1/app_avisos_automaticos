// Evaluación de Riesgo — mapa (estaciones + capa) + 3 modos de input + reporte vertical.

let evrMap, evrMarker, evrCapaLayer, evrEstacionesLayer;
let evrGdrMap, evrChart;
const EVR_DEFAULT_LAT = -5.1783;
const EVR_DEFAULT_LON = -80.6549; // Piura, único departamento con estaciones con datos reales por ahora
const EVR_MESES = ['', 'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];

// El botón de imprimir solo se habilita cuando terminan de cargar TODAS las
// capas del mapa de Gestión de Riesgo (capa de peligro + contorno de
// departamento) — evita imprimir/descargar un PDF con el mapa a medio pintar.
let evrTareasPendientes = 0;
function evrTareaInicio() {
    evrTareasPendientes++;
    const btn = document.getElementById('evr-btn-imprimir');
    btn.disabled = true;
    btn.textContent = 'Cargando mapa...';
}
function evrTareaFin() {
    evrTareasPendientes = Math.max(0, evrTareasPendientes - 1);
    if (evrTareasPendientes === 0) {
        const btn = document.getElementById('evr-btn-imprimir');
        btn.disabled = false;
        btn.textContent = '🖨️ Imprimir / Descargar Reporte (PDF)';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    evrInicializarMapa();
    evrInicializarFormulario();
    evrActualizarUbicacionPreview(EVR_DEFAULT_LAT, EVR_DEFAULT_LON);
    evrCargarCapaEnMapa();
    evrCargarEstaciones();
});

// El canvas de Chart.js a veces queda en blanco al imprimir si el navegador
// toma la foto de impresión antes de que el chart termine de redibujarse al
// ancho de la hoja — se fuerza un resize+redraw síncrono justo antes.
window.addEventListener('beforeprint', () => {
    if (evrChart) { evrChart.resize(); evrChart.update('none'); }
    if (evrGdrMap) { evrGdrMap.invalidateSize(); }
});

// ============================================================================
// Mapa del formulario: marcador arrastrable + capa del evento + TODAS las estaciones
// Recortado/zoomeado a Piura — único departamento con estaciones reales por ahora.
// ============================================================================
function evrInicializarMapa() {
    evrMap = L.map('evr-mapa', { minZoom: 7 }).setView([EVR_DEFAULT_LAT, EVR_DEFAULT_LON], 9);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap',
        maxZoom: 18
    }).addTo(evrMap);

    evrMarker = L.marker([EVR_DEFAULT_LAT, EVR_DEFAULT_LON], { draggable: true }).addTo(evrMap);

    evrMarker.on('dragend', () => {
        const { lat, lng } = evrMarker.getLatLng();
        evrActualizarCoords(lat, lng);
    });

    evrMap.on('click', (e) => {
        evrMarker.setLatLng(e.latlng);
        evrActualizarCoords(e.latlng.lat, e.latlng.lng);
    });

    evrRecortarAPiura();
}

function evrRecortarAPiura() {
    fetch('/evaluacion-riesgo/api/departamento-geojson?nombre=PIURA')
        .then(r => r.ok ? r.json() : null)
        .then(geojson => {
            if (!geojson || !geojson.features || !geojson.features.length) return;
            const capa = L.geoJSON(geojson, { style: { color: '#2c3e50', weight: 1.5, fill: false, dashArray: '4,3' } }).addTo(evrMap);
            capa.bringToBack();
            const bounds = capa.getBounds().pad(0.08); // margen chico para ver el borde completo
            evrMap.setMaxBounds(bounds);
            evrMap.fitBounds(bounds);
        })
        .catch(() => {});
}

function evrCargarEstaciones() {
    fetch('/evaluacion-riesgo/api/estaciones')
        .then(r => r.json())
        .then(geojson => {
            evrEstacionesLayer = L.geoJSON(geojson, {
                pointToLayer: (f, latlng) => L.circleMarker(latlng, {
                    radius: 4,
                    weight: 1,
                    color: f.properties.tiene_datos ? '#1e8449' : '#999',
                    fillColor: f.properties.tiene_datos ? '#27ae60' : '#cccccc',
                    fillOpacity: 0.85
                }).bindTooltip(
                    `${f.properties.nombre} (${f.properties.departamento})` +
                    (f.properties.tiene_datos ? ' — con datos' : ' — sin datos aún')
                )
            }).addTo(evrMap);
        })
        .catch(() => {});
}

function evrActualizarCoords(lat, lon) {
    document.getElementById('evr-coords').textContent = `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
    evrActualizarUbicacionPreview(lat, lon);
}

let evrUbicacionTimer = null;
function evrActualizarUbicacionPreview(lat, lon) {
    clearTimeout(evrUbicacionTimer);
    evrUbicacionTimer = setTimeout(() => {
        fetch(`/evaluacion-riesgo/api/ubicacion?lat=${lat}&lon=${lon}`)
            .then(r => r.json())
            .then(data => {
                const el = document.getElementById('evr-ubicacion-preview');
                if (data.departamento) {
                    el.textContent = `📍 ${data.distrito}, ${data.provincia}, ${data.departamento}`;
                } else {
                    el.textContent = '📍 Fuera del territorio peruano reconocido';
                }
            })
            .catch(() => {});
    }, 300);
}

// ============================================================================
// Polígono de la capa de riesgo del evento seleccionado, dibujado sobre el mapa
// ============================================================================
function evrCargarCapaEnMapa(nombreCapa) {
    if (!nombreCapa) {
        const sel = document.getElementById('evr-evento');
        nombreCapa = sel.options[sel.selectedIndex].dataset.capa;
    }

    if (evrCapaLayer) {
        evrMap.removeLayer(evrCapaLayer);
        evrCapaLayer = null;
    }
    document.getElementById('evr-capa-legend').innerHTML = '';

    fetch(`/api/capas-riesgo/${nombreCapa}/geometria`)
        .then(r => { if (!r.ok) throw new Error('no disponible'); return r.json(); })
        .then(geojson => {
            evrCapaLayer = L.geoJSON(geojson, {
                style: f => ({
                    color: f.properties.color_display || '#999',
                    weight: 1,
                    fillColor: f.properties.color_display || '#999',
                    fillOpacity: 0.35
                })
            }).addTo(evrMap);
            evrCapaLayer.bringToBack();

            const niveles = new Map();
            geojson.features.forEach(f => {
                const n = f.properties.nivel_display ?? 'Zona de riesgo';
                if (!niveles.has(n)) niveles.set(n, f.properties.color_display || '#999');
            });
            const legend = document.getElementById('evr-capa-legend');
            legend.innerHTML = [...niveles.entries()].map(([n, c]) =>
                `<span><span class="sw" style="background:${c}"></span>${n}</span>`).join('');
        })
        .catch(() => { /* capa no disponible todavía (ej. viento/incendios en proceso) */ });
}

// ============================================================================
// Toggle Coordenada / Foto / Excel (lote)
// ============================================================================
function evrCambiarModoInput(modo) {
    document.getElementById('evr-tab-manual').classList.toggle('activo', modo === 'manual');
    document.getElementById('evr-tab-foto').classList.toggle('activo', modo === 'foto');
    document.getElementById('evr-tab-lote').classList.toggle('activo', modo === 'lote');

    document.getElementById('evr-bloque-lote').style.display = modo === 'lote' ? 'block' : 'none';
    document.getElementById('evr-bloque-form').style.display = modo === 'lote' ? 'none' : 'block';
    document.getElementById('evr-bloque-foto').style.display = modo === 'foto' ? 'block' : 'none';
}

function evrProcesarFoto(event) {
    const archivo = event.target.files[0];
    if (!archivo) return;

    const statusEl = document.getElementById('evr-foto-status');
    const dropEl = document.getElementById('evr-foto-drop');
    statusEl.innerHTML = 'Leyendo foto...';

    const formData = new FormData();
    formData.append('foto', archivo);

    fetch('/evaluacion-riesgo/api/extraer-foto', { method: 'POST', body: formData })
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                statusEl.innerHTML = `<span class="falta">${data.error}</span>`;
                return;
            }
            dropEl.classList.add('tiene-foto');
            dropEl.textContent = `📷 ${archivo.name}`;

            const partes = [];
            if (data.tiene_gps) {
                evrMarker.setLatLng([data.lat, data.lon]);
                evrMap.setView([data.lat, data.lon], 12);
                evrActualizarCoords(data.lat, data.lon);
                partes.push('<span class="ok">✓ GPS leído del EXIF</span>');
            } else {
                partes.push('<span class="falta">✗ Sin GPS en el EXIF — ubica el punto manualmente en el mapa</span>');
            }
            if (data.tiene_fecha) {
                document.getElementById('evr-fecha').value = data.fecha;
                partes.push('<span class="ok">✓ Fecha leída del EXIF</span>');
            } else {
                partes.push('<span class="falta">✗ Sin fecha en el EXIF — ingrésala manualmente</span>');
            }
            partes.push('<span class="falta">El tipo de evento siempre se elige manual ↓</span>');
            statusEl.innerHTML = partes.join('<br>');
        })
        .catch(err => { statusEl.innerHTML = `<span class="falta">Error leyendo la foto: ${err}</span>`; });
}

function evrInicializarFormulario() {
    const selectEvento = document.getElementById('evr-evento');
    const hint = document.getElementById('evr-percentil-hint');

    const fecha = document.getElementById('evr-fecha');
    fecha.value = new Date().toISOString().slice(0, 10);
    fecha.max = new Date().toISOString().slice(0, 10);

    function aplicarDefaultsEvento() {
        const opt = selectEvento.options[selectEvento.selectedIndex];
        const cola = opt.dataset.cola;
        hint.textContent = cola === 'superior'
            ? `Se marca como extremo si supera el percentil alto (P90/P95) del histórico de la estación para ese mes, en ${opt.dataset.unidad}.`
            : `Se marca como extremo si está por debajo del percentil bajo (P10/P5) del histórico de la estación para ese mes, en ${opt.dataset.unidad}.`;
        evrCargarCapaEnMapa(opt.dataset.capa);
    }
    selectEvento.addEventListener('change', aplicarDefaultsEvento);
    aplicarDefaultsEvento();
}

// ============================================================================
// Verificación de UN reclamo
// ============================================================================
function evrVerificar() {
    const btn = document.getElementById('evr-btn-verificar');
    const evento = document.getElementById('evr-evento').value;
    const fecha = document.getElementById('evr-fecha').value;
    const severidad = document.getElementById('evr-severidad').value;
    const { lat, lng } = evrMarker.getLatLng();

    if (!fecha) {
        alert('Completa la fecha antes de verificar.');
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Verificando...';

    fetch('/evaluacion-riesgo/api/verificar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ evento, fecha, lat, lon: lng, severidad: parseInt(severidad, 10) })
    })
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                alert('Error: ' + data.error);
                return;
            }
            evrRenderResultado(data);
        })
        .catch(err => alert('Error al verificar: ' + err))
        .finally(() => {
            btn.disabled = false;
            btn.textContent = 'Verificar reclamo';
        });
}

// ============================================================================
// Reporte (siempre vertical): 1.Input -> 2.Meteorológica -> 3.Gestión de Riesgo -> Veredicto
// ============================================================================
function evrRenderResultado(data) {
    document.getElementById('evr-resultado-vacio').style.display = 'none';
    const cont = document.getElementById('evr-resultado-contenido');
    cont.style.display = 'block';
    evrTareasPendientes = 0; // reinicia el contador de una verificación anterior
    const btnImprimir = document.getElementById('evr-btn-imprimir');
    btnImprimir.style.display = 'block';
    btnImprimir.disabled = true;
    btnImprimir.textContent = 'Cargando mapa...';
    document.getElementById('evr-print-fecha').textContent = new Date().toLocaleString('es-PE', {
        day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false
    });

    const veredictoClass = data.veredicto ? 'si' : 'no';
    const veredictoTxt = data.veredicto
        ? '✅ El cliente pudo verse afectado durante el evento'
        : '❌ No hay evidencia suficiente de afectación';
    const veredictoBox = document.getElementById('evr-veredicto-box');
    veredictoBox.className = `evr-veredicto ${veredictoClass}`;
    veredictoBox.innerHTML = `${veredictoTxt}<br><span style="font-size:12px; font-weight:500;">${data.señales_positivas}/3 señales a favor</span>`;

    document.getElementById('evr-input-resumen').innerHTML = evrInputResumenHtml(data);
    document.getElementById('evr-meteo-cont').innerHTML = evrMeteoHtml(data);
    document.getElementById('evr-gdr-datos').innerHTML = evrGdrDatosHtml(data);

    if (data.estacion && data.estacion.serie_diaria && data.estacion.serie_diaria.length) {
        requestAnimationFrame(() => evrRenderChart(data));
    }
    requestAnimationFrame(() => evrRenderGdrMap(data));
}

function evrInputResumenHtml(data) {
    const capaTxt = !data.capa.disponible
        ? `${data.capa.label} — no disponible todavía`
        : data.capa.en_capa
            ? `${data.capa.label} — Nivel ${data.capa.nivel ?? 'N/A'}`
            : `${data.capa.label} — fuera de zona`;
    const ubicacionTxt = data.departamento ? `${data.distrito}, ${data.provincia}, ${data.departamento}` : 'No reconocida';
    const avisoTxt = data.aviso ? `Nº ${data.aviso.numero_aviso} (${data.aviso.nivel})` : 'Sin aviso vigente/posterior';

    const items = [
        ['Fecha del evento', data.fecha],
        ['Tipo de evento', data.evento],
        ['Capa cruzada', capaTxt],
        ['Aviso SENAMHI', avisoTxt],
        ['Coordenadas', `${data.lat.toFixed(4)}, ${data.lon.toFixed(4)}`],
        ['Ubicación', ubicacionTxt],
    ];
    return items.map(([lbl, val]) => `<div class="evr-input-item"><span class="lbl">${lbl}</span><span class="val">${val}</span></div>`).join('');
}

function evrMeteoHtml(data) {
    const est = data.estacion;
    if (!est || !est.promedios_mensuales) {
        return '<p style="color:#999; font-size:13px;">No hay estación con datos meteorológicos cerca de este punto.</p>';
    }
    const mesEventoLabel = EVR_MESES[new Date(data.fecha + 'T00:00:00').getMonth() + 1];
    const filas = est.promedios_mensuales.map(p =>
        `<tr class="${p.mes === mesEventoLabel ? 'mes-evento' : ''}"><td>${p.mes}</td><td>${p.valor ?? '—'}</td></tr>`
    ).join('');
    const valorTxt = est.dias_con_dato != null
        ? `${est.valor} ${data.unidad} acumulados en el mes`
        : `${est.valor} ${data.unidad} el ${est.fecha_dato || data.fecha}`;

    return `
        <div class="evr-meteo-grid">
            <div>
                <div class="evr-meteo-titulo-col">Promedio mensual — ${est.estacion}</div>
                <table class="evr-tabla-meteo">
                    <thead><tr><th>Mes</th><th>${data.unidad}</th></tr></thead>
                    <tbody>${filas}</tbody>
                </table>
            </div>
            <div>
                <div class="evr-meteo-titulo-col">Serie diaria — ${mesEventoLabel} ${data.fecha.slice(0, 4)}</div>
                <p style="font-size:11px; color:#666; margin:-0.35rem 0 0.5rem 0;">
                    Real: <b>${valorTxt}</b> · Percentil ${est.percentil}: <b>${est.percentil_valor ?? 's/d'} ${data.unidad}</b>
                </p>
                <canvas id="evr-chart-meteo"></canvas>
            </div>
        </div>
    `;
}

function evrRenderChart(data) {
    const canvas = document.getElementById('evr-chart-meteo');
    if (!canvas) return;
    if (evrChart) { evrChart.destroy(); evrChart = null; }

    const est = data.estacion;
    const serie = est.serie_diaria || [];
    const dias = serie.map(p => p.dia);
    const valores = serie.map(p => p.valor);
    const diaEvento = est.dia_evento;
    // Precipitación es discreta/dispersa (muchos ceros) -> barra. Temperatura/viento
    // es una serie continua -> línea. (criterio pedido: precipitación=barra, temp=línea)
    const esPrecipitacion = est.variable === 'precipitacion';

    const colorBase = '#2c3e50';
    const colorEvento = '#e07b5a';
    const colorPercentil = '#e67e22';

    const datasetPercentil = {
        type: 'line',
        label: `Percentil ${est.percentil} (${est.percentil_valor ?? 's/d'} ${data.unidad})`,
        data: dias.map(() => est.percentil_valor),
        borderColor: colorPercentil,
        borderDash: [6, 4],
        borderWidth: 2,
        pointRadius: 0,
        fill: false,
    };

    const datasetValor = esPrecipitacion ? {
        type: 'bar',
        label: `Valor diario (${data.unidad})`,
        data: valores,
        backgroundColor: dias.map(d => d === diaEvento ? colorEvento : colorBase),
        borderRadius: 4,
        maxBarThickness: 22,
    } : {
        type: 'line',
        label: `Valor diario (${data.unidad})`,
        data: valores,
        borderColor: colorBase,
        backgroundColor: colorBase,
        borderWidth: 2,
        pointRadius: dias.map(d => d === diaEvento ? 6 : 2),
        pointBackgroundColor: dias.map(d => d === diaEvento ? colorEvento : colorBase),
        pointBorderColor: '#fff',
        pointBorderWidth: dias.map(d => d === diaEvento ? 2 : 0),
        tension: 0.25,
    };

    evrChart = new Chart(canvas, {
        type: esPrecipitacion ? 'bar' : 'line',
        data: { labels: dias, datasets: [datasetValor, datasetPercentil] },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            aspectRatio: 2.1,
            plugins: { legend: { position: 'bottom', labels: { font: { size: 10.5 }, boxWidth: 14 } } },
            scales: {
                x: { title: { display: true, text: 'Día del mes', font: { size: 10.5 } }, grid: { display: false } },
                y: { grid: { color: '#eee' } }
            }
        }
    });
}

function evrGdrDatosHtml(data) {
    if (!data.estacion) {
        return '<p>Sin estación con datos meteorológicos cerca de este punto.</p>';
    }
    const e = data.estacion;
    const capaTxt = data.capa.disponible
        ? (data.capa.en_capa ? `nivel <b>${data.capa.nivel ?? 'N/A'}</b> en el punto reportado` : 'el punto queda fuera de la zona de riesgo mapeada')
        : 'capa aún no disponible';
    return `<p>Estación más cercana: <b>${e.estacion}</b> (código ${e.codigo}) a <b>${e.distancia_km} km</b> del punto reportado.
        Capa "${data.capa.label}" clasificada según el evento "${data.evento}" — ${capaTxt}.</p>`;
}

function evrRenderGdrMap(data) {
    if (!evrGdrMap) {
        evrGdrMap = L.map('evr-mapa-gdr');
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap' }).addTo(evrGdrMap);
    }
    evrGdrMap.eachLayer(l => { if (!(l instanceof L.TileLayer)) evrGdrMap.removeLayer(l); });

    L.marker([data.lat, data.lon]).addTo(evrGdrMap).bindPopup('Punto reportado').openPopup();
    const bounds = L.latLngBounds([[data.lat, data.lon]]);

    if (data.estacion) {
        const estLatLng = [data.estacion.lat, data.estacion.lon];
        L.circleMarker(estLatLng, { radius: 7, color: '#2980b9', fillColor: '#3498db', fillOpacity: 0.9, weight: 2 })
            .addTo(evrGdrMap)
            .bindPopup(`Estación ${data.estacion.estacion} (${data.estacion.distancia_km} km)`);
        L.polyline([[data.lat, data.lon], estLatLng], { color: '#888', dashArray: '5,5' }).addTo(evrGdrMap);
        bounds.extend(estLatLng);
    }

    // El zoom se fija YA, solo con punto + estación (nunca con la capa ni con
    // el departamento completo — eso antes dejaba el mapa mostrando medio Perú
    // cuando el departamento era grande/alargado, ej. Piura hasta Ayabaca).
    evrGdrMap.fitBounds(bounds, { padding: [50, 50], maxZoom: 13 });
    setTimeout(() => evrGdrMap.invalidateSize(), 150);

    // Capa de riesgo y contorno departamental se agregan aparte, solo como
    // contexto visual (no vuelven a tocar el zoom). El botón de imprimir queda
    // deshabilitado hasta que ambas terminen de cargar, para no imprimir/
    // descargar el mapa a medio pintar.
    let tareasIniciadas = 0;

    if (data.capa.disponible) {
        tareasIniciadas++;
        evrTareaInicio();
        fetch(`/api/capas-riesgo/${data.capa.nombre}/geometria`)
            .then(r => r.ok ? r.json() : null)
            .then(geojson => {
                if (!geojson || !geojson.features || !geojson.features.length) return;
                L.geoJSON(geojson, {
                    style: f => ({ color: f.properties.color_display || '#999', weight: 1, fillColor: f.properties.color_display || '#999', fillOpacity: 0.35 })
                }).addTo(evrGdrMap).bringToBack();
            })
            .catch(() => {})
            .finally(evrTareaFin);
    }

    if (data.departamento) {
        tareasIniciadas++;
        evrTareaInicio();
        fetch(`/evaluacion-riesgo/api/departamento-geojson?nombre=${encodeURIComponent(data.departamento)}`)
            .then(r => r.ok ? r.json() : null)
            .then(geojson => {
                if (!geojson || !geojson.features || !geojson.features.length) return;
                L.geoJSON(geojson, {
                    style: { color: '#2c3e50', weight: 1.5, fill: false, dashArray: '4,3' }
                }).addTo(evrGdrMap).bringToBack();
            })
            .catch(() => {})
            .finally(evrTareaFin);
    }

    if (tareasIniciadas === 0) {
        const btn = document.getElementById('evr-btn-imprimir');
        btn.disabled = false;
        btn.textContent = '🖨️ Imprimir / Descargar Reporte (PDF)';
    }
}

// ============================================================================
// Excel (lote): verificar varios reclamos a la vez
// ============================================================================
let evrLoteResultados = [];

function evrVerificarLote() {
    const fileInput = document.getElementById('evr-lote-input');
    const file = fileInput.files[0];
    if (!file) {
        alert('Elige un archivo Excel primero.');
        return;
    }

    const btn = document.getElementById('evr-btn-lote');
    const status = document.getElementById('evr-lote-status');
    btn.disabled = true;
    btn.textContent = 'Verificando...';
    status.textContent = '';

    const fd = new FormData();
    fd.append('excel', file);

    fetch('/evaluacion-riesgo/api/verificar-lote', { method: 'POST', body: fd })
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                status.innerHTML = `<span style="color:#c0392b;">${data.error}</span>`;
                return;
            }
            status.textContent = `${data.total} reclamos procesados.`;
            evrRenderTablaLote(data.resultados);
        })
        .catch(err => { status.innerHTML = `<span style="color:#c0392b;">Error: ${err}</span>`; })
        .finally(() => {
            btn.disabled = false;
            btn.textContent = 'Verificar Lote';
        });
}

function evrRenderTablaLote(resultados) {
    evrLoteResultados = resultados;
    const filas = resultados.map((r, i) => {
        if (r.error) {
            return `<tr><td>${r.referencia}</td><td colspan="3" style="color:#c0392b;">${r.error}</td><td><span class="evr-badge err">Error</span></td><td></td></tr>`;
        }
        const badge = r.veredicto ? '<span class="evr-badge si">Afectado</span>' : '<span class="evr-badge no">No afectado</span>';
        return `<tr>
            <td>${r.referencia}</td><td>${r.evento}</td><td>${r.fecha}</td>
            <td>${r.señales_positivas}/3</td><td>${badge}</td>
            <td><button class="evr-ver-detalle" onclick="evrVerDetalleLote(${i})">Ver reporte</button></td>
        </tr>`;
    }).join('');
    document.getElementById('evr-lote-tabla-cont').innerHTML = `
        <table class="evr-tabla-lote">
            <thead><tr><th>Ref.</th><th>Evento</th><th>Fecha</th><th>Señales</th><th>Veredicto</th><th></th></tr></thead>
            <tbody>${filas}</tbody>
        </table>`;
}

function evrVerDetalleLote(i) {
    const r = evrLoteResultados[i];
    if (!r || r.error) return;

    const selectEvento = document.getElementById('evr-evento');
    selectEvento.value = r.evento_id;
    document.getElementById('evr-fecha').value = r.fecha;
    document.getElementById('evr-severidad').value = String(r.severidad);
    evrMarker.setLatLng([r.lat, r.lon]);
    evrMap.setView([r.lat, r.lon], 11);
    evrActualizarCoords(r.lat, r.lon);
    evrCambiarModoInput('manual');
    evrCargarCapaEnMapa(selectEvento.options[selectEvento.selectedIndex].dataset.capa);
    evrVerificar();
    document.getElementById('evr-col-resultado').scrollIntoView({ behavior: 'smooth' });
}
