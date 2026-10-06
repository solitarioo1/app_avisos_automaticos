// Evaluación de Afiliaciones (antes "Clasifica tu Cliente") — 2 caminos que
// terminan en el MISMO resultado: tabla + mapa + exportable.
//   - Excel de prospectos -> /api/clasificar-excel
//   - Foto(s): 1-3 = una sola parcela, instantáneo (/api/validar-foto).
//              4-100 (sueltas o en .zip) = cada foto un prospecto independiente,
//              en segundo plano con polling (/api/clasificar-lote).

const CC_COLOR_ESTADO = { 'Verificado': '#dc3545', 'Rechazado': '#6c757d', 'Pendiente': '#ffc107' };
const CC_ORDEN_NIVEL = { 'Muy Alto': 4, 'Alto': 3, 'Medio': 2, 'Bajo': 1 };
const CC_MAX_FOTOS_INSTANTANEO = 3;
const CC_MAX_FOTOS_LOTE = 100;

let ccMapa = null;
let ccResultadosActuales = [];  // lo que se exporta / pinta en el mapa

document.addEventListener('DOMContentLoaded', () => {
    ccInicializarMapa();
    ccCargarCapas();
    ccCargarHistorial();
    ccConfigurarDropzone('cc-dropzone-excel', 'cc-archivo', 'cc-archivo-nombre');
    ccConfigurarDropzone('cc-dropzone-fotos', 'cc-fotos', 'cc-fotos-nombre');
});

// ── Dropzone (click o arrastrar-y-soltar) compartido por Excel y Fotos ──
function ccConfigurarDropzone(dropzoneId, inputId, nombreId) {
    const dz = document.getElementById(dropzoneId);
    const input = document.getElementById(inputId);
    const nombreEl = document.getElementById(nombreId);
    if (!dz || !input) return;

    const actualizarNombre = () => {
        const files = input.files;
        nombreEl.textContent = !files || files.length === 0 ? ''
            : files.length === 1 ? '📎 ' + files[0].name
            : `📎 ${files.length} archivos seleccionados`;
    };

    dz.addEventListener('click', () => input.click());
    input.addEventListener('change', actualizarNombre);

    ['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, (e) => {
        e.preventDefault(); e.stopPropagation(); dz.classList.add('cc-dragover');
    }));
    ['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, (e) => {
        e.preventDefault(); e.stopPropagation(); dz.classList.remove('cc-dragover');
    }));
    dz.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        if (dt && dt.files && dt.files.length) {
            input.files = dt.files;
            input.dispatchEvent(new Event('change'));
        }
    });
}

