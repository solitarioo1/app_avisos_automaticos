/* ============================================================================
   PRONOSTICOS.JS - Página de Pronósticos
   Lógica de filtrado y gestión de pronósticos
   ============================================================================ */

const AVISOS_ORIGINALES = [];
const AVISOS_FRESCOS = new Set();

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

    // Identificar los 4 más recientes por fecha
    const porFecha = [...AVISOS_ORIGINALES].sort((a, b) => new Date(b.fecha) - new Date(a.fecha));
    porFecha.slice(0, 4).forEach(a => AVISOS_FRESCOS.add(a.numero));
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

    // Marcar los 4 pronósticos más recientes con fondo suave
    document.querySelectorAll('#tabla-avisos tr').forEach(fila => {
        if (AVISOS_FRESCOS.has(fila.getAttribute('data-numero'))) {
            fila.classList.add('aviso-fresco');
        }
    });
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

    // Evento para botón "Generar capa y clasificar clientes" — antes era "Ver
    // Mapas" (link muerto a /mapas, página ya no se usa). Corre procesar_aviso.py:
    // descarga el SHP del día crítico, lo copia a SHP/aviso_N/ (lo que lee
    // Seguro Comercial para pintar la capa) y cruza clientes -> clientes_por_aviso.
    // Sin este paso, Seguro Comercial no tiene nada que cargar para ese aviso.
    document.querySelectorAll('.btn-procesar').forEach(btn => {
        btn.addEventListener('click', async function() {
            const numero = this.getAttribute('data-numero');
            const btnIcon = this.querySelector('i');
            const originalClass = btnIcon.className;

            try {
                this.disabled = true;
                btnIcon.className = 'bi bi-hourglass-split spin';

                const response = await fetch(`/api/avisos/${numero}/procesar`, {
                    method: 'POST'
                });
                const data = await response.json();

                if (response.ok && data.success) {
                    btnIcon.className = 'bi bi-check-circle';
                    alert(`Capa del aviso ${numero} generada y clientes clasificados. Ya puedes verlo en Seguro Comercial.`);
                    location.reload();
                } else {
                    alert('Error: ' + (data.error || 'no se pudo procesar el aviso'));
                    btnIcon.className = originalClass;
                    this.disabled = false;
                }
            } catch (error) {
                console.error('Error:', error);
                alert('Error al procesar: ' + error.message);
                btnIcon.className = originalClass;
                this.disabled = false;
            }
        });
    });

});
