"""
routes/auth.py — Autenticación básica para testing
Usuarios hardcodeados (NO USAR EN PRODUCCIÓN):
  - solitario / solitario  -> role 'admin'    (acceso completo)
  - inspector / inspector  -> role 'inspector' (solo Evaluación de Riesgo)
"""
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import UserMixin, login_user, logout_user, login_required

auth_bp = Blueprint('auth', __name__)


# ── Modelo de usuario en memoria (solo testing) ──────────────────────────────
class User(UserMixin):
    def __init__(self, id: str, username: str, role: str):
        self.id = id
        self.username = username
        self.role = role


_USUARIOS = {
    '1': User(id='1', username='solitario', role='admin'),
    '2': User(id='2', username='inspector', role='inspector'),
}
_CREDENCIALES = {
    'solitario': ('solitario', '1'),
    'inspector': (os.getenv('INSPECTOR_PASSWORD', 'inspector'), '2'),
}


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
        if credencial and password == credencial[0]:
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
