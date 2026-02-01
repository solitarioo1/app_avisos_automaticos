/* ============================================================================
   DECISIONES.JS - Página Centro de Decisiones
   Lógica interactiva del mapa de decisiones
   ============================================================================ */

document.addEventListener('DOMContentLoaded', function() {
    initializeDecisiones();
});

function initializeDecisiones() {
    console.log('🎯 Centro de Decisiones iniciado');
    setupDepartamentoInteractivity();
    updateFecha();
}

function setupDepartamentoInteractivity() {
    const departamentos = document.querySelectorAll('.departamento-item');
    const tooltip = document.getElementById('dept-tooltip-decisiones');
    const detailPanel = document.getElementById('dept-detail-decisiones');
    
    departamentos.forEach(dept => {
        dept.addEventListener('mouseover', function() {
            const deptName = this.getAttribute('data-dept');
            tooltip.textContent = `${deptName} - Click para ver detalles`;
            tooltip.style.left = this.style.left;
            tooltip.style.top = (parseInt(this.style.top) + 80) + 'px';
            tooltip.style.display = 'block';
        });
        
        dept.addEventListener('mouseout', function() {
            tooltip.style.display = 'none';
        });
        
        dept.addEventListener('click', function() {
            const deptName = this.getAttribute('data-dept');
            mostrarDetallesDepto(deptName, detailPanel);
        });
    });
}

function mostrarDetallesDepto(deptName, panel) {
    const html = `
        <h6 class="text-primary">📍 ${deptName}</h6>
        <div class="alert alert-warning py-2 px-3">
            <small><strong>Nivel:</strong> ALTO RIESGO</small><br>
            <small><strong>Agricultores afectados:</strong> 1,247</small><br>
            <small><strong>Cultivos en riesgo:</strong> Arroz, Maíz</small>
        </div>
        <div class="mt-2">
            <button class="btn btn-sm btn-danger w-100 mb-2" onclick="activarBrigadas()">
                🚨 Activar Brigadas
            </button>
            <button class="btn btn-sm btn-warning w-100" onclick="notificarAutoridades()">
                📢 Notificar Autoridades
            </button>
        </div>
    `;
    panel.innerHTML = html;
}

function resetMapaDecisiones() {
    const detailPanel = document.getElementById('dept-detail-decisiones');
    detailPanel.innerHTML = `
        <h6 class="text-primary">📍 Información Regional</h6>
        <div class="alert alert-info py-2 px-3">
            <small>Seleccione un departamento en el mapa para ver análisis detallado</small>
        </div>
    `;
}

function toggleProvinciasDecisiones() {
    alert('Vista provincial en desarrollo');
}

function exportarMapaDecisiones() {
    alert('Exportación de reporte en desarrollo');
}

function activarBrigadas() {
    mostrarModal('✅ Brigadas Activadas', 'Se han activado las brigadas de respuesta en la región', 'success');
}

function notificarAutoridades() {
    mostrarModal('📢 Notificación Enviada', 'Las autoridades regionales han sido notificadas', 'info');
}

function enviarAlertaWhatsApp() {
    mostrarModal('✅ Alerta Enviada', 'Se envió alerta WhatsApp a 1,247 agricultores', 'success');
}

function activarEquiposTecnicos() {
    mostrarModal('🔧 Equipos Activados', 'Los equipos técnicos están en camino', 'success');
}

function generarReporteCompleto() {
    mostrarModal('📊 Reporte Generado', 'Reporte PDF descargado correctamente', 'success');
}

function updateFecha() {
    const now = new Date();
    const dateString = now.toLocaleString('es-ES', {
        weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });
    const fechaEl = document.getElementById('fecha-actual');
    if (fechaEl) fechaEl.textContent = dateString;
}
