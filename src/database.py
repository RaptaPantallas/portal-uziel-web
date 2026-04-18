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
#   Patrón utilizado: DAO (Data Access Object) - aísla la lógica SQL del
#   resto del programa para facilitar mantenimiento y pruebas.
#
# MÓDULOS DISPONIBLES:
#   - CRM    : Gestión de clientes
#   - PIM    : Gestión de productos/inventario
#   - DAM    : Gestión de activos digitales (fotografías)
#   - Seguridad : Autenticación de usuarios
#   - Estadísticas : Contadores para el Dashboard
#   - Tareas : Asignación y seguimiento de tareas internas
# =============================================================================

import os
import psycopg2
from psycopg2 import Error


# =============================================================================
# ██████████████ CONFIGURACIÓN - EDITAR AQUÍ ██████████████
# =============================================================================

# URL de conexión a PostgreSQL en Render.com
# Formato: postgresql://usuario:contraseña@host/nombre_base_datos
#
# CÓMO CONFIGURAR (elige una opción):
#
#   Opción A — Variable de entorno (RECOMENDADO para producción):
#     Windows CMD : set DATABASE_URL=postgresql://usuario:clave@host/bd
#     Windows PS  : $env:DATABASE_URL="postgresql://usuario:clave@host/bd"
#     Linux/Mac   : export DATABASE_URL="postgresql://usuario:clave@host/bd"
#     Render.com  : Dashboard > Environment > Add Environment Variable
#
#   Opción B — Reemplaza directamente la cadena vacía de abajo (solo para
#              desarrollo local, NUNCA subas esto a GitHub):
#
DATABASE_URL_DEFAULT = "postgresql://variable:LYqte0xjYaVb1EfvIs0aNrjq8G4nsxra@dpg-d6ddpkktgctc73f38gv0-a.oregon-postgres.render.com/importadora_uziel"
URL_BASE_DE_DATOS = os.getenv("DATABASE_URL", DATABASE_URL_DEFAULT)

# =============================================================================


