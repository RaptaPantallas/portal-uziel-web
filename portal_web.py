# =============================================================================
# portal_web.py
# Motor Web y Enrutador Principal — Portal B2B Importadora Uziel
# Proyecto: Dashboard de Marketing - Importadora Uziel C.A.
# Autor: Jesús | Framework: Flask 3.0.0 | Python 3.11.8
# =============================================================================
#
# DESCRIPCIÓN:
#   Este archivo es el servidor Flask. Recibe peticiones HTTP del navegador,
#   verifica permisos, consulta la base de datos y devuelve el HTML correcto.
#
#   Rutas disponibles:
#     GET/POST /login              — Pantalla de inicio de sesión
#     GET      /logout             — Cierra la sesión del usuario
#     GET      /                   — Dashboard principal con estadísticas y tareas
#     GET      /catalogo           — Módulo PIM: lista completa de productos con miniaturas
#     GET      /producto/<sku>     — Ficha de detalle del producto con galería DAM
#     GET      /activos/<archivo>  — Sirve archivos estáticos de almacen_activos/
#     GET      /clientes           — Módulo CRM: directorio de clientes
#     GET/POST /nuevo_producto     — Formulario para agregar producto (solo Admin)
#     GET/POST /nuevo_cliente      — Formulario para agregar cliente (solo Admin)
#     GET/POST /editar/<sku>       — Formulario para editar producto (solo Admin)
#     GET      /eliminar/<sku>     — Elimina un producto (solo Admin)
#     POST     /generar_pdf        — Genera y descarga un PDF con productos seleccionados
#     GET      /tareas             — Gestión de tareas (todas para Admin, propias para otros)
#     POST     /asignar_tarea      — Crea una nueva tarea (solo Admin)
#     POST     /actualizar_tarea/<id>   — Cambia el estado de una tarea
#     GET      /admin/usuarios           — Panel de gestión de usuarios (solo Admin)
#     POST     /admin/usuario/nuevo      — Crear un nuevo usuario (solo Admin)
#     POST     /admin/usuario/<u>/editar — Actualizar datos y permisos (solo Admin)
#     POST     /admin/usuario/<u>/pass   — Cambiar contraseña de usuario (solo Admin)
#     POST     /admin/usuario/<u>/borrar — Eliminar usuario (solo Admin)
#     GET      /cliente/<rif>           — Ficha completa del cliente con historial
#     POST     /cliente/<rif>/editar    — Actualizar datos de contacto del cliente
#     GET      /cotizaciones            — Lista todas las cotizaciones
#     GET/POST /cotizacion/nueva        — Crear nueva cotización (acepta ?cliente_rif=)
#     GET      /cotizacion/<id>         — Detalle de una cotización
#     POST     /cotizacion/<id>/estado  — Cambiar estado de cotización
#     GET      /cotizacion/<id>/pdf     — Descargar PDF de cotización
#
# DESPLIEGUE EN RENDER:
#   Build Command : pip install -r requirements.txt
#   Start Command : gunicorn portal_web:app
# =============================================================================

import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, send_from_directory
from functools import wraps
import io
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas as pdf_canvas
from src.database import ConexionBD
from src.generador_pdf import generar_pdf_cotizacion, generar_reporte_pdf

# =============================================================================
# ██████████████ CONFIGURACIÓN - EDITAR AQUÍ ██████████████
# =============================================================================

# Clave secreta para cifrar las cookies de sesión.
#
# CÓMO CONFIGURAR (elige una opción):
#
#   Opción A — Variable de entorno (RECOMENDADO para producción):
#     Windows CMD : set FLASK_SECRET_KEY=tu_clave_larga_aqui
#     Windows PS  : $env:FLASK_SECRET_KEY="tu_clave_larga_aqui"
#     Linux/Mac   : export FLASK_SECRET_KEY="tu_clave_larga_aqui"
#     Render.com  : Dashboard > Environment > Add Environment Variable
#
#   Genera una clave segura con:
#     python -c "import secrets; print(secrets.token_hex(32))"
#
#   Opción B — Reemplaza la cadena de abajo (solo para desarrollo local,
#              NUNCA subas esto a GitHub):
#
SECRET_KEY_DEFAULT = "cambia_esta_clave_antes_de_produccion"
SECRET_KEY = os.getenv("FLASK_SECRET_KEY", SECRET_KEY_DEFAULT)

# Advertencia si se usa la clave por defecto fuera de desarrollo local
if SECRET_KEY == SECRET_KEY_DEFAULT:
    import warnings
    warnings.warn(
        "\n  SEGURIDAD: Se está usando la SECRET_KEY por defecto.\n"
        "   Configura la variable de entorno FLASK_SECRET_KEY antes de ir a producción.\n"
        "   Genera una clave segura con: python -c \"import secrets; print(secrets.token_hex(32))\"",
        stacklevel=1
    )

# Clave API para que la aplicación de escritorio pueda subir imágenes.
# Debe ser la misma en main.py (variable API_KEY).
# En Render, configúrala como variable de entorno: DESKTOP_API_KEY
API_KEY_DESKTOP = os.getenv("DESKTOP_API_KEY", "uziel-desktop-sync-2026")

# Nombre de la empresa que aparece en el encabezado del PDF generado
NOMBRE_EMPRESA_PDF = "Catálogo de Productos - Importadora Uziel"
SUBTITULO_PDF = "Generado automáticamente desde el Portal B2B"

# Nombre del archivo PDF descargado por el usuario
NOMBRE_ARCHIVO_PDF = "Catalogo_Uziel.pdf"

# =============================================================================

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Instancia global del módulo de base de datos
bd = ConexionBD()


# =============================================================================
# UTILIDAD — Extraer ruta relativa a almacen_activos/
# =============================================================================

def _extraer_ruta_relativa(ruta_archivo):
    """
    Convierte cualquier formato de ruta (absoluta Windows/Linux o relativa)
    a una ruta relativa dentro de almacen_activos/.

    Ejemplos:
      'G:/.../almacen_activos/16572-0P030/1.jpg'  → '16572-0P030/1.jpg'
      '/opt/render/.../almacen_activos/SKU/2.jpg'  → 'SKU/2.jpg'
      '16572-0P030/1.jpg'                           → '16572-0P030/1.jpg'
      '1.jpg'                                       → '1.jpg'  (caso borde)
    """
    if not ruta_archivo:
        return None
    ruta = ruta_archivo.replace('\\', '/')
    # Si contiene 'almacen_activos/', extraer lo que sigue
    if 'almacen_activos/' in ruta:
        idx = ruta.index('almacen_activos/')
        return ruta[idx + len('almacen_activos/'):]
    # Si es ruta absoluta (Windows con letra de unidad o Linux con /)
    if ruta.startswith('/') or (len(ruta) > 2 and ruta[1] == ':'):
        return os.path.basename(ruta)
    # Ya es relativa
    return ruta

# Crear tablas automáticamente al arrancar el servidor —
# operaciones idempotentes, seguras de ejecutar en cada inicio
bd.inicializar_tareas()
bd.inicializar_cotizaciones()
bd.inicializar_permisos_usuarios()


# =============================================================================
# CONTEXTO GLOBAL — disponible en TODOS los templates automáticamente
# =============================================================================

@app.context_processor
def inyectar_notificaciones():
    """
    Inyecta el conteo de tareas pendientes del usuario logueado en todos
    los templates. Así cualquier página puede mostrar el badge de campana
    sin que cada ruta tenga que calcularlo por separado.

    La variable 'total_notif' queda disponible en todos los Jinja2 templates.
    Además inyecta 'puede_ver(modulo)' para controlar la visibilidad del sidebar.
    """
    # Si no hay sesión activa, no hay notificaciones que mostrar
    if 'usuario' not in session:
        return {'total_notif': 0, 'puede_ver': lambda m: False}

    total = bd.contar_tareas_pendientes(session['usuario'])

    def puede_ver(modulo: str) -> bool:
        """
        Devuelve True si el usuario actual puede acceder al módulo indicado.
        El superadmin siempre tiene acceso total.
        """
        _refrescar_si_es_antigua()
        if session.get('es_superadmin'):
            return True
        return modulo in session.get('permisos', [])

    def puede(modulo: str, accion: str = "ver") -> bool:
        """Permiso granular: True si el usuario tiene módulo:acción."""
        return _puede(modulo, accion)

    return {'total_notif': total, 'puede_ver': puede_ver, 'puede': puede}


@app.context_processor
def inject_base_template():
    """Inyecta la plantilla base adecuada dependiendo de si la petición es AJAX o estándar."""
    is_ajax = (request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
               request.args.get('ajax') == '1')
    return {
        'base_template': 'base_ajax.html' if is_ajax else 'base.html',
        'is_ajax': is_ajax
    }