function ccInicializarMapa() {
    if (ccMapa) return ccMapa;
    ccMapa = L.map('cc-mapa').setView([-9.19, -75.02], 5.5);  // Perú completo por defecto
    L.tileLayer('https://api.thunderforest.com/atlas/{z}/{x}/{y}.png?apikey=043ce2146e48404a850da16dae37388a', { attribution: '&copy; <a href="https://www.thunderforest.com/">Thunderforest</a>, &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(ccMapa);

    // Contorno de departamentos (mismo endpoint y estilo que Seguro Comercial)
    fetch('/api/delimitaciones/departamentos')
        .then(r => r.json())
        .then(geojson => {
            L.geoJSON(geojson, {
                style: { fillColor: 'transparent', fillOpacity: 0, color: '#333', weight: 1.5, opacity: .8 },
            }).addTo(ccMapa);
        })
        .catch(() => {});

    setTimeout(() => ccMapa.invalidateSize(), 200);
    return ccMapa;
}

function ccCargarCapas() {
    fetch('/api/capas-riesgo/disponibles')
        .then(r => r.json())
        .then(capas => {
            const select = document.getElementById('cc-capa');
            const disponibles = capas.filter(c => c.disponible);
            const opciones = disponibles.map(c => `<option value="${c.id}">${c.label}</option>`).join('');
            select.innerHTML = '<option value="">Todas (recomendado)</option>' + opciones;
            select.addEventListener('change', ccActualizarPoligonoCapa);
        })
        .catch(() => {});
}

function ccCapaSeleccionada() {
    return document.getElementById('cc-capa').value || '';
}

// Click en un badge de exposición de una fila -> selecciona esa capa arriba
// y dibuja su polígono de inmediato (atajo, evita ir al selector manual).
function ccVerCapaEnMapa(nombre) {
    const select = document.getElementById('cc-capa');
    select.value = nombre;
    ccActualizarPoligonoCapa();
    document.getElementById('cc-mapa').scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// ── Polígono de la capa de riesgo elegida, sobre el/los departamento(s) de
// los resultados actuales (mismo endpoint/estilo que Seguro Comercial:
// color_display/nivel_display ya vienen calculados del backend) ──
let ccCapaPoligonoLayers = {};  // depto -> L.GeoJSON
let ccCapaPoligonoActiva = null;

function ccActualizarPoligonoCapa() {
    const capa = ccCapaSeleccionada();
    Object.values(ccCapaPoligonoLayers).forEach(l => ccMapa.removeLayer(l));
    ccCapaPoligonoLayers = {};
    ccCapaPoligonoActiva = capa || null;
    if (!capa) return;

    const deptos = new Set();
    ccResultadosActuales.forEach(r => {
        const d = r.ubicacion && r.ubicacion.departamento;
        if (d) deptos.add(d);
    });
    deptos.forEach(depto => {
        fetch(`/api/capas-riesgo/${capa}/geometria?depto=${encodeURIComponent(depto)}`)
            .then(r => r.json())
            .then(geojson => {
                if (ccCapaPoligonoActiva !== capa) return;  // llegó tarde, ya cambió la capa
                if (geojson.error || !geojson.features || !geojson.features.length) return;
                const layer = L.geoJSON(geojson, {
                    style: (feature) => ({
                        fillColor: feature.properties.color_display || '#999',
                        fillOpacity: 0.45, color: '#555', weight: 0.3, opacity: 0.4,
                    }),
                }).bindTooltip(l => l.feature.properties.nivel_display || '', { sticky: true }).addTo(ccMapa);
                layer._esCapaPoligono = true;
                ccCapaPoligonoLayers[depto] = layer;
                layer.bringToBack();
            })
            .catch(() => {});
    });
}

// ── Pestañas ──
function ccCambiarTab(tab) {
    ['excel', 'foto'].forEach(t => {
        document.getElementById(`cc-tab-${t}`).classList.toggle('activo', t === tab);
        document.getElementById(`cc-pane-${t}`).classList.toggle('activo', t === tab);
    });
}

// ============================================================================
// Render compartido: tabla + mapa, lo usan Excel / Foto única / Lote por igual
// ============================================================================

function ccPeorNivel(exposicion) {
    let peor = null;
    (exposicion || []).forEach(c => {
        if (c.en_capa && c.nivel && (!peor || CC_ORDEN_NIVEL[c.nivel] > CC_ORDEN_NIVEL[peor])) peor = c.nivel;
    });
    return peor;
}

function ccColorNivel(nivel) {
    return { 'Muy Alto': '#c0392b', 'Alto': '#e67e22', 'Medio': '#f1c40f', 'Bajo': '#2ecc71' }[nivel] || '#999';
}

function ccEtiquetaOrigen(r) {
    if (r.origen === 'excel') {
        const extra = r.extra || {};
        const clave = Object.keys(extra).find(k => /nombre|dni|cliente/i.test(k));
        return clave ? String(extra[clave]) : 'Fila Excel';
    }
    if (r.origen === 'lote') return (r.extra && r.extra.archivo) || 'Foto';
    return 'Foto georreferenciada';
}

let ccMarkersActuales = [];  // paralelo a ccResultadosActuales, para el check/uncheck por fila

function ccMostrarResultados(resultados) {
    ccResultadosActuales = resultados;
    document.getElementById('cc-resultados-card').style.display = resultados.length ? 'block' : 'none';
    document.getElementById('cc-resultados-total').textContent = resultados.length;

    // No tocar el contorno de departamentos ni el polígono de capa (marcados
    // con _esCapaPoligono) — solo se limpian los marcadores de resultados.
    ccMapa.eachLayer(l => {
        if (l instanceof L.TileLayer || l._esCapaPoligono) return;
        if (l instanceof L.GeoJSON) return;  // contorno de departamentos
        ccMapa.removeLayer(l);
    });

    ccMarkersActuales = [];
    const puntos = [];
    const tbody = document.getElementById('cc-resultados-body');
    tbody.innerHTML = resultados.map((r, i) => {
        let marker = null;
        if (r.latitud != null && r.longitud != null) {
            const peor = ccPeorNivel(r.exposicion);
            const color = peor ? ccColorNivel(peor) : '#04ccc4';
            marker = L.circleMarker([r.latitud, r.longitud], { radius: 7, color, fillColor: color, fillOpacity: .85 }).addTo(ccMapa);
            marker.bindPopup(`<strong>${ccEtiquetaOrigen(r)}</strong><br>` +
                (r.exposicion || []).filter(c => c.en_capa).map(c => `${c.label}: ${c.nivel || 'Expuesto'}`).join('<br>') +
                (r.siniestros_cercanos && r.siniestros_cercanos.length ? `<br><em>${r.siniestros_cercanos.length} siniestro(s) cerca</em>` : ''));
            puntos.push([r.latitud, r.longitud]);
        }
        ccMarkersActuales.push(marker);

        const admin = r.ubicacion || {};
        const adminTxt = [admin.departamento, admin.provincia, admin.distrito].filter(Boolean).join(' / ');
        const ubicacion = r.error
            ? `<span class="text-danger">${r.error}</span>`
            : (r.latitud != null
                ? `${r.latitud.toFixed(4)}, ${r.longitud.toFixed(4)}` + (adminTxt ? `<div class="cc-ubicacion-admin">${adminTxt}</div>` : '')
                : (r.estado === 'pendiente' ? '<span class="text-muted">procesando...</span>' : '—'));
        const niveles = (r.exposicion || []).filter(c => c.en_capa).map(c =>
            `<span class="cc-nivel-badge" style="background:${c.color || '#999'};" onclick="ccVerCapaEnMapa('${c.nombre}')" title="Ver ${c.label} en el mapa">${c.label}: ${c.nivel || 'Expuesto'}</span>`
        ).join('') || (r.error ? '' : '<span class="text-muted small">Sin exposición</span>');

        const foto = r.foto_url
            ? `<img class="cc-foto-thumb" src="${r.foto_url}" onclick="ccVerFoto('${r.foto_url}')">`
            : '<span class="text-muted">—</span>';

        const puedeArreglarManual = r.origen === 'lote' && r.estado === 'error' && ccLoteIdActual;
        const accion = puedeArreglarManual ? `
            <div class="cc-manual-fix">
                <input type="text" inputmode="decimal" placeholder="lat" id="cc-mlat-${r.id}">
                <input type="text" inputmode="decimal" placeholder="lon" id="cc-mlon-${r.id}">
                <button type="button" class="cc-manual-pick" onclick="ccPickManualItem(${r.id})" title="Marcar en el mapa">📍</button>
                <button type="button" onclick="ccCalcularManualItem(${r.id})">Calcular</button>
            </div>` : '<span class="text-muted" style="font-size:11px;">Sin pendientes</span>';

        return `<tr>
            <td><input type="checkbox" checked onchange="ccToggleMarker(${i}, this.checked)" ${marker ? '' : 'disabled'}></td>
            <td>${ccEtiquetaOrigen(r)}</td>
            <td>${ubicacion}</td>
            <td><div class="cc-niveles-cell">${niveles}</div></td>
            <td class="text-center">${(r.siniestros_cercanos || []).length || '—'}</td>
            <td class="text-center">${foto}</td>
            <td>${accion}</td>
        </tr>`;
    }).join('');

    if (puntos.length) {
        if (puntos.length === 1) ccMapa.setView(puntos[0], 13);
        else ccMapa.fitBounds(puntos, { padding: [30, 30] });
    }
    ccActualizarPoligonoCapa();
    setTimeout(() => ccMapa.invalidateSize(), 150);
}

function ccToggleMarker(i, visible) {
    const m = ccMarkersActuales[i];
    if (!m) return;
    if (visible) m.addTo(ccMapa); else ccMapa.removeLayer(m);
}

function ccVerFoto(url) {
    const overlay = document.createElement('div');
    overlay.className = 'cc-foto-lightbox';
    overlay.innerHTML = `<img src="${url}">`;
    overlay.onclick = () => overlay.remove();
    document.body.appendChild(overlay);
}

// ── Fix manual por ítem de lote (la mayoría de fotos de campo no traen GPS) ──
let ccPickManualActivo = null;  // item id para el que se está esperando click en el mapa
let ccPickManualHandler = null;

function ccPickManualItem(itemId) {
    if (ccPickManualHandler) ccMapa.off('click', ccPickManualHandler);
    ccPickManualActivo = itemId;
    ccPickManualHandler = (e) => {
        const latInput = document.getElementById(`cc-mlat-${itemId}`);
        const lonInput = document.getElementById(`cc-mlon-${itemId}`);
        if (latInput && lonInput) {
            latInput.value = e.latlng.lat.toFixed(6);
            lonInput.value = e.latlng.lng.toFixed(6);
        }
        ccMapa.off('click', ccPickManualHandler);
        ccPickManualHandler = null;
        ccPickManualActivo = null;
    };
    ccMapa.on('click', ccPickManualHandler);
    alert('Haz click en el mapa donde está la parcela de esta foto.');
}

function ccCalcularManualItem(itemId) {
    const lat = parseFloat((document.getElementById(`cc-mlat-${itemId}`) || {}).value);
    const lon = parseFloat((document.getElementById(`cc-mlon-${itemId}`) || {}).value);
    if (isNaN(lat) || isNaN(lon)) { alert('Ingresa lat/lon válidos, o usa 📍 para marcar en el mapa.'); return; }
    if (!ccLoteIdActual) return;

    fetch(`/clasificar-cliente/api/lote/${ccLoteIdActual}/item/${itemId}/manual`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lat, lon }),
    })
        .then(r => r.json().then(d => ({ ok: r.ok, d })))
        .then(({ ok, d }) => {
            if (!ok) throw new Error(d.error || 'Error calculando');
            const idx = ccResultadosActuales.findIndex(r => r.id === itemId);
            if (idx >= 0) ccResultadosActuales[idx] = d.resultado;
            ccMostrarResultados(ccResultadosActuales);
        })
        .catch(e => alert('Error: ' + e.message));
}

