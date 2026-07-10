import json
from datetime import datetime, timedelta
# pyrefly: ignore [missing-import]
from PyQt6.QtCore import QObject, pyqtSlot

class DashboardBridge(QObject):
    """
    Puente de comunicación entre PyQt6 y el JavaScript del visor web (QWebEngineView).
    Expone métodos decorados con @pyqtSlot para ser invocados desde JS.
    """
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        print("[DashboardBridge] Puente inicializado correctamente.")

    @pyqtSlot(str, str, result=str)
    def obtener_conteos(self, fecha_inicio, fecha_fin):
        """
        Obtiene las métricas agregadas y totales del sistema.
        Llama al método obtener_conteos_reporte de la base de datos.
        """
        print(f"[DashboardBridge] Invocado obtener_conteos({fecha_inicio}, {fecha_fin})")
        try:
            res = self.main_window.bd.obtener_conteos_reporte(fecha_inicio, fecha_fin)
            print(f"[DashboardBridge] obtener_conteos éxito: {res.get('total_clientes')} clientes, {res.get('total_productos')} productos.")
            return json.dumps(res, default=str)
        except Exception as e:
            print(f"[DashboardBridge] Error en obtener_conteos: {e}")
            return json.dumps({"error": str(e)})

    @pyqtSlot(result=str)
    def obtener_ultimos_eventos(self):
        """
        Obtiene los últimos 5 eventos registrados en la bitácora de auditoría.
        """
        print("[DashboardBridge] Invocado obtener_ultimos_eventos()")
        try:
            hoy = datetime.now()
            hace_30_dias = hoy - timedelta(days=30)
            logs = self.main_window.bd.obtener_logs_auditoria(hace_30_dias.strftime("%Y-%m-%d"), hoy.strftime("%Y-%m-%d"))
            
            if not logs:
                logs = self.main_window.bd.obtener_logs_auditoria("2020-01-01", "2099-12-31")
            
            ultimos_logs = logs[:5]
            print(f"[DashboardBridge] obtener_ultimos_eventos éxito: Encontrados {len(ultimos_logs)} eventos.")
            
            resultado = []
            for item in ultimos_logs:
                fecha_val = item[4]
                if hasattr(fecha_val, 'strftime'):
                    fecha_str = fecha_val.strftime("%d/%m/%Y %H:%M")
                else:
                    fecha_str = str(fecha_val)[:16]
                
                resultado.append({
                    "id": item[0],
                    "usuario": item[1],
                    "accion": item[2],
                    "detalle": item[3],
                    "fecha_hora": fecha_str
                })
            
            return json.dumps(resultado, default=str)
        except Exception as e:
            print(f"[DashboardBridge] Error en obtener_ultimos_eventos: {e}")
            return json.dumps({"error": str(e)})

    @pyqtSlot(int)
    def cambiar_pestana(self, index):
        """Cambia la pestaña activa del QTabWidget principal."""
        print(f"[DashboardBridge] Invocado cambiar_pestana({index})")
        try:
            self.main_window.tabs.setCurrentIndex(index)
        except Exception as e:
            print(f"[DashboardBridge] Error en cambiar_pestana: {e}")

    @pyqtSlot(result=str)
    def obtener_usuario_actual(self):
        """Retorna el usuario actualmente autenticado en la sesión."""
        print("[DashboardBridge] Invocado obtener_usuario_actual()")
        try:
            user = self.main_window.usuario_actual
            print(f"[DashboardBridge] obtener_usuario_actual éxito: '{user}'")
            return user
        except Exception as e:
            print(f"[DashboardBridge] Error en obtener_usuario_actual: {e}")
            return "Usuario"

    @pyqtSlot(str, str, result=str)
    def obtener_gastos_periodo(self, desde, hasta):
        """
        Consulta los gastos de publicidad registrados en el rango de fechas.
        """
        print(f"[DashboardBridge] Invocado obtener_gastos_periodo({desde}, {hasta})")
        conexion = self.main_window.bd.conectar()
        if not conexion:
            print("[DashboardBridge] Error obtener_gastos_periodo: No hay conexión a base de datos.")
            return json.dumps({"error": "No hay conexión a la base de datos"})
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT id, post, objetivo, total, ingresos, alcance, clics, conversiones, fecha_creacion
                FROM gastos_publicidad
                WHERE fecha_creacion::date BETWEEN %s AND %s
                ORDER BY fecha_creacion ASC
            """, (desde, hasta))
            rows = cursor.fetchall()
            print(f"[DashboardBridge] obtener_gastos_periodo éxito: Encontradas {len(rows)} campañas.")
            
            resultado = []
            for item in rows:
                resultado.append({
                    "id": item[0],
                    "post": item[1],
                    "objetivo": item[2],
                    "total": float(item[3]) if item[3] is not None else 0.0,
                    "ingresos": float(item[4]) if item[4] is not None else 0.0,
                    "alcance": int(item[5]) if item[5] is not None else 0,
                    "clics": int(item[6]) if item[6] is not None else 0,
                    "conversiones": int(item[7]) if item[7] is not None else 0,
                    "fecha_creacion": str(item[8])[:10]
                })
            return json.dumps(resultado, default=str)
        except Exception as e:
            print(f"[DashboardBridge] Error en obtener_gastos_periodo: {e}")
            return json.dumps({"error": str(e)})
        finally:
            conexion.close()
