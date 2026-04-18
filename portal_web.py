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
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas as pdf_canvas
from src.database import ConexionBD
from src.generador_pdf import generar_pdf_cotizacion

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
        "\n⚠️  SEGURIDAD: Se está usando la SECRET_KEY por defecto.\n"
        "   Configura la variable de entorno FLASK_SECRET_KEY antes de ir a producción.\n"
        "   Genera una clave segura con: python -c \"import secrets; print(secrets.token_hex(32))\"",
        stacklevel=1
    )

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

# Crear tablas automáticamente al arrancar el servidor —
# operaciones idempotentes, seguras de ejecutar en cada inicio
bd.inicializar_tareas()
bd.inicializar_cotizaciones()


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
    """
    # Si no hay sesión activa, no hay notificaciones que mostrar
    if 'usuario' not in session:
        return {'total_notif': 0}

    total = bd.contar_tareas_pendientes(session['usuario'])
    return {'total_notif': total}


# =============================================================================
# DECORADOR DE SEGURIDAD
# =============================================================================

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
            flash('🔒 Acceso denegado. Por favor inicia sesión.', 'error')
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

        datos_usuario = bd.verificar_login(username, password)

        if datos_usuario:
            # Guardar datos del usuario en la cookie de sesión (cifrada)
            session['usuario'] = datos_usuario[0]
            session['rol'] = datos_usuario[1]
            flash(f'¡Bienvenido al sistema, {datos_usuario[0].capitalize()}!', 'exito')
            return redirect(url_for('inicio'))
        else:
            flash('❌ Usuario o contraseña incorrectos. Inténtalo de nuevo.', 'error')

    return render_template('login.html')


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
    inventario  = bd.obtener_productos()
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
    # Extraer solo el nombre de archivo para construir URLs en el template.
    # Se normalizan las barras antes de basename para manejar rutas Windows (\)
    # guardadas por la app de escritorio en sistemas Linux/Mac.
    fotos_por_sku = {
        sku: os.path.basename(ruta.replace('\\', '/'))
        for sku, ruta in bd.obtener_fotos_principales().items()
    }
    return render_template('catalogo.html', productos=inventario, fotos_por_sku=fotos_por_sku)


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
        flash(f'❌ Producto "{sku}" no encontrado en el catálogo.', 'error')
        return redirect(url_for('catalogo'))

    activos = bd.obtener_activos_por_sku(sku)

    # Agrupar activos por ángulo para los tabs de la galería
    galeria = {}
    for activo in activos:
        angulo = activo[3]
        if angulo not in galeria:
            galeria[angulo] = []
        # Normalizar separadores antes de basename para rutas Windows guardadas por el desktop app
        nombre_archivo = os.path.basename(activo[1].replace('\\', '/'))
        galeria[angulo].append({
            'id': activo[0],
            'ruta': activo[1],
            'tipo': activo[2],
            'nombre': nombre_archivo
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
        flash('⚠️ Cliente no encontrado.', 'error')
        return redirect(url_for('clientes'))

    tareas = bd.obtener_tareas_por_cliente(rif)

    # Las cotizaciones son visibles solo para Admin, ya que /cotizaciones
    # y sus rutas derivadas también son exclusivas de Admin.
    cotizaciones = []
    if session.get('rol') == 'Admin':
        cotizaciones = bd.obtener_cotizaciones_por_cliente(rif)

    return render_template(
        'cliente_detalle.html',
        cliente=cliente,
        tareas=tareas,
        cotizaciones=cotizaciones,
        es_admin=(session.get('rol') == 'Admin')
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
    if session.get('rol') != 'Admin':
        flash('⛔ Solo los administradores pueden editar clientes.', 'error')
        return redirect(url_for('cliente_detalle', rif=rif))

    nombre_empresa = request.form.get('nombre_empresa', '').strip()
    telefono       = request.form.get('telefono', '').strip()
    correo         = request.form.get('correo', '').strip()
    direccion      = request.form.get('direccion', '').strip()

    if not nombre_empresa:
        flash('⚠️ El nombre de la empresa es obligatorio.', 'error')
        return redirect(url_for('cliente_detalle', rif=rif))

    ok = bd.actualizar_cliente(rif, nombre_empresa, telefono, correo, direccion)
    if ok:
        flash('✅ Datos del cliente actualizados correctamente.', 'success')
    else:
        flash('🔴 Error al actualizar el cliente. Intenta de nuevo.', 'error')

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
    if session.get('rol') != 'Admin':
        flash('⛔ No tienes permisos para agregar productos.', 'error')
        return redirect(url_for('inicio'))

    if request.method == 'POST':
        sku = request.form['sku'].strip().upper()
        nombre = request.form['nombre'].strip()
        descripcion = request.form['descripcion'].strip()
        marca = request.form['marca'].strip()
        compatibilidad = request.form['compatibilidad'].strip()
        precio = request.form['precio']

        if bd.registrar_producto(sku, nombre, descripcion, marca, compatibilidad, precio):
            flash(f'✅ ¡Producto {sku} agregado exitosamente al inventario!', 'exito')
            return redirect(url_for('catalogo'))
        else:
            flash(f'❌ Error al registrar. El SKU "{sku}" ya podría existir. Verifique.', 'error')

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
    if session.get('rol') != 'Admin':
        flash('⛔ No tienes permisos para agregar clientes.', 'error')
        return redirect(url_for('inicio'))

    if request.method == 'POST':
        rif = request.form['rif'].strip()
        nombre_empresa = request.form['nombre_empresa'].strip()
        telefono = request.form['telefono'].strip()
        correo = request.form['correo'].strip()
        direccion = request.form['direccion'].strip()

        if bd.registrar_cliente(rif, nombre_empresa, telefono, correo, direccion):
            flash(f'✅ ¡Cliente "{nombre_empresa}" registrado exitosamente!', 'exito')
            return redirect(url_for('clientes'))
        else:
            flash('❌ Error al registrar. Verifique que el RIF no esté duplicado.', 'error')

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
    if session.get('rol') != 'Admin':
        flash('⛔ No tienes permisos para editar productos.', 'error')
        return redirect(url_for('inicio'))

    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        descripcion = request.form['descripcion'].strip()
        marca = request.form['marca'].strip()
        compatibilidad = request.form['compatibilidad'].strip()
        precio = request.form['precio']

        if bd.actualizar_producto(sku, nombre, descripcion, marca, compatibilidad, precio):
            flash(f'✅ Producto {sku} actualizado correctamente.', 'exito')
            return redirect(url_for('catalogo'))
        else:
            flash(f'❌ No se pudo actualizar el producto {sku}.', 'error')
    else:
        # GET: cargar datos actuales del producto para pre-llenar el formulario
        producto = bd.obtener_producto(sku)
        if not producto:
            flash(f'❌ El producto con SKU "{sku}" no fue encontrado.', 'error')
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
    if session.get('rol') != 'Admin':
        flash('⛔ No tienes permisos para eliminar productos.', 'error')
        return redirect(url_for('inicio'))

    if bd.eliminar_producto(sku):
        flash(f'🗑️ El producto {sku} fue eliminado del inventario.', 'exito')
    else:
        flash(f'❌ No se pudo eliminar el producto {sku}.', 'error')

    return redirect(url_for('catalogo'))


# =============================================================================
# MÓDULO DE TAREAS — Asignación y seguimiento de trabajo interno
# =============================================================================

@app.route('/tareas')
@login_requerido
def tareas():
    """
    Página de gestión de tareas del sistema.

    El supervisor (Admin) ve todas las tareas creadas con filtros de estado.
    Los demás usuarios ven únicamente sus tareas activas.
    """
    # Cargar datos según el rol del usuario que accede
    if session.get('rol') == 'Admin':
        # El supervisor ve el panorama completo de todas las tareas
        lista_tareas    = bd.obtener_todas_tareas()
        lista_clientes  = bd.obtener_clientes()
        lista_usuarios  = bd.obtener_usuarios()
    else:
        # El diseñador/editor solo ve sus propias tareas pendientes
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
    # Verificar que el usuario tenga permiso de crear tareas
    if session.get('rol') != 'Admin':
        flash('⛔ Solo los supervisores pueden asignar tareas.', 'error')
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
        flash('⚠️ Completa todos los campos obligatorios de la tarea.', 'error')
        return redirect(request.referrer or url_for('tareas'))

    # Guardar la tarea en la base de datos
    if bd.crear_tarea(cliente_rif, cliente_nombre, asignado_a,
                      tipo_tarea, descripcion, fecha_limite, creado_por):
        flash(f'✅ Tarea asignada a "{asignado_a}" correctamente.', 'exito')
    else:
        flash('❌ No se pudo crear la tarea. Intenta de nuevo.', 'error')

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
        flash('⚠️ Estado no válido.', 'error')
        return redirect(url_for('tareas'))

    if bd.actualizar_estado_tarea(tarea_id, nuevo_estado):
        flash(f'✅ Tarea #{tarea_id} marcada como "{nuevo_estado}".', 'exito')
    else:
        flash(f'❌ No se pudo actualizar la tarea #{tarea_id}.', 'error')

    return redirect(url_for('tareas'))


# =============================================================================
# GENERADOR DE PDF
# =============================================================================

@app.route('/generar_pdf', methods=['POST'])
@login_requerido
def generar_pdf():
    """
    Genera un archivo PDF en memoria con los productos seleccionados
    mediante checkboxes y lo envía al navegador como descarga.

    Recibe por POST:
        skus_seleccionados (list[str]): Lista de SKUs marcados en la tabla.

    Retorna:
        Archivo PDF adjunto para descargar, o redirige con error si no
        se seleccionó ningún producto.
    """
    skus_seleccionados = request.form.getlist('skus_seleccionados')

    # Validar que se haya seleccionado al menos un producto
    if not skus_seleccionados:
        flash('⚠️ Selecciona al menos un producto (casilla PDF) antes de generar.', 'error')
        return redirect(url_for('catalogo'))

    # --- Configuración visual del PDF ---
    MARGEN_IZQUIERDO = 50
    MARGEN_DERECHO = 550
    Y_INICIO = 730          # Coordenada Y donde empieza el primer producto
    ESPACIO_POR_PRODUCTO = 55  # Espacio vertical entre productos
    Y_MINIMO = 80           # Si queda menos espacio, se crea una nueva página

    # Colores en formato RGB (0.0 a 1.0)
    COLOR_VERDE_PRECIO = (0.15, 0.68, 0.37)
    COLOR_NEGRO = (0, 0, 0)

    # ---- Crear el archivo PDF en memoria (sin tocar el disco duro) ----
    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=letter)

    # ---- Dibujar encabezado ----
    c.setFont("Helvetica-Bold", 18)
    c.drawString(MARGEN_IZQUIERDO, 750, NOMBRE_EMPRESA_PDF)
    c.setFont("Helvetica", 10)
    c.drawString(MARGEN_IZQUIERDO, 735, SUBTITULO_PDF)
    c.line(MARGEN_IZQUIERDO, 725, MARGEN_DERECHO, 725)  # Línea separadora

    y = Y_INICIO

    # ---- Iterar sobre cada SKU seleccionado y dibujarlo en el PDF ----
    for sku in skus_seleccionados:
        # Obtener datos completos del producto desde la BD
        prod = bd.obtener_producto(sku)  # (sku, nombre, descripcion, marca, compatibilidad, precio)

        if not prod:
            continue  # Si el SKU no existe, saltar al siguiente

        # Línea 1: Nombre del producto y marca
        c.setFont("Helvetica-Bold", 12)
        c.setFillColorRGB(*COLOR_NEGRO)
        c.drawString(MARGEN_IZQUIERDO, y, f"{prod[1]}  —  Marca: {prod[3]}")

        # Línea 2: SKU y compatibilidades
        c.setFont("Helvetica", 11)
        c.drawString(MARGEN_IZQUIERDO, y - 17, f"SKU: {prod[0]}  |  Compatibilidad: {prod[4]}")

        # Precio (alineado a la derecha, en color verde)
        c.setFont("Helvetica-Bold", 13)
        c.setFillColorRGB(*COLOR_VERDE_PRECIO)
        c.drawString(420, y, f"${prod[5]}")

        c.setFillColorRGB(*COLOR_NEGRO)  # Restablecer color a negro

        y -= ESPACIO_POR_PRODUCTO  # Bajar el cursor para el siguiente producto

        # Si nos quedamos sin espacio vertical, crear nueva página
        if y < Y_MINIMO:
            c.showPage()
            y = Y_INICIO

    # ---- Guardar y enviar el PDF ----
    c.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=NOMBRE_ARCHIVO_PDF,
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
    if session.get('rol') != 'Admin':
        flash('⛔ Solo los administradores pueden acceder a las cotizaciones.', 'error')
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
    if session.get('rol') != 'Admin':
        flash('⛔ Solo los administradores pueden crear cotizaciones.', 'error')
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
            flash('⚠️ Debes seleccionar un cliente y agregar al menos un producto.', 'error')
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
                    flash('⚠️ Cantidad o precio inválido en uno de los productos.', 'error')
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
                    flash('✅ Cotización creada exitosamente.', 'success')
                    return redirect(url_for('cotizacion_detalle', cotizacion_id=cot_id))
                else:
                    flash('🔴 Error al guardar la cotización. Intenta de nuevo.', 'error')
            elif not error_validacion:
                flash('⚠️ Debes agregar al menos un producto válido.', 'error')

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
    if session.get('rol') != 'Admin':
        flash('⛔ Solo los administradores pueden ver cotizaciones.', 'error')
        return redirect(url_for('inicio'))
    datos = bd.obtener_cotizacion_con_items(cotizacion_id)
    if not datos:
        flash('⚠️ Cotización no encontrada.', 'error')
        return redirect(url_for('cotizaciones'))
    estados = ['Borrador', 'Enviada', 'Aceptada', 'Rechazada']
    # El template usa 'cab' e 'items' directamente (desestructurado del dict)
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
    if session.get('rol') != 'Admin':
        flash('⛔ Solo los administradores pueden cambiar el estado.', 'error')
        return redirect(url_for('cotizacion_detalle', cotizacion_id=cotizacion_id))

    nuevo_estado = request.form.get('nuevo_estado', '').strip()
    estados_validos = ['Borrador', 'Enviada', 'Aceptada', 'Rechazada']
    if nuevo_estado not in estados_validos:
        flash('⚠️ Estado no válido.', 'error')
    else:
        ok = bd.actualizar_estado_cotizacion(cotizacion_id, nuevo_estado)
        if ok:
            flash(f'✅ Estado actualizado a "{nuevo_estado}".', 'success')
        else:
            flash('🔴 Error al actualizar el estado.', 'error')

    return redirect(url_for('cotizacion_detalle', cotizacion_id=cotizacion_id))


@app.route('/cotizacion/<int:cotizacion_id>/pdf')
@login_requerido
def cotizacion_pdf(cotizacion_id):
    """
    Genera y descarga el PDF de la cotización indicada.
    Solo accesible para usuarios con rol 'Admin'.
    """
    if session.get('rol') != 'Admin':
        flash('⛔ Solo los administradores pueden descargar cotizaciones.', 'error')
        return redirect(url_for('inicio'))
    datos = bd.obtener_cotizacion_con_items(cotizacion_id)
    if not datos:
        flash('⚠️ Cotización no encontrada.', 'error')
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
# PUNTO DE ENTRADA (solo para desarrollo local)
# =============================================================================

if __name__ == '__main__':
    # NOTA: Para producción en Render, usar Gunicorn: gunicorn portal_web:app
    # El modo debug se activa solo si la variable FLASK_DEBUG=1 está definida,
    # para evitar su uso accidental en producción.
    modo_debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host='0.0.0.0', port=5000, debug=modo_debug)
