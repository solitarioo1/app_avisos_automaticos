"""
routes/clasificar_cliente.py - "Clasifica tu Cliente": página independiente
para subir un Excel de clientes EXTERNOS (prospectos, no están en la BD),
clasificarlos contra una capa de riesgo y descargar el resultado.

El procesamiento en sí vive en routes/capas_riesgo.py
(POST /api/capas-riesgo/<nombre>/clasificar-excel) — esta página solo sirve
la UI y reutiliza ese mismo endpoint, para no duplicar la lógica de cruce.
"""
from flask import Blueprint, render_template
from flask_login import login_required

clasificar_cliente_bp = Blueprint('clasificar_cliente', __name__, url_prefix='/clasificar-cliente')


@clasificar_cliente_bp.route('/', methods=['GET'])
@login_required
def index():
    return render_template('clasificar_cliente.html')
