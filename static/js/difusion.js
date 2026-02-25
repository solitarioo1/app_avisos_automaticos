/* ============================================================
   difusion.js — Módulo de Difusión de Avisos SENAMHI
   ============================================================ */

/* ── Estado global ──────────────────────────────────────────── */
const STATE = {
  avisoActual:     null,
  avisoColor:      null,
  canalActual:     'whatsapp',
  nivelActual:     'todos',
  entidadesActuales: [],
  mensajesListos:  false,
  // Opciones
  incluirMapa:     true,
  particion:       false,
  msgsPorBloque:   50,
  intervaloBloques:120,
  programar:       false,
  fechaProgramada: null,
};

/* ── Limpiar cualquier sessionStorage previo al cargar ────────── */
try { sessionStorage.removeItem('difusion_state'); } catch(e) {}

/* ── DOM ready ──────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  cargarAvisos();
  cargarEntidades();
  cargarHistorial();

  // Listeners para canales
  document.querySelectorAll('.canal-option').forEach(el => {
    el.addEventListener('click', () => seleccionarCanal(el.dataset.canal));
  });

  // Listeners para niveles
  document.querySelectorAll('.nivel-option').forEach(el => {
    el.addEventListener('click', () => seleccionarNivel(el.dataset.nivel));
  });

  // Aviso selector
  const selectAviso = document.getElementById('selectAviso');
  if (selectAviso) {
    selectAviso.addEventListener('change', () => {
      const opt = selectAviso.options[selectAviso.selectedIndex];
      STATE.avisoActual    = selectAviso.value ? parseInt(selectAviso.value, 10) : null;
      STATE.avisoColor     = opt ? (opt.dataset.color || null) : null;
      STATE.mensajesListos = false;
      actualizarBotones();
      actualizarBarraAviso(opt);
      actualizarResumenConfig();
      if (STATE.avisoActual) actualizarEstadisticas(STATE.avisoActual);
    });
  }

  // Entidad (multi-select acumulativo)
  const selectEntidad = document.getElementById('selectEntidad');
  if (selectEntidad) {
    selectEntidad.addEventListener('change', () => {
      const val = selectEntidad.value.trim();
      if (val && !STATE.entidadesActuales.includes(val)) {
        STATE.entidadesActuales.push(val);
        actualizarEntidadTags();
        actualizarResumenConfig();
      }
      selectEntidad.value = ''; // reset
    });
  }
});

/* ── Cargar lista de avisos ─────────────────────────────────── */
function cargarAvisos() {
  fetch('/api/avisos?_t=' + Date.now(), { cache: 'no-store' })
    .then(r => r.json())
    .then(data => {
      const sel = document.getElementById('selectAviso');
      if (!sel) return;

      const lista = data.avisos || data.data || data || [];
      // Filtrar solo los que tienen mapa creado
      const conMapa = lista.filter(av => av.mapa_creado === '\u2705');

      sel.innerHTML = '<option value="">— Selecciona un aviso —</option>';
      conMapa.forEach(av => {
        const opt  = document.createElement('option');
        opt.value  = av.numero || av.numero_aviso || av.id;
        opt.dataset.color = (av.color || '').toLowerCase();
        opt.dataset.nivel = av.nivel || '';
        opt.dataset.titulo = av.titulo || '';
        const titulo = av.titulo || `Aviso ${opt.value}`;
        opt.textContent = `Aviso ${opt.value} — ${titulo}`;
        sel.appendChild(opt);
      });

      if (!conMapa.length) {
        sel.innerHTML = '<option value="">No hay avisos con mapa generado</option>';
      }
    })
    .catch(err => console.error('Error cargar avisos:', err));
}

/* ── Cargar entidades ───────────────────────────────────────── */
function cargarEntidades() {
  fetch('/api/entidades?_t=' + Date.now(), { cache: 'no-store' })
    .then(r => r.json())
    .then(data => {
      const sel = document.getElementById('selectEntidad');
      if (!sel) return;
      sel.innerHTML = '<option value="">— Añadir entidad… —</option>';
      const lista = data.data || data.entidades || data || [];
      lista.forEach(e => {
        const opt = document.createElement('option');
        opt.value = e.nombre || e.id;
        opt.textContent = e.nombre || e.id;
        sel.appendChild(opt);
      });
    })
    .catch(err => console.error('Error cargar entidades:', err));
}

