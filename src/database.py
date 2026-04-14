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
DATABASE_URL_DEFAULT = ""   # <-- Pega aquí tu URL solo para desarrollo local
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

    def obtener_clientes(self):
        """
        Recupera todos los clientes ordenados por fecha de registro (más nuevo primero).

        Returns:
            list[tuple]: Lista de tuplas (rif, nombre_empresa, telefono, correo).
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
                "SELECT rif, nombre_empresa, telefono, correo "
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
            cursor.execute(
                "SELECT username, rol FROM usuarios WHERE username = %s AND password = %s",
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
