// ============================================================================
// SENAMHI Dashboard - JavaScript Functions
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    initializeDashboard();
});

// ============================================================================
// INICIALIZACIÓN
// ============================================================================
function initializeDashboard() {
    console.log('🌦️ La Positiva Dashboard iniciado');
    
    // Marcar enlace activo en sidebar
    highlightActiveNavLink();
    
    // Configurar tooltips de Bootstrap
    initializeTooltips();
    
    // Configurar eventos generales
    setupEventListeners();
    
    // Cargar datos iniciales
    loadInitialData();
}

// ============================================================================
// NAVEGACIÓN
// ============================================================================
function highlightActiveNavLink() {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.sidebar .nav-link');
    
    navLinks.forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('href') === currentPath || 
            (currentPath === '/' && link.getAttribute('href') === '/')) {
            link.classList.add('active');
        }
    });
}

// ============================================================================
// TOOLTIPS Y UI
// ============================================================================
function initializeTooltips() {
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// ============================================================================
// EVENT LISTENERS
// ============================================================================
function setupEventListeners() {
    // Responsive sidebar toggle (móvil)
    document.addEventListener('click', function(e) {
        if (e.target.closest('.navbar-toggler')) {
            toggleSidebar();
        }
    });
    
    // Auto-refresh de estadísticas
    setInterval(() => {
        if (document.getElementById('total-avisos')) {
            refreshStats();
        }
    }, 60000); // Cada minuto
}

// ============================================================================
// DATOS INICIALES
// ============================================================================
function loadInitialData() {
    // Cargar estadísticas
    refreshStats();
    
    // Actualizar timestamp
    updateTimestamp();
    setInterval(updateTimestamp, 60000); // Cada minuto
}

// ============================================================================
// ESTADÍSTICAS
// ============================================================================
function refreshStats() {
    fetch('/api/stats')
        .then(response => response.json())
        .then(data => {
            updateStatsDisplay(data);
        })
        .catch(error => {
            console.error('Error actualizando estadísticas:', error);
        });
}

function updateStatsDisplay(stats) {
    const elements = {
        'total-avisos': stats.total_avisos || 0,
        'avisos-procesados': stats.procesados || 0,
        'mapas-generados': stats.mapas || 0,
        'enviados-whatsapp': stats.whatsapp || 0
    };
    
    Object.entries(elements).forEach(([id, value]) => {
        const element = document.getElementById(id);
        if (element) {
            animateNumber(element, parseInt(element.textContent) || 0, value);
        }
    });
}

function animateNumber(element, from, to) {
    const duration = 1000;
    const steps = 20;
    const stepValue = (to - from) / steps;
    const stepTime = duration / steps;
    let current = from;
    
    const timer = setInterval(() => {
        current += stepValue;
        element.textContent = Math.round(current);
        
        if ((stepValue > 0 && current >= to) || (stepValue < 0 && current <= to)) {
            element.textContent = to;
            clearInterval(timer);
        }
    }, stepTime);
}

// ============================================================================
// TIMESTAMP
// ============================================================================
function updateTimestamp() {
    const now = new Date();
    const formatted = now.toLocaleDateString('es-ES') + ' ' + 
                     now.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
    
    const timestampElement = document.getElementById('current-time');
    if (timestampElement) {
        timestampElement.textContent = formatted;
    }
}

// ============================================================================
// NOTIFICACIONES
// ============================================================================
function showNotification(message, type = 'info', duration = 5000) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    alertDiv.style.cssText = 'top: 90px; right: 20px; z-index: 1050; min-width: 300px;';
    
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(alertDiv);
    
    // Auto-dismiss
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, duration);
}

// ============================================================================
// UTILIDADES DE API
// ============================================================================
function apiCall(endpoint, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
        }
    };
    
    return fetch(endpoint, { ...defaultOptions, ...options })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        });
}

// ============================================================================
// RESPONSIVE
// ============================================================================
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const content = document.querySelector('.content');
    
    sidebar.classList.toggle('sidebar-mobile-open');
    content.classList.toggle('content-sidebar-open');
}

// ============================================================================
// FORMULARIOS
// ============================================================================
function resetForm(formId) {
    const form = document.getElementById(formId);
    if (form) {
        form.reset();
        // Limpiar validaciones
        form.querySelectorAll('.is-invalid').forEach(el => {
            el.classList.remove('is-invalid');
        });
        form.querySelectorAll('.invalid-feedback').forEach(el => {
            el.remove();
        });
    }
}

function validateForm(formId) {
    const form = document.getElementById(formId);
    if (!form) return false;
    
    let isValid = true;
    
    // Limpiar validaciones previas
    form.querySelectorAll('.is-invalid').forEach(el => {
        el.classList.remove('is-invalid');
    });
    form.querySelectorAll('.invalid-feedback').forEach(el => {
        el.remove();
    });
    
    // Validar campos requeridos
    form.querySelectorAll('[required]').forEach(field => {
        if (!field.value.trim()) {
            showFieldError(field, 'Este campo es obligatorio');
            isValid = false;
        }
    });
    
    return isValid;
}

function showFieldError(field, message) {
    field.classList.add('is-invalid');
    
    const feedback = document.createElement('div');
    feedback.className = 'invalid-feedback';
    feedback.textContent = message;
    
    field.parentNode.appendChild(feedback);
}

// ============================================================================
// LOADING STATES
// ============================================================================
function showLoading(element) {
    const originalContent = element.innerHTML;
    element.dataset.originalContent = originalContent;
    element.innerHTML = '<i class="bi bi-hourglass-split"></i> Cargando...';
    element.disabled = true;
}

function hideLoading(element) {
    const originalContent = element.dataset.originalContent;
    if (originalContent) {
        element.innerHTML = originalContent;
        delete element.dataset.originalContent;
    }
    element.disabled = false;
}

// ============================================================================
// EXPORTAR FUNCIONES GLOBALES
// ============================================================================
window.SENAMHI = {
    showNotification,
    apiCall,
    refreshStats,
    resetForm,
    validateForm,
    showLoading,
    hideLoading
};