// Clasifica tu Cliente — sube un Excel de clientes/prospectos externos,
// los clasifica contra la capa de riesgo elegida y descarga el resultado
// (2 hojas: Clasificados / No Clasificados). Reutiliza el mismo endpoint
// que ya usa Mapa Clientes (/api/capas-riesgo/<nombre>/clasificar-excel).

document.addEventListener('DOMContentLoaded', () => {
    fetch('/api/capas-riesgo/disponibles')
        .then(r => r.json())
        .then(capas => {
            const select = document.getElementById('cc-capa');
            const disponibles = capas.filter(c => c.disponible);
            if (!disponibles.length) {
                select.innerHTML = '<option value="">-- Ninguna capa disponible todavía --</option>';
                return;
            }
            select.innerHTML = disponibles.map(c => `<option value="${c.id}">${c.label}</option>`).join('');
        })
        .catch(() => {
            document.getElementById('cc-capa').innerHTML = '<option value="">-- Error cargando capas --</option>';
        });
});

// ── Pestañas ──
function ccCambiarTab(tab) {
    document.getElementById('cc-tab-excel').classList.toggle('activo', tab === 'excel');
    document.getElementById('cc-tab-foto').classList.toggle('activo', tab === 'foto');
    document.getElementById('cc-pane-excel').classList.toggle('activo', tab === 'excel');
    document.getElementById('cc-pane-foto').classList.toggle('activo', tab === 'foto');
    if (tab === 'foto') ccCargarHistorial();
}

// ── Foto georreferenciada: preview con GPS ──
let ccFotosSeleccionadas = [];
let ccMapaFoto = null;

const ccInputFotos = document.getElementById('cc-fotos');
if (ccInputFotos) {
    ccInputFotos.addEventListener('change', async () => {
        const archivos = Array.from(ccInputFotos.files).slice(0, 3);
        ccFotosSeleccionadas = archivos;
        const preview = document.getElementById('cc-fotos-preview');
        preview.innerHTML = '';
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
                badge.textContent = tiene ? '📍 Con GPS' : '⚠️ Sin GPS';
            } catch (e) {
                badge.style.background = 'rgba(220,53,69,.85)';
                badge.textContent = '⚠️ Sin GPS';
            }
            item.appendChild(badge);
            preview.appendChild(item);
        }
    });
}

let ccManualLatLon = null;  // {lat, lon} cuando el usuario marca el punto a mano
let ccClickHandlerManual = null;

function ccValidarFoto(reintentoManual) {
    const status = document.getElementById('cc-foto-status');
    status.className = ''; status.textContent = '';

    if (ccFotosSeleccionadas.length === 0) {
        status.className = 'error';
        status.textContent = 'Selecciona al menos 1 foto.';
        return;
    }

    const btn = document.getElementById('cc-btn-validar');
    btn.disabled = true;
    btn.textContent = 'Validando...';

    const fd = new FormData();
    ccFotosSeleccionadas.forEach(f => fd.append('fotos', f));
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
                    status.className = 'error';
                    status.textContent = 'No se pudo leer la ubicación automática — mira la foto y haz click en el mapa donde está la parcela.';
                    return;
                }
                throw new Error(d.error || 'Error validando');
            }
            ccDesactivarModoManual();
            ccMostrarResultadoFoto(d);
            status.className = 'ok';
            status.textContent = '✓ Validado y guardado en el historial.';
            ccCargarHistorial();
        })
        .catch(e => {
            status.className = 'error';
            status.textContent = 'Error: ' + e.message;
        })
        .finally(() => {
            btn.disabled = false;
            btn.textContent = '📍 Validar exposición';
        });
}

function ccActivarModoManual() {
    ccInicializarMapa();
    let aviso = document.getElementById('cc-aviso-manual');
    if (!aviso) {
        aviso = document.createElement('div');
        aviso.id = 'cc-aviso-manual';
        aviso.className = 'alert alert-warning py-2 small mt-2';
        document.getElementById('cc-mapa-foto').insertAdjacentElement('afterend', aviso);
    }
    aviso.innerHTML = 'Haz click en el mapa donde está la parcela (mira la foto de abajo como referencia). ' +
        '<button type="button" class="btn btn-sm btn-success mt-1 d-block" id="cc-btn-confirmar-manual" disabled>Confirmar esta ubicación</button>';

    // Mostrar la primera foto en grande como referencia para ubicarla.
    let refImg = document.getElementById('cc-foto-referencia');
    if (!refImg) {
        refImg = document.createElement('img');
        refImg.id = 'cc-foto-referencia';
        refImg.style.cssText = 'max-width:100%; border-radius:8px; margin-top:.5rem;';
        aviso.insertAdjacentElement('afterend', refImg);
    }
    refImg.src = URL.createObjectURL(ccFotosSeleccionadas[0]);

    if (ccClickHandlerManual) ccMapaFoto.off('click', ccClickHandlerManual);
    ccClickHandlerManual = (e) => {
        ccManualLatLon = { lat: e.latlng.lat, lon: e.latlng.lng };
        ccMapaFoto.eachLayer(l => { if (!(l instanceof L.TileLayer)) ccMapaFoto.removeLayer(l); });
        L.marker([ccManualLatLon.lat, ccManualLatLon.lon]).addTo(ccMapaFoto);
        const btnConfirmar = document.getElementById('cc-btn-confirmar-manual');
        if (btnConfirmar) {
            btnConfirmar.disabled = false;
            btnConfirmar.onclick = () => ccValidarFoto(true);
        }
    };
    ccMapaFoto.on('click', ccClickHandlerManual);
}

