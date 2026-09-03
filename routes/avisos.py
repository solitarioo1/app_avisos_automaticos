"""
Rutas de Avisos - API endpoints para gestión de avisos meteorológicos
"""
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
import psycopg2.extras
from flask import (Blueprint, Response, jsonify, render_template, request,stream_with_context)
from flask_login import login_required
from CONFIG.db import get_connection

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / 'OUTPUT'
SHP_DIR = BASE_DIR / 'SHP'
logger = logging.getLogger(__name__)
active_processes = {}

avisos_bp = Blueprint('avisos', __name__, url_prefix='')


@avisos_bp.route('/avisos', methods=['GET'])
@login_required
def avisos():
    """Página de gestión de avisos - Conectado a BD o archivos locales"""
    avisos_lista = []
    aviso_param = request.args.get('aviso')
    filtro_numero = int(aviso_param) if aviso_param else None

    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        query = (
            "SELECT DISTINCT numero_aviso, fecha_emision, titulo, nivel, "
            "color FROM avisos_completos WHERE color IN ('rojo', 'naranja') "
            "ORDER BY numero_aviso DESC"
        )
        cursor.execute(query)
        avisos_bd = cursor.fetchall()

        # Qué avisos ya corrieron procesar_aviso.py (SHP + clientes_por_aviso)
        # — señal real de "listo para Seguro Comercial", DISTINTA de
        # mapa_creado (que solo mira si hay PNG/WEBP estáticos, flujo viejo).
        # Antes el botón "Generar capa y clasificar clientes" se quedaba
        # siempre del mismo color aunque ya se hubiera procesado — parecía
        # que faltaba generar. Una sola query acá, no una por aviso.
        cursor.execute("SELECT DISTINCT numero_aviso FROM clientes_por_aviso")
        avisos_con_capa = {r['numero_aviso'] for r in cursor.fetchall()}
        cursor.close()
        conn.close()

        for aviso in avisos_bd:
            numero = aviso['numero_aviso']
            if filtro_numero and numero != filtro_numero:
                continue

            json_path = BASE_DIR / 'JSON' / 'aviso_{}.json'.format(numero)
            output_path = OUTPUT_DIR / 'aviso_{}'.format(numero)

            estado_descargado = json_path.exists()
            mapas_creados = (output_path.exists() and
                           (any(output_path.glob('*.webp')) or
                            any(output_path.glob('*.png'))))
            capa_procesada = numero in avisos_con_capa

            css_class = ('table-success' if mapas_creados else
                        ('table-warning' if estado_descargado else ''))
            avisos_lista.append({
                'numero': numero,
                'titulo': aviso['titulo'],
                'nivel': aviso['nivel'],
                'color': aviso['color'],
                'fecha_emision': str(aviso['fecha_emision']),
                'descargado': '✅' if estado_descargado else '⏳',
                'mapa_creado': '✅' if mapas_creados else '⏳',
                'capa_procesada': capa_procesada,
                'estado_css': css_class
            })
    except (psycopg2.Error, ImportError):
        logger.warning("BD no disponible, usando JSON locales")
        json_dir = BASE_DIR / 'JSON'
        if json_dir.exists():
            for json_file in sorted(json_dir.glob('aviso_*.json'),
                                   reverse=True):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        numero_str = data.get('numero_aviso',
                                            json_file.stem.replace('aviso_',
                                                                  ''))
                        numero = int(numero_str)

                        if filtro_numero and numero != filtro_numero:
                            continue

                        color = data.get('color', 'plomo').lower()
                        if color not in ['rojo', 'naranja']:
                            continue

                        output_path = OUTPUT_DIR / 'aviso_{}'.format(numero)
                        mapas_creados = (output_path.exists() and
                                       (any(output_path.glob('*.webp')) or
                                        any(output_path.glob('*.png'))))
                        # Sin BD no se puede consultar clientes_por_aviso —
                        # se usa la carpeta SHP/aviso_N/ como proxy (procesar_
                        # aviso.py la crea junto con el cruce de clientes).
                        capa_procesada = (SHP_DIR / 'aviso_{}'.format(numero)).exists()

                        avisos_lista.append({
                            'numero': numero,
                            'titulo': data.get('titulo', 'Aviso {}'.format(
                                numero)),
                            'nivel': data.get('nivel', 'AMARILLO').upper(),
                            'color': color,
                            'fecha_emision': data.get('fecha_emision',
                                                     '2026-02-01'),
                            'descargado': '✅',
                            'mapa_creado': '✅' if mapas_creados else '⏳',
                            'capa_procesada': capa_procesada,
                            'estado_css': ('table-success' if mapas_creados
                                         else 'table-warning')
                        })
                except (ValueError, KeyError, json.JSONDecodeError,
                       OSError):
                    pass

    return render_template('pronosticos.html', avisos=avisos_lista)


