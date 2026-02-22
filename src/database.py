# src/database.py
import psycopg2
from psycopg2 import Error

class ConexionBD:
    def __init__(self):
        # ¡Tu nueva llave maestra a la Nube!
        self.url_nube = "postgresql://admin:Hk4Bn6VaReRb1U38W7aM0t12QAn1aJ4O@dpg-d6ddpkktgctc73f38gv0-a.oregon-postgres.render.com/importadora_uziel"

    def conectar(self):
        try:
            # Nos conectamos directamente usando la URL de Render
            conexion = psycopg2.connect(self.url_nube)
            return conexion
        except Error as e:
            print(f"🔴 Error al conectar a PostgreSQL en la Nube: {e}")
            return None

    # ==========================================
    # MÓDULO CRM (CLIENTES)
    # ==========================================
    def registrar_cliente(self, rif, nombre_empresa, telefono, correo, direccion):
        conexion = self.conectar()
        if conexion:
            try:
                cursor = conexion.cursor()
                consulta_sql = """
                    INSERT INTO clientes (rif, nombre_empresa, telefono, correo, direccion)
                    VALUES (%s, %s, %s, %s, %s)
                """
                valores = (rif, nombre_empresa, telefono, correo, direccion)
                cursor.execute(consulta_sql, valores)
                conexion.commit()
                return True
            except Error as e:
                print(f"🔴 Error al registrar el cliente: {e}")
                conexion.rollback()
                return False
            finally:
                cursor.close()
                conexion.close()

    def obtener_clientes(self):
        conexion = self.conectar()
        lista_clientes = []
        if conexion:
            try:
                cursor = conexion.cursor()
                cursor.execute("SELECT rif, nombre_empresa, telefono, correo FROM clientes ORDER BY fecha_registro DESC")
                lista_clientes = cursor.fetchall()
            except Error:
                pass
            finally:
                cursor.close()
                conexion.close()
        return lista_clientes

    # ==========================================
    # MÓDULO PIM (PRODUCTOS)
    # ==========================================
    def registrar_producto(self, sku, nombre, descripcion, marca, compatibilidad, precio):
        conexion = self.conectar()
        if conexion:
            try:
                cursor = conexion.cursor()
                consulta_sql = """
                    INSERT INTO productos (sku, nombre, descripcion, marca, compatibilidad, precio)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                valores = (sku, nombre, descripcion, marca, compatibilidad, precio)
                cursor.execute(consulta_sql, valores)
                conexion.commit()
                return True
            except Error as e:
                print(f"🔴 Error al registrar el producto: {e}")
                conexion.rollback()
                return False
            finally:
                cursor.close()
                conexion.close()

    def obtener_productos(self):
        conexion = self.conectar()
        lista_productos = []
        if conexion:
            try:
                cursor = conexion.cursor()
                cursor.execute("SELECT sku, nombre, marca, precio FROM productos ORDER BY fecha_creacion DESC")
                lista_productos = cursor.fetchall()
            except Error:
                pass
            finally:
                cursor.close()
                conexion.close()
        return lista_productos

    # ==========================================
    # MÓDULO DAM (ACTIVOS DIGITALES) - ¡NUEVO!
    # ==========================================
    def registrar_activo(self, sku, ruta_archivo, tipo_archivo, angulo):
        conexion = self.conectar()
        if conexion:
            try:
                cursor = conexion.cursor()
                # Esta consulta es magia relacional: Busca el ID del producto basado en el SKU y luego inserta el activo
                consulta_sql = """
                    INSERT INTO activos_digitales (producto_id, ruta_archivo, tipo_archivo, angulo)
                    VALUES ((SELECT id_producto FROM productos WHERE sku = %s), %s, %s, %s)
                """
                valores = (sku, ruta_archivo, tipo_archivo, angulo)
                cursor.execute(consulta_sql, valores)
                conexion.commit()
                print(f"🟢 Activo digital vinculado al SKU '{sku}' exitosamente.")
                return True
            except Error as e:
                print(f"🔴 Error al vincular el activo (¿Existe el SKU?): {e}")
                conexion.rollback()
                return False
            finally:
                cursor.close()
                conexion.close()

    def obtener_producto_con_imagen(self, sku):
        conexion = self.conectar()
        datos_completos = None
        if conexion:
            try:
                cursor = conexion.cursor()
                # Unimos (JOIN) la tabla de productos con la de activos_digitales
                consulta = """
                    SELECT p.nombre, p.marca, p.compatibilidad, p.precio, a.ruta_archivo 
                    FROM productos p
                    LEFT JOIN activos_digitales a ON p.id_producto = a.producto_id
                    WHERE p.sku = %s
                    LIMIT 1
                """
                cursor.execute(consulta, (sku,))
                datos_completos = cursor.fetchone()
            except Error as e:
                print(f"🔴 Error al unir producto e imagen: {e}")
            finally:
                cursor.close()
                conexion.close()
        return datos_completos