const tablaBody = document.getElementById('tablaBody');
const badgeEstado = (e) => ({
    'Pendiente': 'bg-warning text-dark', 'Verificado': 'bg-success', 'Rechazado': 'bg-danger'
}[e] || 'bg-secondary');

function cargar(estado) {
    tablaBody.innerHTML = '<tr><td colspan="10" class="text-center text-muted py-4">Cargando...</td></tr>';
    fetch(`/evaluacion-riesgo/api/siniestros${estado ? '?estado=' + estado : ''}`)
        .then(r => r.json())
        .then(data => {
            if (!data.siniestros || data.siniestros.length === 0) {
                tablaBody.innerHTML = '<tr><td colspan="10" class="text-center text-muted py-4">No hay siniestros</td></tr>';
                return;
            }
            tablaBody.innerHTML = data.siniestros.map(s => `
                <tr onclick="location.href='/evaluacion-riesgo/siniestros/${s.id}'" style="cursor:pointer;">
                    <td>#${s.id}</td>
                    <td>${new Date(s.creado_en).toLocaleDateString('es-PE')}</td>
                    <td>${s.dni}</td>
                    <td>${s.nombre_completo}</td>
                    <td>${s.cultivo_afectado}</td>
                    <td>${s.evento}</td>
                    <td>${new Date(s.fecha_evento + 'T00:00:00').toLocaleDateString('es-PE')}</td>
                    <td><i class="bi bi-camera"></i> ${s.total_fotos}</td>
                    <td><span class="badge ${badgeEstado(s.estado)}">${s.estado}</span></td>
                    <td><i class="bi bi-chevron-right text-muted"></i></td>
                </tr>
            `).join('');
        });
}

document.querySelectorAll('#filtroEstado .nav-link').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('#filtroEstado .nav-link').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        cargar(btn.dataset.estado);
    });
});

cargar('');