function ccExportar() {
    if (!ccResultadosActuales.length) return;
    fetch('/clasificar-cliente/api/exportar-resultados', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resultados: ccResultadosActuales }),
    })
        .then(r => { if (!r.ok) throw new Error('Error exportando'); return r.blob(); })
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = 'evaluacion_afiliaciones.xlsx';
            document.body.appendChild(a); a.click(); a.remove();
            window.URL.revokeObjectURL(url);
        })
        .catch(e => alert('Error exportando: ' + e.message));
}

// ============================================================================
// 1. Excel
// ============================================================================

function ccClasificarExcel() {
    const file = document.getElementById('cc-archivo').files[0];
    const status = document.getElementById('cc-status');
    status.className = ''; status.textContent = '';
    if (!file) { status.className = 'cc-status-error'; status.textContent = 'Elige un archivo Excel primero.'; return; }

    const btn = document.getElementById('cc-btn-clasificar');
    btn.disabled = true; btn.textContent = 'Evaluando...';

    const fd = new FormData();
    fd.append('excel', file);
    fd.append('capa', ccCapaSeleccionada());

    fetch('/clasificar-cliente/api/clasificar-excel', { method: 'POST', body: fd })
        .then(r => r.json().then(d => ({ ok: r.ok, d })))
        .then(({ ok, d }) => {
            if (!ok) throw new Error(d.error || 'Error evaluando el Excel');
            ccMostrarResultados(d.resultados);
            status.className = 'cc-status-ok';
            status.textContent = `✓ ${d.total} fila(s) evaluada(s).`;
        })
        .catch(e => { status.className = 'cc-status-error'; status.textContent = 'Error: ' + e.message; })
        .finally(() => { btn.disabled = false; btn.textContent = 'Evaluar Excel'; });
}

