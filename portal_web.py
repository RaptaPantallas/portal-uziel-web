from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from functools import wraps
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from src.database import ConexionBD

app = Flask(__name__)
app.secret_key = 'llave_secreta_uziel_2026'

bd = ConexionBD()

# --- EL CANDADO DE SEGURIDAD ---
def login_requerido(f):
    @wraps(f)
    def decorador(*args, **kwargs):
        if 'usuario' not in session:
            flash('🔒 Acceso denegado. Por favor inicia sesión.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorador

# --- RUTAS DE ACCESO ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].lower() # Convertimos a minúscula por si acaso
        password = request.form['password']
        
        datos_usuario = bd.verificar_login(username, password)
        
        if datos_usuario:
            # Guardamos su sesión de forma segura
            session['usuario'] = datos_usuario[0]
            session['rol'] = datos_usuario[1]
            flash(f'¡Bienvenido al sistema, {datos_usuario[0].capitalize()}!', 'exito')
            return redirect(url_for('inicio'))
        else:
            flash('❌ Usuario o contraseña incorrectos.', 'error')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear() # Borramos la sesión
    flash('Has cerrado sesión correctamente.', 'exito')
    return redirect(url_for('login'))

# --- RUTAS PROTEGIDAS (AQUÍ PONEMOS EL CANDADO) ---
@app.route('/')
@login_requerido
def inicio():
    # Obtenemos toda la data para el Dashboard
    inventario = bd.obtener_productos()
    clientes = bd.obtener_clientes()
    total_prod = bd.contar_productos()
    total_cli = bd.contar_clientes()
    
    return render_template('index.html', 
                           productos=inventario, 
                           clientes=clientes,
                           total_prod=total_prod, 
                           total_cli=total_cli)

@app.route('/eliminar/<sku>')
@login_requerido
def eliminar_producto(sku):
    # Solo los Admin pueden borrar
    if session.get('rol') != 'Admin':
        flash('No tienes permisos para borrar productos.', 'error')
        return redirect(url_for('inicio'))
        
    bd.eliminar_producto(sku)
    flash(f'El producto {sku} fue eliminado.', 'error')
    return redirect(url_for('inicio'))

@app.route('/editar/<sku>', methods=['GET', 'POST'])
@login_requerido
def editar_producto(sku):
    # Solo los Admin pueden editar
    if session.get('rol') != 'Admin':
        flash('No tienes permisos para editar productos.', 'error')
        return redirect(url_for('inicio'))

    if request.method == 'POST':
        nombre = request.form['nombre']
        descripcion = request.form['descripcion']
        marca = request.form['marca']
        compatibilidad = request.form['compatibilidad']
        precio = request.form['precio']
        
        bd.actualizar_producto(sku, nombre, descripcion, marca, compatibilidad, precio)
        flash(f'Producto {sku} actualizado correctamente.', 'exito')
        return redirect(url_for('inicio'))
    else:
        producto = bd.obtener_producto(sku)
        return render_template('editar.html', producto=producto)
@app.route('/nuevo_producto', methods=['GET', 'POST'])
@login_requerido
def nuevo_producto():
    # Seguridad: Solo el Admin puede entrar aquí
    if session.get('rol') != 'Admin':
        flash('No tienes permisos para agregar productos.', 'error')
        return redirect(url_for('inicio'))

    if request.method == 'POST':
        sku = request.form['sku']
        nombre = request.form['nombre']
        descripcion = request.form['descripcion']
        marca = request.form['marca']
        compatibilidad = request.form['compatibilidad']
        precio = request.form['precio']
        
        # Usamos tu función registrar_producto
        if bd.registrar_producto(sku, nombre, descripcion, marca, compatibilidad, precio):
            flash(f'¡Producto {sku} agregado exitosamente!', 'exito')
            return redirect(url_for('inicio'))
        else:
            flash(f'Error al registrar. Es posible que el SKU {sku} ya exista.', 'error')
            
    return render_template('nuevo_producto.html')

@app.route('/nuevo_cliente', methods=['GET', 'POST'])
@login_requerido
def nuevo_cliente():
    if session.get('rol') != 'Admin':
        flash('No tienes permisos para agregar clientes.', 'error')
        return redirect(url_for('inicio'))

    if request.method == 'POST':
        rif = request.form['rif']
        nombre_empresa = request.form['nombre_empresa']
        telefono = request.form['telefono']
        correo = request.form['correo']
        direccion = request.form['direccion']
        
        if bd.registrar_cliente(rif, nombre_empresa, telefono, correo, direccion):
            flash(f'¡Cliente {nombre_empresa} registrado!', 'exito')
            return redirect(url_for('inicio'))
        else:
            flash(f'Error al registrar el cliente. Verifique los datos.', 'error')
            
    return render_template('nuevo_cliente.html')
@app.route('/generar_pdf', methods=['POST'])
@login_requerido
def generar_pdf():
    # Recibimos la lista de SKUs que el usuario marcó con la casilla
    skus_seleccionados = request.form.getlist('skus_seleccionados')
    
    if not skus_seleccionados:
        flash('⚠️ Selecciona al menos un producto marcando la casilla para generar el PDF.', 'error')
        return redirect(url_for('inicio'))

    # Creamos un archivo PDF "virtual" en la memoria del servidor
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    
    # Dibujamos el encabezado
    y = 730
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, 750, "Catálogo de Productos - Importadora Uziel")
    c.setFont("Helvetica", 10)
    c.drawString(50, 735, "Generado automáticamente desde el Dashboard B2B")
    
    c.line(50, 720, 550, 720) # Línea separadora
    y = 690

    # Iteramos sobre los SKUs seleccionados para dibujarlos en el PDF
    for sku in skus_seleccionados:
        prod = bd.obtener_producto(sku) # (sku, nombre, descripcion, marca, compatibilidad, precio)
        if prod:
            c.setFont("Helvetica-Bold", 12)
            c.drawString(50, y, f"{prod[1]} (Marca: {prod[3]})")
            c.setFont("Helvetica", 11)
            c.drawString(50, y - 15, f"SKU: {prod[0]} | Compatibilidad: {prod[4]}")
            
            c.setFont("Helvetica-Bold", 12)
            c.setFillColorRGB(0.15, 0.68, 0.37) # Color verde para el precio
            c.drawString(450, y, f"Precio: ${prod[5]}")
            c.setFillColorRGB(0, 0, 0) # Volvemos a negro
            
            y -= 50 # Bajamos el cursor para el siguiente producto
            
            # Si se acaba la página, creamos una nueva
            if y < 50:
                c.showPage()
                y = 730

    c.save()
    buffer.seek(0)
    
    # Enviamos el archivo virtual al navegador para que se descargue
    return send_file(buffer, as_attachment=True, download_name="Catalogo_Uziel.pdf", mimetype='application/pdf')
@app.route('/catalogo')
@login_requerido
def catalogo():
    # Traemos todos los productos para la vista dedicada del PIM
    inventario = bd.obtener_productos()
    return render_template('catalogo.html', productos=inventario)

@app.route('/clientes')
@login_requerido
def clientes():
    # Traemos todos los clientes para la vista dedicada del CRM
    lista_clientes = bd.obtener_clientes()
    return render_template('clientes.html', clientes=lista_clientes)
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)