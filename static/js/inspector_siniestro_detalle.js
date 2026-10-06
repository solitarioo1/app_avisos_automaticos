const siniestroId = document.getElementById('app').dataset.id;
let mapa = null;

function fila(label, valor) {
    return `<div class="fila-dato"><span>${label}</span><strong>${valor ?? '-'}</strong></div>`;
}

fetch(`/evaluacion-riesgo/api/siniestros/${siniestroId}`)
    .then(r => r.json())
    .then(d => {
        document.getElementById('cargando').style.display = 'none';
        document.getElementById('contenido').style.display = 'block';

        document.getElementById('datosAgricultor').innerHTML =
            fila('DNI', d.dni) + fila('Nombre completo', d.nombre_completo) +
            fila('Celular principal', d.celular1) + fila('Celular secundario', d.celular2) +
            fila('Correo', d.correo);

        document.getElementById('datosEvento').innerHTML =
            fila('Cultivo afectado', d.cultivo_afectado) + fila('Alcance del daño', d.alcance_dano) +
            fila('Evento', d.evento) + fila('Fecha del evento', new Date(d.fecha_evento + 'T00:00:00').toLocaleDateString('es-PE')) +
            fila('Reportado el', new Date(d.creado_en).toLocaleString('es-PE'));

        const fFecha = (s) => s ? new Date(s + 'T00:00:00').toLocaleDateString('es-PE') : '-';
        if (d.cliente) {
            const c = d.cliente;
            document.getElementById('datosCliente').innerHTML =
                fila('¿Cliente asegurado?', '<span class="senal-ok">Sí</span>') +
                fila('Vigente', c.vigente ? '<span class="senal-ok">Sí</span>' : '<span class="senal-no">No</span>') +
                fila('Nombre registrado', `${c.nombre} ${c.apellido}`) +
                fila('Teléfono registrado', c.telefono) +
                fila('Entidad financiera', c.entidad_nombre) +
                fila('Cultivo / Variedad', [c.cultivo_nombre, c.variedad].filter(Boolean).join(' / ')) +
                fila('Siembra → Cosecha', `${fFecha(c.fecha_siembra)} → ${fFecha(c.fecha_cosecha)}`) +
                fila('Vigencia póliza', `${fFecha(c.mes_inicio_vigencia)} → ${fFecha(c.mes_fin_vigencia)}`) +
                fila('Hectáreas (total / aseguradas)', `${c.hectareas ?? '-'} / ${c.area_asegurada ?? '-'}`) +
                fila('Suma asegurada', c.monto_asegurado ? 'S/ ' + c.monto_asegurado : '-') +
                fila('Prima neta', c.prima_neta ? 'S/ ' + c.prima_neta : '-') +
                fila('Tasa reaseguro', c.tasa_reaseguro ? (c.tasa_reaseguro * 100).toFixed(2) + '%' : '-');
        } else {
            document.getElementById('datosCliente').innerHTML =
                '<div class="alert alert-warning py-2 mb-0 small">⚠️ Este DNI no está en la base de clientes asegurados.</div>';
        }

        // Exposición ya precalculada del cliente (botón "Actualizar Cruce" de Mapa Clientes)
        const colorNivel = { 'Muy Alto': '#c0392b', 'Alto': '#e67e22', 'Medio': '#f1c40f', 'Bajo': '#2ecc71' };
        if (d.cliente && d.cliente.exposicion_precalculada && Object.keys(d.cliente.exposicion_precalculada).length) {
            document.getElementById('exposicionPrecalculada').innerHTML =
                Object.entries(d.cliente.exposicion_precalculada).map(([capa, nivel]) => `
                    <div class="exposicion-row">
                        <span>${capa}</span>
                        <span class="nivel-chip" style="background:${colorNivel[nivel] || '#999'};">${nivel || '-'}</span>
                    </div>
                `).join('');
        } else {
            document.getElementById('exposicionPrecalculada').innerHTML =
                '<span class="text-muted small">Sin cliente asegurado o sin cruce calculado todavía ("Actualizar Cruce" en Mapa Clientes).</span>';
        }

        document.getElementById('fotosGrid').innerHTML = d.fotos.length
            ? d.fotos.map(f => f.url_drive
                ? `<a href="${f.url_drive}" target="_blank"><i class="bi bi-image" style="font-size:1.5rem;"></i></a>`
                : `<a href="#" class="text-warning">⏳ Subiendo...</a>`).join('')
            : '<span class="text-muted small">Sin fotos</span>';

        // Mapa
        mapa = L.map('mapaSiniestro');
        L.tileLayer('https://api.thunderforest.com/atlas/{z}/{x}/{y}.png?apikey=043ce2146e48404a850da16dae37388a', { attribution: '&copy; <a href="https://www.thunderforest.com/">Thunderforest</a>, &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(mapa);
        if (d.latitud != null) {
            mapa.setView([d.latitud, d.longitud], 12);
            L.marker([d.latitud, d.longitud]).addTo(mapa).bindPopup(`Siniestro #${siniestroId}`);
            const colorEstado = { 'Verificado': '#dc3545', 'Rechazado': '#6c757d', 'Pendiente': '#ffc107' };
            d.cercanos.forEach(c => {
                const color = colorEstado[c.estado] || '#fc6c44';
                L.circleMarker([c.latitud, c.longitud], { radius: 7, color, fillColor: color, fillOpacity: .8 })
                    .addTo(mapa).bindPopup(`#${c.id} — ${c.evento}<br>${c.estado} · ${c.distancia_km} km`);
            });
        } else {
            mapa.setView([-9.19, -75.02], 5);
        }

        // Estaciones meteorológicas: SIEMPRE visibles (obligatorio, no opcional).
        fetch('/evaluacion-riesgo/api/estaciones')
            .then(r => r.json())
            .then(geo => {
                (geo.features || []).forEach(f => {
                    const [lon, lat] = f.geometry.coordinates;
                    const p = f.properties;
                    L.circleMarker([lat, lon], {
                        radius: 4, color: p.tiene_datos ? '#0d6efd' : '#adb5bd',
                        fillColor: p.tiene_datos ? '#0d6efd' : '#adb5bd', fillOpacity: .6, weight: 1,
                    }).bindTooltip(`${p.nombre} (${p.codigo})${p.tiene_datos ? '' : ' — sin histórico'}`)
                      .addTo(mapa);
                });
            })
            .catch(() => {});

        // Selector de capa de riesgo sobre el mapa (recorta por el departamento del siniestro).
        const departamentoSiniestro = (d.verificacion && d.verificacion.departamento) || '';
        let capaLayerActual = null;
        fetch('/api/capas-riesgo/disponibles')
            .then(r => r.json())
            .then(capas => {
                const sel = document.getElementById('selCapaMapa');
                (capas || []).filter(c => c.disponible).forEach(c => {
                    const op = document.createElement('option');
                    op.value = c.id; op.textContent = c.label;
                    sel.appendChild(op);
                });
                sel.addEventListener('change', () => {
                    if (capaLayerActual) { mapa.removeLayer(capaLayerActual); capaLayerActual = null; }
                    if (!sel.value || !departamentoSiniestro) return;
                    fetch(`/api/capas-riesgo/${sel.value}/geometria?depto=${encodeURIComponent(departamentoSiniestro)}`)
                        .then(r => r.json())
                        .then(gj => {
                            if (gj.error || !gj.features || !gj.features.length) return;
                            capaLayerActual = L.geoJSON(gj, {
                                style: (f) => ({ fillColor: f.properties.color_display || '#999', fillOpacity: .45, color: '#555', weight: .4 })
                            }).addTo(mapa);
                            capaLayerActual.bringToBack();
                        });
                });
            })
            .catch(() => {});

        document.getElementById('cercanosLista').innerHTML = d.cercanos.length
            ? `<strong>${d.cercanos.length} siniestro(s) cercano(s) (≤5km):</strong><br>` +
              d.cercanos.map(c => `<a href="/evaluacion-riesgo/siniestros/${c.id}">#${c.id}</a> ${c.evento} — ${c.distancia_km}km`).join('<br>')
            : '<span class="text-muted">Sin otros siniestros cerca</span>';

        // Verificación
        if (d.verificacion && !d.verificacion.error) {
            const v = d.verificacion;
            document.getElementById('verificacion').innerHTML = `
                <div class="p-2 rounded mb-2 text-center fw-bold ${v.veredicto ? 'veredicto-si' : 'veredicto-no'}">
                    ${v.veredicto ? '✓ RESPALDADO por los datos' : '✗ NO respaldado por los datos'}
                    <div class="small fw-normal">${v.señales_positivas} de 3 señales positivas</div>
                </div>
                ${fila('Capa de riesgo', v.capas.map(c => `${c.label}: ${c.en_capa ? 'Sí (' + c.nivel + ')' : 'No'}`).join(', ') || '-')}
                ${fila('Aviso SENAMHI', v.aviso ? 'Sí' : 'No')}
                ${v.estacion ? fila('Estación (' + v.estacion.distancia_km + 'km)', v.estacion.valor + ' ' + v.unidad + (v.estacion.supera_percentil ? ' (supera percentil)' : '')) : fila('Estación', 'Sin dato cercano')}
            `;
            if (v.estacion && v.estacion.grafica) {
                const fe = new Date(d.fecha_evento + 'T00:00:00');
                const diasEnMes = new Date(fe.getFullYear(), fe.getMonth() + 1, 0).getDate();
                graficarEstacion(v.estacion.grafica, diasEnMes);
            }
        } else {
            document.getElementById('verificacion').innerHTML =
                '<div class="text-muted small">No se puede auto-verificar (evento "Otro" o sin ubicación GPS) — evalúa manualmente con las fotos.</div>';
        }

        document.getElementById('selEstado').value = d.estado;
        document.getElementById('txtComentario').value = d.comentario_inspector || '';
        if (d.evaluado_por) {
            document.getElementById('evaluacionInfo').textContent = `Última evaluación: ${d.evaluado_por}, ${new Date(d.evaluado_en).toLocaleString('es-PE')}`;
        }
    });

function graficarEstacion(grafica, diasEnMes, diaEvento) {
    const canvas = document.getElementById('graficaEstacion');
    canvas.style.display = 'block';
    const n = diasEnMes || 31;
    const dias = Array.from({ length: n }, (_, i) => i + 1);

    // La serie diaria no trae todos los días (solo los que tienen dato) —
    // se arma un arreglo de tamaño fijo (1..n) con null donde no hay dato,
    // así Chart.js no conecta/inventa valores en los huecos.
    const porDia = (serie) => {
        const map = new Map((serie?.diaria || []).map(p => [p.dia, p.valor]));
        return dias.map(d => map.has(d) ? map.get(d) : null);
    };
    const lineaPlano = (valor) => valor == null ? [] : Array(n).fill(valor);

    const ctx = canvas.getContext('2d');
    const gradientPP = ctx.createLinearGradient(0, 0, 0, 220);
    gradientPP.addColorStop(0, 'rgba(31,111,235,.85)');
    gradientPP.addColorStop(1, 'rgba(31,111,235,.25)');

    Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif";

    new Chart(canvas, {
        type: 'bar',
        data: {
            labels: dias,
            datasets: [
                {
                    type: 'bar', label: 'Precipitación (mm)', data: porDia(grafica.precipitacion),
                    backgroundColor: gradientPP, borderRadius: 4, borderSkipped: false,
                    barPercentage: .7, yAxisID: 'y', order: 3,
                },
                {
                    type: 'line', label: 'Temp. máx (°C)', data: porDia(grafica.temp_max),
                    borderColor: '#e67e22', backgroundColor: '#e67e22', borderWidth: 2.5,
                    pointRadius: 2, pointHoverRadius: 5, tension: .35, spanGaps: true, yAxisID: 'y1', order: 1,
                },
                {
                    type: 'line', label: 'Temp. mín (°C)', data: porDia(grafica.temp_min),
                    borderColor: '#2980b9', backgroundColor: '#2980b9', borderWidth: 2.5,
                    pointRadius: 2, pointHoverRadius: 5, tension: .35, spanGaps: true, yAxisID: 'y1', order: 2,
                },
                {
                    type: 'line', label: `P90 (${grafica.precipitacion?.p90?.toFixed(1) ?? '-'} mm)`,
                    data: lineaPlano(grafica.precipitacion?.p90), borderColor: '#6c757d',
                    borderDash: [6, 4], borderWidth: 1.5, pointRadius: 0, yAxisID: 'y', order: 4,
                },
                {
                    type: 'line', label: `P95 (${grafica.precipitacion?.p95?.toFixed(1) ?? '-'} mm)`,
                    data: lineaPlano(grafica.precipitacion?.p95), borderColor: '#dc3545',
                    borderDash: [2, 2], borderWidth: 1.5, pointRadius: 0, yAxisID: 'y', order: 4,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                title: {
                    display: true, text: 'Precipitación y temperatura — día a día del mes reportado',
                    font: { size: 12, weight: '600' }, color: '#2c3e50', padding: { bottom: 10 },
                },
                legend: {
                    position: 'bottom',
                    labels: { usePointStyle: true, boxWidth: 8, font: { size: 10.5 }, padding: 12 },
                },
                tooltip: {
                    backgroundColor: 'rgba(33,37,41,.92)', padding: 10, cornerRadius: 8,
                    titleFont: { size: 12, weight: '600' }, bodyFont: { size: 11.5 },
                    callbacks: { title: (items) => `Día ${items[0].label}` },
                },
            },
            scales: {
                x: {
                    grid: { display: false },
                    title: { display: true, text: 'Día del mes', font: { size: 10.5 } },
                    ticks: { font: { size: 9.5 } },
                },
                y: {
                    position: 'left', title: { display: true, text: 'PP (mm)', font: { size: 10.5 } },
                    grid: { color: 'rgba(0,0,0,.05)' }, beginAtZero: true,
                },
                y1: {
                    position: 'right', title: { display: true, text: '°C', font: { size: 10.5 } },
                    grid: { drawOnChartArea: false },
                },
            },
        },
    });
}

function guardarEvaluacion() {
    const estado = document.getElementById('selEstado').value;
    const comentario = document.getElementById('txtComentario').value;
    fetch(`/evaluacion-riesgo/api/siniestros/${siniestroId}/evaluar`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ estado, comentario })
    }).then(r => r.json()).then(d => {
        if (d.status === 'ok') { alert('Evaluación guardada'); location.reload(); }
        else alert('Error: ' + (d.error || 'desconocido'));
    });
}
