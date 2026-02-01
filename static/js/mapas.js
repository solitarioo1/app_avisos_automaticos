/* ============================================================================
   MAPAS.JS - Página de Mapas
   Lógica de carga, generación y filtrado de mapas
   ============================================================================ */

let avisos_cache = [];
let logEventSource = null;
let currentNumero = null;
let processingAborted = false;

async function cargarAvisos() {
    try {
        const url = new URL(window.location);
        const avisoParam = url.searchParams.get('aviso');
        
        let avisos = [];
        
        if (avisoParam) {
            const res = await fetch(`/api/avisos/${parseInt(avisoParam)}/info`);
            const data = await res.json();
            
            if (data.success) {
                avisos = [{
                    numero: data.numero,
                    titulo: data.titulo,
                    nivel: data.nivel,
                    color: data.color
                }];
                document.getElementById('filtro-orden').value = 'reciente';
                document.getElementById('filtro-nivel').value = 'todos';
            } else {
                document.getElementById('avisos-grid').innerHTML = `
                    <div style="grid-column: 1/-1; text-align: center; padding: 2rem;">
                        <p class="text-danger">Aviso no encontrado</p>
                        <a href="/avisos" class="btn btn-primary btn-sm mt-2">Volver a Avisos</a>
                    </div>
                `;
                return;
            }
        } else {
            const res = await fetch('/api/avisos');
            const result = await res.json();
            avisos = result.avisos || [];
        }
        
        const avisoPromises = avisos.map(async (aviso) => {
            try {
                const infoRes = await fetch(`/api/avisos/${aviso.numero}/info`);
                if (!infoRes.ok) return '';
                const info = await infoRes.json();
                if (!info.success) return '';
                
                let departamentos = [];
                if (info.mapas_creados) {
                    const deptosRes = await fetch(`/api/avisos/${aviso.numero}/departamentos`).catch(e => null);
                    if (deptosRes && deptosRes.ok) {
                        const deptosData = await deptosRes.json();
                        departamentos = deptosData.departamentos || [];
                    }
                }
                
                const mapasRes = await fetch(`/api/mapas/aviso/${aviso.numero}`).catch(e => null);
                const mapas = mapasRes ? await mapasRes.json().catch(() => ({ mapas: [] })) : { mapas: [] };
                
                const mapaStatus = info.mapas_creados ? 'ready' : 'pending';
                const mapaStatusText = info.mapas_creados ? '✅ Mapas Creados' : '⏳ No Creados';
                const puedeGenerarMapas = ['rojo', 'naranja'].includes(info.color.toLowerCase());
                const mensajeNivelBajo = !puedeGenerarMapas ? '<em style="color: #999; font-size: 12px;">Este nivel no requiere mapas</em>' : '';
                
                return `
                    <div class="aviso-card color-${info.color}" data-numero="${aviso.numero}">
                        <div class="aviso-header color-${info.color}">
                            <h5 class="aviso-numero">#${aviso.numero}</h5>
                            <p class="aviso-titulo">${aviso.titulo}</p>
                        </div>
                        <div class="aviso-body">
                            <div class="info-row">
                                <div class="info-label">NIVEL</div>
                                <span class="nivel-badge nivel-${info.color}">${info.color.toUpperCase()}</span>
                                ${mensajeNivelBajo}
                            </div>
                            <div class="info-row">
                                <div class="info-label">DEPARTAMENTOS AFECTADOS</div>
                                <div class="departamentos-list">
                                    ${puedeGenerarMapas ? (info.mapas_creados ? (departamentos.length > 0 ? departamentos.map(d => `<span class="depto-tag">${d}</span>`).join('') : '<em style="color: #999;">No disponibles</em>') : '<em style="color: #999;">Se mostrarán después de generar mapas</em>') : '<em style="color: #999;">N/A - Nivel no aplica</em>'}
                                </div>
                            </div>
                            <div class="info-row">
                                <div class="info-label">ESTADO DE MAPAS</div>
                                <span class="status-badge status-${mapaStatus}">${puedeGenerarMapas ? mapaStatusText : '⊘ No Aplica'}</span>
                            </div>
                            ${info.mapas_creados && mapas.mapas && mapas.mapas.length > 0 ? `
                                <div class="info-row">
                                    <div class="info-label">VISTA PREVIA</div>
                                    <div class="mapas-preview">
                                        ${mapas.mapas.slice(0, 4).map(m => `
                                            <div class="mapa-thumb" title="${m.nombre}" onclick="abrirMapaModal(${aviso.numero}, '${m.nombre}', '${m.url}')">
                                                <img src="${m.url}" alt="${m.nombre}">
                                            </div>
                                        `).join('')}
                                        ${mapas.mapas.length > 4 ? `<div class="depto-tag">+${mapas.mapas.length - 4}</div>` : ''}
                                    </div>
                                </div>
                            ` : ''}
                        </div>
                        <div class="aviso-footer">
                            <button class="btn btn-sm btn-outline-primary" onclick="generarMapas(${aviso.numero})" ${!puedeGenerarMapas ? 'disabled title="Los mapas solo se generan para avisos ROJO y NARANJA"' : ''}>
                                <i class="bi bi-cog"></i> Generar${info.mapas_creados ? '/Recrear' : ''}
                            </button>
                            <button class="btn btn-sm btn-outline-info" onclick="abrirTodosMapas(${aviso.numero})" ${!info.mapas_creados ? 'disabled' : ''}>
                                <i class="bi bi-eye"></i> Ver Todos
                            </button>
                        </div>
                    </div>
                `;
            } catch (error) {
                console.error(`Error cargando aviso ${aviso.numero}:`, error);
                return '';
            }
        });
        
        const results = await Promise.all(avisoPromises);
        let html = results.filter(r => r).join('');
        
        if (!html) {
            html = `
                <div style="grid-column: 1/-1; text-align: center; padding: 3rem 1rem;">
                    <i class="bi bi-inbox display-1 text-muted"></i>
                    <h4 class="text-muted mt-3">Sin avisos disponibles</h4>
                    <a href="/avisos" class="btn btn-primary btn-sm mt-2">Ir a Avisos</a>
                </div>
            `;
        }
        
        document.getElementById('avisos-grid').innerHTML = html;
        avisos_cache = Array.from(document.getElementById('avisos-grid').querySelectorAll('.aviso-card'));
        aplicarFiltros();
    } catch (error) {
        console.error('Error:', error);
        document.getElementById('avisos-grid').innerHTML = `
            <div style="grid-column: 1/-1; text-align: center; padding: 2rem;">
                <p class="text-danger">Error: ${error.message}</p>
            </div>
        `;
    }
}