// ============================================================================
// 2. Foto(s) — 1-3 instantáneo (misma parcela) o 4-100 en lote (c/u independiente)
// ============================================================================

let ccFotosSeleccionadas = [];
let ccManualLatLon = null;
let ccClickHandlerManual = null;

const ccInputFotos = document.getElementById('cc-fotos');
if (ccInputFotos) {
    ccInputFotos.addEventListener('change', async () => {
        const archivos = Array.from(ccInputFotos.files);
        ccFotosSeleccionadas = archivos;
        const preview = document.getElementById('cc-fotos-preview');
        preview.innerHTML = '';
        const esZip = archivos.length === 1 && /\.zip$/i.test(archivos[0].name);
        if (esZip || archivos.length > CC_MAX_FOTOS_INSTANTANEO) return;  // sin preview individual para zip/lote
        for (const file of archivos) {
            const item = document.createElement('div');
            item.className = 'cc-foto-item';
            const img = document.createElement('img');
            img.src = URL.createObjectURL(file);
            item.appendChild(img);
            const badge = document.createElement('div');
            badge.className = 'cc-foto-badge';
            try {
                const gps = await exifr.gps(file);
                const tiene = gps && typeof gps.latitude === 'number';
                badge.style.background = tiene ? 'rgba(25,135,84,.85)' : 'rgba(220,53,69,.85)';
                badge.textContent = tiene ? '📍 GPS' : '⚠️ Sin GPS';
            } catch (e) {
                badge.style.background = 'rgba(220,53,69,.85)';
                badge.textContent = '⚠️ Sin GPS';
            }
            item.appendChild(badge);
            preview.appendChild(item);
        }
    });
}

