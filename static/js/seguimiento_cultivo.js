const mapa = L.map('mapa-seguimiento', {
    scrollWheelZoom: false // la rueda del mouse baja la página normal, no hace zoom
}).setView([-9.19, -75.02], 6); // centro Perú, más zoom inicial

// Click en el mapa activa el zoom con rueda (útil si el usuario sí quiere
// hacer zoom); al salir del mapa se desactiva de nuevo para no atrapar el scroll.
mapa.on('click', () => mapa.scrollWheelZoom.enable());
mapa.getContainer().addEventListener('mouseleave', () => mapa.scrollWheelZoom.disable());

L.tileLayer('https://api.thunderforest.com/atlas/{z}/{x}/{y}.png?apikey=043ce2146e48404a850da16dae37388a', {
    attribution: '&copy; <a href="https://www.thunderforest.com/">Thunderforest</a>, &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    className: 'tiles-suaves'
}).addTo(mapa);

let marcador = null;

function zoomACoordenada(lat, lon) {
    if (marcador) {
        mapa.removeLayer(marcador);
    }
    marcador = L.marker([lat, lon]).addTo(mapa);
    mapa.setView([lat, lon], 14);
}

// ── Filtros Departamento / Provincia / Distrito ────────────────────────
const selDepto = document.getElementById('filtro-departamento');
const selProv = document.getElementById('filtro-provincia');
const selDist = document.getElementById('filtro-distrito');
let ubicaciones = {};

fetch('/seguimiento-cultivo/api/ubicaciones')
    .then(r => r.json())
    .then(data => {
        ubicaciones = data;
        Object.keys(data).sort().forEach(dep => {
            const opt = document.createElement('option');
            opt.value = dep;
            opt.textContent = dep.charAt(0) + dep.slice(1).toLowerCase();
            selDepto.appendChild(opt);
        });
    });

let limiteLayer = null;

function zoomAExtent(departamento, provincia, distrito) {
    const params = new URLSearchParams({ departamento });
    if (provincia) params.set('provincia', provincia);
    if (distrito) params.set('distrito', distrito);

    fetch('/seguimiento-cultivo/api/extent?' + params.toString())
        .then(r => r.json())
        .then(data => {
            if (limiteLayer) {
                mapa.removeLayer(limiteLayer);
                limiteLayer = null;
            }
            if (data.limite) {
                limiteLayer = L.geoJSON(data.limite, {
                    style: { color: '#e64a19', weight: 3, fill: false, dashArray: '6 4' }
                }).addTo(mapa);
            }
            if (data.bounds) {
                mapa.fitBounds(data.bounds, { padding: [20, 20] });
            }
        })
        .catch(err => console.warn('No se pudo obtener el extent', err));
}

selDepto.addEventListener('change', () => {
    const dep = selDepto.value;
    selProv.innerHTML = '<option value="">-- Todas --</option>';
    selDist.innerHTML = '<option value="">-- Todos --</option>';
    selProv.disabled = !dep;
    selDist.disabled = true;

    if (dep && ubicaciones[dep]) {
        Object.keys(ubicaciones[dep]).sort().forEach(prov => {
            const opt = document.createElement('option');
            opt.value = prov;
            opt.textContent = prov.charAt(0) + prov.slice(1).toLowerCase();
            selProv.appendChild(opt);
        });
    }

    cargarCapas(dep);
    if (dep) zoomAExtent(dep, '', '');
});

selProv.addEventListener('change', () => {
    const dep = selDepto.value;
    const prov = selProv.value;
    selDist.innerHTML = '<option value="">-- Todos --</option>';
    selDist.disabled = !prov;

    if (dep && prov && ubicaciones[dep] && ubicaciones[dep][prov]) {
        ubicaciones[dep][prov].forEach(dist => {
            const opt = document.createElement('option');
            opt.value = dist;
            opt.textContent = dist.charAt(0) + dist.slice(1).toLowerCase();
            selDist.appendChild(opt);
        });
    }

    zoomAExtent(dep, prov, '');
});

selDist.addEventListener('change', () => {
    const dep = selDepto.value;
    const prov = selProv.value;
    const dist = selDist.value;
    zoomAExtent(dep, prov, dist);
});

// ── Capas del mapa ───────────────────────────────────────────────────
// Orden de dibujo: zona_agricola (fondo) -> sector_estadistico -> arroz -> mango
const CAPAS_ORDEN = ['zona_agricola', 'sector_estadistico', 'arroz', 'mango'];
const CAPAS_ESTILO = {
    zona_agricola:      { color: '#66bb6a', weight: 1, fillColor: '#c8e6c9', fillOpacity: 0.5 },
    sector_estadistico: { color: '#1e88e5', weight: 1, fillOpacity: 0 },
    arroz:               { color: '#fbc02d', weight: 1, fillColor: '#fff59d', fillOpacity: 0.45 },
    mango:                { color: '#e64a19', weight: 1, fillColor: '#ffab91', fillOpacity: 0.45 },
};
const capasLayer = {}; // nombre -> L.geoJSON layer actual

