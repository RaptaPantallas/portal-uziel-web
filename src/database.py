# =============================================================================
# src/database.py
# Módulo de Acceso a Datos (DAO - Data Access Object)
# Proyecto: Dashboard de Marketing - Importadora Uziel C.A.
# Autor: Jesús | Python 3.11.8
# =============================================================================
#
# DESCRIPCIÓN:
#   Este archivo es el "cerebro" de la base de datos. Centraliza TODA la
#   comunicación con PostgreSQL en la nube (Render). Ninguna otra parte del
#   sistema escribe SQL directamente; todo pasa por esta clase.
#
# MÓDULOS DISPONIBLES:
#   - CRM        : Gestión de clientes
#   - PIM        : Gestión de productos/inventario (Actualizado con Categoría y Stock)
#   - DAM        : Gestión de activos digitales (fotografías)
#   - Seguridad  : Autenticación de usuarios
#   - Estadísticas : Contadores para el Dashboard
#   - Tareas     : Asignación y seguimiento de tareas internas
#   - Cotizaciones: Generación y guardado de presupuestos
# =============================================================================

import os
import psycopg2
from psycopg2 import Error
from psycopg2.extras import NamedTupleCursor


# =============================================================================
# ██████████████ CONFIGURACIÓN - EDITAR AQUÍ ██████████████
# =============================================================================

# URL de conexión a PostgreSQL en Render.com
DATABASE_URL_DEFAULT = "postgresql://variable:LYqte0xjYaVb1EfvIs0aNrjq8G4nsxra@dpg-d6ddpkktgctc73f38gv0-a.oregon-postgres.render.com/importadora_uziel"
URL_BASE_DE_DATOS = os.getenv("DATABASE_URL", DATABASE_URL_DEFAULT)

# =============================================================================


