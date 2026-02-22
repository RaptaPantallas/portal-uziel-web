# portal_web.py
from flask import Flask, render_template
from src.database import ConexionBD

app = Flask(__name__)

# ¡Instanciamos el mismo cerebro que usa tu app de escritorio!
bd = ConexionBD()

@app.route('/')
def inicio():
    # Le pedimos a la nube la lista de repuestos
    inventario = bd.obtener_productos()
    
    # Renderizamos la página web pasándole los datos
    return render_template('index.html', productos=inventario)

if __name__ == '__main__':
    # host='0.0.0.0' permite que se acceda desde la red
    app.run(host='0.0.0.0', port=5000, debug=True)