function ccEvaluarFotos() {
    const status = document.getElementById('cc-foto-status');
    status.className = ''; status.textContent = '';
    document.getElementById('cc-lote-fallidos').innerHTML = '';

    if (ccFotosSeleccionadas.length === 0) { status.className = 'cc-status-error'; status.textContent = 'Selecciona al menos 1 foto (o un .zip).'; return; }

    const esZip = ccFotosSeleccionadas.length === 1 && /\.zip$/i.test(ccFotosSeleccionadas[0].name);
    if (esZip) { ccSubirLote(); return; }

    if (ccFotosSeleccionadas.some(f => /\.zip$/i.test(f.name))) {
        status.className = 'cc-status-error';
        status.textContent = 'No mezcles un .zip con fotos sueltas — sube uno u otro.';
        return;
    }
    if (ccFotosSeleccionadas.length > CC_MAX_FOTOS_LOTE) {
        status.className = 'cc-status-error';
        status.textContent = `Máximo ${CC_MAX_FOTOS_LOTE} fotos por lote.`;
        return;
    }
    if (ccFotosSeleccionadas.length > CC_MAX_FOTOS_INSTANTANEO) { ccSubirLote(); return; }

    ccValidarFotoInstantaneo();
}

function ccValidarFotoInstantaneo(reintentoManual) {
    const status = document.getElementById('cc-foto-status');
    status.className = ''; status.textContent = '';

    const btn = document.getElementById('cc-btn-validar');
    btn.disabled = true; btn.textContent = 'Validando...';

    const fd = new FormData();
    ccFotosSeleccionadas.forEach(f => fd.append('fotos', f));
    fd.append('capa', ccCapaSeleccionada());
    if (reintentoManual && ccManualLatLon) {
        fd.append('lat_manual', ccManualLatLon.lat);
        fd.append('lon_manual', ccManualLatLon.lon);
    }

    fetch('/clasificar-cliente/api/validar-foto', { method: 'POST', body: fd })
        .then(r => r.json().then(d => ({ ok: r.ok, d })))
        .then(({ ok, d }) => {
            if (!ok) {
                if (d.necesita_manual) {
                    ccActivarModoManual();
                    status.className = 'cc-status-error';
                    status.textContent = 'No se pudo leer la ubicación automática — mira la foto y haz click en el mapa donde está la parcela.';
                    return;
                }
                throw new Error(d.error || 'Error validando');
            }
            ccDesactivarModoManual();
            ccMostrarResultados([{
                origen: 'foto', extra: {},
                latitud: d.latitud, longitud: d.longitud,
                exposicion: d.exposicion, siniestros_cercanos: d.siniestros_cercanos,
                ubicacion: d.ubicacion, foto_url: d.foto_url,
            }]);
            (d.siniestros_cercanos || []).forEach(c => {
                const color = CC_COLOR_ESTADO[c.estado] || '#fc6c44';
                L.circleMarker([c.latitud, c.longitud], { radius: 6, color, fillColor: color, fillOpacity: .8 })
                    .addTo(ccMapa).bindPopup(`Siniestro #${c.id} — ${c.evento}<br>${c.estado} · ${c.distancia_km} km`);
            });
            status.className = 'cc-status-ok';
            status.textContent = '✓ Validado y guardado en el historial.';
            ccCargarHistorial();
        })
        .catch(e => { status.className = 'cc-status-error'; status.textContent = 'Error: ' + e.message; })
        .finally(() => { btn.disabled = false; btn.textContent = 'Evaluar fotos'; });
}

