/* ============================================================================
   MAPAS.JS - Página de Mapas
   Lógica de carga, generación y filtrado de mapas
   ============================================================================ */

let avisos_cache = [];
let carousel_state = {};
let cards_cache = [];

function obtenerParametroURL(nombre) {
    const params = new URLSearchParams(window.location.search);
    return params.get(nombre);
}

async function cargarAvisos() {
    try {
        const avisoEspecifico = obtenerParametroURL('aviso');

        const res = await fetch('/api/avisos');
        const result = await res.json();
        let avisos = result.avisos || [];

        // Solo avisos con JSON descargado
        avisos = avisos.filter(a => a.descargado === '\u2705');

        if (avisoEspecifico) {
            avisos = avisos.filter(a => a.numero == avisoEspecifico);
        }
        
        const avisoPromises = avisos.map(async (aviso) => {
            try {
                const infoRes = await fetch(`/api/avisos/${aviso.numero}/info`);
                if (!infoRes.ok) return '';

                const info = await infoRes.json();
                if (!info.success) return '';

                const mapasRes = await fetch(`/api/mapas/aviso/${aviso.numero}`).catch(() => null);
                const mapas = mapasRes ? await mapasRes.json().catch(() => ({ mapas: [] })) : { mapas: [] };

                let departamentos = [];
                if (info.mapas_creados) {
                    const deptosRes = await fetch(`/api/avisos/${aviso.numero}/departamentos`).catch(() => null);
                    if (deptosRes && deptosRes.ok) {
                        const deptosData = await deptosRes.json();
                        departamentos = deptosData.departamentos || [];
                    }
                }

                const mapaStatus = info.mapas_creados ? 'ready' : 'pending';
                const mapaStatusText = info.mapas_creados ? '\u2705 Creados' : '\u23f3 No Creados';
                const colorCard = info.color || 'plomo';

                return `
                    <div class="aviso-card color-${colorCard}" data-numero="${aviso.numero}" data-color="${info.color}" data-titulo="${aviso.titulo.replace(/"/g, '&quot;')}">
                        <div class="aviso-header color-${colorCard}">
                            <p class="aviso-titulo">${aviso.titulo}</p>
                            <p class="aviso-numero-small">aviso N\u00b0 ${aviso.numero}</p>
                        </div>
                        <div class="aviso-body">
                            <div class="info-row">
                                <div class="info-label">NIVEL</div>
                                <span class="nivel-badge nivel-${info.color.toLowerCase()}">${info.color.toUpperCase()}</span>
                            </div>
                            <div class="info-row">
                                <div class="info-label">ESTADO</div>
                                <span class="status-badge status-${mapaStatus}">${mapaStatusText}</span>
                            </div>
                            ${departamentos.length > 0 ? `
                                <div class="info-row">
                                    <div class="info-label">DEPARTAMENTOS ${info.mapas_creados ? '<span style="font-size:9px;color:#04ccc4;">(clic para ver mapa)</span>' : ''}</div>
                                    <div class="departamentos-list">
                                        ${departamentos.map(d => `<span class="depto-tag${info.mapas_creados ? ' depto-clickable' : ''}" ${info.mapas_creados ? `onclick="abrirMapaDepartamento(${aviso.numero}, '${d}')" title="Ver mapa de ${d}"` : ''}>${d}</span>`).join('')}
                                    </div>
                                </div>
                            ` : ''}
                        </div>
                        <div class="aviso-footer">
                            ${info.mapas_creados && mapas.mapas.length > 0 ? `
                                <button class="btn btn-sm btn-naranja-turquesa" onclick="abrirCarruselModal(${aviso.numero})">
                                    <i class="bi bi-eye"></i> Ver Todos
                                </button>
                                <button class="btn btn-sm btn-naranja-turquesa" onclick="generarMapas(${aviso.numero}, true)">
                                    <i class="bi bi-arrow-repeat"></i> Regenerar
                                </button>
                            ` : `
                                <button class="btn btn-sm btn-naranja-turquesa" disabled><i class="bi bi-eye"></i> Ver Todos</button>
                                <button class="btn btn-sm btn-naranja-turquesa" onclick="generarMapas(${aviso.numero})">
                                    <i class="bi bi-play-circle"></i> Generar
                                </button>
                            `}
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
            html = `<div style="grid-column: 1/-1; text-align: center; padding: 3rem 1rem;">
                <i class="bi bi-inbox display-1 text-muted"></i>
                <h4 class="text-muted mt-3">Sin avisos</h4>
            </div>`;
        }

        document.getElementById('avisos-grid').innerHTML = html;
        cards_cache = Array.from(document.getElementById('avisos-grid').querySelectorAll('.aviso-card'));
        aplicarFiltros();
    } catch (error) {
        console.error('Error:', error);
        document.getElementById('avisos-grid').innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 2rem;"><p class="text-danger">Error: ${error.message}</p></div>`;
    }
}

async function abrirCarruselModal(numero) {
    const res = await fetch(`/api/mapas/aviso/${numero}`);
    const data = await res.json();

    if (!data.success || !data.mapas.length) {
        alert('Sin mapas');
        return;
    }

    carousel_state[numero] = { mapas: data.mapas, index: 0 };
    mostrarCarrusel(numero);
    const cardEl = document.querySelector(`.aviso-card[data-numero="${numero}"]`);
    const titulo = cardEl ? cardEl.dataset.titulo : '';
    document.getElementById('mapaModalTitle').textContent = `${titulo} (Aviso N\u00b0 ${numero})`;
    document.getElementById('mapaModalDepto').textContent = '';
    new bootstrap.Modal(document.getElementById('mapaModal')).show();
}

async function abrirMapaDepartamento(numero, departamento) {
    const res = await fetch(`/api/mapas/aviso/${numero}`);
    const data = await res.json();

    if (!data.success || !data.mapas.length) {
        alert('Sin mapas para este aviso');
        return;
    }

    // Buscar el mapa cuyo nombre coincide con el departamento (MAYUSCULA.webp)
    const deptoUpper = departamento.toUpperCase();
    let idx = data.mapas.findIndex(m =>
        m.nombre.toUpperCase().replace('.WEBP', '').replace('.PNG', '') === deptoUpper
    );
    if (idx === -1) idx = 0; // fallback al primero si no encuentra exacto

    carousel_state[numero] = { mapas: data.mapas, index: idx };
    mostrarCarrusel(numero);
    const cardEl = document.querySelector(`.aviso-card[data-numero="${numero}"]`);
    const titulo = cardEl ? cardEl.dataset.titulo : '';
    document.getElementById('mapaModalTitle').textContent = `${titulo} (Aviso N\u00b0 ${numero})`;
    document.getElementById('mapaModalDepto').textContent = departamento;
    new bootstrap.Modal(document.getElementById('mapaModal')).show();
}

function mostrarCarrusel(numero) {
    const state = carousel_state[numero];
    const mapa = state.mapas[state.index];
    const departamento = mapa.nombre.replace('.webp', '').replace('.png', '') || 'Mapa';

    const html = `
        <div class="carousel-mapas">
            <button class="carousel-nav" onclick="carouselAnterior(${numero})" ${state.index === 0 ? 'disabled' : ''}>◄</button>
            <div class="carousel-container">
                <img class="carousel-imagen" src="${mapa.url}" alt="${mapa.nombre}" onclick="toggleZoom(this)" id="mapaImg-${numero}">
            </div>
            <button class="carousel-nav" onclick="carouselSiguiente(${numero})" ${state.index === state.mapas.length - 1 ? 'disabled' : ''}>►</button>
        </div>
        <p style="text-align: center; margin: 0.5rem 0; font-size: 12px; color: #666;">
            ${state.index + 1} de ${state.mapas.length}
        </p>
        <a href="${mapa.url}" download class="btn btn-naranja-turquesa w-100">
            <i class="bi bi-download"></i> Descargar ${mapa.nombre}
        </a>
    `;

    document.getElementById('mapaModalTitle').textContent = departamento;
    document.getElementById('carouselContent').innerHTML = html;
}

function toggleZoom(img) {
    if (img.classList.contains('zoomed')) {
        img.classList.remove('zoomed');
        img.style.height = '450px';
        img.style.cursor = 'zoom-in';
    } else {
        img.classList.add('zoomed');
        img.style.height = 'auto';
        img.style.maxHeight = '90vh';
        img.style.cursor = 'zoom-out';
    }
}

function carouselAnterior(numero) {
    const state = carousel_state[numero];
    if (state.index > 0) {
        state.index--;
        mostrarCarrusel(numero);
    }
}

function carouselSiguiente(numero) {
    const state = carousel_state[numero];
    if (state.index < state.mapas.length - 1) {
        state.index++;
        mostrarCarrusel(numero);
    }
}

async function generarMapas(numero, force = false) {
    const modal = new bootstrap.Modal(document.getElementById('mapaModal'));
    document.getElementById('mapaModalTitle').textContent = `${force ? 'Regenerando' : 'Generando'} mapas - Aviso #${numero}`;
    document.getElementById('mapaModalDepto').textContent = force ? '⚠️ Borrando mapas anteriores y reprocesando...' : '';
    document.getElementById('carouselContent').innerHTML = '<p>Iniciando...</p>';
    modal.show();

    const eventSource = new EventSource(`/api/avisos/${numero}/procesar?stream=true${force ? '&force=true' : ''}`);
    let logHTML = '';

    eventSource.onmessage = function(event) {
        const msg = JSON.parse(event.data);

        if (msg.type === 'log') {
            const color = msg.severity === 'error' ? '#cc0000' : msg.severity === 'success' ? '#008000' : '#333';
            logHTML += `<div style="color: ${color}; font-size: 12px;">${msg.message}</div>`;
        } else if (msg.type === 'complete') {
            logHTML += `<div style="color: #008000; font-weight: bold;">✅ ${msg.message}</div>`;
            eventSource.close();
            setTimeout(() => { location.reload(); }, 2000);
        }

        document.getElementById('carouselContent').innerHTML = logHTML;
        document.getElementById('carouselContent').scrollTop = document.getElementById('carouselContent').scrollHeight;
    };

    eventSource.onerror = function() {
        eventSource.close();
        logHTML += `<div style="color: #cc0000;">❌ Error en conexi\u00f3n</div>`;
        document.getElementById('carouselContent').innerHTML = logHTML;
    };
}

function aplicarFiltros() {
    const orden = document.getElementById('filtro-orden').value;
    const nivel = document.getElementById('filtro-nivel').value;
    const numero = document.getElementById('filtro-numero').value.trim();
    const grid = document.getElementById('avisos-grid');

    let cardsFiltradas = cards_cache.filter(card => {
        if (nivel !== '') {
            const color = card.getAttribute('data-color').toLowerCase();
            if (color !== nivel) return false;
        }
        if (numero !== '') {
            const cardNumero = card.getAttribute('data-numero') || '';
            if (!cardNumero.includes(numero)) return false;
        }
        return true;
    });

    cardsFiltradas.sort((a, b) => {
        const numeroA = parseInt(a.dataset.numero) || 0;
        const numeroB = parseInt(b.dataset.numero) || 0;
        return orden === 'desc' ? numeroB - numeroA : numeroA - numeroB;
    });

    grid.innerHTML = '';
    cardsFiltradas.forEach(card => {
        const clone = card.cloneNode(true);
        grid.appendChild(clone);
    });
}

function resetearFiltros() {
    document.getElementById('filtro-orden').value = 'desc';
    document.getElementById('filtro-nivel').value = '';
    document.getElementById('filtro-numero').value = '';
    aplicarFiltros();
}

document.addEventListener('DOMContentLoaded', cargarAvisos);
