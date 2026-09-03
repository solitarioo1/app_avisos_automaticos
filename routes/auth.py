"""
routes/auth.py — Autenticación básica para testing
Usuario hardcodeado: admin / admin  (NO USAR EN PRODUCCIÓN)
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import UserMixin, login_user, logout_user, login_required

auth_bp = Blueprint('auth', __name__)


# ── Modelo de usuario en memoria (solo testing) ──────────────────────────────
class User(UserMixin):
    def __init__(self, id: str, username: str):
        self.id = id
        self.username = username


# Usuario único para testing
_TEST_USER = User(id='1', username='admin')
_TEST_PASSWORD = 'admin'


def get_user(user_id: str):
    """Callback requerido por Flask-Login para cargar usuario por ID."""
    if user_id == _TEST_USER.id:
        return _TEST_USER
    return None


# ── Rutas ────────────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if username == _TEST_USER.username and password == _TEST_PASSWORD:
            login_user(_TEST_USER, remember=False)
            next_page = request.args.get('next') or url_for('utils.inicio')
            return redirect(next_page)

        flash('Usuario o contraseña incorrectos', 'danger')

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