function ccActivarModoManual() {
    let aviso = document.getElementById('cc-aviso-manual');
    if (!aviso) {
        aviso = document.createElement('div');
        aviso.id = 'cc-aviso-manual';
        aviso.className = 'alert alert-warning py-2 small mt-2';
        document.getElementById('cc-mapa').insertAdjacentElement('afterend', aviso);
    }
    aviso.innerHTML = 'Haz click en el mapa donde está la parcela (mira la foto de abajo como referencia). ' +
        '<button type="button" class="btn btn-sm btn-success mt-1 d-block" id="cc-btn-confirmar-manual" disabled>Confirmar esta ubicación</button>';

    let refImg = document.getElementById('cc-foto-referencia');
    if (!refImg) {
        refImg = document.createElement('img');
        refImg.id = 'cc-foto-referencia';
        refImg.style.cssText = 'max-width:100%; border-radius:8px; margin-top:.5rem;';
        aviso.insertAdjacentElement('afterend', refImg);
    }
    refImg.src = URL.createObjectURL(ccFotosSeleccionadas[0]);

    if (ccClickHandlerManual) ccMapa.off('click', ccClickHandlerManual);
    ccClickHandlerManual = (e) => {
        ccManualLatLon = { lat: e.latlng.lat, lon: e.latlng.lng };
        ccMapa.eachLayer(l => { if (!(l instanceof L.TileLayer) && !(l instanceof L.GeoJSON)) ccMapa.removeLayer(l); });
        L.marker([ccManualLatLon.lat, ccManualLatLon.lon]).addTo(ccMapa);
        const btnConfirmar = document.getElementById('cc-btn-confirmar-manual');
        if (btnConfirmar) { btnConfirmar.disabled = false; btnConfirmar.onclick = () => ccValidarFotoInstantaneo(true); }
    };
    ccMapa.on('click', ccClickHandlerManual);
}

function ccDesactivarModoManual() {
    ccManualLatLon = null;
    if (ccClickHandlerManual) ccMapa.off('click', ccClickHandlerManual);
    const aviso = document.getElementById('cc-aviso-manual');
    if (aviso) aviso.remove();
    const refImg = document.getElementById('cc-foto-referencia');
    if (refImg) refImg.remove();
}

