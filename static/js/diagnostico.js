const logs = [];
const originalLog = console.log;
const originalError = console.error;

console.log = function(...args) {
    logs.push('[LOG] ' + args.join(' '));
    originalLog.apply(console, args);
};

console.error = function(...args) {
    logs.push('[ERROR] ' + args.join(' '));
    originalError.apply(console, args);
};

// PASO 1: Verificar elementos
function checkElements() {
    const elementIds = [
        'mapa-leaflet',
        'filtro-aviso',
        'kpi-critico',
        'kpi-alto',
        'kpi-agr',
        'kpi-pol',
        'kpi-ha',
        'stat-nivel',
        'stat-agricultores',
        'stat-poliza',
        'stat-hectareas'
    ];

    let html = '';
    elementIds.forEach(id => {
        const elem = document.getElementById(id);
        const status = elem ? '✅' : '❌';
        html += `${status} #${id}\n`;
    });

    document.getElementById('elemento-check').textContent = html;
}

// PASO 2: Verificar globales
function checkGlobals() {
    const vars = ['mapa', 'avisoActual', 'geojsonLayer', 'clientesLayer', 'delimitacionesLayers', 'nivelSeleccionado'];
    let html = '';
    vars.forEach(v => {
        const exists = typeof window[v] !== 'undefined';
        const status = exists ? '✅' : '❌';
        const type = typeof window[v];
        html += `${status} ${v} (${type})\n`;
    });
    document.getElementById('globals-check').textContent = html;
}

// PASO 3: Verificar endpoints
async function checkEndpoints() {
    let html = 'Intentando conectar a http://localhost:5000\n\n';

    const endpoints = [
        '/listar_avisos',
        '/api/delimitaciones/departamentos',
        '/api/avisos/445/clientes-geojson'
    ];

    for (const endpoint of endpoints) {
        try {
            const resp = await fetch(`http://localhost:5000${endpoint}`);
            const status = resp.ok ? '✅' : `❌ (${resp.status})`;
            html += `${status} GET ${endpoint}\n`;
        } catch (e) {
            html += `❌ GET ${endpoint} - ${e.message}\n`;
        }
    }

    document.getElementById('endpoints-check').textContent = html;
}

// PASO 4: Mostrar logs
function showLogs() {
    document.getElementById('console-log').textContent = logs.join('\n');
}

// Ejecutar todo
window.addEventListener('load', () => {
    checkElements();
    checkGlobals();
    checkEndpoints();
    setInterval(showLogs, 500);
});