async function generarMapas(numero) {
    const btn = event.target.closest('button');
    const originalText = btn.innerHTML;
    currentNumero = numero;
    processingAborted = false;
    
    const logPanel = document.getElementById('logPanel');
    const logContent = document.getElementById('logContent');
    const logStats = document.getElementById('logStats');
    const logProgressBar = document.getElementById('logProgressBar');
    const logTime = document.getElementById('logTime');
    
    logPanel.classList.add('visible');
    logContent.innerHTML = '';
    logStats.innerHTML = 'Conectando...';
    logProgressBar.style.width = '0%';
    logTime.textContent = '--:--';
    
    document.querySelectorAll('.filter-card button, .card button').forEach(b => {
        b.disabled = true;
    });
    document.body.classList.add('blurred');
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-hourglass-split spin"></i> Generando...';
    
    try {
        if (logEventSource) {
            logEventSource.close();
        }
        
        logEventSource = new EventSource(`/api/avisos/${numero}/procesar?stream=true`);
        let startTime = Date.now();
        
        logEventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            if (data.type === 'log') {
                agregarLogLinea(data.message, data.severity || 'info');
            } else if (data.type === 'progress') {
                logStats.innerHTML = `${data.current} / ${data.total} departamentos`;
                const percentage = Math.round((data.current / data.total) * 100);
                logProgressBar.style.width = percentage + '%';
                
                const elapsed = (Date.now() - startTime) / 1000;
                const perDept = elapsed / data.current;
                const remaining = (data.total - data.current) * perDept;
                actualizarTiempo(remaining);
            } else if (data.type === 'error') {
                agregarLogLinea('❌ Error: ' + data.message, 'error');
            } else if (data.type === 'complete') {
                agregarLogLinea('✅ Procesamiento completado', 'success');
                if (logEventSource) {
                    logEventSource.close();
                    logEventSource = null;
                }
                finalizarGeneracion(btn, originalText, numero);
            }
        };
        
        logEventSource.onerror = (error) => {
            if (!processingAborted) {
                agregarLogLinea('⚠️ Reconectando al servidor...', 'warning');
            }
        };
        
    } catch (error) {
        agregarLogLinea('❌ Error: ' + error.message, 'error');
        finalizarGeneracion(btn, originalText, numero);
    }
}

