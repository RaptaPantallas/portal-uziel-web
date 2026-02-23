# portal_web.py
from flask import Flask, render_template, request, redirect, url_for, flash
from src.database import ConexionBD

app = Flask(__name__)
app.secret_key = 'llave_secreta_uziel_2026' # Necesario para mostrar mensajes flotantes

bd = ConexionBD()

@app.route('/')
def inicio():
    inventario = bd.obtener_productos()
    return render_template('index.html', productos=inventario)

@app.route('/eliminar/<sku>')
def eliminar_producto(sku):
    bd.eliminar_producto(sku)
    flash(f'El producto {sku} fue eliminado de la base de datos.', 'error')
    return redirect(url_for('inicio'))

@app.route('/editar/<sku>', methods=['GET', 'POST'])
def editar_producto(sku):
    if request.method == 'POST':
        # Capturamos lo que el usuario escribió en la web
        nombre = request.form['nombre']
        descripcion = request.form['descripcion']
        marca = request.form['marca']
        compatibilidad = request.form['compatibilidad']
        precio = request.form['precio']
        
        # Usamos la MISMA función que usa tu app de escritorio
        bd.actualizar_producto(sku, nombre, descripcion, marca, compatibilidad, precio)
        flash(f'Producto {sku} actualizado correctamente.', 'exito')
        return redirect(url_for('inicio'))
    else:
        # Buscamos los datos actuales para llenar las casillas del formulario
        producto = bd.obtener_producto(sku)
        return render_template('editar.html', producto=producto)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)