@avisos_bp.route('/api/avisos/<int:numero>/descargar', methods=['POST'])
def api_descargar_aviso(numero):
    """API para descargar JSON de aviso desde SENAMHI"""
    try:
        json_path = BASE_DIR / 'JSON' / 'aviso_{}.json'.format(numero)

        if json_path.exists():
            return jsonify({
                'success': True,
                'message': 'Aviso ya descargado',
                'file': str(json_path)
            }), 200

        result = subprocess.run(
            [sys.executable, str(BASE_DIR / 'descargar_aviso.py'),
             str(numero)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False
        )

        if result.returncode == 0:
            if json_path.exists():
                return jsonify({
                    'success': True,
                    'message': 'Aviso {} descargado correctamente'.format(
                        numero),
                    'file': str(json_path)
                }), 200
            return jsonify({
                'success': False,
                'error': 'Descarga completada pero archivo no encontrado'
            }), 400
        return jsonify({
            'success': False,
            'error': 'Error en descarga: {}'.format(result.stderr)
        }), 400

    except subprocess.TimeoutExpired:
        return jsonify({
            'success': False,
            'error': 'Timeout: La descarga tardó demasiado'
        }), 408
    except OSError as e:
        logger.error("Error descargando aviso %d: %s", numero, str(e))
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@avisos_bp.route('/api/avisos/<int:numero>/procesar',
                  methods=['POST', 'GET'])
def api_procesar_aviso(numero):
    """API para generar mapas del aviso con soporte Server-Sent Events"""
    try:
        stream = request.args.get('stream', 'false').lower() == 'true'
        force  = request.args.get('force',  'false').lower() == 'true'
        output_path = OUTPUT_DIR / 'aviso_{}'.format(numero)

        # Si ya existen mapas y NO es force → retornar sin reprocesar
        if (not force and output_path.exists() and
                (any(output_path.glob('*.webp')) or
                 any(output_path.glob('*.png')))):
            if stream:
                def generate_existing():
                    msg = {'type': 'log', 'message': 'Mapas ya existen',
                           'severity': 'info'}
                    yield "data: {}\n\n".format(json.dumps(msg))
                    msg2 = {'type': 'complete',
                            'message': 'Procesamiento completado'}
                    yield "data: {}\n\n".format(json.dumps(msg2))
                return Response(stream_with_context(generate_existing()),
                              mimetype='text/event-stream')
            return jsonify({
                'success': True,
                'message': 'Mapas ya existen',
                'path': str(output_path)
            }), 200

        # force=true → limpiar OUTPUT anterior para reprocesar desde cero
        if force and output_path.exists():
            import shutil
            shutil.rmtree(str(output_path), ignore_errors=True)
            logger.info('Limpiado OUTPUT para forzar regeneración: aviso %d', numero)

        if stream:
            def generate():
                process = None
                try:
                    msg_init = {
                        'type': 'log',
                        'message': ('Iniciando procesamiento del aviso '
                                   '{}...').format(numero),
                        'severity': 'info'
                    }
                    yield "data: {}\n\n".format(json.dumps(msg_init))

                    process = subprocess.Popen(
                        [sys.executable,
                         str(BASE_DIR / 'procesar_aviso.py'),
                         str(numero)],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1,
                        universal_newlines=True
                    )

                    active_processes[numero] = process

                    for line in process.stdout:
                        if (numero in active_processes and
                            active_processes[numero] is None):
                            process.terminate()
                            break

                        line = line.rstrip('\n')
                        if line:
                            if 'ERROR' in line or 'Error' in line:
                                sev = 'error'
                            elif ('SUCCESS' in line or 'completado' in line
                                  or 'generado' in line):
                                sev = 'success'
                            else:
                                sev = 'info'

                            msg = {'type': 'log', 'message': line,
                                   'severity': sev}
                            yield "data: {}\n\n".format(json.dumps(msg))

                    for line in process.stderr:
                        line = line.rstrip('\n')
                        if line:
                            msg = {'type': 'log',
                                   'message': '[STDERR] {}'.format(line),
                                   'severity': 'warning'}
                            yield "data: {}\n\n".format(json.dumps(msg))

                    returncode = process.wait()

                    if returncode == 0:
                        img_files = (list(output_path.glob('*.webp')) +
                                    list(output_path.glob('*.png')))
                        num_mapas = len(img_files)
                        msg_succ = {
                            'type': 'log',
                            'message': ('✅ {} mapas generados '
                                       'exitosamente').format(num_mapas),
                            'severity': 'success'
                        }
                        yield "data: {}\n\n".format(json.dumps(msg_succ))
                        msg_comp = {
                            'type': 'complete',
                            'message': ('Procesamiento completado - {} '
                                       'mapas').format(num_mapas)
                        }
                        yield "data: {}\n\n".format(json.dumps(msg_comp))
                    else:
                        msg_err = {
                            'type': 'error',
                            'message': ('Proceso terminó con código '
                                       '{}').format(returncode)
                        }
                        yield "data: {}\n\n".format(json.dumps(msg_err))
                        msg_fail = {'type': 'complete',
                                   'message': 'Procesamiento fallido'}
                        yield "data: {}\n\n".format(json.dumps(msg_fail))

                    if numero in active_processes:
                        del active_processes[numero]

                except OSError as e:
                    msg_ex = {'type': 'error', 'message': str(e)}
                    yield "data: {}\n\n".format(json.dumps(msg_ex))
                    msg_ex2 = {'type': 'complete', 'message': 'Error'}
                    yield "data: {}\n\n".format(json.dumps(msg_ex2))
                    if numero in active_processes:
                        del active_processes[numero]

            response = Response(stream_with_context(generate()),
                              mimetype='text/event-stream')
            response.headers['Cache-Control'] = 'no-cache'
            response.headers['X-Accel-Buffering'] = 'no'
            return response

        result = subprocess.run(
            [sys.executable, str(BASE_DIR / 'procesar_aviso.py'),
             str(numero)],
            capture_output=True,
            text=True,
            timeout=300,
            check=False
        )

        if result.returncode == 0:
            img_files = (list(output_path.glob('*.webp')) +
                        list(output_path.glob('*.png')))

            return jsonify({
                'success': True,
                'message': 'Mapas generados correctamente',
                'mapas': len(img_files),
                'path': str(output_path)
            }), 200

        return jsonify({
            'success': False,
            'error': 'Error en procesamiento: {}'.format(result.stderr)
        }), 400

    except subprocess.TimeoutExpired:
        return jsonify({
            'success': False,
            'error': 'Timeout: El procesamiento tardó demasiado'
        }), 408
    except OSError as e:
        logger.error("Error procesando aviso %d: %s", numero, str(e))
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@avisos_bp.route('/api/avisos/<int:numero>/cancel', methods=['POST'])
def api_cancel_aviso(numero):
    """API para cancelar la generación de mapas en curso"""
    try:
        if numero in active_processes:
            process = active_processes[numero]
            if process and process.poll() is None:
                import signal
                if hasattr(signal, 'CTRL_C_EVENT'):
                    process.send_signal(signal.CTRL_C_EVENT)
                else:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()

                active_processes[numero] = None
                logger.info("Proceso de aviso %d cancelado", numero)
                return jsonify({
                    'success': True,
                    'message': 'Generación del aviso {} cancelada'.format(
                        numero)
                }), 200

        return jsonify({
            'success': False,
            'error': 'Proceso no encontrado o ya finalizado'
        }), 404

    except OSError as e:
        logger.error("Error cancelando aviso %d: %s", numero, str(e))
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@avisos_bp.route('/api/mapas/aviso/<int:numero>', methods=['GET'])
def api_mapas_por_aviso(numero):
    """API para obtener lista de mapas de un aviso"""
    try:
        output_path = OUTPUT_DIR / 'aviso_{}'.format(numero)
        mapas = []

        if output_path.exists():
            for img_file in output_path.glob('*.*'):
                if img_file.suffix.lower() in ['.webp', '.png']:
                    mapas.append({
                        'nombre': img_file.stem,
                        'archivo': img_file.name,
                        'url': '/mapas/imagen/{}/{}'.format(
                            numero, img_file.name),
                        'ruta': str(img_file)
                    })

        return jsonify({
            'success': True,
            'aviso': numero,
            'mapas': mapas,
            'cantidad': len(mapas)
        }), 200

    except OSError as e:
        logger.error("Error obteniendo mapas de aviso %d: %s", numero,
                    str(e))
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@avisos_bp.route('/api/avisos/<int:numero>/info', methods=['GET'])
def api_info_aviso(numero):
    """API para obtener info del aviso (nivel, departamentos afectados)"""
    try:
        datos = None
        color = 'plomo'

        # 1) Intentar leer JSON local (tiene más campos como color)
        json_path = BASE_DIR / 'JSON' / 'aviso_{}.json'.format(numero)
        if json_path.exists():
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                    color = json_data.get('color', 'plomo')
                    datos = json_data
            except (ValueError, json.JSONDecodeError, OSError):
                pass

        # 2) Si no hay JSON, leer desde BD
        if not datos:
            try:
                conn = get_connection()
                cursor = conn.cursor(
                    cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute(
                    "SELECT numero_aviso, titulo, nivel, color "
                    "FROM avisos_completos WHERE numero_aviso = %s LIMIT 1",
                    (numero,)
                )
                result = cursor.fetchone()
                cursor.close()
                conn.close()
                if result:
                    color = result.get('color', 'plomo') or 'plomo'
                    datos = dict(result)
            except psycopg2.Error:
                pass

        if not datos:
            return jsonify({
                'success': False,
                'error': 'Aviso no encontrado'
            }), 404

        # 3) Departamentos siempre desde BD (aviso_zonas_afectadas)
        deptos = []
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT departamento FROM aviso_zonas_afectadas "
                "WHERE numero_aviso = %s AND departamento IS NOT NULL "
                "ORDER BY departamento",
                (numero,)
            )
            deptos = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
        except psycopg2.Error:
            pass

        output_path = OUTPUT_DIR / 'aviso_{}'.format(numero)
        mapas_creados = (output_path.exists() and
                         (any(output_path.glob('*.webp')) or
                          any(output_path.glob('*.png'))))

        return jsonify({
            'success': True,
            'numero': numero,
            'titulo': datos.get('titulo', ''),
            'nivel': datos.get('nivel', ''),
            'color': color,
            'departamentos': deptos,
            'mapas_creados': mapas_creados,
            'fecha_emision': str(datos.get('fecha_emision', ''))
        }), 200

    except OSError as e:
        logger.error("Error obteniendo info de aviso %d: %s", numero, str(e))
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@avisos_bp.route('/api/avisos/<int:numero>/departamentos',
                  methods=['GET'])
def api_departamentos_aviso(numero):
    """API para obtener departamentos afectados desde BD"""
    try:
        output_path = OUTPUT_DIR / 'aviso_{}'.format(numero)
        mapas_creados = (output_path.exists() and
                         (any(output_path.glob('*.webp')) or
                          any(output_path.glob('*.png'))))

        departamentos = []
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT departamento FROM aviso_zonas_afectadas "
                "WHERE numero_aviso = %s AND departamento IS NOT NULL "
                "ORDER BY departamento",
                (numero,)
            )
            departamentos = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
        except psycopg2.Error as db_err:
            logger.warning("BD no disponible para departamentos aviso %d: %s",
                           numero, str(db_err))

        return jsonify({
            'success': True,
            'departamentos': departamentos,
            'mapas_creados': mapas_creados
        }), 200

    except OSError as e:
        logger.error("Error obteniendo departamentos para aviso %d: %s",
                    numero, str(e))
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@avisos_bp.route('/api/avisos', methods=['GET'])
def api_avisos():
    """API para obtener lista de avisos desde BD y OUTPUT/"""
    try:
        avisos_dict = {}

        try:
            conn = get_connection()
            cursor = conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor)

            query = (
                "SELECT DISTINCT numero_aviso, titulo, nivel, color, "
                "fecha_emision FROM avisos_completos WHERE color IN "
                "('rojo', 'naranja') ORDER BY numero_aviso DESC"
            )
            cursor.execute(query)
            avisos_bd = cursor.fetchall()
            cursor.close()
            conn.close()

            for aviso in avisos_bd:
                numero = aviso['numero_aviso']
                json_path = BASE_DIR / 'JSON' / 'aviso_{}.json'.format(numero)
                output_path = OUTPUT_DIR / 'aviso_{}'.format(numero)
                tiene_json = json_path.exists()
                tiene_mapas = (output_path.exists() and
                               (any(output_path.glob('*.webp')) or
                                any(output_path.glob('*.png'))))
                tiene_shp = (BASE_DIR / 'SHP' / 'aviso_{}'.format(numero) / 'view_aviso.shp').exists()
                avisos_dict[numero] = {
                    'numero': numero,
                    'titulo': aviso['titulo'],
                    'nivel': aviso['nivel'],
                    'color': aviso.get('color', 'plomo'),
                    'fecha_emision': str(aviso.get('fecha_emision', '')),
                    'descargado': '\u2705' if tiene_json else '\u23f3',
                    'mapa_creado': '\u2705' if tiene_mapas else '\u23f3',
                    'tiene_shp': tiene_shp,
                    'fuente': 'bd'
                }
        except (psycopg2.Error, ImportError):
            pass

        if (BASE_DIR / 'JSON').exists():
            for json_file in sorted((BASE_DIR / 'JSON').glob('aviso_*.json'),
                                   reverse=True):
                try:
                    numero_str = json_file.stem.split('_')[1]
                    numero = int(numero_str)

                    if numero not in avisos_dict:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            datos = json.load(f)

                        color = datos.get('color', 'plomo')
                        if color.lower() not in ['rojo', 'naranja']:
                            continue

                        output_path = OUTPUT_DIR / 'aviso_{}'.format(numero)
                        mapas_creados = (output_path.exists() and
                                       (any(output_path.glob('*.webp')) or
                                        any(output_path.glob('*.png'))))

                        shp_path = BASE_DIR / 'SHP' / 'aviso_{}'.format(numero) / 'view_aviso.shp'
                        avisos_dict[numero] = {
                                'numero': numero,
                                'titulo': datos.get('titulo',
                                                  'Aviso {}'.format(numero)),
                                'nivel': datos.get('nivel', 'AMARILLO'),
                                'color': color,
                                'fecha_emision': datos.get('fecha_emision',
                                                          '2026-02-01'),
                                'descargado': '\u2705',
                                'mapa_creado': '\u2705' if mapas_creados else '\u23f3',
                                'tiene_shp': shp_path.exists(),
                                'fuente': 'json'
                            }
                except (ValueError, KeyError, json.JSONDecodeError,
                       OSError):
                    pass

        if OUTPUT_DIR.exists():
            for carpeta in OUTPUT_DIR.iterdir():
                if carpeta.is_dir() and carpeta.name.startswith('aviso_'):
                    try:
                        numero_str = carpeta.name.split('_')[1]
                        numero = int(numero_str)
                        if numero not in avisos_dict:
                            has_maps = (any(carpeta.glob('*.webp')) or
                                       any(carpeta.glob('*.png')))
                            shp_path = BASE_DIR / 'SHP' / 'aviso_{}'.format(numero) / 'view_aviso.shp'
                            avisos_dict[numero] = {
                                'numero': numero,
                                'titulo': 'Aviso {}'.format(numero),
                                'nivel': 'N/A',
                                'color': 'plomo',
                                'fecha_emision': '2026-02-01',
                                'descargado': '\u23f3',
                                'mapa_creado': '\u2705' if has_maps else '\u23f3',
                                'tiene_shp': shp_path.exists(),
                                'fuente': 'output'
                            }
                    except (ValueError, OSError):
                        pass

        avisos_sorted = sorted(avisos_dict.values(),
                       key=lambda x: x['numero'],
                       reverse=True)

        return jsonify({
            'success': True,
            'avisos': avisos_sorted
        }), 200

    except OSError as e:
        logger.error("Error obteniendo avisos: %s", str(e))
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@avisos_bp.route('/api/avisos/nuevos', methods=['GET'])
def api_avisos_nuevos():
    """API para obtener avisos nuevos en las últimas 24 horas"""
    try:
        conn = get_connection()
        cursor = conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor)

        hace_24_horas = datetime.now() - timedelta(hours=24)

        query = (
            "SELECT COUNT(DISTINCT numero_aviso) as total "
            "FROM avisos_completos WHERE color IN ('rojo', 'naranja') "
            "AND fecha_emision >= %s"
        )
        cursor.execute(query, (hace_24_horas,))
        resultado = cursor.fetchone()
        total_nuevos = resultado['total'] if resultado else 0

        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'total_nuevos': total_nuevos,
            'fecha_consulta': datetime.now().isoformat()
        })
    except psycopg2.OperationalError:
        logger.error("Error de conexión BD")
        return jsonify({
            'status': 'error',
            'message': ('No hay conexión a la base de datos. Intenta más '
                       'tarde.')
        }), 503
    except (psycopg2.Error, ImportError):
        logger.error("Error al obtener avisos nuevos")
        return jsonify({
            'status': 'error',
            'message': 'Error al consultar avisos nuevos'
        }), 500