/* ── Chips de entidades seleccionadas ─────────────────────── */
function actualizarEntidadTags() {
  const row = document.getElementById('entidadTags');
  if (!row) return;
  if (!STATE.entidadesActuales.length) {
    row.innerHTML = '<span class="entidad-chip entidad-chip-todas">Todas las entidades</span>';
    return;
  }
  row.innerHTML = STATE.entidadesActuales
    .map(e => `<span class="entidad-chip">${escapeHtml(e)}<button class="entidad-chip-remove" onclick="quitarEntidad('${escapeHtml(e)}')">&#215;</button></span>`)
    .join('');
}

function quitarEntidad(nombre) {
  STATE.entidadesActuales = STATE.entidadesActuales.filter(e => e !== nombre);
  actualizarEntidadTags();
  actualizarResumenConfig();
}

/* ── Barra de info del aviso seleccionado ────────────────── */
function actualizarBarraAviso(opt) {
  const bar = document.getElementById('avisoInfo');
  if (!bar) return;
  if (!opt || !opt.value) { bar.classList.add('d-none'); return; }

  const color  = (opt.dataset.color || '').toLowerCase();
  const nivel  = opt.dataset.nivel  || '';
  const titulo = opt.dataset.titulo || opt.textContent;
  const colores = { rojo: '#e53935', naranja: '#fb8c00', amarillo: '#c6a000', verde: '#43a047' };
  const hex = colores[color] || '#999';

  bar.className = 'aviso-info-bar mt-2';
  bar.innerHTML = `
    <span class="aviso-dot-grande" style="background:${hex}"></span>
    <strong>Aviso ${opt.value}</strong>
    <span class="mx-2 text-muted">—</span>
    <span>${escapeHtml(titulo.replace(/^Aviso \d+ — /, '').replace(/ \[.*\]$/, ''))}</span>`;
}

/* ── Toggle bloques ───────────────────────────────────────── */
function toggleBloques(activo) {
  STATE.particion = activo;
  const box = document.getElementById('bloquesConfig');
  if (box) box.classList.toggle('d-none', !activo);
  actualizarResumenConfig();
}

/* ── Toggle programar ───────────────────────────────────── */
function toggleProgramar(activo) {
  STATE.programar = activo;
  const box = document.getElementById('programarFechaBox');
  if (box) box.classList.toggle('d-none', !activo);
  if (!activo) STATE.fechaProgramada = null;
  actualizarResumenConfig();
}

/* ── Resumen de configuración (bajo los botones) ──────────── */
function actualizarResumenConfig() {
  const el = document.getElementById('resumenConfig');
  if (!el) return;
  if (!STATE.avisoActual) { el.classList.add('d-none'); return; }

  const partes = [
    `Aviso #${STATE.avisoActual}`,
    `Canal: ${STATE.canalActual}`,
    `Nivel: ${STATE.nivelActual}`,
    STATE.entidadesActuales.length ? `🏫 ${STATE.entidadesActuales.join(', ')}` : null,
    STATE.incluirMapa  ? '🗺️ Con mapa' : '🗺️ Sin mapa',
    STATE.particion    ? `✂️ Bloques: ${STATE.msgsPorBloque} msgs / ${STATE.intervaloBloques}s` : null,
    STATE.programar && STATE.fechaProgramada
      ? `⏰ ${new Date(STATE.fechaProgramada).toLocaleString('es-PE')}`
      : null,
  ].filter(Boolean);

  el.className = 'resumen-config mt-3';
  el.innerHTML = partes.map(p => `<span class="resumen-tag">${p}</span>`).join('');
}

/* ── Selección de canal ─────────────────────────────────────── */
function seleccionarCanal(canal) {
  STATE.canalActual = canal;
  document.querySelectorAll('.canal-option').forEach(el => {
    el.classList.remove('selected-wa', 'selected-email', 'selected-sms');
    if (el.dataset.canal === canal) {
      const cls = canal === 'whatsapp' ? 'wa' : canal === 'sms' ? 'sms' : 'email';
      el.classList.add(`selected-${cls}`);
    }
  });
  // Panel descarga CSV (SMS)
  const smsCsvPanel = document.getElementById('smsCsvPanel');
  if (smsCsvPanel) smsCsvPanel.classList.toggle('d-none', canal !== 'sms');

  STATE.mensajesListos = false;
  actualizarBotones();
  actualizarResumenConfig();
}