# =============================================================================
# DECORADOR DE SEGURIDAD
# =============================================================================

def _refrescar_si_es_antigua():
    """Si la sesión no tiene es_superadmin (sesión previa al cambio), refresca permisos."""
    if 'es_superadmin' not in session and 'usuario' in session:
        u = session['usuario']
        session['es_superadmin'] = bd.es_superadmin(u)
        session['permisos'] = bd.obtener_permisos_usuario(u)
        session['permisos_dict'] = bd.obtener_permisos_desktop(u)

def _puede(modulo: str, accion: str = "ver") -> bool:
    """Verifica si el usuario en sesión tiene permiso módulo:acción.
    El superadmin siempre tiene acceso total."""
    _refrescar_si_es_antigua()
    if session.get('es_superadmin'):
        return True
    return session.get('permisos_dict', {}).get(modulo, {}).get(accion, False)


def login_requerido(f):
    """
    Decorador que protege rutas privadas.

    Si el usuario no ha iniciado sesión (no tiene 'usuario' en la sesión),
    lo redirige al login mostrando un mensaje de error. Se aplica con
    @login_requerido antes de cualquier función de ruta que requiera autenticación.
    """
    @wraps(f)
    def decorador(*args, **kwargs):
        if 'usuario' not in session:
            flash(' Acceso denegado. Por favor inicia sesión.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorador


# =============================================================================
# RUTAS PÚBLICAS — No requieren autenticación
# =============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Pantalla de inicio de sesión.

    GET:  Muestra el formulario de login.
    POST: Valida las credenciales. Si son correctas, guarda la sesión y
          redirige al Dashboard. Si son incorrectas, muestra un mensaje de error.
    """
    if request.method == 'POST':
        # Se mantiene el username tal como fue escrito; la comparación
        # insensible a mayúsculas se hace en la consulta SQL con LOWER()
        username = request.form['username'].strip()
        password = request.form['password']

        # Verificar si está bloqueado antes de intentar login
        if bd.usuario_esta_bloqueado(username):
            flash(' Cuenta bloqueada por demasiados intentos fallidos. Contacta al administrador.', 'error')
            return render_template('login.html')

        datos_usuario = bd.verificar_login(username, password)

        if datos_usuario:
            # Guardar datos del usuario en la cookie de sesión (cifrada)
            session['usuario'] = datos_usuario[0]
            session['rol'] = datos_usuario[1]
            # Cargar permisos del usuario en la sesión para el sidebar dinámico
            session['permisos'] = bd.obtener_permisos_usuario(datos_usuario[0])
            session['permisos_dict'] = bd.obtener_permisos_desktop(datos_usuario[0])
            session['es_superadmin'] = bd.es_superadmin(datos_usuario[0])
            flash(f'¡Bienvenido al sistema, {datos_usuario[0].capitalize()}!', 'exito')
            return redirect(url_for('inicio'))
        else:
            intentos = bd.obtener_intentos_fallidos(username)
            restantes = max(0, bd.MAX_INTENTOS - intentos)
            if restantes > 0:
                flash(f' Usuario o contraseña incorrectos. Te quedan {restantes} intento(s).', 'error')
            else:
                flash(' Cuenta bloqueada por demasiados intentos fallidos. Contacta al administrador.', 'error')

    return render_template('login.html')


# =============================================================================
# RECUPERACIÓN DE CONTRASEÑA
# =============================================================================

@app.route('/recuperar', methods=['GET', 'POST'])
def recuperar():
    """
    Paso 1: Solicitar recuperación de contraseña.
    GET:  Muestra formulario para ingresar usuario.
    POST: Busca el usuario, si tiene email, envía código de recuperación.
    """
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        if not username:
            flash(' Ingresa tu nombre de usuario.', 'error')
            return render_template('recuperar.html', paso=1)

        email = bd.obtener_email_usuario(username)
        if not email:
            flash(' No se encontró un email asociado a esa cuenta. Contacta al administrador.', 'error')
            return render_template('recuperar.html', paso=1)

        # Generar código de 6 dígitos
        import random
        codigo = str(random.randint(100000, 999999))

        if bd.guardar_codigo_recuperacion(username, codigo):
            exito, msg = bd.enviar_correo_recuperacion(email, codigo)
            if exito:
                flash(f' Código enviado a {email}. Revisa tu bandeja de entrada.', 'exito')
                return render_template('recuperar.html', paso=2, username=username)
            else:
                flash(f' {msg}', 'error')
        else:
            flash(' Error al generar el código. Intenta de nuevo.', 'error')

    return render_template('recuperar.html', paso=1)


@app.route('/recuperar/verificar', methods=['POST'])
def recuperar_verificar():
    """
    Paso 2: Verificar el código de recuperación.
    POST: Valida el código y permite cambiar la contraseña.
    """
    username = request.form.get('username', '').strip()
    codigo = request.form.get('codigo', '').strip()

    if not username or not codigo:
        flash(' Datos incompletos.', 'error')
        return redirect(url_for('recuperar'))

    if bd.verificar_codigo_recuperacion(username, codigo):
        return render_template('recuperar.html', paso=3, username=username, codigo=codigo)
    else:
        flash(' Código inválido o expirado. Solicita uno nuevo.', 'error')
        return redirect(url_for('recuperar'))


@app.route('/recuperar/cambiar', methods=['POST'])
def recuperar_cambiar():
    """
    Paso 3: Cambiar la contraseña con el código verificado.
    """
    username = request.form.get('username', '').strip()
    codigo = request.form.get('codigo', '').strip()
    password = request.form.get('password', '').strip()
    confirmar = request.form.get('confirmar', '').strip()

    if not username or not codigo or not password:
        flash(' Datos incompletos.', 'error')
        return redirect(url_for('recuperar'))

    if password != confirmar:
        flash(' Las contraseñas no coinciden.', 'error')
        return render_template('recuperar.html', paso=3, username=username, codigo=codigo)

    if len(password) < 4:
        flash(' La contraseña debe tener al menos 4 caracteres.', 'error')
        return render_template('recuperar.html', paso=3, username=username, codigo=codigo)

    if bd.cambiar_password_con_codigo(username, codigo, password):
        flash(' Contraseña actualizada correctamente. Ahora puedes iniciar sesión.', 'exito')
        return redirect(url_for('login'))
    else:
        flash(' Error al cambiar la contraseña. El código puede haber expirado.', 'error')
        return redirect(url_for('recuperar'))


# =============================================================================
# CONFIGURACIÓN DE CORREO SMTP (solo Admin)
# =============================================================================

@app.route('/admin/config_correo', methods=['GET', 'POST'])
@login_requerido
def admin_config_correo():
    """
    Página para configurar el servidor SMTP para envío de correos.
    Requiere permiso usuarios:gestionar.
    """
    if not _puede("usuarios", "gestionar"):
        flash(' No tienes permiso para configurar el correo.', 'error')
        return redirect(url_for('inicio'))

    if request.method == 'POST':
        servidor = request.form.get('servidor', '').strip()
        puerto = request.form.get('puerto', 587, type=int)
        usuario = request.form.get('usuario', '').strip()
        password = request.form.get('password', '').strip()
        usar_tls = request.form.get('usar_tls', 'true') == 'true'
        correo_origen = request.form.get('correo_origen', '').strip()
        nombre_origen = request.form.get('nombre_origen', 'Importadora Uziel').strip()

        if not servidor or not usuario or not correo_origen:
            flash(' Los campos servidor, usuario y correo origen son obligatorios.', 'error')
        else:
            ok = bd.guardar_config_correo(servidor, puerto, usuario, password, usar_tls, correo_origen, nombre_origen)
            if ok:
                flash(' Configuración de correo guardada correctamente.', 'success')
            else:
                flash(' Error al guardar la configuración.', 'error')

    config = bd.obtener_config_correo()
    return render_template('admin_config_correo.html', config=config)


# =============================================================================

@app.route('/logout')
def logout():
    """
    Cierra la sesión del usuario eliminando todos los datos de la cookie.
    Redirige siempre al login después de cerrar sesión.
    """
    session.clear()
    flash('Has cerrado sesión correctamente.', 'exito')
    return redirect(url_for('login'))


# =============================================================================
# RUTAS PROTEGIDAS — Requieren haber iniciado sesión (@login_requerido)
# =============================================================================

@app.route('/')
@login_requerido
def inicio():
    """
    Dashboard principal del portal.

    Muestra las tarjetas de estadísticas (total productos, total clientes,
    total tareas activas) y la tabla de los últimos productos registrados.
    También pasa al template:
      - Las tareas pendientes del usuario actual (para el modal de notificación)
      - La lista de clientes (para el formulario de asignación de tareas)
      - La lista de usuarios (para el dropdown de asignación)
    """
    # Datos de inventario y estadísticas
    inventario  = bd.obtener_productos()[:10]
    total_prod  = bd.contar_productos()
    total_cli   = bd.contar_clientes()

    # Datos para el módulo de tareas en el dashboard
    lista_clientes = bd.obtener_clientes()      # dropdown "seleccionar cliente"
    lista_usuarios = bd.obtener_usuarios()       # dropdown "asignar a"
    mis_tareas     = bd.obtener_tareas_asignadas(session['usuario'])  # notificaciones

    return render_template(
        'index.html',
        productos=inventario,
        total_prod=total_prod,
        total_cli=total_cli,
        lista_clientes=lista_clientes,
        lista_usuarios=lista_usuarios,
        mis_tareas=mis_tareas
    )


@app.route('/catalogo')
@login_requerido
def catalogo():
    """
    Módulo PIM — Vista completa del catálogo de productos.
    Permite seleccionar productos para generar un PDF y, si es Admin,
    editar o eliminar registros. Incluye la foto principal de cada producto
    para mostrar miniaturas en la tabla.
    """
    inventario = bd.obtener_productos()
    return render_template('catalogo.html', productos=inventario)


@app.route('/galeria')
@login_requerido
def galeria():
    """
    Galería visual de productos con fotos.
    Muestra todos los productos que tienen al menos una imagen vinculada
    en activos_digitales, con buscador inteligente por SKU o nombre.
    """
    query = request.args.get('q', '').strip()
    if query:
        resultados = bd.buscar_banco_completo(query, limite=200)
    else:
        resultados = bd.obtener_banco_completo()

    productos_galeria = []
    for r in resultados:
        # r = (sku, nombre, ruta_principal, total_fotos, id_activo)
        productos_galeria.append({
            'sku': r[0],
            'nombre': r[1],
            'ruta': r[2],
            'total_fotos': r[3],
            'id_activo': r[4] if len(r) > 4 else None
        })

    return render_template(
        'galeria.html',
        productos=productos_galeria,
        query=query,
        total=len(productos_galeria)
    )


@app.route('/api/galeria/buscar')
@login_requerido
def api_galeria_buscar():
    """API AJAX para búsqueda en galería — retorna JSON."""
    query = request.args.get('q', '').strip()
    if not query:
        return {'results': [], 'total': 0}
    resultados = bd.buscar_banco_completo(query, limite=50)
    items = []
    for r in resultados:
        items.append({
            'sku': r[0],
            'nombre': r[1],
            'total_fotos': r[3],
            'id_activo': r[4] if len(r) > 4 else None,
            'url': url_for('detalle_producto', sku=r[0])
        })
    return {'results': items, 'total': len(items)}


@app.route('/producto/<sku>')
@login_requerido
def detalle_producto(sku):
    """
    Ficha de detalle de un producto con galería de fotos por ángulo.

    Muestra todos los datos técnicos del producto y las fotografías
    vinculadas desde el módulo DAM, organizadas en tabs por tipo de ángulo
    (Frontal, Lateral, Detalle, En-contexto).

    Args:
        sku (str): Código SKU del producto a mostrar.
    """
    producto = bd.obtener_producto(sku)
    if not producto:
        flash(f' Producto "{sku}" no encontrado en el catálogo.', 'error')
        return redirect(url_for('catalogo'))

    activos = bd.obtener_activos_por_sku(sku)

    # Agrupar activos por ángulo para los tabs de la galería
    galeria = {}
    for activo in activos:
        angulo = activo[3]
        if angulo not in galeria:
            galeria[angulo] = []
        # Extraer ruta relativa a almacen_activos/ para servirla por el navegador
        ruta_relativa = _extraer_ruta_relativa(activo[1])
        galeria[angulo].append({
            'id': activo[0],
            'ruta': activo[1],
            'tipo': activo[2],
            'nombre': ruta_relativa or os.path.basename(activo[1].replace('\\', '/'))
        })

    total_fotos = sum(len(lista) for lista in galeria.values())

    return render_template(
        'producto_detalle.html',
        producto=producto,
        galeria=galeria,
        total_fotos=total_fotos
    )


@app.route('/activos/<path:nombre_archivo>')
@login_requerido
def servir_activo(nombre_archivo):
    """
    Sirve archivos estáticos desde la carpeta 'almacen_activos/'.

    Esta ruta permite que el portal web acceda a las fotografías copiadas
    por la app de escritorio DAM. Solo accesible para usuarios autenticados.

    Args:
        nombre_archivo (str): Nombre del archivo (con extensión) dentro de almacen_activos/.
    """
    carpeta_activos = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'almacen_activos')
    return send_from_directory(carpeta_activos, nombre_archivo)


@app.route('/subir_imagen/<sku>', methods=['POST'])
@login_requerido
def subir_imagen(sku):
    """
    Sube una imagen desde el navegador, la guarda en alta calidad como JPG
    en el filesystem y almacena una previsualización WebP comprimida en la BD.
    Solo accesible para usuarios con rol 'Admin'.
    """
    if not _puede("activos", "subir"):
        flash(' No tienes permisos para subir imágenes.', 'error')
        return redirect(url_for('detalle_producto', sku=sku))

    # Validar que el producto existe
    producto = bd.obtener_producto(sku)
    if not producto:
        flash(f' El producto con SKU "{sku}" no existe.', 'error')
        return redirect(url_for('catalogo'))

    if 'imagen' not in request.files:
        flash(' No se seleccionó ningún archivo.', 'error')
        return redirect(url_for('detalle_producto', sku=sku))

    archivo = request.files['imagen']
    if archivo.filename == '':
        flash(' No se seleccionó ningún archivo.', 'error')
        return redirect(url_for('detalle_producto', sku=sku))

    angulo = request.form.get('angulo', 'Principal').strip()

    # Crear carpeta del SKU
    carpeta_activos = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'almacen_activos')
    carpeta_sku = os.path.join(carpeta_activos, sku)
    os.makedirs(carpeta_sku, exist_ok=True)

    # Determinar el siguiente número secuencial
    existentes = [f for f in os.listdir(carpeta_sku) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
    numeros = []
    for f in existentes:
        base = os.path.splitext(f)[0]
        try:
            numeros.append(int(base))
        except ValueError:
            pass
    siguiente = max(numeros) + 1 if numeros else 1

    nombre_jpg = f"{siguiente}.jpg"
    ruta_jpg = os.path.join(carpeta_sku, nombre_jpg)

    try:
        # Procesar imagen con Pillow
        img = Image.open(archivo)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Guardar JPG alta calidad en filesystem (mismo formato que desktop)
        if img.width > 800 or img.height > 800:
            img.thumbnail((800, 800))
        img.save(ruta_jpg, "JPEG", quality=90, optimize=True)

        # Generar WebP de baja calidad para preview en la BD
        preview = img.copy()
        if preview.width > 300 or preview.height > 300:
            preview.thumbnail((300, 300))
        buf = io.BytesIO()
        preview.save(buf, "WEBP", quality=20, optimize=True)
        preview_binary = buf.getvalue()
        buf.close()

        img.close()

        # Guardar en BD con preview
        if bd.registrar_activo_con_preview(sku, ruta_jpg, preview_binary, "Imagen", angulo):
            flash(f' Imagen subida correctamente para SKU "{sku}".', 'exito')
        else:
            flash(f' La imagen se guardó en disco pero no se pudo registrar en la BD.', 'error')

    except Exception as e:
        flash(f' Error al procesar la imagen: {e}', 'error')

    return redirect(url_for('detalle_producto', sku=sku))


@app.route('/api/subir_imagen/<sku>', methods=['POST'])
def api_subir_imagen(sku):
    """
    Endpoint para que la aplicación de escritorio suba imágenes.
    Usa autenticación por API Key en lugar de cookies de sesión.
    El desktop ya registró el activo en BD; aquí solo se guarda el
    archivo y se actualiza el preview_webp, evitando duplicados.

    Cabecera requerida: X-API-Key: <clave>
    Body: form-data con campo 'imagen' (archivo)
    Campo opcional: ruta_relativa (ej: 'SKU/3.jpg')
    """
    api_key = request.headers.get('X-API-Key', '')
    if api_key != API_KEY_DESKTOP:
        return {"error": "API Key inválida"}, 401

    if 'imagen' not in request.files:
        return {"error": "No se envió ninguna imagen"}, 400

    archivo = request.files['imagen']
    if archivo.filename == '':
        return {"error": "Nombre de archivo vacío"}, 400

    angulo = request.form.get('angulo', 'Principal').strip()
    ruta_relativa = request.form.get('ruta_relativa', '').strip()

    carpeta_activos = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'almacen_activos')

    if ruta_relativa:
        # Usar la ruta exacta que envió el desktop (evita duplicados)
        nombre_jpg = os.path.basename(ruta_relativa)
        ruta_jpg = os.path.join(carpeta_activos, ruta_relativa)
        os.makedirs(os.path.dirname(ruta_jpg), exist_ok=True)
    else:
        # Fallback: calcular número secuencial (solo si no se envió ruta)
        carpeta_sku = os.path.join(carpeta_activos, sku)
        os.makedirs(carpeta_sku, exist_ok=True)
        existentes = [f for f in os.listdir(carpeta_sku) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
        numeros = []
        for f in existentes:
            base = os.path.splitext(f)[0]
            try:
                numeros.append(int(base))
            except ValueError:
                pass
        siguiente = max(numeros) + 1 if numeros else 1
        nombre_jpg = f"{siguiente}.jpg"
        ruta_jpg = os.path.join(carpeta_sku, nombre_jpg)
        ruta_relativa = os.path.join(sku, nombre_jpg)

    try:
        img = Image.open(archivo)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        if img.width > 800 or img.height > 800:
            img.thumbnail((800, 800))
        img.save(ruta_jpg, "JPEG", quality=90, optimize=True)

        preview = img.copy()
        if preview.width > 300 or preview.height > 300:
            preview.thumbnail((300, 300))
        buf = io.BytesIO()
        preview.save(buf, "WEBP", quality=20, optimize=True)
        preview_binary = buf.getvalue()
        buf.close()
        img.close()

        # Actualizar preview en el registro existente (no duplicar)
        actualizado = bd.actualizar_preview_por_ruta(ruta_relativa, preview_binary)
        if actualizado:
            return {
                "ok": True,
                "sku": sku,
                "archivo": nombre_jpg,
                "ruta": ruta_jpg,
                "accion": "preview_actualizado"
            }

        # Fallback: si no existía el registro, crearlo con ruta relativa
        if bd.registrar_activo_con_preview(sku, ruta_relativa, preview_binary, "Imagen", angulo):
            return {
                "ok": True,
                "sku": sku,
                "archivo": nombre_jpg,
                "ruta": ruta_jpg,
                "accion": "registro_creado"
            }
        else:
            return {"error": "No se pudo registrar en la BD (¿existe el SKU?)"}, 500
    except Exception as e:
        return {"error": str(e)}, 500


@app.route('/api/bulk_subir', methods=['POST'])
def api_bulk_subir():
    """
    Endpoint para subir múltiples imágenes desde la aplicación de escritorio.
    Recibe un archivo ZIP con la estructura: SKU/archivo.jpg
    Cabecera requerida: X-API-Key: <clave>
    """
    api_key = request.headers.get('X-API-Key', '')
    if api_key != API_KEY_DESKTOP:
        return {"error": "API Key inválida"}, 401

    import zipfile
    import tempfile

    if 'archivo' not in request.files:
        return {"error": "No se envió ningún archivo"}, 400
    archivo_zip = request.files['archivo']
    if archivo_zip.filename == '':
        return {"error": "Nombre de archivo vacío"}, 400

    carpeta_activos = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'almacen_activos')
    resultados = {"ok": 0, "errores": 0, "detalle": []}

    try:
        with zipfile.ZipFile(archivo_zip) as zf:
            for nombre in zf.namelist():
                # Esperamos: SKU/archivo.jpg
                nombre_normalizado = nombre.replace('\\', '/')
                partes = nombre_normalizado.split('/')
                if len(partes) < 2:
                    continue
                sku = partes[0]
                nombre_archivo = '/'.join(partes[1:])
                if not nombre_archivo or not nombre_archivo.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    continue

                carpeta_sku = os.path.join(carpeta_activos, sku)
                os.makedirs(carpeta_sku, exist_ok=True)

                # Determinar número secuencial
                existentes = [f for f in os.listdir(carpeta_sku) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
                numeros = []
                for f in existentes:
                    base = os.path.splitext(f)[0]
                    try:
                        numeros.append(int(base))
                    except ValueError:
                        pass
                siguiente = max(numeros) + 1 if numeros else 1
                nombre_jpg = f"{siguiente}.jpg"
                ruta_jpg = os.path.join(carpeta_sku, nombre_jpg)

                try:
                    data = zf.read(nombre)
                    img = Image.open(io.BytesIO(data))
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    if img.width > 800 or img.height > 800:
                        img.thumbnail((800, 800))
                    img.save(ruta_jpg, "JPEG", quality=90, optimize=True)

                    preview = img.copy()
                    if preview.width > 300 or preview.height > 300:
                        preview.thumbnail((300, 300))
                    buf = io.BytesIO()
                    preview.save(buf, "WEBP", quality=20, optimize=True)
                    preview_binary = buf.getvalue()
                    buf.close()
                    img.close()

                    if bd.registrar_activo_con_preview(sku, ruta_jpg, preview_binary, "Imagen", "Principal"):
                        resultados["ok"] += 1
                        resultados["detalle"].append({"sku": sku, "archivo": nombre_jpg, "estado": "ok"})
                    else:
                        resultados["errores"] += 1
                        resultados["detalle"].append({"sku": sku, "archivo": nombre_jpg, "estado": "error_bd"})
                except Exception as e:
                    resultados["errores"] += 1
                    resultados["detalle"].append({"sku": sku, "archivo": nombre_archivo, "estado": str(e)})
    except Exception as e:
        return {"error": f"Error al procesar ZIP: {e}"}, 500

    return {"ok": True, "resultados": resultados}


@app.route('/preview/<int:activo_id>')
@login_requerido
def servir_preview(activo_id):
    """
    Sirve la previsualización WebP (baja calidad) desde la base de datos.
    Si el activo no tiene preview en BD, redirige al JPG original del filesystem.
    """
    resultado = bd.obtener_preview_activo(activo_id)
    if resultado:
        preview_bytes, ruta_fallback = resultado
        if preview_bytes:
            return send_file(
                io.BytesIO(bytes(preview_bytes)),
                mimetype='image/webp'
            )
        # Fallback: extraer ruta relativa y redirigir al archivo original
        if ruta_fallback:
            rel_path = _extraer_ruta_relativa(ruta_fallback)
            if rel_path:
                return redirect(url_for('servir_activo', nombre_archivo=rel_path))

    # Si no hay nada, devolver un placeholder 1x1 transparente
    return send_file(io.BytesIO(b''), mimetype='image/png')


@app.route('/sincronizar_previews/<sku>', methods=['POST'])
@login_requerido
def sincronizar_previews(sku):
    """
    Escanea los archivos JPG en almacen_activos/<SKU>/ y genera los previews
    WebP en la BD para todos los activos que aún no tengan preview.
    Solo Admin.

    CORREGIDO: Resuelve la ruta relativa a almacen_activos/ para que funcione
    tanto con rutas absolutas (Windows/Linux) como con rutas relativas.
    """
    if not _puede("activos", "subir"):
        flash(' No tienes permisos para sincronizar.', 'error')
        return redirect(url_for('detalle_producto', sku=sku))

    activos_sin_preview = bd.obtener_activos_sin_preview(sku)
    if not activos_sin_preview:
        flash(f' Todos los activos de "{sku}" ya tienen preview.', 'info')
        return redirect(url_for('detalle_producto', sku=sku))

    carpeta_activos = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'almacen_activos')
    contador = 0
    omitidos = 0
    for activo_id, ruta_archivo in activos_sin_preview:
        # Extraer ruta relativa y resolver contra la carpeta real del servidor
        ruta_relativa = _extraer_ruta_relativa(ruta_archivo)
        if not ruta_relativa:
            print(f" [Sync] No se pudo extraer ruta relativa de: {ruta_archivo}")
            omitidos += 1
            continue
        ruta_real = os.path.join(carpeta_activos, ruta_relativa)
        if not os.path.exists(ruta_real):
            print(f" [Sync] Archivo no encontrado, se omitirá: {ruta_real}")
            omitidos += 1
            continue
        try:
            with Image.open(ruta_real) as img:
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                preview = img.copy()
                if preview.width > 300 or preview.height > 300:
                    preview.thumbnail((300, 300))
                buf = io.BytesIO()
                preview.save(buf, "WEBP", quality=20, optimize=True)
                preview_binary = buf.getvalue()
                buf.close()

                if bd.actualizar_preview_activo(activo_id, preview_binary):
                    contador += 1
        except Exception as e:
            print(f" [Sync] Error al procesar {ruta_real}: {e}")
            omitidos += 1

    if omitidos > 0:
        flash(f' Sincronización: {contador} preview(s) generado(s), {omitidos} omitido(s) (archivos no encontrados en el servidor).', 'exito')
    else:
        flash(f' Sincronización completada: {contador} preview(s) generado(s) para "{sku}".', 'exito')
    return redirect(url_for('detalle_producto', sku=sku))


@app.route('/clientes')
@login_requerido
def clientes():
    """
    Módulo CRM — Directorio completo de clientes activos.
    Muestra RIF, nombre de empresa, teléfono y correo de cada cliente.
    """
    lista_clientes = bd.obtener_clientes()
    return render_template('clientes.html', clientes=lista_clientes)


@app.route('/cliente/<path:rif>')
@login_requerido
def cliente_detalle(rif):
    """
    Ficha completa de un cliente: datos de contacto, tareas asociadas
    y cotizaciones generadas para él.

    Args:
        rif (str): RIF del cliente (puede contener guiones y barras).
    """
    cliente = bd.obtener_cliente(rif)
    if not cliente:
        flash(' Cliente no encontrado.', 'error')
        return redirect(url_for('clientes'))

    tareas = bd.obtener_tareas_por_cliente(rif)

    # Las cotizaciones se muestran según permiso
    cotizaciones = []
    if _puede("cotizaciones", "ver"):
        cotizaciones = bd.obtener_cotizaciones_por_cliente(rif)

    return render_template(
        'cliente_detalle.html',
        cliente=cliente,
        tareas=tareas,
        cotizaciones=cotizaciones,
        puede_cotizaciones=_puede("cotizaciones", "ver")
    )


@app.route('/cliente/<path:rif>/editar', methods=['POST'])
@login_requerido
def cliente_editar(rif):
    """
    Actualiza los datos de contacto de un cliente.
    Solo accesible para usuarios con rol 'Admin'.

    Args:
        rif (str): RIF del cliente a actualizar.
    """
    if not _puede("clientes", "editar"):
        flash(' No tienes permisos para editar clientes.', 'error')
        return redirect(url_for('cliente_detalle', rif=rif))

    nombre_empresa = request.form.get('nombre_empresa', '').strip()
    telefono       = request.form.get('telefono', '').strip()
    correo         = request.form.get('correo', '').strip()
    direccion      = request.form.get('direccion', '').strip()

    if not nombre_empresa:
        flash(' El nombre de la empresa es obligatorio.', 'error')
        return redirect(url_for('cliente_detalle', rif=rif))

    ok = bd.actualizar_cliente(rif, nombre_empresa, telefono, correo, direccion)
    if ok:
        flash(' Datos del cliente actualizados correctamente.', 'success')
    else:
        flash(' Error al actualizar el cliente. Intenta de nuevo.', 'error')

    return redirect(url_for('cliente_detalle', rif=rif))


@app.route('/nuevo_producto', methods=['GET', 'POST'])
@login_requerido
def nuevo_producto():
    """
    Formulario para registrar un nuevo producto en el inventario.
    Solo accesible para usuarios con rol 'Admin'.

    GET:  Muestra el formulario vacío.
    POST: Valida y guarda el nuevo producto. Si el SKU ya existe,
          muestra un error sin perder los datos del formulario.
    """
    if not _puede("productos", "agregar"):
        flash(' No tienes permisos para agregar productos.', 'error')
        return redirect(url_for('inicio'))

    if request.method == 'POST':
        sku = request.form['sku'].strip().upper()
        nombre = request.form['nombre'].strip()
        descripcion = request.form['descripcion'].strip()
        marca = request.form['marca'].strip()
        compatibilidad = request.form['compatibilidad'].strip()
        precio = request.form['precio']

        if bd.registrar_producto(sku, nombre, descripcion, marca, compatibilidad, precio):
            flash(f' ¡Producto {sku} agregado exitosamente al inventario!', 'exito')
            return redirect(url_for('catalogo'))
        else:
            flash(f' Error al registrar. El SKU "{sku}" ya podría existir. Verifique.', 'error')

    return render_template('nuevo_producto.html')


@app.route('/nuevo_cliente', methods=['GET', 'POST'])
@login_requerido
def nuevo_cliente():
    """
    Formulario para registrar un nuevo cliente en el CRM.
    Solo accesible para usuarios con rol 'Admin'.

    GET:  Muestra el formulario vacío.
    POST: Valida y guarda el nuevo cliente. Si el RIF ya existe, muestra un error.
    """
    if not _puede("clientes", "agregar"):
        flash(' No tienes permisos para agregar clientes.', 'error')
        return redirect(url_for('inicio'))

    if request.method == 'POST':
        rif = request.form['rif'].strip()
        nombre_empresa = request.form['nombre_empresa'].strip()
        telefono = request.form['telefono'].strip()
        correo = request.form['correo'].strip()
        direccion = request.form['direccion'].strip()

        if bd.registrar_cliente(rif, nombre_empresa, telefono, correo, direccion):
            flash(f' ¡Cliente "{nombre_empresa}" registrado exitosamente!', 'exito')
            return redirect(url_for('clientes'))
        else:
            flash(' Error al registrar. Verifique que el RIF no esté duplicado.', 'error')

    return render_template('nuevo_cliente.html')


@app.route('/editar/<sku>', methods=['GET', 'POST'])
@login_requerido
def editar_producto(sku):
    """
    Formulario para editar los datos de un producto existente.
    Solo accesible para usuarios con rol 'Admin'. El SKU no puede cambiarse.

    GET:  Carga el formulario con los datos actuales del producto.
    POST: Guarda los cambios y redirige al catálogo.
    """
    if not _puede("productos", "editar"):
        flash(' No tienes permisos para editar productos.', 'error')
        return redirect(url_for('inicio'))

    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        descripcion = request.form['descripcion'].strip()
        marca = request.form['marca'].strip()
        compatibilidad = request.form['compatibilidad'].strip()
        precio = request.form['precio']

        if bd.actualizar_producto(sku, nombre, descripcion, marca, compatibilidad, precio):
            flash(f' Producto {sku} actualizado correctamente.', 'exito')
            return redirect(url_for('catalogo'))
        else:
            flash(f' No se pudo actualizar el producto {sku}.', 'error')
    else:
        # GET: cargar datos actuales del producto para pre-llenar el formulario
        producto = bd.obtener_producto(sku)
        if not producto:
            flash(f' El producto con SKU "{sku}" no fue encontrado.', 'error')
            return redirect(url_for('catalogo'))
        return render_template('editar.html', producto=producto)


@app.route('/eliminar/<sku>')
@login_requerido
def eliminar_producto(sku):
    """
    Elimina permanentemente un producto del inventario.
    Solo accesible para usuarios con rol 'Admin'.
    La confirmación visual se maneja con un onclick en el HTML.
    """
    if not _puede("productos", "eliminar"):
        flash(' No tienes permisos para eliminar productos.', 'error')
        return redirect(url_for('inicio'))

    if bd.eliminar_producto(sku):
        flash(f' El producto {sku} fue eliminado del inventario.', 'exito')
    else:
        flash(f' No se pudo eliminar el producto {sku}.', 'error')

    return redirect(url_for('catalogo'))


# =============================================================================
# MÓDULO DE TAREAS — Asignación y seguimiento de trabajo interno
# =============================================================================

@app.route('/tareas')
@login_requerido
def tareas():
    """
    Página de gestión de tareas del sistema.

    Los usuarios con permiso tareas:gestionar ven todas las tareas.
    Los demás ven únicamente sus tareas activas.
    """
    # Cargar datos según permisos
    if _puede("tareas", "gestionar"):
        # Vista completa de todas las tareas
        lista_tareas    = bd.obtener_todas_tareas()
        lista_clientes  = bd.obtener_clientes()
        lista_usuarios  = bd.obtener_usuarios()
    else:
        # Solo sus tareas pendientes
        lista_tareas    = bd.obtener_tareas_asignadas(session['usuario'])
        lista_clientes  = []
        lista_usuarios  = []

    return render_template(
        'tareas.html',
        lista_tareas=lista_tareas,
        lista_clientes=lista_clientes,
        lista_usuarios=lista_usuarios
    )


@app.route('/asignar_tarea', methods=['POST'])
@login_requerido
def asignar_tarea():
    """
    Crea una nueva tarea a partir del formulario del dashboard o de la
    página de tareas. Solo accesible para usuarios con rol 'Admin'.

    Datos esperados del formulario (POST):
        cliente_rif    — RIF del cliente seleccionado en el dropdown
        cliente_nombre — Nombre de la empresa (campo oculto del dropdown)
        asignado_a     — Username del responsable
        tipo_tarea     — Categoría del trabajo
        descripcion    — Descripción libre
        fecha_limite   — Fecha tope (YYYY-MM-DD)
    """
    if not _puede("tareas", "gestionar"):
        flash(' No tienes permisos para asignar tareas.', 'error')
        return redirect(url_for('inicio'))

    # Leer y limpiar campos del formulario
    cliente_rif    = request.form.get('cliente_rif', '').strip()
    cliente_nombre = request.form.get('cliente_nombre', '').strip()
    asignado_a     = request.form.get('asignado_a', '').strip()
    tipo_tarea     = request.form.get('tipo_tarea', '').strip()
    descripcion    = request.form.get('descripcion', '').strip()
    fecha_limite   = request.form.get('fecha_limite', '').strip()
    creado_por     = session['usuario']

    # Validar que todos los campos obligatorios estén completos
    if not all([cliente_rif, asignado_a, tipo_tarea, fecha_limite]):
        flash(' Completa todos los campos obligatorios de la tarea.', 'error')
        return redirect(request.referrer or url_for('tareas'))

    # Guardar la tarea en la base de datos
    if bd.crear_tarea(cliente_rif, cliente_nombre, asignado_a,
                      tipo_tarea, descripcion, fecha_limite, creado_por):
        flash(f' Tarea asignada a "{asignado_a}" correctamente.', 'exito')
    else:
        flash(' No se pudo crear la tarea. Intenta de nuevo.', 'error')

    # Regresar a la página desde donde se envió el formulario
    return redirect(request.referrer or url_for('tareas'))


@app.route('/actualizar_tarea/<int:tarea_id>', methods=['POST'])
@login_requerido
def actualizar_tarea(tarea_id):
    """
    Actualiza el estado de una tarea (Pendiente → En Progreso → Completada).
    Cualquier usuario puede actualizar el estado de sus propias tareas.

    Args (URL):
        tarea_id (int): ID de la tarea a actualizar.

    Datos esperados del formulario (POST):
        nuevo_estado — 'En Progreso' o 'Completada'
    """
    nuevo_estado = request.form.get('nuevo_estado', '').strip()

    # Validar que el estado recibido sea uno de los permitidos
    estados_validos = {'Pendiente', 'En Progreso', 'Completada'}
    if nuevo_estado not in estados_validos:
        flash(' Estado no válido.', 'error')
        return redirect(url_for('tareas'))

    if bd.actualizar_estado_tarea(tarea_id, nuevo_estado):
        flash(f' Tarea #{tarea_id} marcada como "{nuevo_estado}".', 'exito')
    else:
        flash(f' No se pudo actualizar la tarea #{tarea_id}.', 'error')

    return redirect(url_for('tareas'))


# =============================================================================
# GENERADOR DE PDF
# =============================================================================

@app.route('/generar_pdf', methods=['POST'])
@login_requerido
def generar_pdf():
    skus_seleccionados = request.form.getlist('skus_seleccionados')

    if not skus_seleccionados:
        flash(' Selecciona al menos un producto (casilla PDF) antes de generar.', 'error')
        return redirect(url_for('catalogo'))

    # Colores corporativos (RGB 0.0-1.0) — idénticos al generador de escritorio
    AZUL_EMP   = (0.18, 0.27, 0.86)
    NEGRO      = (0.17, 0.22, 0.31)
    VERDE_PREC = (0.15, 0.68, 0.37)
    GRIS       = (0.55, 0.60, 0.68)
    LINEA      = (0.87, 0.88, 0.93)

    MARGEN_X = 50
    ANCHO_PAG, ALTO_PAG = letter
    ALTO_FILA = 72

    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=letter)
    from datetime import datetime

    def encabezado():
        c.setFillColorRGB(*AZUL_EMP)
        c.rect(0, ALTO_PAG - 80, ANCHO_PAG, 80, fill=True, stroke=False)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(MARGEN_X, ALTO_PAG - 48, "IMPORTADORA UZIEL C.A.")
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(0.8, 0.88, 1.0)
        c.drawString(MARGEN_X, ALTO_PAG - 65, "Catálogo de Productos — Listado General")
        c.drawString(MARGEN_X, ALTO_PAG - 75, f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    def pie():
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(*GRIS)
        c.drawString(MARGEN_X, 35, "Documento generado automáticamente por el Sistema de Información Uziel.")
        c.drawRightString(ANCHO_PAG - MARGEN_X, 35, datetime.now().strftime("Generado el %d/%m/%Y a las %H:%M"))

    def dibujar_fila(sku, nombre, marca, compatibilidad, precio, y, idx):
        # Fondo alternado
        c.setFillColorRGB(0.97, 0.98, 1.0) if idx % 2 == 0 else c.setFillColorRGB(1, 1, 1)
        c.rect(MARGEN_X, y - ALTO_FILA, ANCHO_PAG - 2 * MARGEN_X, ALTO_FILA, fill=True, stroke=False)

        labels = ["SKU:", "Producto:", "Marca:", "Compatibilidad:", "Precio:"]
        valores = [str(sku), str(nombre), str(marca), str(compatibilidad), f"$ {precio}" if precio is not None else "—"]
        ancho_label = 68
        y_linea = y - 16

        for i, (label, valor) in enumerate(zip(labels, valores)):
            c.setFont("Helvetica-Bold", 8)
            c.setFillColorRGB(*GRIS)
            c.drawString(MARGEN_X + 10, y_linea, label)
            c.setFont("Helvetica", 8.5)
            if i == 4:
                c.setFillColorRGB(*VERDE_PREC)
                c.setFont("Helvetica-Bold", 9)
            else:
                c.setFillColorRGB(*NEGRO)

            texto = str(valor)
            if i == 3 and c.stringWidth(texto, "Helvetica", 8.5) > (ANCHO_PAG - MARGEN_X - ancho_label - MARGEN_X - 10):
                while c.stringWidth(texto + "...", "Helvetica", 8.5) > (ANCHO_PAG - MARGEN_X - ancho_label - MARGEN_X - 10):
                    texto = texto[:-1]
                texto += "..."

            c.drawString(MARGEN_X + 10 + ancho_label, y_linea, texto)
            y_linea -= 12

        c.setStrokeColorRGB(*LINEA)
        c.setLineWidth(0.5)
        c.line(MARGEN_X, y - ALTO_FILA, ANCHO_PAG - MARGEN_X, y - ALTO_FILA)

    encabezado()
    y = ALTO_PAG - 115
    idx = 0

    for sku in skus_seleccionados:
        prod = bd.obtener_producto(sku)
        if not prod:
            continue
        if y < ALTO_FILA + 50:
            pie()
            c.showPage()
            encabezado()
            y = ALTO_PAG - 115
        dibujar_fila(prod.sku, prod.nombre, prod.marca, prod.compatibilidad, prod.precio, y, idx)
        y -= ALTO_FILA
        idx += 1

    pie()
    c.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=NOMBRE_ARCHIVO_PDF,
        mimetype='application/pdf'
    )


# =============================================================================
# MÓDULO DE REPORTES
# =============================================================================

@app.route('/reportes')
@login_requerido
def reportes():
    """Página de reportes con selector de fechas personalizado."""
    from datetime import datetime, timedelta

    hoy = datetime.now()

    # Leer fechas de query params o usar valores por defecto (mes actual)
    desde = request.args.get('desde', '')
    hasta = request.args.get('hasta', '')

    if desde and hasta:
        fecha_desde = desde
        fecha_hasta = hasta
    else:
        # Por defecto: mes actual
        inicio_mes = hoy.replace(day=1)
        if hoy.month == 12:
            fin_mes = hoy.replace(year=hoy.year + 1, month=1, day=1)
        else:
            fin_mes = hoy.replace(month=hoy.month + 1, day=1)
        fecha_desde = inicio_mes.strftime("%Y-%m-%d")
        fecha_hasta = fin_mes.strftime("%Y-%m-%d")

    # Datos del reporte
    datos = bd.obtener_datos_reporte(fecha_desde, fecha_hasta)
    datos_productos = bd.obtener_productos_por_fecha(fecha_desde, fecha_hasta, pagina=1, por_pagina=10)

    # Semana actual para referencia rapida
    diasem = hoy.weekday()
    domingo_pasado = hoy - timedelta(days=(diasem + 1) % 7)
    domingo_siguiente = domingo_pasado + timedelta(days=7)

    return render_template(
        'reportes.html',
        desde=fecha_desde,
        hasta=fecha_hasta,
        datos=datos,
        productos_pag=datos_productos,
        semana_inicio=domingo_pasado.strftime("%d/%m/%Y"),
        semana_fin=domingo_siguiente.strftime("%d/%m/%Y")
    )


@app.route('/api/reporte_productos')
@login_requerido
def api_reporte_productos():
    """API JSON para paginacion de productos en reporte."""
    from datetime import datetime, timedelta

    desde = request.args.get('desde', '')
    hasta = request.args.get('hasta', '')
    pagina = request.args.get('pagina', 1, type=int)

    if not desde or not hasta:
        return {"productos": [], "total": 0, "html": ""}

    datos = bd.obtener_productos_por_fecha(desde, hasta, pagina=pagina, por_pagina=10)

    html = ""
    for p in datos["productos"]:
        precio = f"${float(p[4]):,.2f}" if p[4] else "—"
        html += f"""<tr>
            <td><span class="sku-badge">{p[0]}</span></td>
            <td>{p[1]}</td>
            <td>{p[2]}</td>
            <td class="precio">{precio}</td>
        </tr>"""

    return {
        "productos": datos["productos"],
        "total": datos["total"],
        "pagina": datos["pagina"],
        "total_paginas": datos["total_paginas"],
        "html": html
    }


@app.route('/reporte_pdf/<tipo>')
@app.route('/reporte_pdf')
@login_requerido
def reporte_pdf(tipo=None):
    """Descarga el PDF de reporte semanal, mensual o personalizado."""
    from datetime import datetime, timedelta

    hoy = datetime.now()

    desde = request.args.get('desde', '')
    hasta = request.args.get('hasta', '')

    if desde and hasta:
        fecha_inicio = desde
        fecha_fin = hasta
        tipo_reporte = "Personalizado"
    elif tipo == "semanal":
        diasem = hoy.weekday()
        fecha_inicio = hoy - timedelta(days=(diasem + 1) % 7)
        fecha_fin = fecha_inicio + timedelta(days=7)
        tipo_reporte = "Semanal"
    elif tipo == "mensual":
        fecha_inicio = hoy.replace(day=1)
        if hoy.month == 12:
            fecha_fin = hoy.replace(year=hoy.year + 1, month=1, day=1)
        else:
            fecha_fin = hoy.replace(month=hoy.month + 1, day=1)
        tipo_reporte = "Mensual"
    else:
        flash("Especifica un tipo de reporte o fechas.", "error")
        return redirect(url_for('reportes'))

    fi = fecha_inicio if isinstance(fecha_inicio, str) else fecha_inicio.strftime("%Y-%m-%d")
    ff = fecha_fin if isinstance(fecha_fin, str) else fecha_fin.strftime("%Y-%m-%d")

    datos = bd.obtener_datos_reporte(fi, ff)
    datos["fecha_inicio"] = fi
    datos["fecha_fin"] = ff

    prod_data = bd.obtener_productos_por_fecha(fi, ff, pagina=1, por_pagina=500)
    productos_list = prod_data.get("productos", [])

    buffer = generar_reporte_pdf(datos, tipo_reporte, productos_list=productos_list)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Reporte_{tipo_reporte}_{hoy.strftime('%Y%m%d')}.pdf",
        mimetype='application/pdf'
    )


# =============================================================================
# MÓDULO COTIZACIONES
# =============================================================================

@app.route('/cotizaciones')
@login_requerido
def cotizaciones():
    """
    Lista todas las cotizaciones registradas.
    Permite filtrar por estado mediante el parámetro GET ?estado=...
    Solo accesible para usuarios con rol 'Admin'.
    """
    if not _puede("cotizaciones", "ver"):
        flash(' No tienes permisos para acceder a cotizaciones.', 'error')
        return redirect(url_for('inicio'))
    estado_filtro = request.args.get('estado', '')
    lista = bd.obtener_cotizaciones(estado_filtro if estado_filtro else None)
    estados = ['Borrador', 'Enviada', 'Aceptada', 'Rechazada']
    return render_template(
        'cotizaciones.html',
        cotizaciones=lista,
        estados=estados,
        estado_activo=estado_filtro
    )


@app.route('/cotizacion/nueva', methods=['GET', 'POST'])
@login_requerido
def cotizacion_nueva():
    """
    Crear una nueva cotización.

    GET:  Muestra el formulario con selector de cliente y buscador de productos.
    POST: Valida los datos, guarda la cotización y redirige al detalle.
    Solo permite rol Admin.
    """
    if not _puede("cotizaciones", "crear"):
        flash(' No tienes permisos para crear cotizaciones.', 'error')
        return redirect(url_for('cotizaciones'))

    if request.method == 'POST':
        cliente_rif    = request.form.get('cliente_rif', '').strip()
        cliente_nombre = request.form.get('cliente_nombre', '').strip()
        notas          = request.form.get('notas', '').strip()

        # Recopilar ítems del formulario (arrays paralelos)
        skus       = request.form.getlist('sku[]')
        nombres    = request.form.getlist('nombre[]')
        cantidades = request.form.getlist('cantidad[]')
        precios    = request.form.getlist('precio_unitario[]')

        if not cliente_rif or not cliente_nombre or not skus:
            flash(' Debes seleccionar un cliente y agregar al menos un producto.', 'error')
        else:
            # Parseo completo primero — si algo falla, no se guarda nada
            items = []
            error_validacion = False
            for i, sku in enumerate(skus):
                if not sku:
                    continue
                try:
                    cant  = int(cantidades[i])
                    prec  = float(precios[i])
                    if cant <= 0 or prec < 0:
                        raise ValueError("Valores fuera de rango")
                except (ValueError, IndexError):
                    flash(' Cantidad o precio inválido en uno de los productos.', 'error')
                    error_validacion = True
                    break
                items.append({
                    'sku': sku,
                    'nombre': nombres[i] if i < len(nombres) else sku,
                    'cantidad': cant,
                    'precio_unitario': prec
                })

            # Solo persistir si NO hubo error y hay al menos un ítem válido
            if not error_validacion and items:
                cot_id = bd.crear_cotizacion(
                    cliente_rif, cliente_nombre,
                    session['usuario'], items, notas
                )
                if cot_id:
                    flash(' Cotización creada exitosamente.', 'success')
                    return redirect(url_for('cotizacion_detalle', cotizacion_id=cot_id))
                else:
                    flash(' Error al guardar la cotización. Intenta de nuevo.', 'error')
            elif not error_validacion:
                flash(' Debes agregar al menos un producto válido.', 'error')

    # GET — cargar clientes y productos para los selectores.
    # Si viene ?cliente_rif=<rif>, pre-seleccionar ese cliente.
    cliente_preseleccionado = request.args.get('cliente_rif', '')
    clientes_lista  = bd.obtener_clientes()
    productos_lista = bd.obtener_productos()
    return render_template(
        'cotizacion_nueva.html',
        clientes=clientes_lista,
        productos=productos_lista,
        cliente_preseleccionado=cliente_preseleccionado
    )


@app.route('/cotizacion/<int:cotizacion_id>')
@login_requerido
def cotizacion_detalle(cotizacion_id):
    """
    Muestra la cotización completa con todos sus ítems, estado y opciones de acción.
    Solo accesible para usuarios con rol 'Admin'.
    """
    if not _puede("cotizaciones", "ver"):
        flash(' No tienes permisos para ver cotizaciones.', 'error')
        return redirect(url_for('inicio'))
    datos = bd.obtener_cotizacion_con_items(cotizacion_id)
    if not datos:
        flash(' Cotización no encontrada.', 'error')
        return redirect(url_for('cotizaciones'))
    estados = ['Borrador', 'Enviada', 'Aceptada', 'Rechazada']
    return render_template(
        'cotizacion_detalle.html',
        cab=datos['cabecera'],
        items=datos['items'],
        estados=estados
    )


@app.route('/cotizacion/<int:cotizacion_id>/estado', methods=['POST'])
@login_requerido
def cotizacion_estado(cotizacion_id):
    """
    Cambia el estado de una cotización (solo Admin).
    POST param: nuevo_estado
    """
    if not _puede("cotizaciones", "crear"):
        flash(' No tienes permisos para cambiar el estado.', 'error')
        return redirect(url_for('cotizacion_detalle', cotizacion_id=cotizacion_id))

    nuevo_estado = request.form.get('nuevo_estado', '').strip()
    estados_validos = ['Borrador', 'Enviada', 'Aceptada', 'Rechazada']
    if nuevo_estado not in estados_validos:
        flash(' Estado no válido.', 'error')
    else:
        ok = bd.actualizar_estado_cotizacion(cotizacion_id, nuevo_estado)
        if ok:
            flash(f' Estado actualizado a "{nuevo_estado}".', 'success')
        else:
            flash(' Error al actualizar el estado.', 'error')

    return redirect(url_for('cotizacion_detalle', cotizacion_id=cotizacion_id))


@app.route('/cotizacion/<int:cotizacion_id>/pdf')
@login_requerido
def cotizacion_pdf(cotizacion_id):
    """
    Genera y descarga el PDF de la cotización indicada.
    Solo accesible para usuarios con rol 'Admin'.
    """
    if not _puede("cotizaciones", "ver"):
        flash(' No tienes permisos para descargar cotizaciones.', 'error')
        return redirect(url_for('inicio'))
    datos = bd.obtener_cotizacion_con_items(cotizacion_id)
    if not datos:
        flash(' Cotización no encontrada.', 'error')
        return redirect(url_for('cotizaciones'))

    buffer = generar_pdf_cotizacion(datos)
    numero = datos['cabecera'][1]   # numero  (columna 1)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Cotizacion_{numero}.pdf",
        mimetype='application/pdf'
    )


# =============================================================================
# MÓDULO: GESTIÓN DE USUARIOS (solo Admin)
# =============================================================================

@app.route('/admin/usuarios')
@login_requerido
def admin_usuarios():
    """
    Panel de administración de usuarios.
    Muestra la lista completa de usuarios con sus roles y permisos.
    Requiere permiso usuarios:gestionar.
    """
    if not _puede("usuarios", "gestionar"):
        flash(' No tienes permiso para gestionar usuarios.', 'error')
        return redirect(url_for('inicio'))

    usuarios = bd.obtener_todos_usuarios()
    return render_template('admin_usuarios.html', usuarios=usuarios, modulos_acciones=bd.MODULOS_ACCIONES)


@app.route('/admin/usuario/nuevo', methods=['POST'])
@login_requerido
def admin_usuario_nuevo():
    """
    Crea un nuevo usuario en el sistema.
    Requiere permiso usuarios:gestionar.
    """
    if not _puede("usuarios", "gestionar"):
        flash(' No tienes permiso para crear usuarios.', 'error')
        return redirect(url_for('inicio'))

    username   = request.form.get('username', '').strip()
    password   = request.form.get('password', '').strip()
    rol        = request.form.get('rol', 'Empleado').strip()
    email      = request.form.get('email', '').strip()
    permisos   = request.form.get('permisos', '').strip()
    if not permisos:
        permisos = ','.join(request.form.getlist('permisos'))

    if not username or not password:
        flash(' El usuario y la contraseña son obligatorios.', 'error')
        return redirect(url_for('admin_usuarios'))

    ok = bd.crear_usuario(username, password, rol, permisos, email)
    if ok:
        flash(f' Usuario "{username}" creado correctamente.', 'success')
    else:
        flash(f' No se pudo crear el usuario "{username}". '
              'Es posible que ya exista.', 'error')

    return redirect(url_for('admin_usuarios'))


@app.route('/admin/usuario/<username>/editar', methods=['POST'])
@login_requerido
def admin_usuario_editar(username):
    """
    Actualiza nombre de usuario, rol, permisos y email.
    Requiere permiso usuarios:gestionar.
    """
    if not _puede("usuarios", "gestionar"):
        flash(' No tienes permiso para editar usuarios.', 'error')
        return redirect(url_for('inicio'))

    nuevo_username = request.form.get('nuevo_username', '').strip()
    nuevo_rol      = request.form.get('rol', 'Empleado').strip()
    email          = request.form.get('email', '').strip()
    permisos       = request.form.get('permisos', '').strip()
    if not permisos:
        permisos = ','.join(request.form.getlist('permisos'))

    if not nuevo_username:
        flash(' El nombre de usuario no puede quedar vacío.', 'error')
        return redirect(url_for('admin_usuarios'))

    ok = bd.actualizar_usuario(username, nuevo_username, nuevo_rol, permisos, email)
    if ok:
        flash(f' Usuario "{username}" actualizado correctamente.', 'success')
    else:
        flash(f' No se pudo actualizar el usuario "{username}".', 'error')

    return redirect(url_for('admin_usuarios'))


@app.route('/admin/usuario/<username>/desbloquear', methods=['POST'])
@login_requerido
def admin_usuario_desbloquear(username):
    """
    Desbloquea un usuario bloqueado por intentos fallidos.
    Solo superadmin puede usar esta ruta.
    """
    if not session.get('es_superadmin'):
        flash(' Solo el superadmin puede desbloquear usuarios.', 'error')
        return redirect(url_for('inicio'))

    ok = bd.desbloquear_usuario(username)
    if ok:
        flash(f' Usuario "{username}" desbloqueado correctamente.', 'success')
    else:
        flash(f' No se pudo desbloquear "{username}".', 'error')

    return redirect(url_for('admin_usuarios'))


@app.route('/admin/usuario/<username>/pass', methods=['POST'])
@login_requerido
def admin_usuario_pass(username):
    """
    Cambia la contraseña de un usuario.
    Requiere permiso usuarios:gestionar.
    """
    if not _puede("usuarios", "gestionar"):
        flash(' No tienes permiso para cambiar contraseñas.', 'error')
        return redirect(url_for('inicio'))

    nueva_pass   = request.form.get('nueva_password', '').strip()
    confirmar    = request.form.get('confirmar_password', '').strip()

    if not nueva_pass or not confirmar:
        flash(' Ambos campos de contraseña son obligatorios.', 'error')
        return redirect(url_for('admin_usuarios'))

    if nueva_pass != confirmar:
        flash(' Las contraseñas no coinciden.', 'error')
        return redirect(url_for('admin_usuarios'))

    ok = bd.actualizar_password_usuario(username, nueva_pass)
    if ok:
        flash(f' Contraseña de "{username}" actualizada.', 'success')
    else:
        flash(f' No se pudo cambiar la contraseña de "{username}".', 'error')

    return redirect(url_for('admin_usuarios'))


@app.route('/admin/usuario/<username>/borrar', methods=['POST'])
@login_requerido
def admin_usuario_borrar(username):
    """
    Elimina un usuario del sistema.
    Requiere permiso usuarios:gestionar. No permite eliminar al último superadmin.
    """
    if not _puede("usuarios", "gestionar"):
        flash(' No tienes permiso para eliminar usuarios.', 'error')
        return redirect(url_for('inicio'))

    ok = bd.eliminar_usuario(username)
    if ok:
        flash(f' Usuario "{username}" eliminado.', 'success')
    else:
        flash(f' No se pudo eliminar "{username}". '
              'Asegúrate de que no sea el único administrador.', 'error')

    return redirect(url_for('admin_usuarios'))


# =============================================================================
# DIAGNÓSTICO — Ver datos crudos desde el navegador
# =============================================================================

@app.route('/diagnostico')
@login_requerido
def diagnostico():
    """Muestra los datos crudos de los primeros 10 productos para depuración."""
    if not _puede("usuarios", "gestionar"):
        flash(' Solo administradores.', 'error')
        return redirect(url_for('inicio'))
    from src.database import ConexionBD as BD
    bd_local = BD()
    prods = bd_local.obtener_productos()
    html = '<h2>Diagnostico de datos (primeros 10 productos)</h2>'
    html += '<table border="1" cellpadding="6" style="border-collapse:collapse;font-family:monospace;font-size:13px;">'
    html += '<tr><th>#</th><th>sku [0]</th><th>nombre [1]</th><th>desc [2]</th><th>MARCA [3]</th><th>compat [4]</th><th>PRECIO [5]</th><th>cat [6]</th><th>exist [7]</th></tr>'
    for i, p in enumerate(prods[:10]):
        html += f'<tr><td>{i+1}</td>'
        for idx in range(min(8, len(p))):
            val = p[idx] if idx < len(p) else '—'
            clase = ' style="background:#fff3cd;"' if idx in (3, 5) else ''
            html += f'<td{clase}>{repr(val)}</td>'
        html += '</tr>'
    html += '</table>'
    html += f'<p>Total productos en BD: {len(prods)}</p>'
    html += '<p style="color:#666;">Las columnas MARCA [3] y PRECIO [5] estan resaltadas.</p>'
    return html


# =============================================================================
# PUNTO DE ENTRADA (solo para desarrollo local)
# =============================================================================

if __name__ == '__main__':
    # NOTA: Para producción en Render, usar Gunicorn: gunicorn portal_web:app
    # El modo debug se activa solo si la variable FLASK_DEBUG=1 está definida,
    # para evitar su uso accidental en producción.
    modo_debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host='0.0.0.0', port=5000, debug=modo_debug)
