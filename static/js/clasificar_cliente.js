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
