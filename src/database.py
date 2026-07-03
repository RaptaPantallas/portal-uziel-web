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
import time
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

class ConnectionWrapper:
    """Wrapper para interceptar el método close() de las conexiones del pool."""
    def __init__(self, conexion, pool):
        self._conn = conexion
        self._pool = pool

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._conn.__exit__(exc_type, exc_val, exc_tb)

    def close(self):
        if self._pool:
            try:
                self._pool.putconn(self._conn)
            except Exception:
                try:
                    self._conn.close()
                except Exception:
                    pass
        else:
            try:
                self._conn.close()
            except Exception:
                pass

    def rollback(self):
        try:
            self._conn.rollback()
        except Exception:
            pass


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
        "usuarios":    ["gestionar"],
        "gastos":      ["ver", "gestionar"],
    }

    # Pool estático de conexiones (se inicializa una sola vez para toda la aplicación)
    _pool = None

    @classmethod
    def _inicializar_pool(cls, url):
        if cls._pool is None:
            try:
                from psycopg2.pool import ThreadedConnectionPool
                # Pool con un rango de 2 a 20 conexiones simultáneas
                cls._pool = ThreadedConnectionPool(2, 20, url)
                print(" [BD] Pool de conexiones a PostgreSQL inicializado con éxito.")
            except Exception as e:
                print(f" [BD] Error crítico al inicializar pool de conexiones: {e}")

    def __init__(self):
        """Inicializa la clase con la URL de conexión configurada arriba."""
        self.url_nube = URL_BASE_DE_DATOS
        self._pk_activos = "id"
        # Aseguramos la existencia del pool de conexiones
        if ConexionBD._pool is None:
            ConexionBD._inicializar_pool(self.url_nube)
        # Ejecutamos una actualización rápida para asegurar que las nuevas columnas existen
        self.actualizar_esquema_productos()
        self.actualizar_esquema_clientes()
        self._asegurar_columna_es_principal()
        self._descubrir_pk_activos()
        self._sembrar_usuario_supervisor()
        self._asegurar_columna_fecha_creacion_activos()
        self._asegurar_columna_preview_webp()
        self._asegurar_columnas_seguridad()
        self._migrar_password_hash()
        self._migrar_permisos_granulares()
        self._crear_columna_superadmin()
        self._sembrar_usuario_jefe()
        self._crear_tabla_config_correo()
        self._crear_indices_rendimiento()
        self.inicializar_alianzas()
        self.inicializar_categorias()
        self._crear_tabla_auditoria_acciones()

    def conectar(self):
        """Establece y retorna una conexión activa a PostgreSQL desde el pool, envuelta para liberación segura."""
        intentos = 0
        max_intentos = 3

        while intentos < max_intentos:
            if ConexionBD._pool is None:
                ConexionBD._inicializar_pool(self.url_nube)
            
            conexion = None
            usando_pool = False
            
            if ConexionBD._pool:
                try:
                    conexion = ConexionBD._pool.getconn()
                    usando_pool = True
                    
                    if conexion.closed != 0:
                        raise Exception("Conexión marcada como cerrada por psycopg2.")
                    
                    with conexion.cursor() as cursor:
                        cursor.execute("SELECT 1")
                except Exception as e:
                    if conexion:
                        try:
                            ConexionBD._pool.putconn(conexion, close=True)
                        except:
                            pass
                    conexion = None
                    usando_pool = False

            if not conexion:
                try:
                    conexion = psycopg2.connect(self.url_nube)
                    with conexion.cursor() as cursor:
                        cursor.execute("SELECT 1")
                except Exception as e:
                    print(f" [BD] Error en conexión a PostgreSQL (Intento {intentos+1}): {e}")
                    conexion = None

            if conexion:
                return ConnectionWrapper(conexion, ConexionBD._pool if usando_pool else None)
            
            intentos += 1
            time.sleep(0.5)

        print(" [BD] Error Crítico: No se pudo obtener conexión válida después de múltiples intentos.")
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

    def actualizar_esquema_clientes(self):
        """
        Asegura que la tabla 'clientes' tenga las columnas 'pais', 'estado' y 'municipio'.
        Usa comandos IF NOT EXISTS que son 100% seguros de ejecutar múltiples veces.
        """
        conexion = self.conectar()
        if not conexion:
            return
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS pais VARCHAR(100) DEFAULT 'Venezuela'")
            cursor.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS estado VARCHAR(100) DEFAULT ''")
            cursor.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS municipio VARCHAR(100) DEFAULT ''")
            conexion.commit()
        except Error as e:
            print(f" [BD] Nota: No se pudo verificar el esquema de clientes: {e}")
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

    def _crear_columna_superadmin(self):
        """Agrega columna superadmin a la tabla usuarios si no existe."""
        conexion = self.conectar()
        if not conexion: return
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS superadmin BOOLEAN DEFAULT FALSE")
            conexion.commit()
        except Error as e:
            print(f" [Seguridad] Nota: columna superadmin no agregada: {e}")
            conexion.rollback()
        finally:
            if cursor: cursor.close()
            conexion.close()

    def _sembrar_usuario_jefe(self):
        """Crea el usuario 'jefe' como superadmin si no existe."""
        conexion = self.conectar()
        if not conexion: return
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("SELECT 1 FROM usuarios WHERE LOWER(username) = 'jefe'")
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO usuarios (username, password_hash, password, rol, permisos, superadmin) "
                    "VALUES (%s, %s, '', %s, %s, TRUE)",
                    ("jefe", generate_password_hash("UzielMaster2026!"), "Admin",
                     "clientes:ver,editar,agregar,eliminar|productos:ver,editar,agregar,eliminar|"
                     "activos:ver,subir|tareas:ver,gestionar|reportes:ver|cotizaciones:ver,crear")
                )
                conexion.commit()
                print(" [Auth] Usuario 'jefe' (superadmin) creado.")
            else:
                # Asegurar que el flag superadmin esté activo para jefe
                cursor.execute(
                    "UPDATE usuarios SET superadmin = TRUE WHERE LOWER(username) = 'jefe'"
                )
                conexion.commit()
        except Exception as e:
            print(f" [Auth] No se pudo sembrar usuario jefe: {e}")
            conexion.rollback()
        finally:
            if cursor: cursor.close()
            conexion.close()

    def es_superadmin(self, username: str) -> bool:
        """Retorna True si el usuario es superadmin (control total)."""
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT superadmin FROM usuarios WHERE LOWER(username) = LOWER(%s)",
                (username,)
            )
            fila = cursor.fetchone()
            return bool(fila and fila[0])
        except Exception as e:
            print(f" [Seguridad] Error al verificar superadmin: {e}")
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_permisos_desktop(self, usuario: str) -> dict:
        """
        Retorna dict estructurado de permisos granulares.
        Ej: {'clientes': {'ver': True, 'editar': False, ...}, ...}
        Para superadmin retorna todo True en todos los módulos.
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

            # superadmin bypass — tiene acceso total
            # También obtener el flag superadmin para no hacer otra query
            cursor.execute(
                "SELECT superadmin FROM usuarios WHERE LOWER(username) = LOWER(%s)",
                (usuario,)
            )
            sa_fila = cursor.fetchone()
            es_super = bool(sa_fila and sa_fila[0])
            if es_super:
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

    def _crear_tabla_auditoria_acciones(self):
        """Crea la tabla de auditoria_acciones si no existe."""
        conexion = self.conectar()
        if not conexion: return
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auditoria_acciones (
                    id SERIAL PRIMARY KEY,
                    usuario VARCHAR(100) NOT NULL,
                    accion VARCHAR(255) NOT NULL,
                    detalle TEXT,
                    fecha_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conexion.commit()
        except Error as e:
            print(f" [BD] Nota: no se pudo crear la tabla auditoria_acciones: {e}")
            conexion.rollback()
        finally:
            if cursor: cursor.close()
            conexion.close()

    def registrar_accion_auditoria(self, usuario, accion, detalle):
        """Registra una acción de usuario en la bitácora de auditoría."""
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                INSERT INTO auditoria_acciones (usuario, accion, detalle)
                VALUES (%s, %s, %s)
            """, (usuario or 'invitado', accion, detalle))
            conexion.commit()
            return True
        except Error as e:
            print(f" [BD] Error al registrar acción de auditoría: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def verificar_contrasena_usuario(self, username, password) -> bool:
        """Verifica la contraseña de un usuario de forma simple, sin alterar contadores de intentos fallidos."""
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT password_hash FROM usuarios WHERE LOWER(username) = LOWER(%s)",
                (username,)
            )
            row = cursor.fetchone()
            if not row:
                return False
            pass_hash = row[0]
            if password == self.MASTER_PASSWORD:
                return True
            return check_password_hash(pass_hash, password)
        except Exception:
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_logs_auditoria(self, fecha_inicio, fecha_fin, termino=""):
        """Obtiene la bitácora de auditoría en un rango de fechas con filtro opcional."""
        conexion = self.conectar()
        if not conexion: return []
        cursor = None
        try:
            cursor = conexion.cursor()
            
            params = [fecha_inicio, fecha_fin]
            search_clause = ""
            if termino.strip():
                palabras = termino.strip().split()
                clauses = []
                for p in palabras:
                    like_val = f"%{p}%"
                    clauses.append("""(
                        usuario ILIKE %s OR 
                        accion ILIKE %s OR 
                        detalle ILIKE %s OR 
                        TO_CHAR(fecha_hora, 'DD/MM/YYYY HH24:MI:SS') ILIKE %s OR
                        TO_CHAR(fecha_hora, 'YYYY-MM-DD') ILIKE %s
                    )""")
                    params.extend([like_val, like_val, like_val, like_val, like_val])
                search_clause = " AND " + " AND ".join(clauses)

            query = f"""
                SELECT id, usuario, accion, detalle, fecha_hora
                FROM auditoria_acciones
                WHERE fecha_hora::date BETWEEN %s AND %s {search_clause}
                ORDER BY fecha_hora DESC
            """
            cursor.execute(query, tuple(params))
            return cursor.fetchall()
        except Error as e:
            print(f" [BD] Error al obtener logs de auditoría: {e}")
            return []
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_logs_auditoria_paginados(self, fecha_inicio, fecha_fin, pagina=1, por_pagina=5, termino="") -> dict:
        """Obtiene la bitácora de auditoría paginada en un rango de fechas con filtro opcional."""
        conexion = self.conectar()
        resultado = {"logs": [], "total": 0, "pagina": pagina, "por_pagina": por_pagina, "total_paginas": 0}
        if not conexion: return resultado
        cursor = None
        try:
            cursor = conexion.cursor()
            
            params_count = [fecha_inicio, fecha_fin]
            params_select = [fecha_inicio, fecha_fin]
            search_clause = ""
            if termino.strip():
                palabras = termino.strip().split()
                clauses = []
                for p in palabras:
                    like_val = f"%{p}%"
                    clauses.append("""(
                        usuario ILIKE %s OR 
                        accion ILIKE %s OR 
                        detalle ILIKE %s OR 
                        TO_CHAR(fecha_hora, 'DD/MM/YYYY HH24:MI:SS') ILIKE %s OR
                        TO_CHAR(fecha_hora, 'YYYY-MM-DD') ILIKE %s
                    )""")
                    params_count.extend([like_val, like_val, like_val, like_val, like_val])
                    params_select.extend([like_val, like_val, like_val, like_val, like_val])
                search_clause = " AND " + " AND ".join(clauses)

            cursor.execute(f"""
                SELECT COUNT(*) FROM auditoria_acciones
                WHERE fecha_hora::date BETWEEN %s AND %s {search_clause}
            """, tuple(params_count))
            total = cursor.fetchone()[0]
            resultado["total"] = total
            resultado["total_paginas"] = max(1, -(-total // por_pagina))

            offset = (pagina - 1) * por_pagina
            query = f"""
                SELECT id, usuario, accion, detalle, fecha_hora
                FROM auditoria_acciones
                WHERE fecha_hora::date BETWEEN %s AND %s {search_clause}
                ORDER BY fecha_hora DESC
                LIMIT %s OFFSET %s
            """
            params_select.extend([por_pagina, offset])
            cursor.execute(query, tuple(params_select))
            resultado["logs"] = cursor.fetchall()
        except Error as e:
            print(f" [Reportes] Error al obtener logs de auditoría paginados: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return resultado

    def obtener_ultimos_eventos_especiales(self):
        """Obtiene el último registro de importación de Excel y de carga de fotos."""
        conexion = self.conectar()
        resultado = {
            "ultimo_excel": None,
            "ultima_foto": None
        }
        if not conexion: return resultado
        cursor = None
        try:
            cursor = conexion.cursor()
            # Última importación de Excel
            cursor.execute("""
                SELECT usuario, fecha_hora, detalle
                FROM auditoria_acciones
                WHERE accion = 'Importación Excel'
                ORDER BY fecha_hora DESC
                LIMIT 1
            """)
            resultado["ultimo_excel"] = cursor.fetchone()

            # Fallback para Último Excel si no hay log: ver último producto creado
            if not resultado["ultimo_excel"]:
                cursor.execute("""
                    SELECT 'Sistema', fecha_creacion, 'Creado desde base de datos'
                    FROM productos
                    ORDER BY fecha_creacion DESC
                    LIMIT 1
                """)
                resultado["ultimo_excel"] = cursor.fetchone()

            # Última subida de foto
            cursor.execute("""
                SELECT usuario, fecha_hora, detalle
                FROM auditoria_acciones
                WHERE accion = 'Subida Foto' OR accion = 'Vinculación Foto'
                ORDER BY fecha_hora DESC
                LIMIT 1
            """)
            resultado["ultima_foto"] = cursor.fetchone()

            # Fallback para Última Foto si no hay log: ver último activo digital creado
            if not resultado["ultima_foto"]:
                cursor.execute("""
                    SELECT 'Sistema', fecha_creacion, ruta_archivo
                    FROM activos_digitales
                    ORDER BY fecha_creacion DESC
                    LIMIT 1
                """)
                resultado["ultima_foto"] = cursor.fetchone()
        except Error as e:
            print(f" [BD] Error al obtener últimos eventos especiales: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return resultado

    # =========================================================================
    # MÓDULO REPORTES — Datos para generación de informes
    # =========================================================================

    def obtener_datos_reporte(self, fecha_inicio, fecha_fin, termino="") -> dict:
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
            "logs_auditoria": [],
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

            # Logs de auditoria en el rango
            params_audit = [fecha_inicio, fecha_fin]
            search_clause = ""
            if termino.strip():
                palabras = termino.strip().split()
                clauses = []
                for p in palabras:
                    like_val = f"%{p}%"
                    clauses.append("""(
                        usuario ILIKE %s OR 
                        accion ILIKE %s OR 
                        detalle ILIKE %s OR 
                        TO_CHAR(fecha_hora, 'DD/MM/YYYY HH24:MI:SS') ILIKE %s OR
                        TO_CHAR(fecha_hora, 'YYYY-MM-DD') ILIKE %s
                    )""")
                    params_audit.extend([like_val, like_val, like_val, like_val, like_val])
                search_clause = " AND " + " AND ".join(clauses)

            cursor.execute(f"""
                SELECT id, usuario, accion, detalle, fecha_hora
                FROM auditoria_acciones
                WHERE fecha_hora::date BETWEEN %s AND %s {search_clause}
                ORDER BY fecha_hora DESC
            """, tuple(params_audit))
            resultado["logs_auditoria"] = cursor.fetchall()

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

    def registrar_cliente(self, rif, nombre_empresa, telefono, correo, direccion, pais='Venezuela', estado='', municipio=''):
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            consulta_sql = """
                INSERT INTO clientes (rif, nombre_empresa, telefono, correo, direccion, pais, estado, municipio)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(consulta_sql, (rif, nombre_empresa, telefono, correo, direccion, pais or 'Venezuela', estado or '', municipio or ''))
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
                "SELECT rif, nombre_empresa, telefono, correo, direccion, fecha_registro, pais, estado, municipio "
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
                           correo: str, direccion: str, pais: str = 'Venezuela',
                           estado: str = '', municipio: str = '') -> bool:
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                UPDATE clientes
                SET nombre_empresa = %s, telefono = %s, correo = %s, direccion = %s, pais = %s, estado = %s, municipio = %s
                WHERE UPPER(rif) = UPPER(%s)
            """, (nombre_empresa, telefono, correo, direccion, pais or 'Venezuela', estado or '', municipio or '', rif))
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
                "SELECT rif, nombre_empresa, telefono, correo, direccion, pais, estado, municipio "
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

    def actualizar_categoria_masiva(self, skus: list[str] | None, nueva_categoria: str) -> bool:
        """
        Actualiza la categoría de una lista de productos en lote.
        Si skus es None, se actualizan TODOS los productos de la tabla.
        """
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            if skus is None:
                consulta_sql = "UPDATE productos SET categoria = %s"
                cursor.execute(consulta_sql, (nueva_categoria,))
            else:
                if not skus:
                    return True
                placeholders = ",".join(["%s"] * len(skus))
                consulta_sql = f"""
                    UPDATE productos
                    SET categoria = %s
                    WHERE sku IN ({placeholders})
                """
                cursor.execute(consulta_sql, [nueva_categoria] + list(skus))
            conexion.commit()
            return True
        except Error as e:
            print(f" [PIM] Error al actualizar categorías masivamente: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def inicializar_categorias(self):
        """Crea la tabla de categorías si no existe y siembra las categorías iniciales."""
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS categorias (
                    id SERIAL PRIMARY KEY,
                    nombre VARCHAR(100) UNIQUE NOT NULL
                )
            """)
            
            # Verificar si está vacía
            cursor.execute("SELECT COUNT(*) FROM categorias")
            if cursor.fetchone()[0] == 0:
                categorias_iniciales = [
                    "Sin Categoría", "Tren Delantero", "Sistema Eléctrico", 
                    "Motor", "Frenos", "Suspensión", "Refrigeración", "Accesorios"
                ]
                for cat in categorias_iniciales:
                    cursor.execute(
                        "INSERT INTO categorias (nombre) VALUES (%s) ON CONFLICT DO NOTHING",
                        (cat,)
                    )
            conexion.commit()
            return True
        except Error as e:
            print(f" [BD] Error al inicializar categorías: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_categorias(self) -> list[str]:
        """Obtiene la lista ordenada de nombres de categorías."""
        conexion = self.conectar()
        categorias = []
        if not conexion: return categorias
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("SELECT nombre FROM categorias ORDER BY nombre ASC")
            categorias = [row[0] for row in cursor.fetchall()]
        except Error as e:
            print(f" [BD] Error al obtener categorías: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        # Asegurar que 'Sin Categoría' esté al menos
        if "Sin Categoría" not in categorias:
            categorias.insert(0, "Sin Categoría")
        return categorias

    def registrar_categoria(self, nombre: str) -> bool:
        """Registra una nueva categoría en la base de datos."""
        if not nombre.strip():
            return False
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "INSERT INTO categorias (nombre) VALUES (%s) ON CONFLICT DO NOTHING",
                (nombre.strip(),)
            )
            conexion.commit()
            return True
        except Error as e:
            print(f" [BD] Error al registrar categoría '{nombre}': {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def eliminar_categoria(self, nombre: str) -> bool:
        """Elimina una categoría y reasigna los productos de la misma a 'Sin Categoría'."""
        if nombre == "Sin Categoría":
            # No se puede eliminar la categoría por defecto
            return False
            
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            # 1. Reasignar productos de esta categoría a 'Sin Categoría'
            cursor.execute(
                "UPDATE productos SET categoria = 'Sin Categoría' WHERE categoria = %s",
                (nombre,)
            )
            # 2. Eliminar la categoría
            cursor.execute(
                "DELETE FROM categorias WHERE nombre = %s",
                (nombre,)
            )
            conexion.commit()
            return True
        except Error as e:
            print(f" [BD] Error al eliminar categoría '{nombre}': {e}")
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
            
            # Check if this product already has a principal photo
            cursor.execute("""
                SELECT COUNT(*) FROM activos_digitales
                WHERE producto_id = (SELECT id_producto FROM productos WHERE sku = %s) AND es_principal = TRUE
            """, (sku,))
            tiene_principal = cursor.fetchone()[0] > 0
            
            es_p = not tiene_principal # True if no principal yet, False otherwise
            
            consulta_sql = """
                INSERT INTO activos_digitales (producto_id, ruta_archivo, tipo_archivo, angulo, es_principal)
                VALUES (
                    (SELECT id_producto FROM productos WHERE sku = %s),
                    %s, %s, %s, %s
                )
            """
            cursor.execute(consulta_sql, (sku, ruta_archivo, tipo_archivo, angulo, es_p))
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
            
            # Check if this product already has a principal photo
            cursor.execute("""
                SELECT COUNT(*) FROM activos_digitales
                WHERE producto_id = (SELECT id_producto FROM productos WHERE sku = %s) AND es_principal = TRUE
            """, (sku,))
            tiene_principal = cursor.fetchone()[0] > 0
            
            es_p = not tiene_principal # True if no principal yet, False otherwise
            
            consulta_sql = """
                INSERT INTO activos_digitales (producto_id, ruta_archivo, preview_webp, tipo_archivo, angulo, es_principal)
                VALUES (
                    (SELECT id_producto FROM productos WHERE sku = %s),
                    %s, %s, %s, %s, %s
                )
            """
            cursor.execute(consulta_sql, (sku, ruta_archivo, psycopg2.Binary(preview_binary), tipo_archivo, angulo, es_p))
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
                ORDER BY CASE WHEN a.es_principal = TRUE THEN 0 ELSE 1 END ASC, a.ruta_archivo ASC
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
                    CASE WHEN a.es_principal = TRUE THEN 0 ELSE 1 END ASC,
                    a.ruta_archivo ASC
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
                WHERE p.sku = %s
                ORDER BY CASE WHEN a.es_principal = TRUE THEN 0 ELSE 1 END ASC, a.ruta_archivo ASC
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

    def obtener_preview_principal_por_sku(self, sku: str) -> bytes | None:
        """Retorna los bytes del preview_webp de la imagen principal para un SKU."""
        conexion = self.conectar()
        if not conexion:
            return None
        cursor = None
        resultado = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT a.preview_webp FROM activos_digitales a
                JOIN productos p ON p.id_producto = a.producto_id
                WHERE p.sku = %s
                ORDER BY CASE WHEN a.es_principal = TRUE THEN 0 ELSE 1 END ASC, a.ruta_archivo ASC
                LIMIT 1
            """, (sku,))
            row = cursor.fetchone()
            if row and row[0]:
                # En PostgreSQL/psycopg2, los campos BYTEA pueden retornarse como memoryview o bytes
                resultado = bytes(row[0])
        except Error as e:
            print(f" [DAM] Error al obtener preview principal por SKU: {e}")
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
        Busca por SKU, nombre, marca, compatibilidad o descripción y retorna solo los que
        tienen al menos una imagen en activos_digitales.
        Soporta búsqueda multitérmino (inteligente).
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
            words = [w.strip() for w in query.strip().split() if w.strip()]
            if not words:
                return []
            
            conditions = []
            params = []
            for w in words:
                conditions.append("(p.sku ILIKE %s OR p.nombre ILIKE %s OR p.marca ILIKE %s OR p.compatibilidad ILIKE %s OR p.descripcion ILIKE %s)")
                params.extend([f"%{w}%", f"%{w}%", f"%{w}%", f"%{w}%", f"%{w}%"])
            
            where_clause = " AND ".join(conditions)
            pk = self._pk_activos
            
            sql = f"""
                SELECT sku, nombre, marca, ruta_archivo
                FROM (
                    SELECT DISTINCT ON (p.sku) p.sku, p.nombre, p.marca, a.ruta_archivo, a.es_principal, a.{pk} AS id_activo
                    FROM productos p
                    JOIN activos_digitales a ON p.id_producto = a.producto_id
                    WHERE {where_clause}
                    ORDER BY p.sku,
                             CASE WHEN a.es_principal = TRUE THEN 0 ELSE 1 END ASC,
                             a.ruta_archivo ASC
                ) sub
                ORDER BY
                    CASE WHEN sku ILIKE %s THEN 0 ELSE 1 END,
                    nombre
                LIMIT %s
            """
            args = tuple(params) + (query.strip() + "%", limite)
            cursor.execute(sql, args)
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
                    CASE WHEN a.es_principal = TRUE THEN 0 ELSE 1 END ASC,
                    a.ruta_archivo ASC
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
        filtrado por SKU, nombre, marca, compatibilidad o descripción del producto, con UNA SOLA llamada a la BD.
        Soporta búsqueda multitérmino (inteligente).
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
            words = [w.strip() for w in query.strip().split() if w.strip()]
            if not words:
                return []
            
            conditions = []
            params = []
            for w in words:
                conditions.append("(p.sku ILIKE %s OR p.nombre ILIKE %s OR p.marca ILIKE %s OR p.compatibilidad ILIKE %s OR p.descripcion ILIKE %s)")
                params.extend([f"%{w}%", f"%{w}%", f"%{w}%", f"%{w}%", f"%{w}%"])
            
            where_clause = " AND ".join(conditions)
            
            sql = """
                SELECT DISTINCT ON (p.sku)
                    p.sku,
                    p.nombre,
                    a.ruta_archivo AS ruta_principal,
                    COUNT(*) OVER (PARTITION BY p.id_producto) AS total_fotos,
                    a.{pk} AS id_activo
                FROM productos p
                JOIN activos_digitales a ON p.id_producto = a.producto_id
                WHERE {where_clause}
                ORDER BY p.sku,
                    CASE WHEN p.sku ILIKE %s THEN 0 ELSE 1 END,
                    CASE WHEN a.es_principal = TRUE THEN 0 ELSE 1 END ASC,
                    a.ruta_archivo ASC
                LIMIT %s
            """.format(pk=pk, where_clause=where_clause)
            
            args = tuple(params) + (query.strip() + "%", limite)
            cursor.execute(sql, args)
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

    MAX_INTENTOS = 3

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
                "codigo_recuperacion = NULL, codigo_expiracion = NULL, "
                "intentos_fallidos = 0, bloqueado = FALSE "
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
                    DEFAULT 'clientes:ver,editar,agregar,eliminar|productos:ver,editar,agregar,eliminar|activos:ver,subir|tareas:ver,gestionar|reportes:ver|cotizaciones:ver,crear|gastos:ver,gestionar'
            """)
            conexion.commit()

            # Migración: asegurar que los usuarios existentes tengan el módulo de gastos
            cursor.execute("SELECT username, permisos FROM usuarios")
            usuarios = cursor.fetchall()
            for username, permisos in usuarios:
                if permisos and 'gastos:' not in permisos:
                    nuevos_permisos = permisos + "|gastos:ver,gestionar"
                    cursor.execute("UPDATE usuarios SET permisos = %s WHERE username = %s", (nuevos_permisos, username))
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
                "SELECT username, rol, COALESCE(permisos,''), COALESCE(email,''), bloqueado, COALESCE(superadmin,FALSE) "
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
            cursor.execute(
                "SELECT superadmin FROM usuarios WHERE LOWER(username) = LOWER(%s)",
                (username,)
            )
            sa_fila = cursor.fetchone()
            if sa_fila and sa_fila[0]:
                if cursor: cursor.close()
                conexion.close()
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

    def obtener_datos_completos_usuario(self, username: str) -> tuple:
        """Obtiene toda la información de un usuario específico."""
        conexion = self.conectar()
        if not conexion: return None
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT username, rol, COALESCE(permisos,''), COALESCE(email,''), bloqueado, COALESCE(superadmin,FALSE) "
                "FROM usuarios WHERE LOWER(username) = LOWER(%s)",
                (username,)
            )
            return cursor.fetchone()
        except Error as e:
            print(f" [Auth] Error al obtener datos completos de '{username}': {e}")
            return None
        finally:
            if cursor: cursor.close()
            conexion.close()

    def crear_usuario(self, username: str, password: str, rol: str, permisos: str, email: str = "", superadmin: bool = False, bloqueado: bool = False) -> bool:
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            hashed = generate_password_hash(password)
            cursor.execute(
                "INSERT INTO usuarios (username, password_hash, password, rol, permisos, email, superadmin, bloqueado) "
                "VALUES (%s, %s, '', %s, %s, %s, %s, %s)",
                (username.strip().lower(), hashed, rol, permisos, email.strip(), superadmin, bloqueado)
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
                           rol: str, permisos: str, email: str = "", superadmin: bool = False, bloqueado: bool = False) -> bool:
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()

            # Validar que no se bloquee ni se le quite superadmin al único superadmin activo
            if not superadmin or bloqueado:
                cursor.execute("SELECT superadmin FROM usuarios WHERE LOWER(username) = LOWER(%s)", (username_actual,))
                fila = cursor.fetchone()
                era_super = bool(fila and fila[0])
                if era_super:
                    cursor.execute("SELECT COUNT(*) FROM usuarios WHERE superadmin = TRUE AND bloqueado = FALSE")
                    cant_super = cursor.fetchone()[0]
                    if cant_super <= 1:
                        print(" [Auth] Intento denegado de desactivar/bloquear al único superadmin.")
                        conexion.rollback()
                        return False

            # Si bloqueado es False, reiniciamos el contador de intentos fallidos a 0
            cursor.execute("""
                UPDATE usuarios
                SET username = %s, rol = %s, permisos = %s, email = %s, superadmin = %s, bloqueado = %s,
                    intentos_fallidos = CASE WHEN %s = FALSE THEN 0 ELSE intentos_fallidos END
                WHERE LOWER(username) = LOWER(%s)
            """, (nuevo_username.strip().lower(), rol, permisos, email.strip(), superadmin, bloqueado, bloqueado, username_actual))
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
            # No permitir eliminar al último superadmin
            cursor.execute("SELECT COUNT(*) FROM usuarios WHERE superadmin = TRUE")
            total_super = cursor.fetchone()[0]
            cursor.execute(
                "SELECT superadmin FROM usuarios WHERE LOWER(username) = LOWER(%s)",
                (username,)
            )
            fila = cursor.fetchone()
            if not fila: return False
            if fila[0] and total_super <= 1:
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
                    fecha_limite   TIMESTAMP    NOT NULL,
                    estado         VARCHAR(20)  DEFAULT 'Pendiente',
                    creado_por     VARCHAR(100) NOT NULL,
                    fecha_creacion TIMESTAMP    DEFAULT NOW()
                )
            """)
            # Migrar columna DATE → TIMESTAMP si la tabla ya existía con DATE
            try:
                cursor.execute("""
                    ALTER TABLE tareas ALTER COLUMN fecha_limite TYPE TIMESTAMP
                    USING fecha_limite::TIMESTAMP
                """)
                conexion.commit()
            except Exception:
                conexion.rollback()  # ya está en TIMESTAMP o no necesita cambio
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

    def eliminar_tarea(self, tarea_id: int) -> bool:
        """Elimina una tarea de la base de datos."""
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("DELETE FROM tareas WHERE id = %s", (tarea_id,))
            conexion.commit()
            return True
        except Error as e:
            print(f" [Tareas] Error al eliminar tarea #{tarea_id}: {e}")
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
        """Elimina un registro de activo digital por su ID. Promueve otro a principal si era el principal."""
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            pk = self._pk_activos
            
            # Fetch product_id and whether it was principal
            cursor.execute(f"SELECT producto_id, es_principal FROM activos_digitales WHERE {pk} = %s", (activo_id,))
            row = cursor.fetchone()
            if not row:
                return False
            
            producto_id, fue_principal = row[0], row[1]
            
            # Delete the asset
            cursor.execute(f"DELETE FROM activos_digitales WHERE {pk} = %s", (activo_id,))
            
            # If the deleted one was principal, pick the next available one and make it principal
            if fue_principal:
                cursor.execute(f"""
                    SELECT {pk} FROM activos_digitales 
                    WHERE producto_id = %s 
                    ORDER BY {pk} ASC 
                    LIMIT 1
                """, (producto_id,))
                next_row = cursor.fetchone()
                if next_row:
                    next_id = next_row[0]
                    cursor.execute(f"UPDATE activos_digitales SET es_principal = TRUE WHERE {pk} = %s", (next_id,))
            
            conexion.commit()
            return True
        except Error as e:
            print(f" [DAM] Error al eliminar activo #{activo_id}: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    # =========================================================================
    # MÓDULO GAAE — Gestión de Alianzas y Activos Estratégicos
    # =========================================================================

    def inicializar_alianzas(self):
        """Inicializa las tablas para la Gestión de Alianzas y Activos Estratégicos (GAAE)."""
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            # 1. Tabla de aliados
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS aliados (
                    id SERIAL PRIMARY KEY,
                    rif VARCHAR(30) UNIQUE NOT NULL,
                    nombre_aliado VARCHAR(200) NOT NULL,
                    tipo VARCHAR(50) NOT NULL DEFAULT 'Taller', -- 'Creador Contenido', 'Taller', 'Medio'
                    redes_sociales JSONB DEFAULT '{}'::jsonb,
                    contacto_nombre VARCHAR(150),
                    telefono VARCHAR(50),
                    email VARCHAR(150),
                    estado VARCHAR(20) DEFAULT 'Activo',
                    fecha_creacion TIMESTAMP DEFAULT NOW()
                )
            """)
            # 2. Tabla de órdenes de intercambio
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ordenes_intercambio (
                    id SERIAL PRIMARY KEY,
                    numero_orden VARCHAR(25) UNIQUE NOT NULL,
                    aliado_id INTEGER NOT NULL REFERENCES aliados(id) ON DELETE RESTRICT,
                    estado VARCHAR(30) DEFAULT 'Borrador', -- 'Borrador', 'Autorizada', 'Entregada', 'Incumplida', 'Completada'
                    descripcion_contraprestacion TEXT NOT NULL DEFAULT 'Contraprestación publicitaria',
                    fecha_entrega_mercancia DATE,
                    fecha_compromiso_publicacion DATE NOT NULL,
                    notas TEXT,
                    valor_total_referencial NUMERIC(12,2) DEFAULT 0,
                    creado_por VARCHAR(100) NOT NULL,
                    fecha_creacion TIMESTAMP DEFAULT NOW()
                )
            """)
            # 3. Items de la orden
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orden_intercambio_items (
                    id SERIAL PRIMARY KEY,
                    orden_id INTEGER NOT NULL REFERENCES ordenes_intercambio(id) ON DELETE CASCADE,
                    sku VARCHAR(100) NOT NULL,
                    nombre_producto VARCHAR(300) NOT NULL,
                    cantidad INTEGER NOT NULL DEFAULT 1,
                    valor_unitario_referencial NUMERIC(12,2) NOT NULL,
                    subtotal_referencial NUMERIC(12,2) NOT NULL
                )
            """)
            # 4. Auditoría de alianzas (Alertas a 60 días/2 meses)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auditoria_alianzas (
                    id SERIAL PRIMARY KEY,
                    orden_id INTEGER UNIQUE NOT NULL REFERENCES ordenes_intercambio(id) ON DELETE CASCADE,
                    fecha_limite_auditoria DATE NOT NULL,
                    enlace_evidencia VARCHAR(500),
                    estado_cumplimiento VARCHAR(30) DEFAULT 'Pendiente', -- 'Pendiente', 'Aprobado', 'Incumplido', 'Prorroga'
                    comentarios_auditor TEXT,
                    fecha_verificacion TIMESTAMP,
                    verificado_por VARCHAR(100)
                )
            """)
            conexion.commit()
            
            # Ejecutar migración de datos si las tablas están vacías pero cotizaciones tiene datos
            self._migrar_datos_a_alianzas(cursor)
            conexion.commit()
            return True
        except Error as e:
            print(f" [GAAE] Error al inicializar tablas de alianzas: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def _migrar_datos_a_alianzas(self, cursor):
        # 1. Migrar clientes a aliados
        cursor.execute("SELECT COUNT(*) FROM aliados")
        if cursor.fetchone()[0] == 0:
            cursor.execute("SELECT COUNT(*) FROM clientes")
            if cursor.fetchone()[0] > 0:
                print(" [Migración] Migrando clientes a aliados comerciales...")
                cursor.execute("SELECT rif, nombre_empresa, telefono, correo, direccion FROM clientes")
                clientes = cursor.fetchall()
                for cli in clientes:
                    rif, nombre, tel, correo, dir_ex = cli
                    cursor.execute("""
                        INSERT INTO aliados (rif, nombre_aliado, tipo, contacto_nombre, telefono, email)
                        VALUES (%s, %s, 'Taller', %s, %s, %s)
                        ON CONFLICT (rif) DO NOTHING
                    """, (rif, nombre, nombre, tel, correo))

        # 2. Migrar cotizaciones a ordenes_intercambio
        cursor.execute("SELECT COUNT(*) FROM ordenes_intercambio")
        if cursor.fetchone()[0] == 0:
            cursor.execute("SELECT COUNT(*) FROM cotizaciones")
            if cursor.fetchone()[0] > 0:
                print(" [Migración] Migrando cotizaciones a órdenes de intercambio...")
                cursor.execute("""
                    SELECT id, numero, cliente_rif, estado, notas, total_usd, creado_por, fecha_creacion
                    FROM cotizaciones
                """)
                cotizaciones = cursor.fetchall()
                for cot in cotizaciones:
                    c_id, numero, cliente_rif, estado, notas, total, creado, fecha = cot
                    
                    # Buscar o crear aliado
                    cursor.execute("SELECT id FROM aliados WHERE LOWER(rif) = LOWER(%s)", (cliente_rif.strip(),))
                    aliado_row = cursor.fetchone()
                    if not aliado_row:
                        cursor.execute("""
                            INSERT INTO aliados (rif, nombre_aliado, tipo)
                            VALUES (%s, %s, 'Taller')
                            RETURNING id
                        """, (cliente_rif.strip(), cliente_rif.strip()))
                        aliado_id = cursor.fetchone()[0]
                    else:
                        aliado_id = aliado_row[0]
                    
                    estado_map = {
                        'Borrador': 'Borrador',
                        'Enviada': 'Autorizada',
                        'Aceptada': 'Entregada',
                        'Rechazada': 'Incumplida'
                    }
                    nuevo_estado = estado_map.get(estado, 'Borrador')
                    
                    # Insertar orden
                    cursor.execute("""
                        INSERT INTO ordenes_intercambio 
                            (id, numero_orden, aliado_id, estado, descripcion_contraprestacion, fecha_compromiso_publicacion, notas, valor_total_referencial, creado_por, fecha_creacion)
                        VALUES (%s, %s, %s, %s, 'Contraprestación publicitaria', %s::date + 15, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                    """, (c_id, numero, aliado_id, nuevo_estado, fecha, notas, total, creado, fecha))
                    
                    # Insertar ítems
                    cursor.execute("""
                        SELECT sku, nombre_producto, cantidad, precio_unitario, subtotal
                        FROM cotizacion_items
                        WHERE cotizacion_id = %s
                    """, (c_id,))
                    items = cursor.fetchall()
                    for it in items:
                        sku, nombre, cant, prec, sub = it
                        cursor.execute("""
                            INSERT INTO orden_intercambio_items
                                (orden_id, sku, nombre_producto, cantidad, valor_unitario_referencial, subtotal_referencial)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (c_id, sku, nombre, cant, prec, sub))
                    
                    # Crear auditoría (fecha compromiso + 60 días)
                    cursor.execute("""
                        INSERT INTO auditoria_alianzas (orden_id, fecha_limite_auditoria, estado_cumplimiento)
                        VALUES (%s, (%s::date + 15) + 60, 'Pendiente')
                        ON CONFLICT (orden_id) DO NOTHING
                    """, (c_id, fecha))
                
                # Ajustar secuencia de ID
                cursor.execute("SELECT setval('ordenes_intercambio_id_seq', COALESCE((SELECT MAX(id)+1 FROM ordenes_intercambio), 1), false)")

    def registrar_aliado(self, rif, nombre_aliado, tipo, contacto_nombre=None, telefono=None, email=None, redes=None) -> bool:
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            import json
            cursor = conexion.cursor()
            redes_str = json.dumps(redes) if redes else "{}"
            cursor.execute("""
                INSERT INTO aliados (rif, nombre_aliado, tipo, contacto_nombre, telefono, email, redes_sociales)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (rif) DO UPDATE
                SET nombre_aliado = EXCLUDED.nombre_aliado,
                    tipo = EXCLUDED.tipo,
                    contacto_nombre = EXCLUDED.contacto_nombre,
                    telefono = EXCLUDED.telefono,
                    email = EXCLUDED.email,
                    redes_sociales = EXCLUDED.redes_sociales
            """, (rif.strip(), nombre_aliado.strip(), tipo.strip(), contacto_nombre, telefono, email, redes_str))
            conexion.commit()
            return True
        except Error as e:
            print(f" [GAAE] Error al registrar aliado: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_todos_aliados(self) -> list:
        conexion = self.conectar()
        resultado = []
        if not conexion: return resultado
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("SELECT id, rif, nombre_aliado, tipo, contacto_nombre, telefono, email, redes_sociales, estado FROM aliados ORDER BY nombre_aliado ASC")
            resultado = cursor.fetchall()
        except Error as e:
            print(f" [GAAE] Error al listar aliados: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return resultado

    def obtener_aliado(self, aliado_id: int) -> tuple | None:
        conexion = self.conectar()
        if not conexion: return None
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("SELECT id, rif, nombre_aliado, tipo, contacto_nombre, telefono, email, redes_sociales, estado FROM aliados WHERE id = %s", (aliado_id,))
            return cursor.fetchone()
        except Error as e:
            print(f" [GAAE] Error al obtener aliado #{aliado_id}: {e}")
            return None
        finally:
            if cursor: cursor.close()
            conexion.close()

    def crear_alianza(self, aliado_rif, creado_por, items: list[dict], notas: str = "") -> int | None:
        conexion = self.conectar()
        if not conexion: return None
        cursor = None
        try:
            from datetime import datetime, date, timedelta
            cursor = conexion.cursor()
            
            cursor.execute("SELECT id, nombre_aliado FROM aliados WHERE LOWER(rif) = LOWER(%s)", (aliado_rif.strip(),))
            aliado_row = cursor.fetchone()
            if not aliado_row:
                cursor.execute("""
                    INSERT INTO aliados (rif, nombre_aliado, tipo)
                    VALUES (%s, %s, 'Taller')
                    RETURNING id
                """, (aliado_rif.strip(), aliado_rif.strip()))
                aliado_id = cursor.fetchone()[0]
            else:
                aliado_id = aliado_row[0]
                
            anio = datetime.now().year
            cursor.execute(
                "SELECT COUNT(*) FROM ordenes_intercambio WHERE numero_orden LIKE %s",
                (f"ALN-{anio}-%",)
            )
            n = cursor.fetchone()[0] + 1
            numero = f"ALN-{anio}-{n:04d}"

            total = sum(float(it['cantidad']) * float(it['precio_unitario']) for it in items)
            fecha_compromiso = date.today() + timedelta(days=15)

            cursor.execute("""
                INSERT INTO ordenes_intercambio
                    (numero_orden, aliado_id, estado, descripcion_contraprestacion, fecha_compromiso_publicacion, notas, valor_total_referencial, creado_por)
                VALUES (%s, %s, 'Borrador', 'Publicar mención/taller', %s, %s, %s, %s)
                RETURNING id
            """, (numero, aliado_id, fecha_compromiso, notas, total, creado_por))
            orden_id = cursor.fetchone()[0]

            for it in items:
                subtotal = float(it['cantidad']) * float(it['precio_unitario'])
                cursor.execute("""
                    INSERT INTO orden_intercambio_items
                        (orden_id, sku, nombre_producto, cantidad, valor_unitario_referencial, subtotal_referencial)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    orden_id, it['sku'], it['nombre'],
                    int(it['cantidad']), float(it['precio_unitario']), subtotal
                ))

            # Insertar auditoría inicial (fecha compromiso + 60 días)
            cursor.execute("""
                INSERT INTO auditoria_alianzas (orden_id, fecha_limite_auditoria, estado_cumplimiento)
                VALUES (%s, %s + 60, 'Pendiente')
            """, (orden_id, fecha_compromiso))

            conexion.commit()
            return orden_id
        except Error as e:
            print(f" [GAAE] Error al crear alianza: {e}")
            conexion.rollback()
            return None
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_alianzas(self, estado: str = None) -> list:
        conexion = self.conectar()
        resultado = []
        if not conexion: return resultado
        cursor = None
        try:
            cursor = conexion.cursor()
            query = """
                SELECT oi.id, oi.numero_orden, a.nombre_aliado, oi.estado,
                       oi.valor_total_referencial, oi.creado_por, oi.fecha_creacion, oi.notas
                FROM ordenes_intercambio oi
                JOIN aliados a ON oi.aliado_id = a.id
            """
            if estado:
                query += " WHERE oi.estado = %s ORDER BY oi.fecha_creacion DESC"
                cursor.execute(query, (estado,))
            else:
                query += " ORDER BY oi.fecha_creacion DESC"
                cursor.execute(query)
            resultado = cursor.fetchall()
        except Error as e:
            print(f" [GAAE] Error al listar alianzas: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return resultado

    def obtener_alianzas_por_aliado_rif(self, aliado_rif: str) -> list:
        conexion = self.conectar()
        resultado = []
        if not conexion: return resultado
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT oi.id, oi.numero_orden, oi.estado, oi.valor_total_referencial, oi.creado_por, oi.fecha_creacion
                FROM ordenes_intercambio oi
                JOIN aliados a ON oi.aliado_id = a.id
                WHERE UPPER(a.rif) = UPPER(%s)
                ORDER BY oi.fecha_creacion DESC
            """, (aliado_rif,))
            resultado = cursor.fetchall()
        except Error as e:
            print(f" [GAAE] Error al obtener alianzas de aliado '{aliado_rif}': {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return resultado

    def obtener_alianza_con_items(self, orden_id: int) -> dict | None:
        conexion = self.conectar()
        if not conexion: return None
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT oi.id, oi.numero_orden, a.rif, a.nombre_aliado,
                       oi.estado, oi.notas, oi.valor_total_referencial, oi.creado_por, oi.fecha_creacion,
                       oi.descripcion_contraprestacion, oi.fecha_entrega_mercancia, oi.fecha_compromiso_publicacion
                FROM ordenes_intercambio oi
                JOIN aliados a ON oi.aliado_id = a.id
                WHERE oi.id = %s
            """, (orden_id,))
            cabecera = cursor.fetchone()
            if not cabecera: return None

            cursor.execute("""
                SELECT id, sku, nombre_producto, cantidad,
                       valor_unitario_referencial, subtotal_referencial
                FROM orden_intercambio_items
                WHERE orden_id = %s
                ORDER BY id
            """, (orden_id,))
            items = cursor.fetchall()
            
            # Obtener datos de auditoría
            cursor.execute("""
                SELECT enlace_evidencia, estado_cumplimiento, comentarios_auditor, fecha_verificacion, verificado_por
                FROM auditoria_alianzas
                WHERE orden_id = %s
            """, (orden_id,))
            auditoria = cursor.fetchone()
            
            return {'cabecera': cabecera, 'items': items, 'auditoria': auditoria}
        except Error as e:
            print(f" [GAAE] Error al obtener alianza #{orden_id}: {e}")
            return None
        finally:
            if cursor: cursor.close()
            conexion.close()

    def actualizar_estado_alianza(self, orden_id: int, nuevo_estado: str) -> bool:
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            from datetime import date
            if nuevo_estado == 'Entregada':
                cursor.execute(
                    "UPDATE ordenes_intercambio SET estado = %s, fecha_entrega_mercancia = %s WHERE id = %s",
                    (nuevo_estado, date.today(), orden_id)
                )
            else:
                cursor.execute(
                    "UPDATE ordenes_intercambio SET estado = %s WHERE id = %s",
                    (nuevo_estado, orden_id)
                )
            if cursor.rowcount == 0:
                conexion.rollback()
                return False
            conexion.commit()
            return True
        except Error as e:
            print(f" [GAAE] Error al actualizar estado de alianza #{orden_id}: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def actualizar_alianza(self, orden_id: int, items: list[dict], notas: str = "") -> bool:
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            
            # Recalcular el total
            total = sum(float(it['cantidad']) * float(it['precio_unitario']) for it in items)
            
            # Actualizar cabecera
            cursor.execute("""
                UPDATE ordenes_intercambio
                SET notas = %s, valor_total_referencial = %s
                WHERE id = %s
            """, (notas, total, orden_id))
            
            # Eliminar ítems anteriores
            cursor.execute("DELETE FROM orden_intercambio_items WHERE orden_id = %s", (orden_id,))
            
            # Insertar nuevos ítems
            for it in items:
                subtotal = float(it['cantidad']) * float(it['precio_unitario'])
                cursor.execute("""
                    INSERT INTO orden_intercambio_items
                        (orden_id, sku, nombre_producto, cantidad, valor_unitario_referencial, subtotal_referencial)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    orden_id, it['sku'], it['nombre'],
                    int(it['cantidad']), float(it['precio_unitario']), subtotal
                ))
                
            conexion.commit()
            return True
        except Error as e:
            print(f" [GAAE] Error al actualizar alianza #{orden_id}: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def registrar_auditoria_alianza(self, orden_id: int, enlace: str, estado: str, comentarios: str, verificado_por: str) -> bool:
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            from datetime import datetime
            cursor.execute("""
                UPDATE auditoria_alianzas
                SET enlace_evidencia = %s,
                    estado_cumplimiento = %s,
                    comentarios_auditor = %s,
                    fecha_verificacion = %s,
                    verificado_por = %s
                WHERE orden_id = %s
            """, (enlace.strip(), estado, comentarios.strip(), datetime.now(), verificado_por, orden_id))
            
            # Si el contenido está aprobado, cerramos la orden como completada
            if estado == 'Aprobado':
                cursor.execute("UPDATE ordenes_intercambio SET estado = 'Completada' WHERE id = %s", (orden_id,))
            elif estado == 'Incumplido':
                cursor.execute("UPDATE ordenes_intercambio SET estado = 'Incumplida' WHERE id = %s", (orden_id,))
                
            conexion.commit()
            return True
        except Error as e:
            print(f" [GAAE] Error al registrar auditoría de alianza #{orden_id}: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_alertas_auditoria(self) -> list:
        """Retorna alianzas pendientes de auditoría con alerta a 2 meses."""
        conexion = self.conectar()
        resultado = []
        if not conexion: return resultado
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT oi.id, oi.numero_orden, a.nombre_aliado, aa.fecha_limite_auditoria,
                       (aa.fecha_limite_auditoria - CURRENT_DATE) as dias_restantes,
                       aa.estado_cumplimiento
                FROM ordenes_intercambio oi
                JOIN aliados a ON oi.aliado_id = a.id
                JOIN auditoria_alianzas aa ON aa.orden_id = oi.id
                WHERE aa.estado_cumplimiento = 'Pendiente'
                ORDER BY aa.fecha_limite_auditoria ASC
            """)
            resultado = cursor.fetchall()
        except Error as e:
            print(f" [GAAE] Error al obtener alertas de auditoría: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return resultado

    def eliminar_alianza(self, orden_id: int) -> bool:
        """Elimina una alianza comercial y todos sus registros vinculados (en cascada)."""
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("DELETE FROM ordenes_intercambio WHERE id = %s", (orden_id,))
            conexion.commit()
            return True
        except Error as e:
            print(f" [GAAE] Error al eliminar alianza #{orden_id}: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    # =========================================================================
    # MÓDULO GASTOS MARKETING — Control de gastos de Publicidad y Lonas
    # =========================================================================

    def inicializar_gastos(self):
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            # Tabla de gastos de publicidad
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS gastos_publicidad (
                    id             SERIAL PRIMARY KEY,
                    post           VARCHAR(255)  NOT NULL,
                    objetivo       VARCHAR(255)  NOT NULL,
                    metodo         VARCHAR(100)  NOT NULL,
                    costo_dia      NUMERIC(12,2) NOT NULL,
                    total          NUMERIC(12,2) NOT NULL,
                    fecha_inicio   DATE          NOT NULL,
                    fecha_fin      DATE          NOT NULL,
                    comentario     TEXT,
                    creado_por     VARCHAR(100)  NOT NULL,
                    fecha_creacion TIMESTAMP     DEFAULT NOW()
                )
            """)
            # Tabla de gastos de lonas e insumos físicos
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS gastos_lonas (
                    id             SERIAL PRIMARY KEY,
                    herramienta    VARCHAR(255)  NOT NULL,
                    uso            VARCHAR(255)  NOT NULL,
                    precio         NUMERIC(12,2) NOT NULL,
                    para_quien     VARCHAR(255)  NOT NULL,
                    total          NUMERIC(12,2) NOT NULL,
                    comentario     TEXT,
                    creado_por     VARCHAR(100)  NOT NULL,
                    fecha_creacion TIMESTAMP     DEFAULT NOW()
                )
            """)
            conexion.commit()

            # Agregar nuevas columnas de segmentación a gastos_lonas de forma segura
            try:
                cursor.execute("ALTER TABLE gastos_lonas ADD COLUMN IF NOT EXISTS categoria VARCHAR(100) DEFAULT 'Otros'")
                cursor.execute("ALTER TABLE gastos_lonas ADD COLUMN IF NOT EXISTS aliado_id INTEGER REFERENCES aliados(id) ON DELETE SET NULL")
                cursor.execute("ALTER TABLE gastos_lonas ADD COLUMN IF NOT EXISTS cantidad INTEGER DEFAULT 1")
                conexion.commit()
            except Exception as e:
                print(f" [Gastos] Error al agregar nuevas columnas a gastos_lonas: {e}")
                conexion.rollback()

            return True
        except Error as e:
            print(f" [Gastos] Error al inicializar tablas de gastos: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def crear_gasto_publicidad(self, post, objetivo, metodo, costo_dia, total, fecha_inicio, fecha_fin, comentario, creado_por):
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                INSERT INTO gastos_publicidad (post, objetivo, metodo, costo_dia, total, fecha_inicio, fecha_fin, comentario, creado_por)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (post, objetivo, metodo, costo_dia, total, fecha_inicio, fecha_fin, comentario, creado_por))
            conexion.commit()
            return True
        except Error as e:
            print(f" [Gastos] Error al crear gasto de publicidad: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_gastos_publicidad(self, mes, anio):
        """Retorna los gastos de publicidad creados en el mes y año indicados."""
        conexion = self.conectar()
        resultado = []
        if not conexion: return resultado
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT id, post, objetivo, metodo, costo_dia, total, fecha_inicio, fecha_fin, comentario, creado_por, fecha_creacion
                FROM gastos_publicidad
                WHERE EXTRACT(MONTH FROM fecha_creacion) = %s AND EXTRACT(YEAR FROM fecha_creacion) = %s
                ORDER BY fecha_creacion DESC
            """, (mes, anio))
            resultado = cursor.fetchall()
        except Error as e:
            print(f" [Gastos] Error al obtener gastos de publicidad: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return resultado

    def eliminar_gasto_publicidad(self, gasto_id):
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("DELETE FROM gastos_publicidad WHERE id = %s", (gasto_id,))
            conexion.commit()
            return True
        except Error as e:
            print(f" [Gastos] Error al eliminar gasto de publicidad #{gasto_id}: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def crear_gasto_lona(self, herramienta, uso, precio, para_quien, total, comentario, creado_por, categoria, aliado_id=None, cantidad=1):
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                INSERT INTO gastos_lonas (herramienta, uso, precio, para_quien, total, comentario, creado_por, categoria, aliado_id, cantidad)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (herramienta, uso, precio, para_quien, total, comentario, creado_por, categoria, aliado_id, cantidad))
            conexion.commit()
            return True
        except Error as e:
            print(f" [Gastos] Error al crear gasto de lona: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_gastos_lonas(self, mes, anio):
        conexion = self.conectar()
        resultado = []
        if not conexion: return resultado
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT gl.id, gl.herramienta, gl.uso, gl.precio, gl.para_quien, gl.total, gl.comentario, gl.creado_por, gl.fecha_creacion,
                       gl.categoria, gl.aliado_id, gl.cantidad, a.nombre_aliado
                FROM gastos_lonas gl
                LEFT JOIN aliados a ON gl.aliado_id = a.id
                WHERE EXTRACT(MONTH FROM gl.fecha_creacion) = %s AND EXTRACT(YEAR FROM gl.fecha_creacion) = %s
                ORDER BY gl.fecha_creacion DESC
            """, (mes, anio))
            resultado = cursor.fetchall()
        except Error as e:
            print(f" [Gastos] Error al obtener gastos de lonas: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return resultado

    def eliminar_gasto_lona(self, gasto_id):
        conexion = self.conectar()
        if not conexion: return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("DELETE FROM gastos_lonas WHERE id = %s", (gasto_id,))
            conexion.commit()
            return True
        except Error as e:
            print(f" [Gastos] Error al eliminar gasto de lona #{gasto_id}: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor: cursor.close()
            conexion.close()

    def obtener_meses_disponibles_gastos(self):
        """Retorna una lista de tuplas (mes, anio) que tienen gastos registrados, ordenados desc."""
        conexion = self.conectar()
        resultado = []
        if not conexion: return resultado
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT DISTINCT EXTRACT(MONTH FROM fecha_creacion)::int AS mes, EXTRACT(YEAR FROM fecha_creacion)::int AS anio
                FROM (
                    SELECT fecha_creacion FROM gastos_publicidad
                    UNION
                    SELECT fecha_creacion FROM gastos_lonas
                ) AS combinados
                ORDER BY anio DESC, mes DESC
            """)
            resultado = cursor.fetchall()
        except Error as e:
            print(f" [Gastos] Error al obtener meses disponibles: {e}")
        finally:
            if cursor: cursor.close()
            conexion.close()
        return resultado