function ccDesactivarModoManual() {
    ccManualLatLon = null;
    if (ccClickHandlerManual && ccMapaFoto) ccMapaFoto.off('click', ccClickHandlerManual);
    const aviso = document.getElementById('cc-aviso-manual');
    if (aviso) aviso.remove();
    const refImg = document.getElementById('cc-foto-referencia');
    if (refImg) refImg.remove();
}

// Color del siniestro cercano según cómo quedó evaluado por el Inspector:
// Verificado = va a ser indemnizado (rojo), Rechazado = plomo, Pendiente = amarillo.
const CC_COLOR_ESTADO = { 'Verificado': '#dc3545', 'Rechazado': '#6c757d', 'Pendiente': '#ffc107' };

function ccInicializarMapa() {
    if (ccMapaFoto) return ccMapaFoto;
    ccMapaFoto = L.map('cc-mapa-foto').setView([-9.19, -75.02], 5.5);  // Perú completo por defecto
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap' }).addTo(ccMapaFoto);
    setTimeout(() => ccMapaFoto.invalidateSize(), 200);
    return ccMapaFoto;
}

document.addEventListener('DOMContentLoaded', ccInicializarMapa);

function ccMostrarResultadoFoto(d) {
    ccInicializarMapa();
    ccMapaFoto.eachLayer(l => { if (!(l instanceof L.TileLayer)) ccMapaFoto.removeLayer(l); });
    ccMapaFoto.setView([d.latitud, d.longitud], 13);
    L.marker([d.latitud, d.longitud]).addTo(ccMapaFoto).bindPopup('Cliente/parcela').openPopup();
    (d.siniestros_cercanos || []).forEach(c => {
        const color = CC_COLOR_ESTADO[c.estado] || '#fc6c44';
        L.circleMarker([c.latitud, c.longitud], { radius: 7, color, fillColor: color, fillOpacity: .8 })
            .addTo(ccMapaFoto).bindPopup(`Siniestro #${c.id} — ${c.evento}<br>${c.estado} · ${c.distancia_km} km`);
    });
    setTimeout(() => ccMapaFoto.invalidateSize(), 200);

    const lista = document.getElementById('cc-exposicion-lista');
    lista.innerHTML = d.exposicion.map(c => `
        <div class="cc-exposicion-row">
            <span>${c.label}</span>
            ${c.en_capa
                ? `<span class="cc-nivel-badge" style="background:${c.color || '#999'};">${c.nivel}</span>`
                : `<span class="text-muted small">${c.disponible ? 'No expuesto' : 'No disponible'}</span>`}
        </div>
    `).join('') + (d.siniestros_cercanos.length
        ? `<div class="mt-2 small text-muted">${d.siniestros_cercanos.length} siniestro(s) reportado(s) cerca (≤5km)</div>`
        : '<div class="mt-2 small text-muted">Sin siniestros cercanos reportados</div>');
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

function ccClasificar() {
    const capa = document.getElementById('cc-capa').value;
    const fileInput = document.getElementById('cc-archivo');
    const file = fileInput.files[0];
    const status = document.getElementById('cc-status');
    status.className = '';
    status.textContent = '';

    if (!capa) {
        status.className = 'error';
        status.textContent = 'Selecciona una capa de riesgo.';
        return;
    }
    if (!file) {
        status.className = 'error';
        status.textContent = 'Elige un archivo Excel primero.';
        return;
    }

    const btn = document.getElementById('cc-btn-clasificar');
    btn.disabled = true;
    btn.textContent = 'Clasificando...';

    const fd = new FormData();
    fd.append('excel', file);

    fetch(`/api/capas-riesgo/${capa}/clasificar-excel`, { method: 'POST', body: fd })
        .then(r => {
            if (!r.ok) return r.json().then(d => { throw new Error(d.error || 'Error clasificando'); });
            return r.blob();
        })
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `clientes_clasificados_${capa}.xlsx`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
            status.className = 'ok';
            status.textContent = '✓ Listo, revisa tu carpeta de descargas.';
        })
        .catch(e => {
            status.className = 'error';
            status.textContent = 'Error: ' + e.message;
        })
        .finally(() => {
            btn.disabled = false;
            btn.textContent = '⬆ Clasificar y Descargar';
        });
}