function agregarLogLinea(mensaje, severity = 'info') {
    const logContent = document.getElementById('logContent');
    const linea = document.createElement('div');
    linea.className = 'log-line ' + severity;
    
    const timestamp = new Date().toLocaleTimeString();
    linea.textContent = `[${timestamp}] ${mensaje}`;
    
    logContent.appendChild(linea);
    logContent.scrollTop = logContent.scrollHeight;
}

function actualizarTiempo(segundos) {
    const logTime = document.getElementById('logTime');
    logTime.textContent = formatearTiempo(segundos);
}

function formatearTiempo(segundos) {
    const mins = Math.floor(segundos / 60);
    const secs = Math.floor(segundos % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

function finalizarGeneracion(btn, originalText, numero) {
    document.querySelectorAll('.filter-card button, .card button').forEach(b => {
        b.disabled = false;
    });
    document.body.classList.remove('blurred');
    
    btn.disabled = false;
    btn.innerHTML = originalText;
    
    setTimeout(() => {
        cargarAvisos();
        if (!processingAborted) {
            setTimeout(() => {
                document.getElementById('logPanel').classList.remove('visible');
            }, 5000);
        }
    }, 2000);
}

function cancelarGeneracion() {
    processingAborted = true;
    
    if (logEventSource) {
        logEventSource.close();
        logEventSource = null;
    }
    
    if (currentNumero) {
        fetch(`/api/avisos/${currentNumero}/cancel`, { method: 'POST' }).catch(e => console.log('Cancel request failed'));
    }
    
    agregarLogLinea('🛑 Generación cancelada por el usuario', 'warning');
    
    setTimeout(() => {
        document.getElementById('logPanel').classList.remove('visible');
    }, 3000);
}

async function abrirTodosMapas(numero) {
    const res = await fetch(`/api/mapas/aviso/${numero}`);
    const data = await res.json();
    
    if (!data.success) {
        alert('Error al cargar mapas');
        return;
    }
    
    let html = '';
    for (const mapa of data.mapas) {
        html += `
            <div>
                <h6>${mapa.nombre}</h6>
                <img src="${mapa.url}" class="img-fluid" style="border-radius: 4px;">
                <a href="${mapa.url}" download class="btn btn-sm btn-outline-primary mt-2">
                    <i class="bi bi-download"></i> Descargar
                </a>
            </div>
        `;
    }
    
    document.getElementById('mapaModalTitle').textContent = `Aviso #${numero} - Todos los Mapas`;
    document.getElementById('mapaModalContent').innerHTML = html;
    new bootstrap.Modal(document.getElementById('mapaModal')).show();
}

function abrirMapaModal(numero, nombre, url) {
    document.getElementById('mapaModalTitle').textContent = `Aviso #${numero} - ${nombre}`;
    document.getElementById('mapaModalContent').innerHTML = `
        <div>
            <img src="${url}" class="img-fluid" style="border-radius: 4px;">
            <div style="margin-top: 1rem;">
                <a href="${url}" download class="btn btn-primary w-100">
                    <i class="bi bi-download"></i> Descargar ${nombre}
                </a>
            </div>
        </div>
    `;
    new bootstrap.Modal(document.getElementById('mapaModal')).show();
}

function aplicarFiltros() {
    const orden = document.getElementById('filtro-orden').value;
    const nivel = document.getElementById('filtro-nivel').value;
    const grid = document.getElementById('avisos-grid');
    const cards = Array.from(grid.querySelectorAll('.aviso-card'));
    
    const cardsFiltradas = cards.filter(card => {
        if (nivel === 'todos') return true;
        return card.classList.contains('color-' + nivel);
    });
    
    cardsFiltradas.sort((a, b) => {
        const numeroA = parseInt(a.dataset.numero) || 0;
        const numeroB = parseInt(b.dataset.numero) || 0;
        
        if (orden === 'reciente') {
            return numeroA - numeroB;
        } else {
            return numeroB - numeroA;
        }
    });
    
    cards.forEach(card => card.style.display = 'none');
    
    grid.innerHTML = '';
    cardsFiltradas.forEach(card => {
        card.style.display = 'block';
        grid.appendChild(card);
    });
}

function resetearFiltros() {
    document.getElementById('filtro-orden').value = 'reciente';
    document.getElementById('filtro-nivel').value = 'todos';
    
    const url = new URL(window.location);
    if (url.searchParams.has('aviso')) {
        window.location.href = '/mapas';
        return;
    }
    
    const grid = document.getElementById('avisos-grid');
    grid.innerHTML = '';
    avisos_cache.forEach(card => {
        grid.appendChild(card.cloneNode(true));
    });
    
    aplicarFiltros();
}

document.addEventListener('DOMContentLoaded', cargarAvisos);