/* ── Selección de nivel ─────────────────────────────────────── */
function seleccionarNivel(nivel) {
  STATE.nivelActual = nivel;
  document.querySelectorAll('.nivel-option').forEach(el => {
    el.className = el.className.replace(/selected-\S+/g, '').trim();
    if (el.dataset.nivel === nivel) el.classList.add(`selected-${nivel}`);
  });
  STATE.mensajesListos = false;
  actualizarBotones();
  actualizarResumenConfig();
}

/* ── Actualizar estadísticas del sidebar ────────────────────── */
function actualizarEstadisticas(numeroAviso) {
  if (!numeroAviso) return;
  fetch(`/api/difusion/clientes/${numeroAviso}?_t=${Date.now()}`, { cache: 'no-store' })
    .then(r => r.json())
    .then(data => {
      if (!data.success) return;
      renderizarSidebar(data);
    })
    .catch(err => console.error('Error estadísticas:', err));
}

function renderizarSidebar(data) {
  const cont = document.getElementById('statsPorNivel');
  if (!cont) return;

  const colores = { Rojo: '#e53935', Naranja: '#fb8c00', Amarillo: '#c6a000', Verde: '#43a047' };

  let html = '';
  (data.por_nivel || []).forEach(n => {
    const color = colores[n.nivel] || '#999';
    html += `
      <div class="stat-row ${n.nivel}">
        <div class="d-flex align-items-center">
          <span class="stat-nivel-dot ${n.nivel}"></span>
          <strong>${n.nivel}</strong>
        </div>
        <div class="d-flex align-items-center gap-2">
          <span class="stat-badge">${n.total} clientes</span>
          ${n.con_email   ? `<span class="canal-count email">✉ ${n.con_email}</span>` : ''}
          ${n.con_telefono ? `<span class="canal-count wa">📱 ${n.con_telefono}</span>` : ''}
        </div>
      </div>`;
  });

  if (!html) html = '<p class="text-muted small">Sin datos para este aviso</p>';
  cont.innerHTML = html;

  // Total
  const spanTotal = document.getElementById('totalClientes');
  if (spanTotal) spanTotal.textContent = data.total_clientes || 0;

  // Mensajes generados
  const spanGen = document.getElementById('mensajesGenerados');
  if (spanGen) {
    const gen = data.mensajes_generados || {};
    const totalGen = Object.values(gen).reduce((a, b) => a + b, 0);
    spanGen.textContent = totalGen;
    if (totalGen > 0) {
      STATE.mensajesListos = true;
      actualizarBotones();
    }
  }
}

/* ── Actualizar estado visual de botones ────────────────────── */
function actualizarBotones() {
  const btnGenerar  = document.getElementById('btnGenerar');
  const btnPreview  = document.getElementById('btnPreview');
  const btnEnviar   = document.getElementById('btnEnviar');

  if (btnGenerar) btnGenerar.disabled  = !STATE.avisoActual;
  if (btnPreview) btnPreview.disabled  = !STATE.mensajesListos;
  if (btnEnviar)  btnEnviar.disabled   = !STATE.mensajesListos;
}