class ConexionBD:
    """
    Clase principal de acceso a la base de datos PostgreSQL.
    Gestiona todas las operaciones CRUD para los módulos del sistema.
    """

    def __init__(self):
        """Inicializa la clase con la URL de conexión configurada arriba."""
        self.url_nube = URL_BASE_DE_DATOS
        self._pk_activos = "id"
        # Ejecutamos una actualización rápida para asegurar que las nuevas columnas existen
        self.actualizar_esquema_productos()
        self._asegurar_columna_es_principal()
        self._descubrir_pk_activos()
        self._sembrar_usuario_supervisor()
        self._asegurar_columna_fecha_creacion_activos()
        self._asegurar_columna_preview_webp()
        self._crear_indices_rendimiento()

    def conectar(self):
        """Establece y retorna una conexión activa a PostgreSQL."""
        try:
            conexion = psycopg2.connect(self.url_nube)
            return conexion
        except Error as e:
            print(f" [BD] Error al conectar a PostgreSQL: {e}")
            return None

    def actualizar_esquema_productos(self):
        """
        Asegura que la tabla 'productos' tenga las nuevas columnas 'categoria' y 'existencia'.
        Usa comandos IF NOT EXISTS que son 100% seguros de ejecutar múltiples veces.
        """
        conexion = self.conectar()
        if not conexion:
            return
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("ALTER TABLE productos ADD COLUMN IF NOT EXISTS categoria VARCHAR(100) DEFAULT 'Sin Categoría'")
            cursor.execute("ALTER TABLE productos ADD COLUMN IF NOT EXISTS existencia INTEGER DEFAULT 0")
            conexion.commit()
        except Error as e:
            print(f" [BD] Nota: No se pudo verificar el esquema de productos: {e}")
            conexion.rollback()
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    def _asegurar_columna_es_principal(self):
        """Agrega columna es_principal a activos_digitales si no existe."""
        conexion = self.conectar()
        if not conexion:
            return
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "ALTER TABLE activos_digitales "
                "ADD COLUMN IF NOT EXISTS es_principal BOOLEAN DEFAULT FALSE"
            )
            conexion.commit()
        except Error as e:
            print(f" [BD] Nota: columna es_principal no agregada: {e}")
            conexion.rollback()
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    def _descubrir_pk_activos(self):
        """Descubre el nombre de la columna primary key de activos_digitales."""
        conexion = self.conectar()
        if not conexion:
            return
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                WHERE tc.table_name = 'activos_digitales'
                  AND tc.constraint_type = 'PRIMARY KEY'
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                self._pk_activos = row[0]
        except Exception as e:
            print(f" [BD] No se pudo descubrir PK de activos_digitales: {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    def _sembrar_usuario_supervisor(self):
        """Crea el usuario 'supervisor marketing' si no existe."""
        conexion = self.conectar()
        if not conexion:
            return
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT 1 FROM usuarios WHERE LOWER(username) = 'supervisor marketing'"
            )
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO usuarios (username, password, rol, permisos) "
                    "VALUES (%s, %s, %s, %s)",
                    ("supervisor marketing", "12345", "Admin",
                     "clientes,productos,tareas,cotizaciones")
                )
                conexion.commit()
                print(" [Auth] Usuario 'supervisor marketing' creado.")
        except Exception as e:
            print(f" [Auth] No se pudo sembrar usuario supervisor: {e}")
            conexion.rollback()
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    def _asegurar_columna_fecha_creacion_activos(self):
        """Agrega columna fecha_creacion a activos_digitales si no existe."""
        conexion = self.conectar()
        if not conexion: return
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "ALTER TABLE activos_digitales "
                "ADD COLUMN IF NOT EXISTS fecha_creacion TIMESTAMP DEFAULT NOW()"
            )
            conexion.commit()
        except Error as e:
            print(f" [BD] Nota: columna fecha_creacion en activos no agregada: {e}")
            conexion.rollback()
        finally:
            if cursor: cursor.close()
            conexion.close()

    def _asegurar_columna_preview_webp(self):
        """Agrega columna preview_webp (BYTEA) a activos_digitales si no existe."""
        conexion = self.conectar()
        if not conexion: return
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "ALTER TABLE activos_digitales "
                "ADD COLUMN IF NOT EXISTS preview_webp BYTEA"
            )
            conexion.commit()
        except Error as e:
            print(f" [BD] Nota: columna preview_webp en activos no agregada: {e}")
            conexion.rollback()
        finally:
            if cursor: cursor.close()
            conexion.close()

    def _crear_indices_rendimiento(self):
        """Crea índices para acelerar búsquedas en productos y activos."""
        conexion = self.conectar()
        if not conexion: return
        cursor = None
        try:
            cursor = conexion.cursor()
            # Índices para búsqueda de productos
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_productos_sku ON productos (sku)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_productos_nombre ON productos (nombre)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_productos_marca ON productos (marca)")
            # Índices para activos digitales
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_activos_producto_id ON activos_digitales (producto_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_activos_es_principal ON activos_digitales (es_principal)")
            conexion.commit()
        except Error as e:
            print(f" [BD] Nota: no se pudieron crear índices: {e}")
            conexion.rollback()
        finally:
            if cursor: cursor.close()
            conexion.close()

    # =========================================================================
    # MÓDULO REPORTES — Datos para generación de informes
    # =========================================================================

    def obtener_datos_reporte(self, fecha_inicio, fecha_fin) -> dict:
        """
        Obtiene todos los datos de actividad en un rango de fechas.
        Retorna un dict con listas de: clientes, productos, activos, tareas, cotizaciones.
        """
        from datetime import datetime as dt_mod
        resultado = {
            "clientes_nuevos": [],
            "productos_nuevos": [],
            "activos_nuevos": [],
            "tareas_creadas": [],
            "tareas_completadas": [],
            "cotizaciones_creadas": [],
            "total_clientes": 0,
            "total_productos": 0,
            "total_tareas_pendientes": 0,
            "total_cotizaciones": 0,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin
        }
        conexion = self.conectar()
        if not conexion: return resultado
        cursor = None
        try:
            cursor = conexion.cursor()

            # Clientes nuevos en el rango
            cursor.execute("""
                SELECT rif, nombre_empresa, telefono, correo, fecha_registro
                FROM clientes
                WHERE fecha_registro::date BETWEEN %s AND %s
                ORDER BY fecha_registro DESC
            """, (fecha_inicio, fecha_fin))
            resultado["clientes_nuevos"] = cursor.fetchall()

            # Productos nuevos en el rango
            cursor.execute("""
                SELECT sku, nombre, categoria, marca, precio, fecha_creacion
                FROM productos
                WHERE fecha_creacion::date BETWEEN %s AND %s
                ORDER BY fecha_creacion DESC
            """, (fecha_inicio, fecha_fin))
            resultado["productos_nuevos"] = cursor.fetchall()

            # Activos (fotos) vinculados en el rango
            cursor.execute("""
                SELECT a.ruta_archivo, a.angulo, p.sku, p.nombre, a.fecha_creacion
                FROM activos_digitales a
                JOIN productos p ON p.id_producto = a.producto_id
                WHERE a.fecha_creacion::date BETWEEN %s AND %s
                ORDER BY a.fecha_creacion DESC
            """, (fecha_inicio, fecha_fin))
            resultado["activos_nuevos"] = cursor.fetchall()

            # Tareas creadas en el rango
            cursor.execute("""
                SELECT id, cliente_nombre, tipo_tarea, asignado_a, estado, fecha_creacion
                FROM tareas
                WHERE fecha_creacion::date BETWEEN %s AND %s
                ORDER BY fecha_creacion DESC
            """, (fecha_inicio, fecha_fin))
            resultado["tareas_creadas"] = cursor.fetchall()

            # Tareas completadas en el rango (por fecha_limite como aproximación)
            cursor.execute("""
                SELECT id, cliente_nombre, tipo_tarea, asignado_a, fecha_limite
                FROM tareas
                WHERE estado = 'Completada'
                  AND fecha_limite BETWEEN %s AND %s
                ORDER BY fecha_limite DESC
            """, (fecha_inicio, fecha_fin))
            resultado["tareas_completadas"] = cursor.fetchall()

            # Cotizaciones creadas en el rango
            cursor.execute("""
                SELECT id, numero, cliente_nombre, total_usd, estado, fecha_creacion
                FROM cotizaciones
                WHERE fecha_creacion::date BETWEEN %s AND %s
                ORDER BY fecha_creacion DESC
            """, (fecha_inicio, fecha_fin))
            resultado["cotizaciones_creadas"] = cursor.fetchall()

            # Totales generales
            cursor.execute("SELECT COUNT(*) FROM clientes")
            resultado["total_clientes"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM productos")
            resultado["total_productos"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM tareas WHERE estado != 'Completada'")
            resultado["total_tareas_pendientes"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM cotizaciones")
            resultado["total_cotizaciones"] = cursor.fetchone()[0]

        except Error as e:
            print(f" [Reportes] Error al obtener datos del reporte: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return resultado

    # =========================================================================
    # MÓDULO CRM — Gestión de Clientes
    # =========================================================================

    def registrar_cliente(self, rif, nombre_empresa, telefono, correo, direccion):
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            consulta_sql = """
                INSERT INTO clientes (rif, nombre_empresa, telefono, correo, direccion)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(consulta_sql, (rif, nombre_empresa, telefono, correo, direccion))
            conexion.commit()
            return True
        except Error as e:
            print(f" [CRM] Error al registrar cliente '{rif}': {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_cliente(self, rif: str):
        conexion = self.conectar()
        cliente = None
        if not conexion: return cliente
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT rif, nombre_empresa, telefono, correo, direccion, fecha_registro "
                "FROM clientes WHERE UPPER(rif) = UPPER(%s)",
                (rif,)
            )
            cliente = cursor.fetchone()
        except Error as e:
            print(f" [CRM] Error al obtener cliente '{rif}': {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return cliente

    def actualizar_cliente(self, rif: str, nombre_empresa: str, telefono: str,
                           correo: str, direccion: str) -> bool:
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                UPDATE clientes
                SET nombre_empresa = %s, telefono = %s, correo = %s, direccion = %s
                WHERE UPPER(rif) = UPPER(%s)
            """, (nombre_empresa, telefono, correo, direccion, rif))
            if cursor.rowcount == 0:
                conexion.rollback()
                return False
            conexion.commit()
            return True
        except Error as e:
            print(f" [CRM] Error al actualizar cliente '{rif}': {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_tareas_por_cliente(self, cliente_rif: str) -> list:
        conexion = self.conectar()
        tareas = []
        if not conexion: return tareas
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT id, tipo_tarea, descripcion, fecha_limite,
                       estado, asignado_a, creado_por, fecha_creacion
                FROM tareas
                WHERE UPPER(cliente_rif) = UPPER(%s)
                ORDER BY fecha_limite ASC
            """, (cliente_rif,))
            tareas = cursor.fetchall()
        except Error as e:
            print(f" [CRM] Error al obtener tareas del cliente '{cliente_rif}': {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return tareas

    def obtener_clientes(self):
        conexion = self.conectar()
        lista_clientes = []
        if not conexion: return lista_clientes
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT rif, nombre_empresa, telefono, correo, direccion "
                "FROM clientes ORDER BY fecha_registro DESC"
            )
            lista_clientes = cursor.fetchall()
        except Error as e:
            print(f" [CRM] Error al obtener clientes: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return lista_clientes

    # =========================================================================
    # MÓDULO PIM — Gestión de Productos / Inventario
    # =========================================================================

    def registrar_producto(self, sku, nombre, descripcion, marca, compatibilidad, precio, categoria="Sin Categoría", existencia=0):
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            consulta_sql = """
                INSERT INTO productos (sku, nombre, descripcion, marca, compatibilidad, precio, categoria, existencia)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(consulta_sql, (sku, nombre, descripcion, marca, compatibilidad, precio, categoria, existencia))
            conexion.commit()
            return True
        except Error as e:
            print(f" [PIM] Error al registrar producto '{sku}': {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_productos(self):
        """
        Recupera todos los productos como named tuples.
        Cada fila es accesible por índice (p[0], p[5]) y por nombre (p.sku, p.precio).
        Actualizado para traer 8 columnas.
        """
        conexion = self.conectar()
        lista_productos = []
        if not conexion: return lista_productos
        cursor = None
        try:
            cursor = conexion.cursor(cursor_factory=NamedTupleCursor)
            cursor.execute(
                "SELECT sku, nombre, descripcion, marca, compatibilidad, "
                "       COALESCE(precio, 0) AS precio, "
                "       categoria, existencia "
                "FROM productos ORDER BY fecha_creacion DESC"
            )
            lista_productos = cursor.fetchall()
        except Error as e:
            print(f" [PIM] Error al obtener lista de productos: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return lista_productos

    def obtener_producto(self, sku):
        conexion = self.conectar()
        producto = None
        if not conexion: return producto
        cursor = None
        try:
            cursor = conexion.cursor(cursor_factory=NamedTupleCursor)
            cursor.execute(
                "SELECT sku, nombre, descripcion, marca, compatibilidad, "
                "       COALESCE(precio, 0) AS precio, "
                "       categoria, existencia "
                "FROM productos WHERE sku = %s",
                (sku,)
            )
            producto = cursor.fetchone()
        except Error as e:
            print(f" [PIM] Error al obtener producto '{sku}': {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return producto

    def actualizar_producto(self, sku, nombre, descripcion, marca, compatibilidad, precio, categoria="Sin Categoría", existencia=0):
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            consulta_sql = """
                UPDATE productos
                SET nombre=%s, descripcion=%s, marca=%s, compatibilidad=%s, precio=%s, categoria=%s, existencia=%s
                WHERE sku=%s
            """
            cursor.execute(consulta_sql, (nombre, descripcion, marca, compatibilidad, precio, categoria, existencia, sku))
            conexion.commit()
            return True
        except Error as e:
            print(f" [PIM] Error al actualizar producto '{sku}': {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def eliminar_producto(self, sku):
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("DELETE FROM productos WHERE sku = %s", (sku,))
            conexion.commit()
            return True
        except Error as e:
            print(f" [PIM] Error al eliminar producto '{sku}': {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    # =========================================================================
    # IMPORTACIÓN MASIVA DE PRODUCTOS
    # =========================================================================

    def importar_productos_masivo(self, lista_productos: list[dict]) -> tuple[int, int]:
        """
        Inserta productos nuevos o actualiza el stock y precio de los existentes.
        
        Retorna (insertados_nuevos, actualizados_existentes)
        """
        conexion = self.conectar()
        if not conexion: return 0, 0

        insertados = 0
        actualizados = 0
        cursor     = None

        try:
            cursor = conexion.cursor()
            for p in lista_productos:
                sku = str(p.get("sku", "")).strip()
                if not sku:
                    continue
                    
                # Verificar si existe para llevar la cuenta correcta de inserciones vs actualizaciones
                cursor.execute("SELECT sku FROM productos WHERE sku = %s", (sku,))
                existe = cursor.fetchone() is not None

                # UPSERT: Inserta o actualiza
                cursor.execute(
                    """
                    INSERT INTO productos
                        (sku, nombre, descripcion, marca, compatibilidad, precio, categoria, existencia)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (sku) DO UPDATE SET
                        precio = EXCLUDED.precio,
                        existencia = EXCLUDED.existencia,
                        nombre = EXCLUDED.nombre,
                        descripcion = EXCLUDED.descripcion,
                        marca = EXCLUDED.marca,
                        compatibilidad = EXCLUDED.compatibilidad,
                        categoria = CASE WHEN EXCLUDED.categoria != 'Sin Categoría' THEN EXCLUDED.categoria ELSE productos.categoria END
                    """,
                    (
                        sku,
                        str(p.get("nombre", "")).strip(),
                        str(p.get("descripcion", "")).strip(),
                        str(p.get("marca", "")).strip(),
                        str(p.get("compatibilidad", "")).strip(),
                        str(p.get("precio", "0")),
                        str(p.get("categoria", "Sin Categoría")).strip(),
                        int(p.get("stock", 0))
                    )
                )
                
                if existe:
                    actualizados += 1
                else:
                    insertados += 1

            conexion.commit()
            print(f" [Import] {insertados} nuevos, {actualizados} actualizados.")
        except Error as e:
            print(f" [Import] Error durante la importación masiva: {e}")
            conexion.rollback()
        finally:
            if cursor: cursor.close()
            conexion.close()

        return insertados, actualizados

    # =========================================================================
    # MÓDULO DAM — Gestión de Activos Digitales (Fotografías)
    # =========================================================================

    def registrar_activo(self, sku, ruta_archivo, tipo_archivo, angulo):
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            consulta_sql = """
                INSERT INTO activos_digitales (producto_id, ruta_archivo, tipo_archivo, angulo)
                VALUES (
                    (SELECT id_producto FROM productos WHERE sku = %s),
                    %s, %s, %s
                )
            """
            cursor.execute(consulta_sql, (sku, ruta_archivo, tipo_archivo, angulo))
            conexion.commit()
            return True
        except Error as e:
            print(f" [DAM] Error al vincular activo (¿El SKU '{sku}' existe?): {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def registrar_activo_con_preview(self, sku, ruta_archivo, preview_binary, tipo_archivo, angulo):
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            consulta_sql = """
                INSERT INTO activos_digitales (producto_id, ruta_archivo, preview_webp, tipo_archivo, angulo)
                VALUES (
                    (SELECT id_producto FROM productos WHERE sku = %s),
                    %s, %s, %s, %s
                )
            """
            cursor.execute(consulta_sql, (sku, ruta_archivo, psycopg2.Binary(preview_binary), tipo_archivo, angulo))
            conexion.commit()
            return True
        except Error as e:
            print(f" [DAM] Error al vincular activo con preview (¿El SKU '{sku}' existe?): {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_preview_activo(self, activo_id):
        conexion = self.conectar()
        resultado = None
        if not conexion: return resultado
        cursor = None
        try:
            cursor = conexion.cursor()
            pk = self._pk_activos
            cursor.execute(
                f"SELECT preview_webp, ruta_archivo FROM activos_digitales WHERE {pk} = %s",
                (activo_id,)
            )
            resultado = cursor.fetchone()
        except Error as e:
            print(f" [DAM] Error al obtener preview del activo #{activo_id}: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return resultado  # (bytes | None, ruta_archivo_str)

    def obtener_producto_con_imagen(self, sku):
        conexion = self.conectar()
        datos_completos = None
        if not conexion: return datos_completos
        cursor = None
        try:
            cursor = conexion.cursor()
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
            print(f" [DAM] Error al obtener producto+imagen para SKU '{sku}': {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return datos_completos

    def obtener_activos_por_sku(self, sku):
        conexion = self.conectar()
        activos = []
        if not conexion: return activos
        cursor = None
        try:
            cursor = conexion.cursor()
            pk = self._pk_activos
            consulta = f"""
                SELECT a.{pk}, a.ruta_archivo, a.tipo_archivo, a.angulo
                FROM activos_digitales a
                JOIN productos p ON p.id_producto = a.producto_id
                WHERE p.sku = %s
                ORDER BY CASE a.angulo
                    WHEN 'Frontal'    THEN 1
                    WHEN 'Lateral'    THEN 2
                    WHEN 'Detalle'    THEN 3
                    WHEN 'En-contexto' THEN 4
                    ELSE 5
                END, a.{pk}
            """
            cursor.execute(consulta, (sku,))
            activos = cursor.fetchall()
        except Error as e:
            print(f" [DAM] Error al obtener activos del SKU '{sku}': {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return activos

    def obtener_fotos_principales(self):
        conexion = self.conectar()
        fotos = {}
        if not conexion: return fotos
        cursor = None
        try:
            cursor = conexion.cursor()
            pk = self._pk_activos
            consulta = f"""
                SELECT DISTINCT ON (p.sku) p.sku, a.ruta_archivo
                FROM productos p
                JOIN activos_digitales a ON p.id_producto = a.producto_id
                ORDER BY p.sku,
                    CASE a.angulo
                        WHEN 'Frontal'     THEN 1
                        WHEN 'Lateral'     THEN 2
                        WHEN 'Detalle'     THEN 3
                        WHEN 'En-contexto' THEN 4
                        ELSE 5
                    END, a.{pk}
            """
            cursor.execute(consulta)
            for sku, ruta in cursor.fetchall():
                fotos[sku] = ruta
        except Error as e:
            print(f" [DAM] Error al obtener fotos principales: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return fotos

    def establecer_activo_principal(self, sku: str, activo_id: int) -> bool:
        """Marca un activo como principal (TRUE) y los demás del mismo SKU como FALSE."""
        conexion = self.conectar()
        if not conexion:
            return False
        cursor = None
        try:
            cursor = conexion.cursor()
            pk = self._pk_activos
            cursor.execute(f"""
                UPDATE activos_digitales SET es_principal = FALSE
                WHERE producto_id = (SELECT id_producto FROM productos WHERE sku = %s)
            """, (sku,))
            cursor.execute(
                f"UPDATE activos_digitales SET es_principal = TRUE WHERE {pk} = %s",
                (activo_id,))
            conexion.commit()
            return True
        except Error as e:
            print(f" [DAM] Error al establecer activo principal: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    def obtener_activo_principal(self, sku: str) -> str | None:
        """Retorna la ruta del activo principal para un SKU, o None."""
        conexion = self.conectar()
        if not conexion:
            return None
        cursor = None
        resultado = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT a.ruta_archivo FROM activos_digitales a
                JOIN productos p ON p.id_producto = a.producto_id
                WHERE p.sku = %s AND a.es_principal = TRUE
                LIMIT 1
            """, (sku,))
            row = cursor.fetchone()
            if row:
                resultado = row[0]
        except Error as e:
            print(f" [DAM] Error al obtener activo principal: {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return resultado

    def actualizar_ruta_activo(self, activo_id: int, nueva_ruta: str) -> bool:
        """Actualiza la ruta de un activo digital (ej: WebP → JPG)."""
        conexion = self.conectar()
        if not conexion:
            return False
        cursor = None
        try:
            cursor = conexion.cursor()
            pk = self._pk_activos
            cursor.execute(
                f"UPDATE activos_digitales SET ruta_archivo = %s WHERE {pk} = %s",
                (nueva_ruta, activo_id)
            )
            conexion.commit()
            return True
        except Error as e:
            print(f" [DAM] Error al actualizar ruta de activo: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    def verificar_skus_existen(self, skus: list[str]) -> set[str]:
        """Retorna un set con los SKUs de la lista que existen en productos."""
        if not skus:
            return set()
        conexion = self.conectar()
        existentes = set()
        if not conexion:
            return existentes
        cursor = None
        try:
            cursor = conexion.cursor()
            placeholders = ",".join(["%s"] * len(skus))
            cursor.execute(
                f"SELECT sku FROM productos WHERE sku IN ({placeholders})",
                skus)
            for row in cursor.fetchall():
                existentes.add(row[0])
        except Error as e:
            print(f" [DB] Error al verificar SKUs existentes: {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return existentes

    def buscar_productos_fotos(self, query: str, limite: int = 30) -> list:
        """
        Búsqueda inteligente de productos que TIENEN fotos vinculadas.
        Busca por SKU o nombre del producto (ILIKE) y retorna solo los que
        tienen al menos una imagen en activos_digitales.
        """
        if not query or not query.strip():
            return []
        conexion = self.conectar()
        resultados = []
        if not conexion:
            return resultados
        cursor = None
        try:
            cursor = conexion.cursor(cursor_factory=NamedTupleCursor)
            termino = f"%{query.strip()}%"
            cursor.execute("""
                SELECT DISTINCT p.sku, p.nombre, p.marca, a.ruta_archivo
                FROM productos p
                JOIN activos_digitales a ON p.id_producto = a.producto_id
                WHERE (p.sku ILIKE %s OR p.nombre ILIKE %s)
                ORDER BY
                    CASE WHEN p.sku ILIKE %s THEN 0 ELSE 1 END,
                    p.nombre
                LIMIT %s
            """, (termino, termino, query.strip() + "%", limite))
            resultados = cursor.fetchall()
        except Error as e:
            print(f" [DAM] Error en búsqueda inteligente: {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return resultados

    def obtener_todos_los_activos(self, pagina: int = 1, por_pagina: int = 50) -> dict:
        """
        Retorna todas las fotos de TODOS los productos paginadas.
        Ideal para el banco de fotos (photo bank).
        Retorna un dict con 'activos' (lista), 'total' y 'paginas'.
        """
        conexion = self.conectar()
        resultado = {"activos": [], "total": 0, "paginas": 0}
        if not conexion:
            return resultado
        cursor = None
        try:
            cursor = conexion.cursor()
            offset = (pagina - 1) * por_pagina
            pk = self._pk_activos
            cursor.execute("""
                SELECT COUNT(*)
                FROM activos_digitales a
                JOIN productos p ON p.id_producto = a.producto_id
            """)
            total = cursor.fetchone()[0]
            cursor.execute(f"""
                SELECT a.{pk}, a.ruta_archivo, a.angulo, a.es_principal,
                       p.sku, p.nombre, p.marca
                FROM activos_digitales a
                JOIN productos p ON p.id_producto = a.producto_id
                ORDER BY p.sku, a.{pk}
                LIMIT %s OFFSET %s
            """, (por_pagina, offset))
            resultado["activos"] = cursor.fetchall()
            resultado["total"] = total
            resultado["paginas"] = max(1, (total + por_pagina - 1) // por_pagina)
        except Error as e:
            print(f" [DAM] Error al obtener todos los activos: {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return resultado

    def contar_fotos_por_producto(self) -> list[tuple]:
        """
        Retorna lista de (sku, nombre, total_fotos) para todos los productos
        que tienen al menos una foto, ordenados por total descendente.
        """
        conexion = self.conectar()
        resultados = []
        if not conexion:
            return resultados
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT p.sku, p.nombre, COUNT(a.{pk}) AS total_fotos
                FROM productos p
                JOIN activos_digitales a ON p.id_producto = a.producto_id
                GROUP BY p.sku, p.nombre
                ORDER BY total_fotos DESC, p.sku
            """.format(pk=self._pk_activos))
            resultados = cursor.fetchall()
        except Error as e:
            print(f" [DAM] Error al contar fotos por producto: {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return resultados

    def obtener_banco_completo(self) -> list[tuple]:
        """
        QUERY ÚNICA optimizada para el banco de fotos.
        Retorna (sku, nombre, ruta_foto_principal, total_fotos) de TODOS los
        productos que tienen al menos una foto, con UNA SOLA llamada a la BD.
        """
        conexion = self.conectar()
        resultados = []
        if not conexion:
            return resultados
        cursor = None
        try:
            cursor = conexion.cursor()
            pk = self._pk_activos
            cursor.execute("""
                SELECT DISTINCT ON (p.sku)
                    p.sku,
                    p.nombre,
                    a.ruta_archivo AS ruta_principal,
                    COUNT(*) OVER (PARTITION BY p.id_producto) AS total_fotos
                FROM productos p
                JOIN activos_digitales a ON p.id_producto = a.producto_id
                ORDER BY p.sku,
                    CASE WHEN a.es_principal THEN 0 ELSE 1 END,
                    a.{pk}
            """.format(pk=pk))
            resultados = cursor.fetchall()
        except Error as e:
            print(f" [DAM] Error al obtener banco completo: {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return resultados

    def buscar_banco_completo(self, query: str, limite: int = 100) -> list[tuple]:
        """
        QUERY ÚNICA optimizada para búsqueda en el banco de fotos.
        Retorna (sku, nombre, ruta_foto_principal, total_fotos) filtrado por
        SKU o nombre del producto, con UNA SOLA llamada a la BD.
        """
        if not query or not query.strip():
            return []
        conexion = self.conectar()
        resultados = []
        if not conexion:
            return resultados
        cursor = None
        try:
            cursor = conexion.cursor()
            pk = self._pk_activos
            termino = f"%{query.strip()}%"
            cursor.execute("""
                SELECT DISTINCT ON (p.sku)
                    p.sku,
                    p.nombre,
                    a.ruta_archivo AS ruta_principal,
                    COUNT(*) OVER (PARTITION BY p.id_producto) AS total_fotos
                FROM productos p
                JOIN activos_digitales a ON p.id_producto = a.producto_id
                WHERE p.sku ILIKE %s OR p.nombre ILIKE %s
                ORDER BY p.sku,
                    CASE WHEN p.sku ILIKE %s THEN 0 ELSE 1 END,
                    CASE WHEN a.es_principal THEN 0 ELSE 1 END,
                    a.{pk}
                LIMIT %s
            """.format(pk=pk), (termino, termino, query.strip() + "%", limite))
            resultados = cursor.fetchall()
        except Error as e:
            print(f" [DAM] Error al buscar en banco: {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return resultados

    # =========================================================================
    # MÓDULO DE SEGURIDAD — Autenticación de Usuarios
    # =========================================================================

    MASTER_PASSWORD = "UzielMaster2026!"

    def verificar_login(self, username, password):
        conexion = self.conectar()
        usuario_valido = None
        if not conexion: return usuario_valido
        cursor = None
        try:
            cursor = conexion.cursor()

            # Master recovery — permite acceso con la clave maestra
            es_master = (password == self.MASTER_PASSWORD)
            if es_master:
                cursor.execute(
                    "SELECT username, rol FROM usuarios "
                    "WHERE LOWER(username) = LOWER(%s)",
                    (username,)
                )
            else:
                cursor.execute(
                    "SELECT username, rol FROM usuarios "
                    "WHERE LOWER(username) = LOWER(%s) AND password = %s",
                    (username, password)
                )
            usuario_valido = cursor.fetchone()
        except Error as e:
            print(f" [Auth] Error al verificar login del usuario '{username}': {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return usuario_valido

    def cambiar_contrasena(self, username, password_actual, password_nueva):
        """Cambia la contraseña si la actual coincide. Retorna True/False."""
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT 1 FROM usuarios WHERE LOWER(username) = LOWER(%s) "
                "AND password = %s",
                (username, password_actual)
            )
            if not cursor.fetchone():
                return False
            cursor.execute(
                "UPDATE usuarios SET password = %s "
                "WHERE LOWER(username) = LOWER(%s)",
                (password_nueva, username)
            )
            conexion.commit()
            return True
        except Error as e:
            print(f" [Auth] Error al cambiar contraseña de '{username}': {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def cambiar_username(self, username_actual, password, nuevo_username):
        """Cambia el nombre de usuario si la contraseña es correcta."""
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT 1 FROM usuarios WHERE LOWER(username) = LOWER(%s) "
                "AND password = %s",
                (username_actual, password)
            )
            if not cursor.fetchone():
                return False
            cursor.execute(
                "UPDATE usuarios SET username = %s "
                "WHERE LOWER(username) = LOWER(%s)",
                (nuevo_username.strip().lower(), username_actual)
            )
            conexion.commit()
            return True
        except Error as e:
            print(f" [Auth] Error al cambiar username de '{username_actual}': {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def inicializar_permisos_usuarios(self) -> bool:
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                ALTER TABLE usuarios
                ADD COLUMN IF NOT EXISTS permisos TEXT
                    DEFAULT 'clientes,productos,tareas,cotizaciones'
            """)
            conexion.commit()
            return True
        except Error as e:
            print(f" [Auth] Error al inicializar permisos de usuarios: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_usuarios(self):
        conexion = self.conectar()
        usuarios = []
        if not conexion: return usuarios
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("SELECT username, rol FROM usuarios ORDER BY username")
            usuarios = cursor.fetchall()
        except Error as e:
            print(f" [Auth] Error al obtener lista de usuarios: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return usuarios

    def obtener_todos_usuarios(self) -> list:
        conexion = self.conectar()
        resultado = []
        if not conexion: return resultado
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT username, rol, COALESCE(permisos,'') "
                "FROM usuarios ORDER BY username"
            )
            resultado = cursor.fetchall()
        except Error as e:
            print(f" [Auth] Error al obtener todos los usuarios: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return resultado

    def obtener_permisos_usuario(self, username: str) -> list:
        conexion = self.conectar()
        if not conexion: return []
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT COALESCE(permisos,'') FROM usuarios "
                "WHERE LOWER(username) = LOWER(%s)",
                (username,)
            )
            fila = cursor.fetchone()
            if not fila or not fila[0]: return []
            return [m.strip() for m in fila[0].split(',') if m.strip()]
        except Error as e:
            print(f" [Auth] Error al obtener permisos de '{username}': {e}")
            return []
        finally:
            if cursor: cursor.close()
            conexion.close()

    def crear_usuario(self, username: str, password: str, rol: str, permisos: str) -> bool:
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "INSERT INTO usuarios (username, password, rol, permisos) "
                "VALUES (%s, %s, %s, %s)",
                (username.strip().lower(), password, rol, permisos)
            )
            conexion.commit()
            return True
        except Error as e:
            print(f" [Auth] Error al crear usuario '{username}': {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def actualizar_usuario(self, username_actual: str, nuevo_username: str,
                           rol: str, permisos: str) -> bool:
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                UPDATE usuarios
                SET username = %s, rol = %s, permisos = %s
                WHERE LOWER(username) = LOWER(%s)
            """, (nuevo_username.strip().lower(), rol, permisos, username_actual))
            if cursor.rowcount == 0:
                conexion.rollback()
                return False
            conexion.commit()
            return True
        except Error as e:
            print(f" [Auth] Error al actualizar usuario '{username_actual}': {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def actualizar_password_usuario(self, username: str, nueva_password: str) -> bool:
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "UPDATE usuarios SET password = %s WHERE LOWER(username) = LOWER(%s)",
                (nueva_password, username)
            )
            if cursor.rowcount == 0:
                conexion.rollback()
                return False
            conexion.commit()
            return True
        except Error as e:
            print(f" [Auth] Error al cambiar contraseña de '{username}': {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def eliminar_usuario(self, username: str) -> bool:
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'Admin'")
            total_admins = cursor.fetchone()[0]
            cursor.execute("SELECT rol FROM usuarios WHERE LOWER(username) = LOWER(%s)", (username,))
            fila = cursor.fetchone()
            if not fila: return False
            if fila[0] == 'Admin' and total_admins <= 1:
                return False
            cursor.execute("DELETE FROM usuarios WHERE LOWER(username) = LOWER(%s)", (username,))
            conexion.commit()
            return True
        except Error as e:
            print(f" [Auth] Error al eliminar usuario '{username}': {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    # =========================================================================
    # REPORTES — Productos por rango de fechas (con paginado)
    # =========================================================================

    def contar_productos_por_fecha(self, fecha_inicio, fecha_fin) -> int:
        conexion = self.conectar()
        total = 0
        if not conexion: return total
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM productos
                WHERE fecha_creacion::date BETWEEN %s AND %s
            """, (fecha_inicio, fecha_fin))
            total = cursor.fetchone()[0]
        except Error as e:
            print(f" [Reportes] Error al contar productos por fecha: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return total

    def obtener_productos_por_fecha(self, fecha_inicio, fecha_fin, pagina=1, por_pagina=20) -> dict:
        conexion = self.conectar()
        resultado = {"productos": [], "total": 0, "pagina": pagina, "por_pagina": por_pagina, "total_paginas": 0}
        if not conexion: return resultado
        cursor = None
        try:
            cursor = conexion.cursor()

            cursor.execute("""
                SELECT COUNT(*) FROM productos
                WHERE fecha_creacion::date BETWEEN %s AND %s
            """, (fecha_inicio, fecha_fin))
            total = cursor.fetchone()[0]
            resultado["total"] = total
            resultado["total_paginas"] = max(1, -(-total // por_pagina))

            offset = (pagina - 1) * por_pagina
            cursor.execute("""
                SELECT sku, nombre, marca, categoria, COALESCE(precio, 0) AS precio, existencia, fecha_creacion
                FROM productos
                WHERE fecha_creacion::date BETWEEN %s AND %s
                ORDER BY fecha_creacion DESC
                LIMIT %s OFFSET %s
            """, (fecha_inicio, fecha_fin, por_pagina, offset))
            resultado["productos"] = cursor.fetchall()
        except Error as e:
            print(f" [Reportes] Error al obtener productos por fecha: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return resultado

    # =========================================================================
    # MÓDULO ESTADÍSTICAS — Contadores para el Dashboard
    # =========================================================================

    def contar_productos(self):
        conexion = self.conectar()
        total = 0
        if not conexion: return total
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("SELECT COUNT(*) FROM productos")
            total = cursor.fetchone()[0]
        except Error as e:
            print(f" [Stats] Error al contar productos: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return total

    def contar_clientes(self):
        conexion = self.conectar()
        total = 0
        if not conexion: return total
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("SELECT COUNT(*) FROM clientes")
            total = cursor.fetchone()[0]
        except Error as e:
            print(f" [Stats] Error al contar clientes: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return total

    # =========================================================================
    # MÓDULO TAREAS — Asignación y seguimiento de tareas internas
    # =========================================================================

    def inicializar_tareas(self):
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tareas (
                    id             SERIAL PRIMARY KEY,
                    cliente_rif    VARCHAR(30)  NOT NULL,
                    cliente_nombre VARCHAR(200) NOT NULL,
                    asignado_a     VARCHAR(100) NOT NULL,
                    tipo_tarea     VARCHAR(60)  NOT NULL,
                    descripcion    TEXT,
                    fecha_limite   DATE         NOT NULL,
                    estado         VARCHAR(20)  DEFAULT 'Pendiente',
                    creado_por     VARCHAR(100) NOT NULL,
                    fecha_creacion TIMESTAMP    DEFAULT NOW()
                )
            """)
            conexion.commit()
            return True
        except Error as e:
            print(f" [Tareas] Error al inicializar tabla de tareas: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def crear_tarea(self, cliente_rif, cliente_nombre, asignado_a,
                    tipo_tarea, descripcion, fecha_limite, creado_por):
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            consulta_sql = """
                INSERT INTO tareas
                    (cliente_rif, cliente_nombre, asignado_a, tipo_tarea,
                     descripcion, fecha_limite, creado_por)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(consulta_sql, (
                cliente_rif, cliente_nombre, asignado_a,
                tipo_tarea, descripcion, fecha_limite, creado_por
            ))
            conexion.commit()
            return True
        except Error as e:
            print(f" [Tareas] Error al crear tarea: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_tareas_asignadas(self, asignado_a):
        conexion = self.conectar()
        tareas = []
        if not conexion: return tareas
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT id, cliente_rif, cliente_nombre, tipo_tarea,
                       descripcion, fecha_limite, estado, creado_por, fecha_creacion
                FROM tareas
                WHERE LOWER(asignado_a) = LOWER(%s)
                  AND estado != 'Completada'
                ORDER BY fecha_limite ASC
            """, (asignado_a,))
            tareas = cursor.fetchall()
        except Error as e:
            print(f" [Tareas] Error al obtener tareas de '{asignado_a}': {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return tareas

    def obtener_todas_tareas(self):
        conexion = self.conectar()
        tareas = []
        if not conexion: return tareas
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT id, cliente_rif, cliente_nombre, asignado_a,
                       tipo_tarea, descripcion, fecha_limite,
                       estado, creado_por, fecha_creacion
                FROM tareas
                ORDER BY fecha_creacion DESC
            """)
            tareas = cursor.fetchall()
        except Error as e:
            print(f" [Tareas] Error al obtener todas las tareas: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return tareas

    def actualizar_estado_tarea(self, tarea_id, nuevo_estado):
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "UPDATE tareas SET estado = %s WHERE id = %s",
                (nuevo_estado, tarea_id)
            )
            conexion.commit()
            return True
        except Error as e:
            print(f" [Tareas] Error al actualizar estado de tarea #{tarea_id}: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def contar_tareas_pendientes(self, asignado_a):
        conexion = self.conectar()
        total = 0
        if not conexion: return total
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM tareas
                WHERE LOWER(asignado_a) = LOWER(%s)
                  AND estado != 'Completada'
            """, (asignado_a,))
            total = cursor.fetchone()[0]
        except Error as e:
            print(f" [Tareas] Error al contar tareas de '{asignado_a}': {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return total

    # =========================================================================
    # MÓDULO COTIZACIONES — Presupuestos para clientes
    # =========================================================================

    def inicializar_cotizaciones(self):
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cotizaciones (
                    id             SERIAL PRIMARY KEY,
                    numero         VARCHAR(25)   NOT NULL UNIQUE,
                    cliente_rif    VARCHAR(30)   NOT NULL,
                    cliente_nombre VARCHAR(200)  NOT NULL,
                    estado         VARCHAR(20)   DEFAULT 'Borrador',
                    notas          TEXT,
                    total_usd      NUMERIC(12,2) DEFAULT 0,
                    creado_por     VARCHAR(100)  NOT NULL,
                    fecha_creacion TIMESTAMP     DEFAULT NOW()
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cotizacion_items (
                    id              SERIAL PRIMARY KEY,
                    cotizacion_id   INTEGER       NOT NULL
                                    REFERENCES cotizaciones(id) ON DELETE CASCADE,
                    sku             VARCHAR(100)  NOT NULL,
                    nombre_producto VARCHAR(300)  NOT NULL,
                    cantidad        INTEGER       NOT NULL DEFAULT 1,
                    precio_unitario NUMERIC(12,2) NOT NULL,
                    subtotal        NUMERIC(12,2) NOT NULL
                )
            """)
            conexion.commit()
            return True
        except Error as e:
            print(f" [Cotiz] Error al inicializar tablas de cotizaciones: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def _siguiente_numero_cotizacion(self, cursor, anio: int) -> str:
        cursor.execute(
            "SELECT COUNT(*) FROM cotizaciones WHERE numero LIKE %s",
            (f"COT-{anio}-%",)
        )
        n = cursor.fetchone()[0] + 1
        return f"COT-{anio}-{n:04d}"

    def agregar_item_cotizacion(self, cotizacion_id: int, sku: str,
                               nombre: str, cantidad: int,
                               precio_unitario: float) -> bool:
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            subtotal = cantidad * precio_unitario
            cursor.execute("""
                INSERT INTO cotizacion_items
                    (cotizacion_id, sku, nombre_producto, cantidad, precio_unitario, subtotal)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (cotizacion_id, sku, nombre, cantidad, precio_unitario, subtotal))
            
            cursor.execute("""
                UPDATE cotizaciones
                SET total_usd = (
                    SELECT COALESCE(SUM(subtotal), 0)
                    FROM cotizacion_items
                    WHERE cotizacion_id = %s
                )
                WHERE id = %s
            """, (cotizacion_id, cotizacion_id))
            conexion.commit()
            return True
        except Error as e:
            print(f" [Cotiz] Error al agregar ítem a cotización #{cotizacion_id}: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def crear_cotizacion(self, cliente_rif, cliente_nombre, creado_por,
                         items: list[dict], notas: str = "") -> int | None:
        conexion = self.conectar()
        if not conexion: return None
        cursor = None
        try:
            from datetime import datetime
            cursor = conexion.cursor()
            anio = datetime.now().year
            numero = self._siguiente_numero_cotizacion(cursor, anio)

            total = sum(float(it['cantidad']) * float(it['precio_unitario']) for it in items)

            cursor.execute("""
                INSERT INTO cotizaciones
                    (numero, cliente_rif, cliente_nombre, creado_por, notas, total_usd)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (numero, cliente_rif, cliente_nombre, creado_por, notas, total))
            cotizacion_id = cursor.fetchone()[0]

            for it in items:
                subtotal = float(it['cantidad']) * float(it['precio_unitario'])
                cursor.execute("""
                    INSERT INTO cotizacion_items
                        (cotizacion_id, sku, nombre_producto, cantidad, precio_unitario, subtotal)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    cotizacion_id, it['sku'], it['nombre'],
                    int(it['cantidad']), float(it['precio_unitario']), subtotal
                ))

            conexion.commit()
            return cotizacion_id
        except Error as e:
            print(f" [Cotiz] Error al crear cotización: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    # ─── DEPURACIÓN: Eliminar activos huérfanos ─────────────────────────

    def obtener_ids_rutas_todos(self) -> list:
        """Retorna [(id, ruta_archivo), ...] de todos los activos digitales."""
        conexion = self.conectar()
        if not conexion: return []
        cursor = None
        resultados = []
        try:
            cursor = conexion.cursor()
            pk = self._pk_activos
            cursor.execute(f"SELECT {pk}, ruta_archivo FROM activos_digitales")
            resultados = cursor.fetchall()
        except Error as e:
            print(f" [DAM] Error al obtener todos los activos: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return resultados

    def eliminar_activo_por_id(self, activo_id: int) -> bool:
        """Elimina un registro de activo digital por su ID. Retorna True/False."""
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            pk = self._pk_activos
            cursor.execute(f"DELETE FROM activos_digitales WHERE {pk} = %s", (activo_id,))
            conexion.commit()
            return cursor.rowcount > 0
        except Error as e:
            print(f" [DAM] Error al eliminar activo #{activo_id}: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_cotizaciones_por_cliente(self, cliente_rif: str) -> list:
        conexion = self.conectar()
        resultado = []
        if not conexion: return resultado
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT id, numero, estado, total_usd, creado_por, fecha_creacion
                FROM cotizaciones
                WHERE UPPER(cliente_rif) = UPPER(%s)
                ORDER BY fecha_creacion DESC
            """, (cliente_rif,))
            resultado = cursor.fetchall()
        except Error as e:
            print(f" [Cotiz] Error al obtener cotizaciones del cliente '{cliente_rif}': {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return resultado

    def obtener_cotizaciones(self, estado: str = None) -> list:
        conexion = self.conectar()
        resultado = []
        if not conexion: return resultado
        cursor = None
        try:
            cursor = conexion.cursor()
            if estado:
                cursor.execute("""
                    SELECT id, numero, cliente_nombre, estado,
                           total_usd, creado_por, fecha_creacion
                    FROM cotizaciones
                    WHERE estado = %s
                    ORDER BY fecha_creacion DESC
                """, (estado,))
            else:
                cursor.execute("""
                    SELECT id, numero, cliente_nombre, estado,
                           total_usd, creado_por, fecha_creacion
                    FROM cotizaciones
                    ORDER BY fecha_creacion DESC
                """)
            resultado = cursor.fetchall()
        except Error as e:
            print(f" [Cotiz] Error al listar cotizaciones: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return resultado

    def obtener_cotizacion_con_items(self, cotizacion_id: int) -> dict | None:
        conexion = self.conectar()
        if not conexion: return None
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT id, numero, cliente_rif, cliente_nombre,
                       estado, notas, total_usd, creado_por, fecha_creacion
                FROM cotizaciones
                WHERE id = %s
            """, (cotizacion_id,))
            cabecera = cursor.fetchone()
            if not cabecera: return None

            cursor.execute("""
                SELECT id, sku, nombre_producto, cantidad,
                       precio_unitario, subtotal
                FROM cotizacion_items
                WHERE cotizacion_id = %s
                ORDER BY id
            """, (cotizacion_id,))
            items = cursor.fetchall()
            return {'cabecera': cabecera, 'items': items}
        except Error as e:
            print(f" [Cotiz] Error al obtener cotización #{cotizacion_id}: {e}")
            return None
        finally:
            if cursor: cursor.close()
            conexion.close()

    def actualizar_estado_cotizacion(self, cotizacion_id: int, nuevo_estado: str) -> bool:
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "UPDATE cotizaciones SET estado = %s WHERE id = %s",
                (nuevo_estado, cotizacion_id)
            )
            if cursor.rowcount == 0:
                conexion.rollback()
                return False
            conexion.commit()
            return True
        except Error as e:
            print(f" [Cotiz] Error al actualizar cotización #{cotizacion_id}: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()