class ConexionBD:
    """
    Clase principal de acceso a la base de datos PostgreSQL.

    Gestiona todas las operaciones CRUD para los módulos CRM, PIM, DAM
    y el sistema de autenticación. Cada método abre su propia conexión,
    ejecuta la operación y la cierra (patrón conexión por petición).

    Uso:
        bd = ConexionBD()
        clientes = bd.obtener_clientes()
    """

    def __init__(self):
        """Inicializa la clase con la URL de conexión configurada arriba."""
        self.url_nube = URL_BASE_DE_DATOS

    def conectar(self):
        """
        Establece y retorna una conexión activa a PostgreSQL.

        Returns:
            psycopg2.connection: Objeto de conexión activo, o None si falla.

        Nota:
            Siempre llama a conexion.close() al terminar de usarla.
        """
        try:
            conexion = psycopg2.connect(self.url_nube)
            return conexion
        except Error as e:
            print(f"🔴 [BD] Error al conectar a PostgreSQL: {e}")
            return None

    # =========================================================================
    # MÓDULO CRM — Gestión de Clientes
    # =========================================================================

    def registrar_cliente(self, rif, nombre_empresa, telefono, correo, direccion):
        """
        Inserta un nuevo cliente en la tabla 'clientes'.

        Args:
            rif (str): RIF de la empresa (Ej: "J-12345678-9"). Es la clave primaria.
            nombre_empresa (str): Nombre legal de la empresa.
            telefono (str): Número de teléfono de contacto.
            correo (str): Correo electrónico de contacto.
            direccion (str): Dirección física de la empresa.

        Returns:
            bool: True si se registró correctamente, False si hubo un error
                  (por ejemplo, si el RIF ya existe en la base de datos).
        """
        conexion = self.conectar()
        if not conexion:
            return False
        cursor = None
        try:
            cursor = conexion.cursor()
            consulta_sql = """
                INSERT INTO clientes (rif, nombre_empresa, telefono, correo, direccion)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(consulta_sql, (rif, nombre_empresa, telefono, correo, direccion))
            conexion.commit()
            print(f"🟢 [CRM] Cliente '{nombre_empresa}' (RIF: {rif}) registrado.")
            return True
        except Error as e:
            print(f"🔴 [CRM] Error al registrar cliente '{rif}': {e}")
            conexion.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    def obtener_cliente(self, rif: str):
        """
        Recupera todos los datos de un cliente específico por su RIF.

        Args:
            rif (str): RIF del cliente (clave primaria).

        Returns:
            tuple | None: (rif, nombre_empresa, telefono, correo, direccion,
                           fecha_registro) o None si no existe.
        """
        conexion = self.conectar()
        cliente = None
        if not conexion:
            return cliente
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
            print(f"🔴 [CRM] Error al obtener cliente '{rif}': {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return cliente

    def actualizar_cliente(self, rif: str, nombre_empresa: str, telefono: str,
                           correo: str, direccion: str) -> bool:
        """
        Actualiza los datos de contacto de un cliente existente.

        Args:
            rif            (str): RIF del cliente (clave primaria, no editable).
            nombre_empresa (str): Nuevo nombre de la empresa.
            telefono       (str): Nuevo número de teléfono.
            correo         (str): Nuevo correo electrónico.
            direccion      (str): Nueva dirección física.

        Returns:
            bool: True si se actualizó correctamente, False en caso de error
                  o si el RIF no existe.
        """
        conexion = self.conectar()
        if not conexion:
            return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("""
                UPDATE clientes
                SET nombre_empresa = %s, telefono = %s, correo = %s, direccion = %s
                WHERE UPPER(rif) = UPPER(%s)
            """, (nombre_empresa, telefono, correo, direccion, rif))
            if cursor.rowcount == 0:
                print(f"⚠️  [CRM] Cliente '{rif}' no encontrado al intentar actualizar.")
                conexion.rollback()
                return False
            conexion.commit()
            print(f"🟢 [CRM] Cliente '{rif}' actualizado correctamente.")
            return True
        except Error as e:
            print(f"🔴 [CRM] Error al actualizar cliente '{rif}': {e}")
            conexion.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    def obtener_tareas_por_cliente(self, cliente_rif: str) -> list:
        """
        Recupera todas las tareas asociadas a un cliente ordenadas por fecha límite.

        Args:
            cliente_rif (str): RIF del cliente.

        Returns:
            list[tuple]: Lista de tuplas
                (id, tipo_tarea, descripcion, fecha_limite, estado,
                 asignado_a, creado_por, fecha_creacion)
                ordenadas por fecha_limite ascendente.
        """
        conexion = self.conectar()
        tareas = []
        if not conexion:
            return tareas
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
            print(f"🔴 [CRM] Error al obtener tareas del cliente '{cliente_rif}': {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return tareas

    def obtener_clientes(self):
        """
        Recupera todos los clientes ordenados por fecha de registro (más nuevo primero).

        Returns:
            list[tuple]: Lista de tuplas (rif, nombre_empresa, telefono, correo, direccion).
                         Retorna lista vacía si no hay datos o hay error.
        """
        conexion = self.conectar()
        lista_clientes = []
        if not conexion:
            return lista_clientes
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT rif, nombre_empresa, telefono, correo, direccion "
                "FROM clientes ORDER BY fecha_registro DESC"
            )
            lista_clientes = cursor.fetchall()
        except Error as e:
            print(f"🔴 [CRM] Error al obtener clientes: {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return lista_clientes

    # =========================================================================
    # MÓDULO PIM — Gestión de Productos / Inventario
    # =========================================================================

    def registrar_producto(self, sku, nombre, descripcion, marca, compatibilidad, precio):
        """
        Inserta un nuevo producto en la tabla 'productos'.

        Args:
            sku (str): Código único del producto (Ej: "BMB-GAS-CORS-01").
            nombre (str): Nombre descriptivo de la pieza.
            descripcion (str): Descripción técnica del producto.
            marca (str): Marca o fabricante.
            compatibilidad (str): Vehículos o modelos con los que es compatible.
            precio (float | str): Precio corporativo en dólares.

        Returns:
            bool: True si se insertó correctamente, False si el SKU ya existe u otro error.
        """
        conexion = self.conectar()
        if not conexion:
            return False
        cursor = None
        try:
            cursor = conexion.cursor()
            consulta_sql = """
                INSERT INTO productos (sku, nombre, descripcion, marca, compatibilidad, precio)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(consulta_sql, (sku, nombre, descripcion, marca, compatibilidad, precio))
            conexion.commit()
            print(f"🟢 [PIM] Producto '{sku}' registrado exitosamente.")
            return True
        except Error as e:
            print(f"🔴 [PIM] Error al registrar producto '{sku}': {e}")
            conexion.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    def obtener_productos(self):
        """
        Recupera todos los productos para el listado (vista resumida).
        Retorna solo las columnas necesarias para la tabla del Dashboard.

        Returns:
            list[tuple]: Lista de tuplas (sku, nombre, marca, precio).
                         Ordenadas por fecha de creación descendente.
        """
        conexion = self.conectar()
        lista_productos = []
        if not conexion:
            return lista_productos
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT sku, nombre, marca, precio "
                "FROM productos ORDER BY fecha_creacion DESC"
            )
            lista_productos = cursor.fetchall()
        except Error as e:
            print(f"🔴 [PIM] Error al obtener lista de productos: {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return lista_productos

    def obtener_producto(self, sku):
        """
        Recupera todos los datos de un producto específico por su SKU.
        Usado para la pantalla de edición y para el generador de PDF.

        Args:
            sku (str): Código SKU del producto a buscar.

        Returns:
            tuple | None: Tupla (sku, nombre, descripcion, marca, compatibilidad, precio)
                          o None si el SKU no existe.
        """
        conexion = self.conectar()
        producto = None
        if not conexion:
            return producto
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT sku, nombre, descripcion, marca, compatibilidad, precio "
                "FROM productos WHERE sku = %s",
                (sku,)
            )
            producto = cursor.fetchone()
        except Error as e:
            print(f"🔴 [PIM] Error al obtener producto '{sku}': {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return producto

    def actualizar_producto(self, sku, nombre, descripcion, marca, compatibilidad, precio):
        """
        Actualiza los datos de un producto existente. El SKU no puede cambiar
        (es la clave primaria y se usa como filtro en el WHERE).

        Args:
            sku (str): SKU del producto a actualizar (no se modifica).
            nombre (str): Nuevo nombre de la pieza.
            descripcion (str): Nueva descripción técnica.
            marca (str): Nueva marca.
            compatibilidad (str): Nueva lista de compatibilidades.
            precio (float | str): Nuevo precio.

        Returns:
            bool: True si la actualización fue exitosa, False en caso de error.
        """
        conexion = self.conectar()
        if not conexion:
            return False
        cursor = None
        try:
            cursor = conexion.cursor()
            consulta_sql = """
                UPDATE productos
                SET nombre=%s, descripcion=%s, marca=%s, compatibilidad=%s, precio=%s
                WHERE sku=%s
            """
            cursor.execute(consulta_sql, (nombre, descripcion, marca, compatibilidad, precio, sku))
            conexion.commit()
            print(f"🟢 [PIM] Producto '{sku}' actualizado correctamente.")
            return True
        except Error as e:
            print(f"🔴 [PIM] Error al actualizar producto '{sku}': {e}")
            conexion.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    def eliminar_producto(self, sku):
        """
        Elimina permanentemente un producto de la base de datos.
        ADVERTENCIA: Esta operación también puede eliminar activos digitales
        vinculados si la tabla tiene CASCADE configurado.

        Args:
            sku (str): SKU del producto a eliminar.

        Returns:
            bool: True si se eliminó correctamente, False en caso de error.
        """
        conexion = self.conectar()
        if not conexion:
            return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("DELETE FROM productos WHERE sku = %s", (sku,))
            conexion.commit()
            print(f"🟢 [PIM] Producto '{sku}' eliminado.")
            return True
        except Error as e:
            print(f"🔴 [PIM] Error al eliminar producto '{sku}': {e}")
            conexion.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    # =========================================================================
    # MÓDULO DAM — Gestión de Activos Digitales (Fotografías)
    # =========================================================================

    def registrar_activo(self, sku, ruta_archivo, tipo_archivo, angulo):
        """
        Vincula una fotografía a un producto existente mediante un JOIN inverso.
        Busca el id_producto usando el SKU y luego inserta el activo digital.

        Args:
            sku (str): SKU del producto al que se vincula la foto.
            ruta_archivo (str): Ruta relativa al archivo copiado en 'almacen_activos/'.
            tipo_archivo (str): MIME type del archivo (Ej: "imagen/jpg").
            angulo (str): Tipo de toma: "Frontal", "Lateral", "Detalle" o "En-contexto".

        Returns:
            bool: True si se vinculó correctamente, False si el SKU no existe u otro error.
        """
        conexion = self.conectar()
        if not conexion:
            return False
        cursor = None
        try:
            cursor = conexion.cursor()
            # Subconsulta: obtiene el id_producto a partir del SKU legible
            consulta_sql = """
                INSERT INTO activos_digitales (producto_id, ruta_archivo, tipo_archivo, angulo)
                VALUES (
                    (SELECT id_producto FROM productos WHERE sku = %s),
                    %s, %s, %s
                )
            """
            cursor.execute(consulta_sql, (sku, ruta_archivo, tipo_archivo, angulo))
            conexion.commit()
            print(f"🟢 [DAM] Activo '{angulo}' vinculado al SKU '{sku}'.")
            return True
        except Error as e:
            print(f"🔴 [DAM] Error al vincular activo (¿El SKU '{sku}' existe?): {e}")
            conexion.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    def obtener_producto_con_imagen(self, sku):
        """
        Recupera los datos completos de un producto junto con la ruta de su
        fotografía principal. Utilizado por el generador de PDF de ficha técnica.

        Args:
            sku (str): SKU del producto a consultar.

        Returns:
            tuple | None: Tupla (nombre, marca, compatibilidad, precio, ruta_imagen)
                          o None si no se encuentra el SKU.
                          La ruta_imagen puede ser None si no tiene foto en el DAM.
        """
        conexion = self.conectar()
        datos_completos = None
        if not conexion:
            return datos_completos
        cursor = None
        try:
            cursor = conexion.cursor()
            # LEFT JOIN: trae el producto aunque NO tenga imagen en el DAM
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
            print(f"🔴 [DAM] Error al obtener producto+imagen para SKU '{sku}': {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return datos_completos

    def obtener_activos_por_sku(self, sku):
        """
        Devuelve todos los activos digitales (fotografías) vinculados a un
        producto, ordenados por tipo de ángulo para mostrarlos en tabs.

        Args:
            sku (str): SKU del producto a consultar.

        Returns:
            list[tuple]: Lista de tuplas (id, ruta_archivo, tipo_archivo, angulo).
                         Lista vacía si el producto no tiene fotos o no existe.
        """
        conexion = self.conectar()
        activos = []
        if not conexion:
            return activos
        cursor = None
        try:
            cursor = conexion.cursor()
            consulta = """
                SELECT a.id, a.ruta_archivo, a.tipo_archivo, a.angulo
                FROM activos_digitales a
                JOIN productos p ON p.id_producto = a.producto_id
                WHERE p.sku = %s
                ORDER BY CASE a.angulo
                    WHEN 'Frontal'    THEN 1
                    WHEN 'Lateral'    THEN 2
                    WHEN 'Detalle'    THEN 3
                    WHEN 'En-contexto' THEN 4
                    ELSE 5
                END, a.id
            """
            cursor.execute(consulta, (sku,))
            activos = cursor.fetchall()
        except Error as e:
            print(f"🔴 [DAM] Error al obtener activos del SKU '{sku}': {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return activos

    def obtener_fotos_principales(self):
        """
        Recupera la foto principal (preferiblemente Frontal) de cada producto
        en una sola consulta, para mostrar miniaturas en el catálogo.

        Returns:
            dict: Mapa {sku: ruta_archivo}. Solo incluye SKUs que tienen fotos.
        """
        conexion = self.conectar()
        fotos = {}
        if not conexion:
            return fotos
        cursor = None
        try:
            cursor = conexion.cursor()
            # DISTINCT ON (sku): toma la primera fila por SKU después de ordenar
            # por prioridad de ángulo, resultando en la foto principal de cada producto
            consulta = """
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
                    END, a.id
            """
            cursor.execute(consulta)
            for sku, ruta in cursor.fetchall():
                fotos[sku] = ruta
        except Error as e:
            print(f"🔴 [DAM] Error al obtener fotos principales: {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return fotos

    # =========================================================================
    # MÓDULO DE SEGURIDAD — Autenticación de Usuarios
    # =========================================================================

    def verificar_login(self, username, password):
        """
        Verifica las credenciales de un usuario contra la tabla 'usuarios'.

        NOTA DE SEGURIDAD: Las contraseñas se comparan en texto plano.
        Para mayor seguridad, implementar hashing con bcrypt o werkzeug.

        Args:
            username (str): Nombre de usuario (se recibe en minúsculas).
            password (str): Contraseña ingresada por el usuario.

        Returns:
            tuple | None: Tupla (username, rol) si las credenciales son correctas,
                          o None si el usuario/contraseña no coinciden.
        """
        conexion = self.conectar()
        usuario_valido = None
        if not conexion:
            return usuario_valido
        cursor = None
        try:
            cursor = conexion.cursor()
            # LOWER() en ambos lados: el login funciona sin importar si el
            # usuario escribió "admin", "Admin" o "ADMIN"
            cursor.execute(
                "SELECT username, rol FROM usuarios "
                "WHERE LOWER(username) = LOWER(%s) AND password = %s",
                (username, password)
            )
            usuario_valido = cursor.fetchone()
        except Error as e:
            print(f"🔴 [Auth] Error al verificar login del usuario '{username}': {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return usuario_valido

    # =========================================================================
    # MÓDULO ESTADÍSTICAS — Contadores para el Dashboard
    # =========================================================================

    def contar_productos(self):
        """
        Cuenta el total de productos registrados en el inventario.

        Returns:
            int: Número total de productos en la tabla 'productos'. Retorna 0 en error.
        """
        conexion = self.conectar()
        total = 0
        if not conexion:
            return total
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("SELECT COUNT(*) FROM productos")
            total = cursor.fetchone()[0]
        except Error as e:
            print(f"🔴 [Stats] Error al contar productos: {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return total

    def contar_clientes(self):
        """
        Cuenta el total de clientes registrados en el CRM.

        Returns:
            int: Número total de clientes en la tabla 'clientes'. Retorna 0 en error.
        """
        conexion = self.conectar()
        total = 0
        if not conexion:
            return total
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("SELECT COUNT(*) FROM clientes")
            total = cursor.fetchone()[0]
        except Error as e:
            print(f"🔴 [Stats] Error al contar clientes: {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return total

    # =========================================================================
    # MÓDULO TAREAS — Asignación y seguimiento de tareas internas
    # =========================================================================
    #
    # Las tareas permiten que los supervisores (rol Admin) asignen trabajo
    # a diseñadores o editores relacionado con un cliente específico.
    # Cada tarea lleva: cliente, responsable, tipo de trabajo, descripción,
    # fecha límite y estado de avance.
    #
    # Tabla en BD: tareas
    #   id             — Identificador único automático
    #   cliente_rif    — RIF del cliente asociado a la tarea
    #   cliente_nombre — Nombre de la empresa (guardado para evitar JOINs)
    #   asignado_a     — Username del responsable de ejecutar la tarea
    #   tipo_tarea     — Categoría del trabajo: Diseño, Edición, Fotografía, etc.
    #   descripcion    — Detalle libre de lo que hay que hacer
    #   fecha_limite   — Fecha tope para entregar el trabajo
    #   estado         — Pendiente | En Progreso | Completada
    #   creado_por     — Username del supervisor que creó la tarea
    #   fecha_creacion — Timestamp automático al insertar
    # =========================================================================

    def inicializar_tareas(self):
        """
        Crea la tabla 'tareas' en la base de datos si aún no existe.
        Se llama automáticamente al arrancar el servidor Flask para garantizar
        que la tabla esté disponible sin necesidad de scripts externos.

        Returns:
            bool: True si la tabla existe o fue creada, False si hubo error.
        """
        conexion = self.conectar()
        if not conexion:
            return False
        cursor = None
        try:
            cursor = conexion.cursor()
            # Crear tabla solo si no existe — operación idempotente y segura
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
            print("🟢 [Tareas] Tabla 'tareas' verificada/creada correctamente.")
            return True
        except Error as e:
            print(f"🔴 [Tareas] Error al inicializar tabla de tareas: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    def crear_tarea(self, cliente_rif, cliente_nombre, asignado_a,
                    tipo_tarea, descripcion, fecha_limite, creado_por):
        """
        Inserta una nueva tarea en la base de datos.

        Args:
            cliente_rif    (str): RIF del cliente al que se refiere la tarea.
            cliente_nombre (str): Nombre de la empresa del cliente.
            asignado_a     (str): Username del usuario que debe ejecutar la tarea.
            tipo_tarea     (str): Tipo de trabajo (Diseño, Edición, Fotografía...).
            descripcion    (str): Descripción detallada de lo que se necesita.
            fecha_limite   (str): Fecha tope en formato YYYY-MM-DD.
            creado_por     (str): Username del supervisor que asignó la tarea.

        Returns:
            bool: True si se creó correctamente, False en caso de error.
        """
        conexion = self.conectar()
        if not conexion:
            return False
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
            print(f"🟢 [Tareas] Tarea creada para '{asignado_a}' "
                  f"(cliente: {cliente_nombre}, tipo: {tipo_tarea}).")
            return True
        except Error as e:
            print(f"🔴 [Tareas] Error al crear tarea: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    def obtener_tareas_asignadas(self, asignado_a):
        """
        Devuelve todas las tareas PENDIENTES o EN PROGRESO asignadas a un usuario.
        Se usa para generar las notificaciones que ve el diseñador/editor al entrar.

        Args:
            asignado_a (str): Username del usuario cuyas tareas se quieren consultar.

        Returns:
            list[tuple]: Lista de tuplas con los campos:
                (id, cliente_rif, cliente_nombre, tipo_tarea,
                 descripcion, fecha_limite, estado, creado_por, fecha_creacion)
                Ordenadas por fecha_limite ascendente (las más urgentes primero).
        """
        conexion = self.conectar()
        tareas = []
        if not conexion:
            return tareas
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
            print(f"🔴 [Tareas] Error al obtener tareas de '{asignado_a}': {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return tareas

    def obtener_todas_tareas(self):
        """
        Devuelve el listado completo de tareas (todas las personas, todos los estados).
        Usado en la vista de gestión de tareas del supervisor.

        Returns:
            list[tuple]: Lista de tuplas con todos los campos de la tabla tareas,
                         ordenadas por fecha de creación descendente.
        """
        conexion = self.conectar()
        tareas = []
        if not conexion:
            return tareas
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
            print(f"🔴 [Tareas] Error al obtener todas las tareas: {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return tareas

    def actualizar_estado_tarea(self, tarea_id, nuevo_estado):
        """
        Cambia el estado de una tarea (Pendiente → En Progreso → Completada).

        Args:
            tarea_id     (int): ID de la tarea a modificar.
            nuevo_estado (str): El nuevo estado: 'En Progreso' o 'Completada'.

        Returns:
            bool: True si se actualizó, False en caso de error.
        """
        conexion = self.conectar()
        if not conexion:
            return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "UPDATE tareas SET estado = %s WHERE id = %s",
                (nuevo_estado, tarea_id)
            )
            conexion.commit()
            print(f"🟢 [Tareas] Tarea #{tarea_id} actualizada a '{nuevo_estado}'.")
            return True
        except Error as e:
            print(f"🔴 [Tareas] Error al actualizar estado de tarea #{tarea_id}: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    def contar_tareas_pendientes(self, asignado_a):
        """
        Cuenta cuántas tareas activas (Pendiente + En Progreso) tiene un usuario.
        Se usa para mostrar el número en la campana de notificaciones del sidebar.

        Args:
            asignado_a (str): Username del usuario.

        Returns:
            int: Número de tareas activas. Retorna 0 en caso de error.
        """
        conexion = self.conectar()
        total = 0
        if not conexion:
            return total
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
            print(f"🔴 [Tareas] Error al contar tareas de '{asignado_a}': {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return total

    def obtener_usuarios(self):
        """
        Devuelve todos los usuarios registrados en el sistema.
        Se usa para popular el dropdown de asignación de tareas.

        Returns:
            list[tuple]: Lista de tuplas (username, rol) ordenadas por username.
        """
        conexion = self.conectar()
        usuarios = []
        if not conexion:
            return usuarios
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute("SELECT username, rol FROM usuarios ORDER BY username")
            usuarios = cursor.fetchall()
        except Error as e:
            print(f"🔴 [Auth] Error al obtener lista de usuarios: {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return usuarios

    # =========================================================================
    # MÓDULO COTIZACIONES — Presupuestos para clientes
    # =========================================================================
    #
    # Dos tablas relacionadas:
    #   cotizaciones      — Cabecera del documento (cliente, estado, total, notas)
    #   cotizacion_items  — Líneas del presupuesto (sku, nombre, cantidad, precio)
    #
    # Estados posibles: Borrador | Enviada | Aceptada | Rechazada
    # =========================================================================

    def inicializar_cotizaciones(self):
        """
        Crea las tablas 'cotizaciones' y 'cotizacion_items' si aún no existen.
        Se llama automáticamente al arrancar el servidor Flask.

        Returns:
            bool: True si las tablas existen o fueron creadas, False si hubo error.
        """
        conexion = self.conectar()
        if not conexion:
            return False
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
            print("🟢 [Cotiz] Tablas 'cotizaciones' y 'cotizacion_items' verificadas.")
            return True
        except Error as e:
            print(f"🔴 [Cotiz] Error al inicializar tablas de cotizaciones: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    def _siguiente_numero_cotizacion(self, cursor, anio: int) -> str:
        """
        Genera el siguiente número correlativo de cotización del año dado.
        Formato: COT-AAAA-NNNN  (ej. COT-2026-0001)

        Args:
            cursor: Cursor de BD ya abierto (no se cierra aquí).
            anio   : Año de 4 dígitos.

        Returns:
            str: Número de cotización único.
        """
        cursor.execute(
            "SELECT COUNT(*) FROM cotizaciones WHERE numero LIKE %s",
            (f"COT-{anio}-%",)
        )
        n = cursor.fetchone()[0] + 1
        return f"COT-{anio}-{n:04d}"

    def agregar_item_cotizacion(self, cotizacion_id: int, sku: str,
                               nombre: str, cantidad: int,
                               precio_unitario: float) -> bool:
        """
        Inserta un ítem en una cotización existente y recalcula su total.

        Args:
            cotizacion_id   (int)  : ID de la cotización padre.
            sku             (str)  : Código de producto.
            nombre          (str)  : Nombre del producto.
            cantidad        (int)  : Unidades.
            precio_unitario (float): Precio en USD por unidad.

        Returns:
            bool: True si se insertó correctamente, False en caso de error.
        """
        conexion = self.conectar()
        if not conexion:
            return False
        cursor = None
        try:
            cursor = conexion.cursor()
            subtotal = cantidad * precio_unitario
            cursor.execute("""
                INSERT INTO cotizacion_items
                    (cotizacion_id, sku, nombre_producto, cantidad,
                     precio_unitario, subtotal)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (cotizacion_id, sku, nombre, cantidad, precio_unitario, subtotal))
            # Recalcular total de la cotización
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
            print(f"🟢 [Cotiz] Ítem '{sku}' agregado a cotización #{cotizacion_id}.")
            return True
        except Error as e:
            print(f"🔴 [Cotiz] Error al agregar ítem a cotización #{cotizacion_id}: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    def crear_cotizacion(self, cliente_rif, cliente_nombre, creado_por,
                         items: list[dict], notas: str = "") -> int | None:
        """
        Crea una cotización completa (cabecera + ítems) en una sola transacción.

        Args:
            cliente_rif    (str): RIF del cliente.
            cliente_nombre (str): Nombre de la empresa.
            creado_por     (str): Username del Admin.
            items (list[dict]): Lista de {'sku', 'nombre', 'cantidad', 'precio_unitario'}.
            notas          (str): Observaciones opcionales.

        Returns:
            int | None: ID de la cotización creada, o None si hubo error.
        """
        conexion = self.conectar()
        if not conexion:
            return None
        cursor = None
        try:
            from datetime import datetime
            cursor = conexion.cursor()
            anio = datetime.now().year
            numero = self._siguiente_numero_cotizacion(cursor, anio)

            # Calcular total
            total = sum(
                float(it['cantidad']) * float(it['precio_unitario'])
                for it in items
            )

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
                        (cotizacion_id, sku, nombre_producto, cantidad,
                         precio_unitario, subtotal)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    cotizacion_id,
                    it['sku'],
                    it['nombre'],
                    int(it['cantidad']),
                    float(it['precio_unitario']),
                    subtotal
                ))

            conexion.commit()
            print(f"🟢 [Cotiz] Cotización '{numero}' creada (ID {cotizacion_id}).")
            return cotizacion_id
        except Error as e:
            print(f"🔴 [Cotiz] Error al crear cotización: {e}")
            conexion.rollback()
            return None
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    def obtener_cotizaciones_por_cliente(self, cliente_rif: str) -> list:
        """
        Recupera todas las cotizaciones asociadas a un cliente ordenadas por fecha.

        Args:
            cliente_rif (str): RIF del cliente.

        Returns:
            list[tuple]: (id, numero, estado, total_usd, creado_por, fecha_creacion)
                         ordenadas por fecha_creacion DESC.
        """
        conexion = self.conectar()
        resultado = []
        if not conexion:
            return resultado
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
            print(f"🔴 [Cotiz] Error al obtener cotizaciones del cliente '{cliente_rif}': {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return resultado

    def obtener_cotizaciones(self, estado: str = None) -> list:
        """
        Lista todas las cotizaciones, opcionalmente filtradas por estado.

        Args:
            estado (str | None): 'Borrador', 'Enviada', 'Aceptada', 'Rechazada', o None.

        Returns:
            list[tuple]: (id, numero, cliente_nombre, estado, total_usd, creado_por, fecha_creacion)
        """
        conexion = self.conectar()
        resultado = []
        if not conexion:
            return resultado
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
            print(f"🔴 [Cotiz] Error al listar cotizaciones: {e}")
        finally:
            if cursor:
                cursor.close()
            conexion.close()
        return resultado

    def obtener_cotizacion_con_items(self, cotizacion_id: int) -> dict | None:
        """
        Recupera la cabecera y todos los ítems de una cotización.

        Args:
            cotizacion_id (int): ID de la cotización.

        Returns:
            dict | None: {'cabecera': tuple, 'items': list[tuple]} o None si no existe.
        """
        conexion = self.conectar()
        if not conexion:
            return None
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
            if not cabecera:
                return None

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
            print(f"🔴 [Cotiz] Error al obtener cotización #{cotizacion_id}: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    def actualizar_estado_cotizacion(self, cotizacion_id: int, nuevo_estado: str) -> bool:
        """
        Cambia el estado de una cotización.

        Args:
            cotizacion_id (int): ID de la cotización.
            nuevo_estado  (str): Uno de: 'Borrador', 'Enviada', 'Aceptada', 'Rechazada'.

        Returns:
            bool: True si se actualizó, False en caso de error.
        """
        conexion = self.conectar()
        if not conexion:
            return False
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "UPDATE cotizaciones SET estado = %s WHERE id = %s",
                (nuevo_estado, cotizacion_id)
            )
            # Verificar que la fila existía y fue actualizada
            if cursor.rowcount == 0:
                print(f"⚠️  [Cotiz] Cotización #{cotizacion_id} no encontrada al actualizar estado.")
                conexion.rollback()
                return False
            conexion.commit()
            print(f"🟢 [Cotiz] Cotización #{cotizacion_id} → '{nuevo_estado}'.")
            return True
        except Error as e:
            print(f"🔴 [Cotiz] Error al actualizar cotización #{cotizacion_id}: {e}")
            conexion.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            conexion.close()

    # =========================================================================
    # IMPORTACIÓN MASIVA DE PRODUCTOS
    # =========================================================================

    def importar_productos_masivo(self, lista_productos: list[dict]) -> tuple[int, int]:
        """
        Inserta múltiples productos en la base de datos, ignorando los que ya
        existen (comparación por SKU).

        Usa INSERT ... ON CONFLICT (sku) DO NOTHING para que la operación sea
        atómica y no genere errores en productos duplicados.

        Args:
            lista_productos (list[dict]): Lista de diccionarios con las claves
                'sku', 'nombre', 'descripcion', 'marca', 'compatibilidad', 'precio'.

        Returns:
            tuple[int, int]: (insertados, omitidos)
                - insertados : Cantidad de productos nuevos añadidos a la BD.
                - omitidos   : Cantidad de productos que ya existían y se saltaron.
        """
        conexion = self.conectar()
        if not conexion:
            return 0, len(lista_productos)

        insertados = 0
        omitidos   = 0
        cursor     = None

        try:
            cursor = conexion.cursor()
            for p in lista_productos:
                cursor.execute(
                    """
                    INSERT INTO productos
                        (sku, nombre, descripcion, marca, compatibilidad, precio)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (sku) DO NOTHING
                    """,
                    (
                        str(p.get("sku", "")).strip(),
                        str(p.get("nombre", "")).strip(),
                        str(p.get("descripcion", "")).strip(),
                        str(p.get("marca", "")).strip(),
                        str(p.get("compatibilidad", "")).strip(),
                        str(p.get("precio", "0")),
                    )
                )
                # rowcount = 1 si se insertó, 0 si ya existía (DO NOTHING)
                if cursor.rowcount > 0:
                    insertados += 1
                else:
                    omitidos += 1

            conexion.commit()
            print(f"🟢 [Import] {insertados} productos nuevos, {omitidos} omitidos.")

        except Error as e:
            print(f"🔴 [Import] Error durante la importación masiva: {e}")
            conexion.rollback()

        finally:
            if cursor:
                cursor.close()
            conexion.close()

        return insertados, omitidos
