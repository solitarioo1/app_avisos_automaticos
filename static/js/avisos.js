/* ============================================================================
   AVISOS.JS - Página de Avisos
   Lógica de filtrado y gestión de avisos
   ============================================================================ */

const AVISOS_ORIGINALES = [];

function guardarAvisosOriginales() {
    const filas = document.querySelectorAll('#tabla-avisos tr');
    filas.forEach(fila => {
        AVISOS_ORIGINALES.push({
            numero: fila.getAttribute('data-numero'),
            nivel: fila.getAttribute('data-nivel'),
            color: fila.getAttribute('data-color'),
            descargado: fila.getAttribute('data-descargado'),
            procesado: fila.getAttribute('data-procesado'),
            fecha: fila.getAttribute('data-fecha'),
            html: fila.outerHTML
        });
    });
}

function aplicarFiltros() {
    const nivelSeleccionado = document.getElementById('filtro-nivel').value;
    const orden = document.getElementById('filtro-orden').value;
    const numero = document.getElementById('filtro-numero').value.toLowerCase();
    
    let avisosFiltrados = AVISOS_ORIGINALES.filter(aviso => {
        const color = aviso.color ? aviso.color.toLowerCase() : '';
        const cumpleNivel = !nivelSeleccionado || color === nivelSeleccionado;
        const cumpleNumero = !numero || aviso.numero.toString().includes(numero);
        
        return cumpleNivel && cumpleNumero;
    });
    
    if (orden === 'asc') {
        avisosFiltrados.sort((a, b) => new Date(a.fecha) - new Date(b.fecha));
    } else {
        avisosFiltrados.sort((a, b) => new Date(b.fecha) - new Date(a.fecha));
    }
    
    const tbody = document.getElementById('tabla-avisos');
    tbody.innerHTML = avisosFiltrados.map(a => a.html).join('');
}

async function consultarNuevos() {
    const btn = document.getElementById('btnConsultarNuevos');
    const originalHTML = btn.innerHTML;
    
    try {
        btn.disabled = true;
        btn.innerHTML = '<i class="bi bi-hourglass-split spin"></i> Consultando...';
        
        const response = await fetch('/api/avisos/nuevos');
        const data = await response.json();
        
        if (data.status === 'success') {
            const total = data.total_nuevos;
            
            if (total > 0) {
                mostrarModal('✅ Avisos Nuevos Encontrados', `Se encontraron <strong>${total}</strong> aviso(s) nuevo(s) en las últimas 24 horas.`, 'success', true);
            } else {
                mostrarModal('ℹ️ Sin Avisos Nuevos', 'Por el momento no contamos con avisos nuevos', 'info');
            }
        } else {
            mostrarModal('❌ Error', data.message, 'danger');
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarModal('❌ Error', 'Error al consultar: ' + error.message, 'danger');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalHTML;
    }
}

document.addEventListener('DOMContentLoaded', function() {
    guardarAvisosOriginales();
    aplicarFiltros();
    
    // Evento para botón Reset Filtros
    const btnReset = document.getElementById('btnResetearFiltros');
    if (btnReset) {
        btnReset.addEventListener('click', function() {
            document.getElementById('filtro-numero').value = '';
            document.getElementById('filtro-nivel').value = '';
            document.getElementById('filtro-orden').value = 'desc';
            aplicarFiltros();
        });
    }
    
    // Evento para cambios en filtros (aplicar en tiempo real)
    ['filtro-numero', 'filtro-nivel', 'filtro-orden'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', aplicarFiltros);
            el.addEventListener('keyup', aplicarFiltros);
        }
    });
    
    // Evento para botón Descargar
    document.querySelectorAll('.btn-descargar').forEach(btn => {
        btn.addEventListener('click', async function() {
            const numero = this.getAttribute('data-numero');
            const btnIcon = this.querySelector('i');
            const originalClass = btnIcon.className;
            
            try {
                this.disabled = true;
                btnIcon.className = 'bi bi-hourglass-split spin';
                
                const response = await fetch(`/api/avisos/${numero}/descargar`, {
                    method: 'POST'
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    btnIcon.className = 'bi bi-check-circle';
                    this.classList.remove('btn-outline-primary');
                    this.classList.add('btn-success');
                    
                    // Actualizar tabla
                    location.reload();
                } else {
                    alert('Error: ' + data.error);
                    btnIcon.className = originalClass;
                    this.disabled = false;
                }
            } catch (error) {
                console.error('Error:', error);
                alert('Error al descargar: ' + error.message);
                btnIcon.className = originalClass;
                this.disabled = false;
            }
        });
    });
    
    // Evento para botón Consultar Nuevos
    const btnConsultar = document.getElementById('btnConsultarNuevos');
    if (btnConsultar) {
        btnConsultar.addEventListener('click', consultarNuevos);
    }
});
