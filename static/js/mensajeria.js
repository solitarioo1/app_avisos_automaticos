// ============================================================================
// MENSAJERÍA.JS - La Positiva AgroSeguros
// Lógica de envío WhatsApp via n8n + historial Google Sheets
// ============================================================================

// ── Configuración de Webhooks n8n (se cargan desde Flask/env) ──
// Los URLs se inyectan desde el backend en la ruta Flask
const WEBHOOKS = window.MENSAJERIA_CONFIG || {
    afiliaciones:    '',
    resultados:      '',
    indemnizaciones: '',
    alertas:         ''
};

// Estado global de gráficos
let chartTipo   = null;
let chartEstado = null;
let todosLosRegistros = [];

// ============================================================================
// ENVÍO DE MENSAJES
// ============================================================================

async function enviarMensaje(tipo, btnEl) {
    if (!WEBHOOKS[tipo]) {
        mostrarToast('error', 'Error de configuración', `Webhook de "${tipo}" no está configurado.`);
        return;
    }

    // Confirmar antes de enviar
    if (!confirm(`¿Enviar mensajes de tipo "${tipo.toUpperCase()}"?\nSolo se enviarán registros con estado "pendiente".`)) return;

    // Estado: cargando
    setBotonCargando(btnEl, true);
    marcarCardActiva(tipo, true);
    mostrarToast('info', '⏳ Enviando...', `Enviando mensajes de ${tipo}. Esto puede tomar un momento...`);

    try {
        const response = await fetch(`/mensajeria/enviar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tipo: tipo })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            // Mostrar KPIs
            actualizarKPIs(data);
            const msg = `${data.enviados} enviados · ${data.fallidos} fallidos · ${data.pendientes} pendientes`;
            mostrarToast('success', '✅ Envío completado', msg);
            
            // Scroll a KPIs
            document.getElementById('kpiStrip').scrollIntoView({ behavior: 'smooth', block: 'center' });
            
            // Recargar historial AUTOMÁTICAMENTE tras 2-3 segundos
            setTimeout(async () => {
                mostrarToast('info', '⏳ Actualizando historial...', 'Refrescando desde Google Sheet...');
                await cargarHistorial();
            }, 2500);
        } else {
            mostrarToast('error', '❌ Error en el envío', data.mensaje || 'Ocurrió un error inesperado.');
        }

    } catch (err) {
        console.error(err);
        mostrarToast('error', '❌ Error de conexión', err.message || 'No se pudo conectar con el servidor.');
    } finally {
        setBotonCargando(btnEl, false);
        marcarCardActiva(tipo, false);
        cerrarToast();
    }
}

// ── Helpers de UI ──
function setBotonCargando(btn, cargando) {
    const icon  = btn.querySelector('i');
    const label = btn.querySelector('.btn-label');
    if (cargando) {
        btn.disabled = true;
        btn.classList.add('loading');
        icon.className  = 'bi bi-arrow-repeat spin';
        label.textContent = 'Enviando...';
    } else {
        btn.disabled = false;
        btn.classList.remove('loading');
        icon.className  = 'bi bi-whatsapp';
        label.textContent = 'Enviar';
    }
}

function marcarCardActiva(tipo, activa) {
    const card = document.getElementById(`card-${tipo}`);
    if (card) {
        card.style.opacity = activa ? '0.7' : '1';
    }
}

function actualizarKPIs(data) {
    const strip = document.getElementById('kpiStrip');
    strip.style.display = 'flex';
    document.getElementById('kpiEnviados').textContent  = data.enviados   || 0;
    document.getElementById('kpiFallidos').textContent  = data.fallidos   || 0;
    document.getElementById('kpiPendientes').textContent = data.pendientes || 0;
    document.getElementById('kpiTotal').textContent     = data.total      || 0;
    document.getElementById('kpiHora').textContent      = data.hora       || '--:--';
}

// ============================================================================
// HISTORIAL - Carga desde Flask (que lee Google Sheets)
// ============================================================================

async function cargarHistorial() {
    const section = document.getElementById('historialSection');
    const loading = document.getElementById('tablaLoading');
    const tbody   = document.getElementById('historialBody');

    // Mostrar sección
    section.style.display = 'flex';
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });

    // Loading
    loading.style.display = 'block';
    tbody.innerHTML = '';

    try {
        // Agregar timestamp para evitar caché del navegador
        const url = `/mensajeria/historial?t=${Date.now()}`;
        const response = await fetch(url);
        const data = await response.json();

        if (response.ok && data.registros) {
            todosLosRegistros = data.registros;
            renderizarTabla(todosLosRegistros);
            renderizarGraficos(todosLosRegistros);

            // Actualizar KPIs con datos del historial
            const enviados  = data.registros.filter(r => r.estado === 'enviado').length;
            const fallidos  = data.registros.filter(r => r.estado === 'fallido').length;
            const pendientes = data.registros.filter(r => r.estado === 'pendiente').length;
            actualizarKPIs({
                enviados, fallidos, pendientes,
                total: data.registros.length,
                hora: new Date().toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' })
            });
        } else {
            tbody.innerHTML = `<tr><td colspan="7" class="tabla-empty">
                <i class="bi bi-exclamation-triangle"></i> ${data.mensaje || 'Error al cargar historial'}
            </td></tr>`;
        }

    } catch (err) {
        console.error(err);
        tbody.innerHTML = `<tr><td colspan="7" class="tabla-empty">
            <i class="bi bi-wifi-off"></i> Error de conexión con el servidor
        </td></tr>`;
    } finally {
        loading.style.display = 'none';
    }
}

function renderizarTabla(registros) {
    const tbody = document.getElementById('historialBody');

    if (!registros.length) {
        tbody.innerHTML = `<tr><td colspan="7" class="tabla-empty">
            <i class="bi bi-inbox"></i> No hay registros para mostrar
        </td></tr>`;
        return;
    }

    const iconoEstado = { enviado: '✅', fallido: '❌', pendiente: '⏳' };
    const iconoTipo   = {
        afiliaciones:    '<i class="bi bi-person-check-fill"></i>',
        resultados:      '<i class="bi bi-clipboard-data-fill"></i>',
        indemnizaciones: '<i class="bi bi-cash-coin"></i>',
        alertas:         '<i class="bi bi-cloud-lightning-rain-fill"></i>'
    };

    tbody.innerHTML = registros.map((r, i) => `
        <tr>
            <td>${i + 1}</td>
            <td>
                <span class="tipo-badge tipo-${r.tipo || 'resultados'}">
                    ${iconoTipo[r.tipo] || ''} ${capitalize(r.tipo || '-')}
                </span>
            </td>
            <td>${r.nombre || '-'}</td>
            <td>${r.numero || '-'}</td>
            <td>${r.entidad || '-'}</td>
            <td>
                <span class="estado-badge estado-${r.estado || 'pendiente'}">
                    ${iconoEstado[r.estado] || '⏳'} ${capitalize(r.estado || 'pendiente')}
                </span>
            </td>
            <td>${r.fecha_envio || '-'}</td>
        </tr>
    `).join('');
}

function filtrarHistorial() {
    const hoja   = document.getElementById('filtroHoja').value;
    const estado = document.getElementById('filtroEstado').value;

    let filtrados = todosLosRegistros;
    if (hoja)   filtrados = filtrados.filter(r => r.tipo === hoja);
    if (estado) filtrados = filtrados.filter(r => r.estado === estado);

    renderizarTabla(filtrados);
}

// ============================================================================
// GRÁFICOS con Chart.js
// ============================================================================

function renderizarGraficos(registros) {
    document.getElementById('chartRow').style.display = 'grid';

    // ── Gráfico 1: Mensajes por Tipo (barras) ──
    const tiposCounts = {
        afiliaciones:    registros.filter(r => r.tipo === 'afiliaciones').length,
        resultados:      registros.filter(r => r.tipo === 'resultados').length,
        indemnizaciones: registros.filter(r => r.tipo === 'indemnizaciones').length,
        alertas:         registros.filter(r => r.tipo === 'alertas').length
    };

    const ctxTipo = document.getElementById('chartTipo').getContext('2d');
    if (chartTipo) chartTipo.destroy();
    chartTipo = new Chart(ctxTipo, {
        type: 'bar',
        data: {
            labels: ['Afiliaciones', 'Resultados', 'Indemnizaciones', 'Alertas'],
            datasets: [{
                label: 'Registros',
                data: Object.values(tiposCounts),
                backgroundColor: ['#04ccc4', '#fc6c44', '#28a745', '#ffc107'],
                borderRadius: 6,
                borderSkipped: false
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, ticks: { stepSize: 1 } },
                x: { grid: { display: false } }
            }
        }
    });

    // ── Gráfico 2: Estado General (dona) ──
    const enviados   = registros.filter(r => r.estado === 'enviado').length;
    const fallidos   = registros.filter(r => r.estado === 'fallido').length;
    const pendientes = registros.filter(r => r.estado === 'pendiente').length;

    const ctxEstado = document.getElementById('chartEstado').getContext('2d');
    if (chartEstado) chartEstado.destroy();
    chartEstado = new Chart(ctxEstado, {
        type: 'doughnut',
        data: {
            labels: ['Enviados', 'Fallidos', 'Pendientes'],
            datasets: [{
                data: [enviados, fallidos, pendientes],
                backgroundColor: ['#28a745', '#dc3545', '#ffc107'],
                borderWidth: 2,
                borderColor: '#fff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { font: { size: 11 }, padding: 10 }
                }
            }
        }
    });
}

// ============================================================================
// TOAST
// ============================================================================

let toastTimer = null;

function mostrarToast(tipo, titulo, mensaje) {
    const toast = document.getElementById('msgToast');
    const iconEl = document.getElementById('toastIcon');
    const titleEl = document.getElementById('toastTitle');
    const msgEl   = document.getElementById('toastMsg');

    const iconos = {
        success: '✅',
        error:   '❌',
        warning: '⚠️',
        info:    'ℹ️'
    };

    toast.className = `msg-toast toast-${tipo}`;
    iconEl.textContent  = iconos[tipo] || 'ℹ️';
    titleEl.textContent = titulo;
    msgEl.textContent   = mensaje;
    toast.style.display = 'flex';

    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(cerrarToast, 5000);
}

function cerrarToast() {
    document.getElementById('msgToast').style.display = 'none';
}

// ============================================================================
// UTILS
// ============================================================================

function capitalize(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1);
}