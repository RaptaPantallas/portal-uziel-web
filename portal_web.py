# portal_web.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
from functools import wraps
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
    inventario = bd.obtener_productos()
    return render_template('index.html', productos=inventario)

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)