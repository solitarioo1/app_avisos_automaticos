"""
routes/auth.py — Autenticación.

Usuario y contraseña NUNCA están en el código: salen de variables de entorno
(ADMIN_USERNAME/ADMIN_PASSWORD, INSPECTOR_USERNAME/INSPECTOR_PASSWORD) — mismo
nivel de confianza que DB_PASSWORD, que este proyecto ya maneja así (texto
plano en variables de entorno de EasyPanel, nunca en el código/git). El hash
de verdad (scrypt, vía werkzeug.security) se calcula accá mismo, UNA vez al
arrancar — el login compara contra ese hash, nunca contra texto plano.

Si alguno de los 2 pares usuario/contraseña no está configurado, ese usuario
simplemente no puede loguearse (no hay fallback a una contraseña conocida).
"""
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import UserMixin, login_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash

auth_bp = Blueprint('auth', __name__)


# ── Modelo de usuario en memoria ─────────────────────────────────────────────
class User(UserMixin):
    def __init__(self, id: str, username: str, role: str):
        self.id = id
        self.username = username
        self.role = role


_USUARIOS = {
    '1': User(id='1', username=os.getenv('ADMIN_USERNAME', ''), role='admin'),
    '2': User(id='2', username=os.getenv('INSPECTOR_USERNAME', ''), role='inspector'),
}

# username -> (password_hash, user_id) -- solo se registra el par si AMBAS
# variables (usuario Y contraseña) están presentes; si falta una, ese usuario
# queda simplemente sin poder loguearse (no hay valor por defecto "de prueba").
_CREDENCIALES = {}
if os.getenv('ADMIN_USERNAME') and os.getenv('ADMIN_PASSWORD'):
    _CREDENCIALES[os.environ['ADMIN_USERNAME']] = (generate_password_hash(os.environ['ADMIN_PASSWORD']), '1')
if os.getenv('INSPECTOR_USERNAME') and os.getenv('INSPECTOR_PASSWORD'):
    _CREDENCIALES[os.environ['INSPECTOR_USERNAME']] = (generate_password_hash(os.environ['INSPECTOR_PASSWORD']), '2')


def get_user(user_id: str):
    """Callback requerido por Flask-Login para cargar usuario por ID."""
    return _USUARIOS.get(user_id)


# ── Rutas ────────────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        credencial = _CREDENCIALES.get(username)
        if credencial and check_password_hash(credencial[0], password):
            usuario = _USUARIOS[credencial[1]]
            login_user(usuario, remember=False)
            next_page = request.args.get('next') or ''
            # Solo rutas internas (evita open redirect: //evil.com, http://...)
            if not next_page.startswith('/') or next_page.startswith('//') or '\\' in next_page:
                # Inspector entra directo a su única sección habilitada.
                next_page = url_for('evaluacion_riesgo.index') if usuario.role == 'inspector' else url_for('utils.inicio')
            return redirect(next_page)

        flash('Usuario o contraseña incorrectos', 'danger')

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
