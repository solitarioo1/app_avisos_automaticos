/* ============================================================================
   WHATSAPP.JS - Página WhatsApp Masivo
   Lógica de envío de mensajes
   ============================================================================ */

document.addEventListener('DOMContentLoaded', function() {
    initializeWhatsApp();
});

function initializeWhatsApp() {
    console.log('💬 WhatsApp masivo iniciado');
    setupFormHandlers();
    loadContactosRecientes();
}

function setupFormHandlers() {
    // Simulación de inputs
    const previewBtn = document.getElementById('btnPreviewMsg');
    if (previewBtn) {
        previewBtn.addEventListener('click', previewMensaje);
    }
    
    const sendBtn = document.getElementById('btnEnviarMasivo');
    if (sendBtn) {
        sendBtn.addEventListener('click', enviarMasivo);
    }
}

function previewMensaje() {
    const titulo = document.getElementById('msgTitulo')?.value || 'Alerta Meteorológica';
    const aviso = document.getElementById('msgAviso')?.value || 'Se ha generado un aviso importante';
    
    const preview = `
🌦️ *${titulo}*

${aviso}

_Sistema La Positiva AgroSeguros_
    `;
    
    mostrarModal('📱 Vista Previa', `<pre style="text-align:left; background:#f0f0f0; padding:1rem; border-radius:4px;">${preview}</pre>`, 'info');
}

async function enviarMasivo() {
    const cantidad = document.getElementById('cantidadContactos')?.textContent || '0';
    
    try {
        const response = await fetch('/api/whatsapp/enviar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                titulo: document.getElementById('msgTitulo')?.value,
                mensaje: document.getElementById('msgAviso')?.value
            })
        });
        
        if (response.ok) {
            mostrarModal('✅ Envío Iniciado', `Se están enviando mensajes a ${cantidad} contactos`, 'success', true);
        } else {
            mostrarModal('❌ Error', 'Error al enviar mensajes masivos', 'danger');
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarModal('❌ Error', 'Error en la solicitud: ' + error.message, 'danger');
    }
}

function loadContactosRecientes() {
    // Simulación de carga de contactos recientes
    console.log('Cargando contactos recientes...');
}

function agregarContacto() {
    const telefono = document.getElementById('nuevoTelefono')?.value;
    if (!telefono) {
        mostrarModal('⚠️ Datos Incompletos', 'Por favor ingrese un número de teléfono', 'warning');
        return;
    }
    
    mostrarModal('✅ Contacto Agregado', `Contacto ${telefono} agregado correctamente`, 'success');
    document.getElementById('nuevoTelefono').value = '';
}

function exportarContactos() {
    mostrarModal('📥 Exportación', 'Los contactos están siendo exportados...', 'info');
}

function importarContactos() {
    mostrarModal('📤 Importación', 'Seleccione un archivo CSV de contactos', 'info');
}
