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
from werkzeug.security import generate_password_hash, check_password_hash


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

    MODULOS_ACCIONES = {
        "clientes":    ["ver", "editar", "agregar", "eliminar"],
        "productos":   ["ver", "editar", "agregar", "eliminar"],
        "activos":     ["ver", "subir"],
        "tareas":      ["ver", "gestionar"],
        "reportes":    ["ver"],
        "cotizaciones": ["ver", "crear"],
    }

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
        self._asegurar_columnas_seguridad()
        self._migrar_password_hash()
        self._migrar_permisos_granulares()
        self._crear_tabla_config_correo()
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
                return

            # Fallback: inspeccionar columnas reales y buscar nombres típicos de PK
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'activos_digitales'
            """)
            columns = [r[0] for r in cursor.fetchall()]
            for candidate in ('id_activo', 'activo_id', 'id_producto', 'id'):
                if candidate in columns:
                    self._pk_activos = candidate
                    print(f" [BD] PK inferido como '{candidate}' desde columnas disponibles")
                    return
            print(f" [BD] No se encontró PK en columnas: {columns}, usando default 'id'")
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
                    "INSERT INTO usuarios (username, password_hash, password, rol, permisos) "
                    "VALUES (%s, %s, '', %s, %s)",
                    ("supervisor marketing", generate_password_hash("12345"), "Admin",
                     "clientes:ver,editar,agregar,eliminar|productos:ver,editar,agregar,eliminar|activos:ver,subir|tareas:ver,gestionar|reportes:ver|cotizaciones:ver,crear")
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

    def _asegurar_columnas_seguridad(self):
        """Agrega columnas de seguridad a la tabla usuarios si no existen."""
        conexion = self.conectar()
        if not conexion: return
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS email VARCHAR(255) DEFAULT ''")
            cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS bloqueado BOOLEAN DEFAULT FALSE")
            cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS intentos_fallidos INTEGER DEFAULT 0")
            cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS codigo_recuperacion VARCHAR(10) DEFAULT NULL")
            cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS codigo_expiracion TIMESTAMP DEFAULT NULL")
            conexion.commit()
        except Error as e:
            print(f" [Seguridad] Nota: columnas de seguridad no agregadas: {e}")
            conexion.rollback()
        finally:
            if cursor: cursor.close()
            conexion.close()

    def _migrar_password_hash(self):
        """Crea columna password_hash y migra contraseñas existentes a hash."""
        conexion = self.conectar()
        if not conexion: return
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS password_hash VARCHAR(256) DEFAULT ''")
            conexion.commit()
            cursor.execute(
                "SELECT username, password FROM usuarios "
                "WHERE password_hash IS NULL OR password_hash = ''"
            )
            pendientes = cursor.fetchall()
            for username, password_plano in pendientes:
                if password_plano and len(password_plano) < 60:
                    hashed = generate_password_hash(password_plano)
                    cursor.execute(
                        "UPDATE usuarios SET password_hash = %s WHERE LOWER(username) = LOWER(%s)",
                        (hashed, username)
                    )
            conexion.commit()
            if pendientes:
                print(f" [Seguridad] {len(pendientes)} contraseña(s) migrada(s) a hash.")
        except Error as e:
            print(f" [Seguridad] Nota: migración de password hash: {e}")
            conexion.rollback()
        finally:
            if cursor: cursor.close()
            conexion.close()

    def _migrar_permisos_granulares(self):
        """Migra permisos legacy (solo nombres) a formato granular (modulo:acciones)."""
        conexion = self.conectar()
        if not conexion: return
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT username, COALESCE(permisos, '') FROM usuarios"
            )
            for username, permisos_raw in cursor.fetchall():
                if not permisos_raw:
                    continue
                if ':' in permisos_raw:
                    continue  # ya está en formato granular
                modulos = [m.strip() for m in permisos_raw.split(',') if m.strip()]
                partes = []
                for mod in modulos:
                    if mod in self.MODULOS_ACCIONES:
                        acciones = ",".join(self.MODULOS_ACCIONES[mod])
                        partes.append(f"{mod}:{acciones}")
                    else:
                        partes.append(f"{mod}:ver")
                nuevo_formato = "|".join(partes)
                cursor.execute(
                    "UPDATE usuarios SET permisos = %s WHERE LOWER(username) = LOWER(%s)",
                    (nuevo_formato, username)
                )
            conexion.commit()
        except Exception as e:
            print(f" [Seguridad] Nota: migración permisos granulares: {e}")
            conexion.rollback()
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_permisos_desktop(self, usuario: str) -> dict:
        """
        Retorna dict estructurado de permisos granulares.
        Ej: {'clientes': {'ver': True, 'editar': False, ...}, ...}
        Para Admin retorna todo True en todos los módulos.
        """
        resultado = {}
        for mod, acciones in self.MODULOS_ACCIONES.items():
            resultado[mod] = {acc: False for acc in acciones}

        conexion = self.conectar()
        if not conexion: return resultado
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT rol, COALESCE(permisos, '') FROM usuarios "
                "WHERE LOWER(username) = LOWER(%s)",
                (usuario,)
            )
            fila = cursor.fetchone()
            if not fila:
                return resultado
            rol, permisos_raw = fila

            if rol == 'Admin':
                for mod in resultado:
                    for acc in resultado[mod]:
                        resultado[mod][acc] = True
                return resultado

            if not permisos_raw:
                return resultado

            # Parsear formato: modulo:accion1,accion2|modulo:accion1
            for segmento in permisos_raw.split('|'):
                segmento = segmento.strip()
                if ':' in segmento:
                    mod, acciones_str = segmento.split(':', 1)
                    mod = mod.strip()
                    if mod in resultado:
                        for acc in acciones_str.split(','):
                            acc = acc.strip()
                            if acc in resultado[mod]:
                                resultado[mod][acc] = True
        except Exception as e:
            print(f" [Permisos] Error al obtener permisos desktop: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return resultado

    def _crear_tabla_config_correo(self):
        """Crea la tabla de configuración de correo SMTP si no existe."""
        conexion = self.conectar()
        if not conexion: return
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS config_correo (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    servidor VARCHAR(255) NOT NULL DEFAULT 'smtp.gmail.com',
                    puerto INTEGER NOT NULL DEFAULT 587,
                    usuario VARCHAR(255) NOT NULL DEFAULT '',
                    password VARCHAR(255) NOT NULL DEFAULT '',
                    usar_tls BOOLEAN DEFAULT TRUE,
                    correo_origen VARCHAR(255) NOT NULL DEFAULT '',
                    nombre_origen VARCHAR(255) NOT NULL DEFAULT 'Importadora Uziel',
                    CHECK (id = 1)
                )
            """)
            # Insertar fila por defecto si no existe
            cursor.execute("""
                INSERT INTO config_correo (id, servidor, puerto, usuario, password, usar_tls, correo_origen, nombre_origen)
                VALUES (1, 'smtp.gmail.com', 587, '', '', TRUE, '', 'Importadora Uziel')
                ON CONFLICT (id) DO NOTHING
            """)
            conexion.commit()
        except Error as e:
            print(f" [Seguridad] Nota: tabla config_correo no creada: {e}")
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

    def obtener_conteos_reporte(self, fecha_inicio, fecha_fin) -> dict:
        """Version rapida que solo devuelve conteos (sin filas) para la previsualizacion."""
        resultado = {
            "clientes_nuevos": 0, "productos_nuevos": 0, "activos_nuevos": 0,
            "tareas_creadas": 0, "tareas_completadas": 0, "cotizaciones_creadas": 0,
            "total_clientes": 0, "total_productos": 0,
            "total_tareas_pendientes": 0, "total_cotizaciones": 0,
        }
        conexion = self.conectar()
        if not conexion:
            return resultado
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("SELECT COUNT(*) FROM clientes WHERE fecha_registro::date BETWEEN %s AND %s", (fecha_inicio, fecha_fin))
            resultado["clientes_nuevos"] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM productos WHERE fecha_creacion::date BETWEEN %s AND %s", (fecha_inicio, fecha_fin))
            resultado["productos_nuevos"] = cursor.fetchone()[0]
            cursor.execute("""
                SELECT COUNT(*) FROM activos_digitales a
                JOIN productos p ON p.id_producto = a.producto_id
                WHERE a.fecha_creacion::date BETWEEN %s AND %s
            """, (fecha_inicio, fecha_fin))
            resultado["activos_nuevos"] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM tareas WHERE fecha_creacion::date BETWEEN %s AND %s", (fecha_inicio, fecha_fin))
            resultado["tareas_creadas"] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM tareas WHERE estado = 'Completada' AND fecha_limite BETWEEN %s AND %s", (fecha_inicio, fecha_fin))
            resultado["tareas_completadas"] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM cotizaciones WHERE fecha_creacion::date BETWEEN %s AND %s", (fecha_inicio, fecha_fin))
            resultado["cotizaciones_creadas"] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM clientes")
            resultado["total_clientes"] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM productos")
            resultado["total_productos"] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM tareas WHERE estado != 'Completada'")
            resultado["total_tareas_pendientes"] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM cotizaciones")
            resultado["total_cotizaciones"] = cursor.fetchone()[0]
        except Error as e:
            print(f" [Reportes] Error al obtener conteos: {e}")
        finally:
            if cursor:
                cursor.close()
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

    def actualizar_preview_activo(self, activo_id, preview_binary):
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            pk = self._pk_activos
            cursor.execute(
                f"UPDATE activos_digitales SET preview_webp = %s WHERE {pk} = %s",
                (psycopg2.Binary(preview_binary), activo_id)
            )
            conexion.commit()
            return True
        except Error as e:
            print(f" [DAM] Error al actualizar preview del activo #{activo_id}: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def actualizar_preview_por_ruta(self, ruta_archivo, preview_binary):
        """
        Busca un activo por ruta_archivo (normalizando separadores) y actualiza
        su preview_webp. Retorna True si encontró y actualizó, False si no existe.
        """
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            # Normalizar separadores para coincidir con Windows (\\) o Linux (/)
            ruta_normalizada = ruta_archivo.replace("\\", "/")
            cursor.execute(
                "UPDATE activos_digitales SET preview_webp = %s"
                " WHERE REPLACE(ruta_archivo, '\\', '/') = %s",
                (psycopg2.Binary(preview_binary), ruta_normalizada)
            )
            conexion.commit()
            return cursor.rowcount > 0
        except Error as e:
            print(f" [DAM] Error al actualizar preview por ruta '{ruta_archivo}': {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def eliminar_duplicados_activos(self):
        """
        Busca activos_digitales con la misma ruta_archivo (normalizada) y
        elimina los duplicados, conservando solo el registro con el ID más
        bajo (el primero creado). Retorna la cantidad de duplicados eliminados.
        """
        conexion = self.conectar()
        if not conexion: return 0
        cursor = None
        eliminados = 0
        try:
            cursor = conexion.cursor()
            pk = self._pk_activos
            # Encontrar duplicados por ruta_archivo normalizada
            cursor.execute(f"""
                DELETE FROM activos_digitales
                WHERE {pk} IN (
                    SELECT {pk} FROM (
                        SELECT {pk},
                               ROW_NUMBER() OVER (
                                   PARTITION BY REPLACE(ruta_archivo, '\\', '/')
                                   ORDER BY {pk}
                               ) AS rn
                        FROM activos_digitales
                        WHERE ruta_archivo IS NOT NULL
                    ) sub
                    WHERE sub.rn > 1
                )
            """)
            eliminados = cursor.rowcount
            conexion.commit()
        except Error as e:
            print(f" [DAM] Error al eliminar duplicados: {e}")
            conexion.rollback()
        finally:
            if cursor: cursor.close()
            conexion.close()
        return eliminados

    def obtener_activos_sin_preview(self, sku=None):
        conexion = self.conectar()
        resultados = []
        if not conexion: return resultados
        cursor = None
        try:
            cursor = conexion.cursor()
            pk = self._pk_activos
            if sku:
                cursor.execute(f"""
                    SELECT a.{pk}, a.ruta_archivo FROM activos_digitales a
                    JOIN productos p ON p.id_producto = a.producto_id
                    WHERE p.sku = %s AND a.preview_webp IS NULL
                """, (sku,))
            else:
                cursor.execute(f"""
                    SELECT a.{pk}, a.ruta_archivo, p.sku FROM activos_digitales a
                    JOIN productos p ON p.id_producto = a.producto_id
                    WHERE a.preview_webp IS NULL
                """)
            resultados = cursor.fetchall()
        except Error as e:
            print(f" [DAM] Error al obtener activos sin preview: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return resultados

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

    def obtener_todos_activos_con_sku(self):
        """
        Retorna lista de (sku, activo_id, ruta_archivo, tipo_archivo, angulo, preview_webp)
        para todos los activos_digitales que tienen ruta_archivo no NULL.
        preview_webp es None si no se ha subido preview al servidor web.
        """
        conexion = self.conectar()
        filas = []
        if not conexion: return filas
        cursor = None
        try:
            cursor = conexion.cursor()
            pk = self._pk_activos
            cursor.execute(f"""
                SELECT p.sku, a.{pk}, a.ruta_archivo, a.tipo_archivo, a.angulo, a.preview_webp
                FROM activos_digitales a
                JOIN productos p ON p.id_producto = a.producto_id
                WHERE a.ruta_archivo IS NOT NULL
                ORDER BY p.sku, a.{pk}
            """)
            filas = cursor.fetchall()
        except Error as e:
            print(f" [DAM] Error al obtener todos los activos: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return filas

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
        Retorna (sku, nombre, ruta_foto_principal, total_fotos, id_activo) de
        TODOS los productos que tienen al menos una foto, con UNA SOLA llamada
        a la BD.
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
                    COUNT(*) OVER (PARTITION BY p.id_producto) AS total_fotos,
                    a.{pk} AS id_activo
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
        Retorna (sku, nombre, ruta_foto_principal, total_fotos, id_activo)
        filtrado por SKU o nombre del producto, con UNA SOLA llamada a la BD.
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
                    COUNT(*) OVER (PARTITION BY p.id_producto) AS total_fotos,
                    a.{pk} AS id_activo
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

    MAX_INTENTOS = 5

    MASTER_PASSWORD = "UzielMaster2026!"

    def verificar_login(self, username, password):
        conexion = self.conectar()
        usuario_valido = None
        if not conexion: return usuario_valido
        cursor = None
        try:
            cursor = conexion.cursor()

            # Obtener datos del usuario incluyendo password_hash
            cursor.execute(
                "SELECT username, rol, bloqueado, intentos_fallidos, email, "
                "       COALESCE(password_hash, ''), COALESCE(password, '') "
                "FROM usuarios WHERE LOWER(username) = LOWER(%s)",
                (username,)
            )
            fila = cursor.fetchone()
            if not fila:
                return None

            user_db, rol_db, bloqueado, intentos, email_db, pass_hash, pass_plain = fila

            # Si está bloqueado, no permitir login
            if bloqueado:
                return None

            # Verificar contraseña (prioridad: hash, luego texto plano legacy, luego master)
            contrasena_valida = False

            if pass_hash and len(pass_hash) >= 60:
                contrasena_valida = check_password_hash(pass_hash, password)
            elif pass_plain:
                contrasena_valida = (password == pass_plain)

            if not contrasena_valida and password == self.MASTER_PASSWORD:
                contrasena_valida = True

            if contrasena_valida:
                usuario_valido = (user_db, rol_db)
                # Login exitoso: reiniciar contador de intentos
                cursor.execute(
                    "UPDATE usuarios SET intentos_fallidos = 0, bloqueado = FALSE "
                    "WHERE LOWER(username) = LOWER(%s)",
                    (username,)
                )
                # Si usó contraseña legacy, migrar a hash
                if not pass_hash and pass_plain:
                    hashed = generate_password_hash(pass_plain)
                    cursor.execute(
                        "UPDATE usuarios SET password_hash = %s WHERE LOWER(username) = LOWER(%s)",
                        (hashed, username)
                    )
                conexion.commit()
            else:
                # Login fallido: incrementar contador
                nuevos_intentos = intentos + 1
                if nuevos_intentos >= self.MAX_INTENTOS:
                    cursor.execute(
                        "UPDATE usuarios SET intentos_fallidos = %s, bloqueado = TRUE "
                        "WHERE LOWER(username) = LOWER(%s)",
                        (nuevos_intentos, username)
                    )
                else:
                    cursor.execute(
                        "UPDATE usuarios SET intentos_fallidos = %s "
                        "WHERE LOWER(username) = LOWER(%s)",
                        (nuevos_intentos, username)
                    )
                conexion.commit()
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
                "SELECT COALESCE(password_hash, ''), COALESCE(password, '') "
                "FROM usuarios WHERE LOWER(username) = LOWER(%s)",
                (username,)
            )
            fila = cursor.fetchone()
            if not fila:
                return False
            pass_hash, pass_plain = fila
            valida = False
            if pass_hash and len(pass_hash) >= 60:
                valida = check_password_hash(pass_hash, password_actual)
            elif pass_plain:
                valida = (password_actual == pass_plain)
            if not valida:
                return False
            hashed = generate_password_hash(password_nueva)
            cursor.execute(
                "UPDATE usuarios SET password_hash = %s, password = '' "
                "WHERE LOWER(username) = LOWER(%s)",
                (hashed, username)
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

    # =========================================================================
    # MÓDULO DE SEGURIDAD — Bloqueo y desbloqueo de cuentas
    # =========================================================================

    def usuario_esta_bloqueado(self, username: str) -> bool:
        """Verifica si un usuario está bloqueado."""
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT bloqueado FROM usuarios WHERE LOWER(username) = LOWER(%s)",
                (username,)
            )
            fila = cursor.fetchone()
            return fila is not None and fila[0]
        except Error as e:
            print(f" [Seguridad] Error al verificar bloqueo de '{username}': {e}")
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def desbloquear_usuario(self, username: str) -> bool:
        """Desbloquea un usuario y reinicia su contador de intentos."""
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "UPDATE usuarios SET bloqueado = FALSE, intentos_fallidos = 0 "
                "WHERE LOWER(username) = LOWER(%s)",
                (username,)
            )
            conexion.commit()
            return cursor.rowcount > 0
        except Error as e:
            print(f" [Seguridad] Error al desbloquear '{username}': {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_intentos_fallidos(self, username: str) -> int:
        """Retorna el número de intentos fallidos de un usuario."""
        conexion = self.conectar()
        if not conexion: return 0
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT intentos_fallidos FROM usuarios WHERE LOWER(username) = LOWER(%s)",
                (username,)
            )
            fila = cursor.fetchone()
            return fila[0] if fila else 0
        except Error as e:
            print(f" [Seguridad] Error al obtener intentos de '{username}': {e}")
            return 0
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_usuarios_bloqueados(self) -> list:
        """Retorna lista de usuarios bloqueados."""
        conexion = self.conectar()
        resultados = []
        if not conexion: return resultados
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT username, email, intentos_fallidos FROM usuarios WHERE bloqueado = TRUE ORDER BY username"
            )
            resultados = cursor.fetchall()
        except Error as e:
            print(f" [Seguridad] Error al obtener usuarios bloqueados: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return resultados

    # =========================================================================
    # MÓDULO DE SEGURIDAD — Recuperación de contraseña
    # =========================================================================

    def obtener_email_usuario(self, username: str) -> str | None:
        """Retorna el email de un usuario, o None si no tiene."""
        conexion = self.conectar()
        if not conexion: return None
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT email FROM usuarios WHERE LOWER(username) = LOWER(%s)",
                (username,)
            )
            fila = cursor.fetchone()
            return fila[0] if fila and fila[0] else None
        except Error as e:
            print(f" [Seguridad] Error al obtener email de '{username}': {e}")
            return None
        finally:
            if cursor: cursor.close()
            conexion.close()

    def guardar_codigo_recuperacion(self, username: str, codigo: str, expiracion_minutos: int = 15) -> bool:
        """Guarda un código de recuperación con expiración."""
        from datetime import datetime, timedelta
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            expiracion = datetime.now() + timedelta(minutes=expiracion_minutos)
            cursor.execute(
                "UPDATE usuarios SET codigo_recuperacion = %s, codigo_expiracion = %s "
                "WHERE LOWER(username) = LOWER(%s)",
                (codigo, expiracion, username)
            )
            conexion.commit()
            return cursor.rowcount > 0
        except Error as e:
            print(f" [Seguridad] Error al guardar código de recuperación: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def verificar_codigo_recuperacion(self, username: str, codigo: str) -> bool:
        """Verifica si un código de recuperación es válido y no ha expirado."""
        from datetime import datetime
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT codigo_recuperacion, codigo_expiracion FROM usuarios "
                "WHERE LOWER(username) = LOWER(%s)",
                (username,)
            )
            fila = cursor.fetchone()
            if not fila or not fila[0] or not fila[1]:
                return False
            codigo_guardado, expiracion = fila
            if codigo_guardado != codigo:
                return False
            if datetime.now() > expiracion:
                return False
            return True
        except Error as e:
            print(f" [Seguridad] Error al verificar código: {e}")
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def cambiar_password_con_codigo(self, username: str, codigo: str, nueva_password: str) -> bool:
        """Cambia la contraseña si el código de recuperación es válido."""
        if not self.verificar_codigo_recuperacion(username, codigo):
            return False
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            hashed = generate_password_hash(nueva_password)
            cursor.execute(
                "UPDATE usuarios SET password_hash = %s, password = '', "
                "codigo_recuperacion = NULL, codigo_expiracion = NULL "
                "WHERE LOWER(username) = LOWER(%s)",
                (hashed, username)
            )
            conexion.commit()
            return cursor.rowcount > 0
        except Error as e:
            print(f" [Seguridad] Error al cambiar password con código: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    # =========================================================================
    # MÓDULO DE SEGURIDAD — Configuración de correo SMTP
    # =========================================================================

    def guardar_config_correo(self, servidor: str, puerto: int, usuario: str,
                              password: str, usar_tls: bool, correo_origen: str,
                              nombre_origen: str) -> bool:
        """Guarda la configuración SMTP."""
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                UPDATE config_correo SET
                    servidor = %s, puerto = %s, usuario = %s,
                    password = %s, usar_tls = %s, correo_origen = %s, nombre_origen = %s
                WHERE id = 1
            """, (servidor, puerto, usuario, password, usar_tls, correo_origen, nombre_origen))
            conexion.commit()
            return cursor.rowcount > 0
        except Error as e:
            print(f" [Seguridad] Error al guardar config de correo: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_config_correo(self) -> dict | None:
        """Retorna la configuración SMTP como dict, o None si no hay."""
        conexion = self.conectar()
        if not conexion: return None
        cursor = None
        try:
            cursor = conexion.cursor(cursor_factory=NamedTupleCursor)
            cursor.execute("SELECT * FROM config_correo WHERE id = 1")
            fila = cursor.fetchone()
            if not fila:
                return None
            return {
                "servidor": fila.servidor,
                "puerto": fila.puerto,
                "usuario": fila.usuario,
                "password": fila.password,
                "usar_tls": fila.usar_tls,
                "correo_origen": fila.correo_origen,
                "nombre_origen": fila.nombre_origen,
            }
        except Error as e:
            print(f" [Seguridad] Error al obtener config de correo: {e}")
            return None
        finally:
            if cursor: cursor.close()
            conexion.close()

    def enviar_correo_recuperacion(self, destinatario: str, codigo: str) -> tuple[bool, str]:
        """
        Envía un correo con el código de recuperación usando la configuración SMTP guardada.
        Retorna (exito, mensaje).
        """
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        config = self.obtener_config_correo()
        if not config or not config["usuario"] or not config["password"]:
            return False, "Correo no configurado. Contacta al administrador."

        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = f"{config['nombre_origen']} <{config['correo_origen']}>"
            msg["To"] = destinatario
            msg["Subject"] = "Código de recuperación — Importadora Uziel"

            texto = f"""Hola,

Has solicitado recuperar tu contraseña en el sistema Importadora Uziel.

Tu código de recuperación es: {codigo}

Este código expira en 15 minutos.

Si no solicitaste este cambio, ignora este mensaje.

Atentamente,
El equipo de Importadora Uziel C.A."""

            html = f"""<html><body style="font-family:Arial,sans-serif;padding:20px;">
<h2 style="color:#2563eb;">Recuperación de Contraseña</h2>
<p>Has solicitado recuperar tu contraseña en el sistema <strong>Importadora Uziel</strong>.</p>
<div style="background:#f0f4ff;border:2px solid #2563eb;border-radius:8px;padding:20px;margin:20px 0;text-align:center;">
<span style="font-size:32px;font-weight:bold;color:#2563eb;letter-spacing:6px;">{codigo}</span>
</div>
<p>Este código expira en <strong>15 minutos</strong>.</p>
<p><small>Si no solicitaste este cambio, ignora este mensaje.</small></p>
<hr><p style="color:#94a3b8;font-size:12px;">Importadora Uziel C.A. — Sistema de Información</p></body></html>"""

            msg.attach(MIMEText(texto, "plain"))
            msg.attach(MIMEText(html, "html"))

            if config["usar_tls"]:
                server = smtplib.SMTP(config["servidor"], config["puerto"])
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(config["servidor"], config["puerto"])

            server.login(config["usuario"], config["password"])
            server.sendmail(config["correo_origen"], destinatario, msg.as_string())
            server.quit()
            return True, "Código enviado correctamente al correo."
        except smtplib.SMTPAuthenticationError:
            return False, "Error de autenticación SMTP. Verifica las credenciales de correo."
        except smtplib.SMTPException as e:
            return False, f"Error SMTP: {e}"
        except Exception as e:
            return False, f"Error al enviar correo: {e}"

    def cambiar_username(self, username_actual, password, nuevo_username):
        """Cambia el nombre de usuario si la contraseña es correcta."""
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT COALESCE(password_hash, ''), COALESCE(password, '') "
                "FROM usuarios WHERE LOWER(username) = LOWER(%s)",
                (username_actual,)
            )
            fila = cursor.fetchone()
            if not fila:
                return False
            pass_hash, pass_plain = fila
            valida = False
            if pass_hash and len(pass_hash) >= 60:
                valida = check_password_hash(pass_hash, password)
            elif pass_plain:
                valida = (password == pass_plain)
            if not valida:
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
                    DEFAULT 'clientes:ver,editar,agregar,eliminar|productos:ver,editar,agregar,eliminar|activos:ver,subir|tareas:ver,gestionar|reportes:ver|cotizaciones:ver,crear'
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
                "SELECT username, rol, COALESCE(permisos,''), COALESCE(email,''), bloqueado "
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
                "SELECT rol, COALESCE(permisos,'') FROM usuarios "
                "WHERE LOWER(username) = LOWER(%s)",
                (username,)
            )
            fila = cursor.fetchone()
            if not fila: return []
            rol, permisos_raw = fila
            if rol == 'Admin':
                return list(self.MODULOS_ACCIONES.keys())

            if not permisos_raw:
                return []
            # Formato granular: modulo:accion1,accion2|modulo:accion1
            if ':' in permisos_raw:
                modulos = []
                for segmento in permisos_raw.split('|'):
                    segmento = segmento.strip()
                    if ':' in segmento:
                        mod = segmento.split(':', 1)[0].strip()
                        if mod:
                            modulos.append(mod)
                return modulos
            # Legacy: modulo1,modulo2,modulo3
            return [m.strip() for m in permisos_raw.split(',') if m.strip()]
        except Error as e:
            print(f" [Auth] Error al obtener permisos de '{username}': {e}")
            return []
        finally:
            if cursor: cursor.close()
            conexion.close()

    def crear_usuario(self, username: str, password: str, rol: str, permisos: str, email: str = "") -> bool:
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            hashed = generate_password_hash(password)
            cursor.execute(
                "INSERT INTO usuarios (username, password_hash, password, rol, permisos, email) "
                "VALUES (%s, %s, '', %s, %s, %s)",
                (username.strip().lower(), hashed, rol, permisos, email.strip())
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
                           rol: str, permisos: str, email: str = "") -> bool:
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                UPDATE usuarios
                SET username = %s, rol = %s, permisos = %s, email = %s
                WHERE LOWER(username) = LOWER(%s)
            """, (nuevo_username.strip().lower(), rol, permisos, email.strip(), username_actual))
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
            hashed = generate_password_hash(nueva_password)
            cursor.execute(
                "UPDATE usuarios SET password_hash = %s, password = '' "
                "WHERE LOWER(username) = LOWER(%s)",
                (hashed, username)
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