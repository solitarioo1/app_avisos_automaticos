/* ============================================================================
   MAIN.JS - Funciones Globales
   Scripts reutilizables en todas las páginas
   ============================================================================ */

// Reloj en tiempo real del header
function updateClock() {
    const now = new Date();
    const timeString = now.toLocaleString('es-ES', {
        hour: '2-digit', minute: '2-digit', second: '2-digit',
        day: '2-digit', month: '2-digit', year: 'numeric'
    });
    const el = document.getElementById('current-time');
    if (el) el.textContent = timeString;
}

// Iniciar reloj
document.addEventListener('DOMContentLoaded', function() {
    setInterval(updateClock, 1000);
    updateClock();
});

// Modal genérico de notificaciones
function mostrarModal(titulo, mensaje, tipo, reload = false) {
    const tipoColor = {
        'success': '#10b981',
        'info': '#6366f1',
        'danger': '#ef4444'
    };
    
    const tipoIcono = {
        'success': '✅',
        'info': '🌩️',
        'danger': '⚠️'
    };
    
    const tipoLabel = {
        'success': 'Éxito',
        'info': 'Información',
        'danger': 'Error'
    };
    
    const modalHTML = `
        <div class="modal fade" id="modalNotificacion" tabindex="-1" aria-hidden="true" style="backdrop-filter: blur(4px) !important;">
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content border-0" style="border-radius: 16px !important; overflow: hidden !important; box-shadow: 0 20px 60px rgba(0,0,0,0.25) !important;">
                    <div style="background: linear-gradient(135deg, ${tipoColor[tipo]} 0%, ${tipoColor[tipo]}e0 100%) !important; padding: 40px 30px !important; text-align: center !important; position: relative !important;">
                        <div style="position: absolute !important; top: 15px !important; right: 15px !important; background: rgba(255,255,255,0.2) !important; padding: 6px 12px !important; border-radius: 20px !important; font-size: 11px !important; color: white !important; font-weight: 600 !important; text-transform: uppercase !important; letter-spacing: 0.5px !important;">${tipoLabel[tipo]}</div>
                        <div style="font-size: 56px !important; margin-bottom: 15px !important; animation: bounce 2s infinite !important;">${tipoIcono[tipo]}</div>
                        <h5 style="font-size: 24px !important; font-weight: 800 !important; margin: 0 !important; color: white !important; letter-spacing: -0.5px !important;">${titulo}</h5>
                    </div>
                    <div style="padding: 35px 30px !important; background: #ffffff !important;">
                        <p style="font-size: 15px !important; color: #64748b !important; line-height: 1.7 !important; margin: 0 !important; font-weight: 500 !important;">${mensaje}</p>
                    </div>
                    <div style="padding: 20px 30px 30px !important; background: #f8fafc !important; text-align: center !important; border-top: 1px solid #e2e8f0 !important;">
                        <button type="button" style="background: linear-gradient(135deg, ${tipoColor[tipo]} 0%, ${tipoColor[tipo]}e0 100%) !important; color: white !important; border: none !important; padding: 12px 40px !important; border-radius: 10px !important; font-weight: 700 !important; font-size: 15px !important; cursor: pointer !important; transition: all 0.3s ease !important; box-shadow: 0 4px 15px rgba(0,0,0,0.1) !important;" onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 8px 25px rgba(0,0,0,0.15)'" onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 4px 15px rgba(0,0,0,0.1)'" data-bs-dismiss="modal" onclick="${reload ? 'location.reload()' : ''}">
                            ${reload ? '🔄 Recargar' : '✓ Aceptar'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
        <style>
            @keyframes bounce {
                0%, 100% { transform: scale(1); }
                50% { transform: scale(1.1); }
            }
        </style>
    `;
    
    let modal = document.getElementById('modalNotificacion');
    if (modal) modal.remove();
    
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    const newModal = new bootstrap.Modal(document.getElementById('modalNotificacion'));
    newModal.show();
}

// Spinner CSS
const style = document.createElement('style');
style.textContent = `
    .spin {
        display: inline-block;
        animation: spin 1s linear infinite;
    }
    @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
`;
document.head.appendChild(style);
