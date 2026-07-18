import os
import json
from datetime import datetime
import threading
import time
from src.database import ConexionBD

def crear_respaldo():
    """Crea un respaldo de todas las tablas principales de la base de datos en formato JSON."""
    bd = ConexionBD()
    tablas = ['usuarios', 'clientes', 'productos', 'activos', 'tareas', 'cotizaciones', 'gastos', 'auditoria']
    respaldo_data = {}
    
    try:
        with bd._get_conexion() as conn:
            with conn.cursor() as cur:
                for tabla in tablas:
                    try:
                        cur.execute(f"SELECT * FROM {tabla}")
                        columnas = [desc[0] for desc in cur.description]
                        filas = cur.fetchall()
                        # Convertir fechas y objetos complejos a string para JSON
                        filas_procesadas = []
                        for fila in filas:
                            fila_dict = {}
                            for i, val in enumerate(fila):
                                if isinstance(val, datetime):
                                    fila_dict[columnas[i]] = val.isoformat()
                                else:
                                    fila_dict[columnas[i]] = val
                            filas_procesadas.append(fila_dict)
                        respaldo_data[tabla] = filas_procesadas
                    except Exception as e:
                        print(f"Error respaldando tabla {tabla}: {e}")
                        conn.rollback() # Ignorar si la tabla no existe o falla
    except Exception as e:
        print(f"Error de conexion al respaldar: {e}")
        return None

    # Crear carpeta si no existe
    backup_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backups')
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    fecha_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"respaldo_uziel_{fecha_str}.json"
    filepath = os.path.join(backup_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(respaldo_data, f, ensure_ascii=False, indent=2)

    return filepath

def tarea_respaldo_automatico():
    """Ejecuta respaldos periódicamente cada 24 horas."""
    while True:
        time.sleep(24 * 60 * 60) # Esperar 24 horas
        print("Iniciando respaldo automático de la base de datos...")
        filepath = crear_respaldo()
        if filepath:
            print(f"Respaldo automático guardado en {filepath}")

def iniciar_hilo_respaldos():
    t = threading.Thread(target=tarea_respaldo_automatico, daemon=True)
    t.start()
