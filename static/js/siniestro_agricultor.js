const form = document.getElementById('formSiniestro');
const inputFotos = document.getElementById('inputFotos');
const fotosPreview = document.getElementById('fotosPreview');
const fotosError = document.getElementById('fotosError');
const btnEnviar = document.getElementById('btnEnviar');
let archivosSeleccionados = [];

document.querySelectorAll('.btn-evento input[type=radio]').forEach(radio => {
    radio.addEventListener('change', () => {
        const grupo = radio.name;
        document.querySelectorAll(`.btn-evento input[name=${grupo}]`).forEach(r => {
            r.closest('.btn-evento').classList.toggle('activo', r.checked);
        });
    });
});

async function leerGPS(file) {
    // Lectura REAL del GPS en el navegador (misma librería que usa el server
    // para el mismo dato) — no un chequeo aproximado, así el agricultor ve
    // de una si la foto sirve o no, antes de mandar el reporte.
    try {
        const gps = await exifr.gps(file);
        if (gps && typeof gps.latitude === 'number' && typeof gps.longitude === 'number') {
            return { lat: gps.latitude, lon: gps.longitude };
        }
        return null;
    } catch (e) {
        return null;
    }
}

inputFotos.addEventListener('change', async () => {
    const seleccionados = Array.from(inputFotos.files);
    fotosPreview.innerHTML = '';
    fotosError.style.display = 'none';

    if (seleccionados.length > 6) {
        fotosError.textContent = 'Máximo 6 fotos.';
        fotosError.style.display = 'block';
    }

    // Las fotos sin GPS se RECHAZAN: no se cuentan ni se mandan — hay que
    // Sin EXIF no se rechaza acá — el servidor todavía puede leer la
    // ubicación con OCR del texto quemado en la foto (apps tipo GPS Map
    // Camera). Solo se avisa; el rechazo final (si tampoco hay OCR) lo
    // decide el servidor al enviar.
    archivosSeleccionados = [];
    let sinExif = 0;
    for (const file of seleccionados) {
        const item = document.createElement('div');
        item.className = 'foto-item';
        const img = document.createElement('img');
        img.src = URL.createObjectURL(file);
        item.appendChild(img);
        const gps = await leerGPS(file);
        const badge = document.createElement('div');
        if (gps) {
            badge.className = 'con-gps';
            badge.textContent = '📍 Con ubicación';
        } else {
            badge.className = 'sin-gps';
            badge.textContent = '🔎 Se revisará con OCR';
            sinExif++;
        }
        archivosSeleccionados.push(file);
        item.appendChild(badge);
        fotosPreview.appendChild(item);
    }

    const aceptadas = archivosSeleccionados.length;
    if (sinExif > 0) {
        fotosError.textContent = `${sinExif} foto(s) sin ubicación directa — el sistema va a intentar leer las coordenadas del texto en la foto al enviar. Si no las encuentra, te va a pedir reemplazarlas.`;
        fotosError.style.display = 'block';
    }
});

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    document.getElementById('erroresGenerales').style.display = 'none';

    if (archivosSeleccionados.length < 1) {
        fotosError.textContent = 'Necesitas al menos 1 foto.';
        fotosError.style.display = 'block';
        inputFotos.scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
    }

    btnEnviar.disabled = true;
    btnEnviar.textContent = 'Enviando...';

    const fd = new FormData(form);
    fd.delete('fotos');
    archivosSeleccionados.forEach(f => fd.append('fotos', f));

    try {
        const resp = await fetch('/siniestro/reportar', { method: 'POST', body: fd });
        const data = await resp.json();
        if (!resp.ok || data.status !== 'ok') {
            throw new Error((data.errores || ['Error desconocido']).join(', '));
        }
        document.getElementById('formScreen').style.display = 'none';
        document.getElementById('okNumero').textContent = '#' + data.siniestro_id;
        document.getElementById('okScreen').style.display = 'block';
    } catch (err) {
        document.getElementById('formScreen').style.display = 'none';
        document.getElementById('errMensaje').textContent = err.message;
        document.getElementById('errScreen').style.display = 'block';
    }
});