function limpiarCapas() {
    CAPAS_ORDEN.forEach(nombre => {
        if (capasLayer[nombre]) {
            mapa.removeLayer(capasLayer[nombre]);
            delete capasLayer[nombre];
        }
    });
}

function checkboxActivo(nombre) {
    return document.getElementById('capa-' + nombre).checked;
}

const statusDiv = document.getElementById('capas-status');

function cargarCapas(departamento) {
    limpiarCapas();
    statusDiv.textContent = '';
    if (!departamento) return;

    statusDiv.textContent = 'Cargando capas de ' + departamento + '...';
    const resumen = [];

    // Se cargan en orden para que zona_agricola quede al fondo
    CAPAS_ORDEN.reduce((promesaAnterior, nombre) => {
        return promesaAnterior.then(() =>
            fetch(`/seguimiento-cultivo/api/capa/${nombre}?departamento=${encodeURIComponent(departamento)}`)
                .then(r => {
                    if (!r.ok) throw new Error('HTTP ' + r.status);
                    return r.json();
                })
                .then(geojson => {
                    if (geojson.error) throw new Error(geojson.error);
                    const nFeatures = (geojson.features || []).length;
                    const layer = L.geoJSON(geojson, {
                        style: CAPAS_ESTILO[nombre],
                        onEachFeature: (feature, capaFeature) => {
                            const p = feature.properties || {};
                            if (nombre === 'sector_estadistico' && p.NOM_SE) {
                                capaFeature.bindTooltip(p.NOM_SE, { sticky: true });
                            } else if (nombre === 'zona_agricola' && p.NOM_SE) {
                                capaFeature.bindTooltip(p.NOM_SE, { sticky: true });
                            } else if (nombre === 'arroz' && p.NOMBDEP) {
                                capaFeature.bindTooltip('Arroz - ' + p.NOMBDEP, { sticky: true });
                            } else if (nombre === 'mango' && p.NOMBDIST) {
                                capaFeature.bindTooltip('Mango - ' + p.NOMBDIST, { sticky: true });
                            }
                        }
                    });
                    capasLayer[nombre] = layer;
                    if (checkboxActivo(nombre)) {
                        layer.addTo(mapa);
                    }
                    resumen.push(nombre + ': ' + nFeatures);
                })
                .catch(err => {
                    console.warn('No se pudo cargar capa', nombre, err);
                    resumen.push(nombre + ': ERROR (' + err.message + ')');
                })
        );
    }, Promise.resolve()).then(() => {
        statusDiv.textContent = resumen.join(' | ');
    });
}

CAPAS_ORDEN.forEach(nombre => {
    document.getElementById('capa-' + nombre).addEventListener('change', (e) => {
        const layer = capasLayer[nombre];
        if (!layer) return;
        if (e.target.checked) {
            layer.addTo(mapa);
        } else {
            mapa.removeLayer(layer);
        }
    });
});

document.getElementById('form-consulta').addEventListener('submit', async (e) => {
    e.preventDefault();

    const lat = parseFloat(document.getElementById('input-lat').value);
    const lon = parseFloat(document.getElementById('input-lon').value);
    const fecha = document.getElementById('input-fecha').value;
    const cultivo = document.getElementById('input-cultivo').value;

    zoomACoordenada(lat, lon);

    const resultadoDiv = document.getElementById('resultado');
    const titulo = document.getElementById('resultado-titulo');
    const mensaje = document.getElementById('resultado-mensaje');

    try {
        const resp = await fetch('/seguimiento-cultivo/api/consultar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lat, lon, fecha, cultivo })
        });
        const data = await resp.json();

        resultadoDiv.style.display = 'block';
        resultadoDiv.className = 'resultado-section resultado-' + (data.estado || 'pendiente');

        if (data.estado === 'si') {
            titulo.textContent = '✓ Sí se sembró ' + cultivo;
        } else if (data.estado === 'no') {
            titulo.textContent = '✗ No se sembró ' + cultivo;
        } else {
            titulo.textContent = '⏳ Pendiente';
        }
        mensaje.textContent = data.mensaje || '';
    } catch (err) {
        resultadoDiv.style.display = 'block';
        resultadoDiv.className = 'resultado-section resultado-pendiente';
        titulo.textContent = 'Error';
        mensaje.textContent = 'No se pudo consultar: ' + err.message;
    }
});