function ccCargarHistorial() {
    const tbody = document.getElementById('cc-historial-body');
    fetch('/clasificar-cliente/api/historial')
        .then(r => r.json())
        .then(d => {
            if (!d.historial || d.historial.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">Sin consultas todavía</td></tr>';
                return;
            }
            tbody.innerHTML = d.historial.map(h => {
                const resumen = (h.exposicion || []).filter(c => c.en_capa && c.nivel && c.nivel !== 'Bajo')
                    .map(c => `${c.label}: ${c.nivel}`).join(', ') || 'Sin exposición alta';
                return `<tr>
                    <td>${new Date(h.creado_en).toLocaleString('es-PE')}</td>
                    <td>${h.usuario}</td>
                    <td>${h.latitud.toFixed(4)}, ${h.longitud.toFixed(4)}</td>
                    <td>${h.total_fotos}</td>
                    <td>${resumen}</td>
                </tr>`;
            }).join('');
        })
        .catch(() => { tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">Error cargando historial</td></tr>'; });
}

// ============================================================================
// 3. Lote (fotos sueltas 4-100, o 1 .zip) — procesamiento en segundo plano
// ============================================================================

let ccLotePolling = null;
let ccLoteArchivosActuales = null;  // Files en memoria, para poder reintentar sin pedir que vuelvan a seleccionar
let ccLoteIdActual = null;
let ccLoteEsZip = false;

function ccSubirLote() {
    const status = document.getElementById('cc-foto-status');
    status.className = ''; status.textContent = '';

    ccLoteArchivosActuales = ccFotosSeleccionadas;
    ccLoteEsZip = ccLoteArchivosActuales.length === 1 && /\.zip$/i.test(ccLoteArchivosActuales[0].name);

    const btn = document.getElementById('cc-btn-validar');
    btn.disabled = true; btn.textContent = 'Subiendo...';

    const fd = new FormData();
    if (ccLoteEsZip) fd.append('zip', ccLoteArchivosActuales[0]);
    else ccLoteArchivosActuales.forEach(f => fd.append('fotos', f));
    fd.append('capa', ccCapaSeleccionada());

    fetch('/clasificar-cliente/api/clasificar-lote', { method: 'POST', body: fd })
        .then(r => r.json().then(d => ({ ok: r.ok, d })))
        .then(({ ok, d }) => {
            if (!ok) throw new Error(d.error || 'Error subiendo el lote');
            ccLoteIdActual = d.lote_id;
            document.getElementById('cc-progreso-wrap').style.display = 'block';
            status.textContent = `Procesando ${d.total} foto(s)...`;
            ccPollLote(d.lote_id);
        })
        .catch(e => {
            status.className = 'cc-status-error'; status.textContent = 'Error: ' + e.message;
            btn.disabled = false; btn.textContent = 'Evaluar fotos';
        });
}

function ccPollLote(loteId) {
    if (ccLotePolling) clearInterval(ccLotePolling);
    const consultar = () => {
        fetch(`/clasificar-cliente/api/lote/${loteId}/estado`)
            .then(r => r.json())
            .then(d => {
                const pct = d.total ? Math.round(100 * d.procesados / d.total) : 0;
                document.getElementById('cc-progreso-bar').style.width = pct + '%';
                document.getElementById('cc-foto-status').textContent = `${d.procesados} / ${d.total} procesadas...`;
                ccMostrarResultados(d.resultados);

                if (d.estado === 'completo') {
                    clearInterval(ccLotePolling);
                    const btn = document.getElementById('cc-btn-validar');
                    btn.disabled = false; btn.textContent = 'Evaluar fotos';
                    const status = document.getElementById('cc-foto-status');
                    status.className = 'cc-status-ok';
                    status.textContent = `✓ Lote terminado: ${d.total} foto(s).`;

                    const fallidos = d.resultados.filter(r => r.estado === 'error');
                    const cajaFallidos = document.getElementById('cc-lote-fallidos');
                    if (fallidos.length) {
                        cajaFallidos.innerHTML = `<div class="cc-alerta-fallidos">
                            <span>⚠ ${fallidos.length} de ${d.total} no se pudieron ubicar (sin GPS ni texto legible).</span>
                            <button class="cc-btn" style="width:auto; padding:5px 12px; font-size:11px; background:#fc6c44;" onclick="ccReintentarLote()">Reintentar fallidas</button>
                        </div>`;
                    } else {
                        cajaFallidos.innerHTML = '';
                    }
                }
            })
            .catch(() => clearInterval(ccLotePolling));
    };
    consultar();
    ccLotePolling = setInterval(consultar, 2000);
}

function ccReintentarLote() {
    if (!ccLoteArchivosActuales || !ccLoteIdActual) return;
    const status = document.getElementById('cc-foto-status');
    status.className = ''; status.textContent = 'Reintentando fallidas...';
    document.getElementById('cc-lote-fallidos').innerHTML = '';

    const fd = new FormData();
    if (ccLoteEsZip) fd.append('zip', ccLoteArchivosActuales[0]);
    else ccLoteArchivosActuales.forEach(f => fd.append('fotos', f));
    fd.append('lote_id', ccLoteIdActual);
    fd.append('capa', ccCapaSeleccionada());

    fetch('/clasificar-cliente/api/clasificar-lote', { method: 'POST', body: fd })
        .then(r => r.json().then(d => ({ ok: r.ok, d })))
        .then(({ ok, d }) => {
            if (!ok) throw new Error(d.error || 'Error reintentando');
            document.getElementById('cc-progreso-wrap').style.display = 'block';
            ccPollLote(ccLoteIdActual);
        })
        .catch(e => { status.className = 'cc-status-error'; status.textContent = 'Error: ' + e.message; });
}