/* ── Generar mensajes ───────────────────────────────────────── */
function generarMensajes() {
  if (!STATE.avisoActual) {
    mostrarAlerta('Selecciona un aviso primero', 'warning');
    return;
  }

  const btnGenerar = document.getElementById('btnGenerar');
  const spinner    = document.getElementById('spinnerGenerar');

  if (btnGenerar) { btnGenerar.disabled = true; btnGenerar.textContent = 'Generando…'; }
  if (spinner)    spinner.classList.add('visible');

  const payload = {
    numero_aviso:      STATE.avisoActual,
    canal:             STATE.canalActual,
    nivel:             STATE.nivelActual,                                          // "todos" | "Rojo" | "Naranja" | "Amarillo"
    entidades:         STATE.entidadesActuales.length ? STATE.entidadesActuales : ["todas"],  // array siempre
    incluir_mapa:      STATE.incluirMapa,
    partir_mensajes:   STATE.particion,
    msgs_por_bloque:   STATE.particion ? STATE.msgsPorBloque    : 0,
    intervalo_bloques: STATE.particion ? STATE.intervaloBloques : 0,
    programar_envio:   (STATE.programar && STATE.fechaProgramada) ? STATE.fechaProgramada : "inmediato",
  };

  fetch('/api/difusion/generar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
    .then(r => r.json())
    .then(data => {
      if (spinner) spinner.classList.remove('visible');
      if (btnGenerar) { btnGenerar.disabled = false; btnGenerar.textContent = '⚡ Generar mensajes'; }

      if (data.success) {
        mostrarAlerta('✅ Solicitud enviada a n8n. Los mensajes se generarán en breve.', 'success');
        // Refrescar stats después de 3s para dar tiempo a n8n
        setTimeout(() => {
          actualizarEstadisticas(STATE.avisoActual);
          cargarHistorial();
        }, 3000);
      } else {
        mostrarAlerta(`Error: ${data.error}`, 'danger');
      }
    })
    .catch(err => {
      if (spinner) spinner.classList.remove('visible');
      if (btnGenerar) { btnGenerar.disabled = false; btnGenerar.textContent = '⚡ Generar mensajes'; }
      mostrarAlerta(`Error de red: ${err.message}`, 'danger');
    });
}

/* ── Ver preview ────────────────────────────────────────────── */
function verPreview() {
  if (!STATE.avisoActual) return;

  const params = new URLSearchParams({
    canal: STATE.canalActual === 'todos' ? '' : STATE.canalActual,
    nivel: STATE.nivelActual === 'todos' ? '' : STATE.nivelActual,
  });

  fetch(`/api/difusion/preview/${STATE.avisoActual}?${params}`)
    .then(r => r.json())
    .then(data => {
      if (!data.success) {
        mostrarAlerta(`Error cargando preview: ${data.error}`, 'danger');
        return;
      }
      renderizarPreviewModal(data);
      const modal = new bootstrap.Modal(document.getElementById('previewModal'));
      modal.show();
    })
    .catch(err => mostrarAlerta(`Error: ${err.message}`, 'danger'));
}

/* ── Renderizar tarjetas de preview ─────────────────────────── */
function renderizarPreviewModal(data) {
  // Resumen numérico
  const resumenEl = document.getElementById('previewResumen');
  if (resumenEl) {
    const res = data.resumen || [];
    let html = '';
    res.forEach(r => {
      html += `
        <div class="preview-resumen-item">
          <span>${canalIcon(r.canal_enviado)} <strong>${r.canal_enviado}</strong></span>
          <span class="estado-badge ${r.estado}">${r.estado}: ${r.total}</span>
        </div>`;
    });
    resumenEl.innerHTML = html || '<span class="text-muted">Sin datos</span>';
  }

  // Cards de muestra
  const cardsEl = document.getElementById('previewCards');
  if (!cardsEl) return;

  if (!data.muestras || data.muestras.length === 0) {
    cardsEl.innerHTML = `
      <div class="text-center text-muted py-3">
        <p>No hay mensajes generados aún.</p>
        <p class="small">Usa "Generar mensajes" primero.</p>
      </div>`;
    return;
  }

  let html = '';
  data.muestras.forEach(m => {
    const nombre  = `${m.nombre || ''} ${m.apellido || ''}`.trim() || 'Cliente';
    const inicial = nombre.charAt(0).toUpperCase();
    const canal   = m.canal_enviado || 'whatsapp';
    const nivel   = m.nivel_filtro  || '';
    const texto   = m.mensaje_texto ? escapeHtml(m.mensaje_texto) : '<em>Sin texto</em>';
    const contacto = canal === 'email'
      ? `<span class="wa-meta">✉ ${m.correo || 'sin correo'}</span>`
      : `<span class="wa-meta">📱 ${m.telefono || 'sin teléfono'}</span>`;

    html += `
      <div class="wa-card canal-${canal}">
        <div class="wa-card-header">
          <div class="wa-avatar">${inicial}</div>
          <div class="wa-card-info">
            <div class="wa-name">
              ${escapeHtml(nombre)}
              ${nivel ? `<span class="nivel-tag ${nivel}">${nivel}</span>` : ''}
            </div>
            ${contacto}
          </div>
          <div class="ms-auto">
            <span class="canal-count ${canal === 'email' ? 'email' : 'wa'}">${canalIcon(canal)} ${canal}</span>
          </div>
        </div>
        <div class="wa-bubble">${texto}</div>
      </div>`;
  });

  cardsEl.innerHTML = html;
}

/* ── Confirmar y enviar ─────────────────────────────────────── */
function confirmarEnvio() {
  if (!STATE.avisoActual || !STATE.mensajesListos) return;

  const confirmado = confirm(
    `¿Confirmas el envío de mensajes para el Aviso #${STATE.avisoActual}?\n` +
    `Canal: ${STATE.canalActual} | Nivel: ${STATE.nivelActual}`
  );
  if (!confirmado) return;

  fetch(`/api/difusion/enviar/${STATE.avisoActual}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ canal: STATE.canalActual }),
  })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        mostrarAlerta('🚀 Envío iniciado correctamente en n8n.', 'success');
        setTimeout(() => cargarHistorial(), 2000);
      } else {
        mostrarAlerta(`Error al enviar: ${data.error}`, 'danger');
      }
    })
    .catch(err => mostrarAlerta(`Error: ${err.message}`, 'danger'));
}

/* ── Reanudar envío (errores) ───────────────────────────────── */
function reanudarEnvio(numeroAviso) {
  if (!confirm(`¿Reanudar envíos con error para el Aviso #${numeroAviso}?`)) return;

  fetch(`/api/difusion/reanudar/${numeroAviso}`, { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        mostrarAlerta(`✅ ${data.mensaje}`, 'success');
        cargarHistorial();
      } else {
        mostrarAlerta(`Error: ${data.error}`, 'danger');
      }
    })
    .catch(err => mostrarAlerta(`Error: ${err.message}`, 'danger'));
}

/* ── Cargar historial ───────────────────────────────────────── */
function cargarHistorial() {
  const btn = document.querySelector('[onclick="cargarHistorial()"]');
  if (btn) { btn.disabled = true; btn.textContent = '🔄 Actualizando…'; }

  fetch('/api/difusion/historial?limit=20&_t=' + Date.now(), { cache: 'no-store' })
    .then(r => r.json())
    .then(data => {
      if (!data.success) {
        mostrarAlerta('Error al cargar historial: ' + (data.error || 'desconocido'), 'danger');
        return;
      }
      renderizarTablaHistorial(data.por_aviso || []);
      renderizarPanelCanal(data.por_canal || []);
      // Refrescar estadísticas del aviso actualmente seleccionado
      if (STATE.avisoActual) actualizarEstadisticas(STATE.avisoActual);
    })
    .catch(err => {
      mostrarAlerta('Error de red al cargar historial: ' + err.message, 'danger');
    })
    .finally(() => {
      if (btn) { btn.disabled = false; btn.textContent = '🔄 Actualizar historial'; }
    });
}

function renderizarTablaHistorial(filas) {
  const tbody = document.getElementById('historialTbody');
  if (!tbody) return;

  if (!filas.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-3">Sin registros de difusión</td></tr>';
    return;
  }

  tbody.innerHTML = filas.map(f => {
    const errorBtn = (f.errores || 0) > 0
      ? `<button class="btn-reanudar ms-1" onclick="reanudarEnvio(${f.numero_aviso})">↺ Reanudar</button>`
      : '';
    const fecha = f.ultima_fecha
      ? new Date(f.ultima_fecha).toLocaleString('es-PE', { dateStyle: 'short', timeStyle: 'short' })
      : '—';

    return `
      <tr>
        <td>${fecha}</td>
        <td><strong>#${f.numero_aviso}</strong></td>
        <td>${f.nivel_filtro ? `<span class="nivel-tag ${f.nivel_filtro}">${f.nivel_filtro}</span>` : '—'}</td>
        <td>${canalIcon(f.canal_enviado)} ${f.canal_enviado}</td>
        <td>${f.total_enviado || 0} / ${(f.total_enviado || 0) + (f.total_pendiente || 0) + (f.errores || 0)}</td>
        <td>
          <span class="estado-badge ${estadoGeneral(f)}">
            ${estadoGeneral(f)}
          </span>
          ${errorBtn}
        </td>
        <td>${f.tasa_exito_pct ? f.tasa_exito_pct + '%' : '—'}</td>
      </tr>`;
  }).join('');
}

function renderizarPanelCanal(filas) {
  const cont = document.getElementById('historialPorCanal');
  if (!cont) return;

  if (!filas.length) {
    cont.innerHTML = '<p class="text-muted small">Sin datos</p>';
    return;
  }

  cont.innerHTML = filas.map(f => `
    <div class="historial-canal-row">
      <div>
        <div class="canal-name">${canalIcon(f.canal_enviado)} ${f.canal_enviado}</div>
        <div class="tasa">${f.tasa_exito_pct ? f.tasa_exito_pct + '% éxito' : 'Sin envíos'}</div>
      </div>
      <div class="text-end">
        <div><span class="estado-badge enviado">${f.total_enviado || 0} enviados</span></div>
        <div class="mt-1"><span class="estado-badge error">${f.total_error || 0} errores</span></div>
      </div>
    </div>`).join('');
}

/* ── Exportar CSV genérico ────────────────────────────────── */
function exportarCSV() {
  if (!STATE.avisoActual) {
    mostrarAlerta('Selecciona un aviso primero', 'warning');
    return;
  }
  const params = new URLSearchParams();
  if (STATE.nivelActual   && STATE.nivelActual   !== 'todos') params.set('nivel', STATE.nivelActual);
  if (STATE.entidadesActuales.length) params.set('entidad', STATE.entidadesActuales.join(','));
  window.location.href = `/api/difusion/clientes/export/${STATE.avisoActual}?${params}`;
}

/* ── Exportar CSV + marcar enviado SMS ────────────────────── */
function exportarCSVSms() {
  if (!STATE.avisoActual) {
    mostrarAlerta('Selecciona un aviso primero', 'warning');
    return;
  }
  const params = new URLSearchParams();
  if (STATE.nivelActual && STATE.nivelActual !== 'todos') params.set('nivel', STATE.nivelActual);
  if (STATE.entidadesActuales.length) params.set('entidad', STATE.entidadesActuales.join(','));

  // 1. Descarga el CSV
  window.open(`/api/difusion/clientes/export/${STATE.avisoActual}?${params}`, '_blank');

  // 2. Marca como enviado en BD (pequeño delay para que la descarga inicie)
  setTimeout(() => {
    fetch(`/api/difusion/marcar_enviado_sms/${STATE.avisoActual}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nivel: STATE.nivelActual, entidades: STATE.entidadesActuales })
    })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        mostrarAlerta(`✅ ${data.marcados} contactos marcados como enviados (SMS)`, 'success');
        cargarHistorial();
      }
    })
    .catch(err => console.error('Error marcar SMS:', err));
  }, 800);
}

/* ── Helpers ────────────────────────────────────────────────── */
function canalIcon(canal) {
  if (!canal) return '';
  const icons = { whatsapp: '📱', email: '✉️', sms: '💬' };
  return icons[canal.toLowerCase()] || '📨';
}

function estadoGeneral(f) {
  if ((f.errores || 0) > 0 && (f.total_pendiente || 0) === 0) return 'error';
  if ((f.total_pendiente || 0) > 0)                            return 'pendiente';
  if ((f.total_enviado   || 0) > 0)                            return 'enviado';
  return 'enviando';
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/\n/g, '<br>');
}

function mostrarAlerta(mensaje, tipo = 'info') {
  const zona = document.getElementById('alertaZona');
  if (!zona) { console[tipo === 'danger' ? 'error' : 'log'](mensaje); return; }

  const div = document.createElement('div');
  div.className = `alert alert-${tipo} alert-dismissible fade show`;
  div.setAttribute('role', 'alert');
  div.innerHTML = `${mensaje}
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
  zona.prepend(div);

  // Auto-cerrar en 5s
  setTimeout(() => div.remove(), 5000);
}
