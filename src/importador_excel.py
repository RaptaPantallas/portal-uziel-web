# =============================================================================
# src/importador_excel.py
# Importador de Catálogo de Productos desde archivos Excel
# Proyecto: Dashboard de Marketing — Importadora Uziel C.A.
# Autor: Jesús | Python 3.11.8
# =============================================================================
#
# DESCRIPCIÓN:
#   Lee archivos de catálogo de productos en dos formatos:
#
#   1. XLS "disfrazado" (HTML exportado por sistemas ERP venezolanos)
#      — El archivo tiene extensión .xls pero su contenido es HTML con una
#        tabla Bootstrap. Se parsea usando el html.parser de la librería
#        estándar de Python (sin dependencias externas).
#      — Columnas esperadas (en orden): IMAGEN | CÓDIGO | REFERENCIA |
#        DESCRIPCIÓN | UNIDAD | MARCA | MODELO | PRECIO SIN IVA | STOCK | CATEGORÍA
#
#   2. XLSX estándar (Open XML)
#      — Misma estructura de columnas en formato real de Excel.
#      — Requiere openpyxl (pip install openpyxl).
#
#   La función principal `leer_archivo_excel(ruta)` detecta automáticamente
#   el formato y devuelve una lista de diccionarios listos para insertar en BD.
#
# USO:
#   from src.importador_excel import leer_archivo_excel
#   productos = leer_archivo_excel("/ruta/al/archivo.xls")
#   # → [{'sku': '...', 'nombre': '...', 'stock': 10, 'categoria': '...', ...}, ...]
# =============================================================================

import html as _html_module
import re
from html.parser import HTMLParser


# ---------------------------------------------------------------------------
# FUNCIONES AUXILIARES — Limpieza y conversión
# ---------------------------------------------------------------------------

def _limpiar(texto: str) -> str:
    """
    Limpia el texto de una celda HTML:
      - Decodifica entidades HTML (&Oacute; → Ó, &nbsp; → espacio, etc.)
      - Elimina el sufijo de ubicación que añaden algunos ERP
      - Normaliza espacios múltiples y saltos de línea
    """
    if not texto:
        return ""
    texto = _html_module.unescape(str(texto))
    # Quitar el bloque "Ubicación: ..." que viene al final de las descripciones
    texto = re.sub(r'\s*Ubicaci[oó]n\s*:\s*.*$', '', texto,
                   flags=re.IGNORECASE | re.DOTALL)
    # Colapsar espacios múltiples y eliminar saltos de línea
    texto = re.sub(r'[\r\n\t]+', ' ', texto)
    texto = re.sub(r'\s{2,}', ' ', texto)
    return texto.strip()


def _precio_float(texto: str) -> float:
    """Convierte un texto de precio ('11,61' o '11.61') a float."""
    if not texto:
        return 0.0
    limpio = texto.replace(",", ".").strip()
    try:
        return round(float(limpio), 2)
    except ValueError:
        return 0.0


def _stock_int(texto: str) -> int:
    """Convierte un texto de stock/existencia ('15', '0.0') a entero."""
    if not texto:
        return 0
    limpio = texto.replace(",", ".").strip()
    try:
        return int(float(limpio))
    except ValueError:
        return 0


def _es_encabezado(textos: list[str]) -> bool:
    """Detecta si una lista de textos corresponde al encabezado de la tabla."""
    unidos = " ".join(textos).upper()
    return any(kw in unidos for kw in ("CODIGO", "CÓDIGO", "DESCRIP", "PRECIO", "STOCK", "EXISTENCIA", "PRODUCTO", "ARTICULO"))


def _mapear_columnas(textos: list[str]) -> dict:
    """
    Analiza la fila de encabezado y detecta en qué posición (índice) está
    cada columna vital mediante palabras clave. Permite leer archivos de 
    cualquier formato o ERP.
    """
    mapa = {
        'sku': -1, 'descripcion': -1, 'marca': -1, 'compatibilidad': -1,
        'precio': -1, 'stock': -1, 'categoria': -1
    }
    for i, col in enumerate(textos):
        c_up = col.upper()
        if any(k in c_up for k in ("CODIGO", "CÓDIGO", "SKU", "REFERENCIA", "ARTICULO", "ARTÍCULO")):
            if mapa['sku'] == -1: mapa['sku'] = i
        elif any(k in c_up for k in ("DESCRIP", "PRODUCTO", "NOMBRE")):
            if mapa['descripcion'] == -1: mapa['descripcion'] = i
        elif any(k in c_up for k in ("MARCA", "FABRICANTE")):
            if mapa['marca'] == -1: mapa['marca'] = i
        elif any(k in c_up for k in ("MODELO", "COMPAT", "APLICAC")):
            if mapa['compatibilidad'] == -1: mapa['compatibilidad'] = i
        elif any(k in c_up for k in ("PRECIO", "COSTO", "PVP")):
            if mapa['precio'] == -1: mapa['precio'] = i
        elif any(k in c_up for k in ("STOCK", "EXISTENCIA", "CANTIDAD", "DISPON", "SALDO")):
            if mapa['stock'] == -1: mapa['stock'] = i
        elif any(k in c_up for k in ("CATEGORIA", "CATEGORÍA", "LINEA", "GRUPO", "FAMILIA")):
            if mapa['categoria'] == -1: mapa['categoria'] = i
    return mapa


# ---------------------------------------------------------------------------
# PARSER HTML usando la librería estándar de Python (sin dependencias)
# ---------------------------------------------------------------------------

class _TablaParser(HTMLParser):
    """
    Parser de tabla HTML usando html.parser de la librería estándar.
    Extrae filas (<tr>) y celdas (<th>/<td>) de la primera <table> del documento.
    """

    def __init__(self):
        super().__init__()
        self.en_tabla     = False   # Estamos dentro de <table>?
        self.en_celda     = False   # Estamos dentro de <th> o <td>?
        self.fila_actual  = []      # Celdas de la fila que se está procesando
        self.texto_celda  = []      # Fragmentos de texto de la celda actual
        self.filas        = []      # Todas las filas completas extraídas

    def handle_starttag(self, tag, attrs):
        if tag == "table" and not self.en_tabla:
            self.en_tabla = True
        elif tag == "tr" and self.en_tabla:
            self.fila_actual = []
        elif tag in ("th", "td") and self.en_tabla:
            self.en_celda   = True
            self.texto_celda = []

    def handle_endtag(self, tag):
        if tag == "table":
            self.en_tabla = False
        elif tag == "tr" and self.en_tabla:
            if self.fila_actual:
                self.filas.append(self.fila_actual[:])
        elif tag in ("th", "td") and self.en_tabla:
            self.fila_actual.append(" ".join(self.texto_celda))
            self.en_celda   = False
            self.texto_celda = []

    def handle_data(self, data):
        if self.en_celda:
            self.texto_celda.append(data)

    def handle_entityref(self, name):
        # Resolución de entidades HTML nombradas (ej: &Oacute; → Ó)
        if self.en_celda:
            self.texto_celda.append(_html_module.unescape(f"&{name};"))


# ---------------------------------------------------------------------------
# FUNCIÓN PÚBLICA PRINCIPAL
# ---------------------------------------------------------------------------

def leer_archivo_excel(ruta: str) -> list[dict]:
    """
    Lee un archivo de catálogo (.xls o .xlsx) y retorna una lista de productos.

    Detecta automáticamente si el archivo es HTML disfrazado de XLS
    (exportación de ERP) o un XLSX estándar.

    Args:
        ruta (str): Ruta absoluta o relativa al archivo de catálogo.

    Returns:
        list[dict]: Lista de diccionarios con las claves:
                    'sku', 'nombre', 'descripcion', 'marca',
                    'compatibilidad', 'precio', 'stock', 'categoria'
                    Lista vacía si el archivo no pudo parsearse.

    Raises:
        FileNotFoundError : Si la ruta no existe.
        ImportError       : Si falta openpyxl (solo para archivos .xlsx).
        ValueError        : Si la extensión no es reconocida.
    """
    # Leer los primeros bytes para detectar el formato real del archivo
    with open(ruta, "rb") as f:
        cabecera = f.read(512)

    # Si el contenido empieza con markup HTML → parsear como HTML (sin deps)
    es_html = b"<" in cabecera[:50] or b"html" in cabecera.lower()
    ext     = ruta.lower().rsplit(".", 1)[-1]

    if es_html or ext == "xls":
        return _leer_html_xls(ruta)
    elif ext == "xlsx":
        return _leer_xlsx(ruta)
    else:
        raise ValueError(
            f"Formato de archivo no reconocido: '.{ext}'. "
            "Se aceptan archivos .xls (incluyendo exportaciones ERP) y .xlsx."
        )


# ---------------------------------------------------------------------------
# PARSER — HTML disfrazado de XLS (sin dependencias externas)
# ---------------------------------------------------------------------------

def _leer_html_xls(ruta: str) -> list[dict]:
    """
    Parsea un archivo XLS cuyo contenido real es una tabla HTML.
    Usa únicamente el módulo 'html.parser' de la librería estándar de Python.
    """
    with open(ruta, "rb") as f:
        raw = f.read()

    # Decodificar — los ERP venezolanos suelen usar ISO-8859-1
    contenido = None
    for enc in ("iso-8859-1", "latin-1", "utf-8", "cp1252"):
        try:
            contenido = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if contenido is None:
        print("🔴 [Importador] No se pudo decodificar el archivo.")
        return []

    # Parsear la tabla HTML
    parser = _TablaParser()
    parser.feed(contenido)

    if not parser.filas:
        print("🔴 [Importador] No se encontraron filas de tabla en el archivo.")
        return []

    productos            = []
    encabezado_detectado = False
    mapa_columnas        = {}

    for fila_raw in parser.filas:
        # Limpiar cada celda de la fila
        textos = [_limpiar(c) for c in fila_raw]

        # Saltar filas hasta encontrar el encabezado y mapearlo
        if not encabezado_detectado and _es_encabezado(textos):
            encabezado_detectado = True
            mapa_columnas = _mapear_columnas(textos)
            print(f"📊 [Importador] Mapa de columnas detectado: {mapa_columnas}")
            continue

        if not encabezado_detectado:
            continue

        # --- LÓGICA DE EXTRACCIÓN ROBUSTA (Para lidiar con HTML malformado del ERP) ---
        # Si la fila tiene menos columnas de las esperadas (ej. falta una celda vacía de Modelo)
        # intentamos adivinar dónde están el precio y el stock basándonos en si parecen números.
        
        sku  = textos[mapa_columnas.get('sku', 1)] if len(textos) > mapa_columnas.get('sku', 1) else ""
        desc = textos[mapa_columnas.get('descripcion', 3)] if len(textos) > mapa_columnas.get('descripcion', 3) else ""
        marc = textos[mapa_columnas.get('marca', 5)] if len(textos) > mapa_columnas.get('marca', 5) else ""
        
        # Por defecto, intentamos usar el mapa estricto
        mode = textos[mapa_columnas.get('compatibilidad', 6)] if len(textos) > mapa_columnas.get('compatibilidad', 6) else ""
        prec_str = textos[mapa_columnas.get('precio', 7)] if len(textos) > mapa_columnas.get('precio', 7) else ""
        stock_str = textos[mapa_columnas.get('stock', 8)] if len(textos) > mapa_columnas.get('stock', 8) else ""
        cat_str   = textos[mapa_columnas.get('categoria', 9)] if len(textos) > mapa_columnas.get('categoria', 9) else "Sin Categoría"

        # Heurística: Si lo que capturamos como 'modelo' parece un precio (ej. "4,16")
        # y lo que capturamos como 'precio' parece un stock alto (ej. "291"),
        # significa que la columna Modelo estaba vacía y el parser se comió el <td>.
        # Desplazamos los valores hacia la derecha.
        if mode and re.match(r'^\d+[\.,]\d{2}$', mode): 
            # Si el modelo parece un precio exacto con dos decimales
            stock_str = prec_str # El precio que agarramos era en realidad el stock
            prec_str = mode      # El modelo que agarramos era en realidad el precio
            mode = ""            # Asumimos que no había modelo
            
        # Ignorar filas vacías o de navegación
        if not sku or sku.lower() in ("", "nbsp", "&nbsp;", "none", "0", "código"):
            continue

        # El nombre es la primera línea de la descripción (antes del salto de línea)
        nombre = re.split(r'[\n\r]', desc)[0].strip() if desc else sku

        # Truncar campos muy largos
        if len(nombre) > 500:
            nombre = nombre[:500]
            
        if not cat_str or cat_str.lower() in ("nbsp", "&nbsp;", "none"):
            cat_str = "Sin Categoría"

        producto = {
            "sku":            sku,
            "nombre":         nombre,
            "descripcion":    desc[:1000] if desc else nombre,
            "marca":          marc[:100]  if marc else "",
            "compatibilidad": mode[:500]  if mode else "",
            "precio":         _precio_float(prec_str),
            "stock":          _stock_int(stock_str),
            "categoria":      cat_str[:60]
        }
        productos.append(producto)

    print(f"📦 [Importador] Total leídos del archivo HTML/XLS: {len(productos)} producto(s).")
    return productos


# ---------------------------------------------------------------------------
# PARSER — XLSX estándar (requiere openpyxl)
# ---------------------------------------------------------------------------
def _leer_xlsx(ruta: str) -> list[dict]:
    """
    Parsea un archivo .xlsx estándar con openpyxl.
    Asume la misma estructura de columnas que la exportación HTML del ERP.
    Agrega extracción de columnas de STOCK y CATEGORÍA.

    Requiere: pip install openpyxl
    """
    try:
        import openpyxl
    except ImportError:
        raise ImportError(
            "Para leer archivos .xlsx necesitas instalar openpyxl:\n"
            "  pip install openpyxl\n\n"
            "Los archivos .xls exportados del ERP no requieren ninguna instalación."
        )

    wb = openpyxl.load_workbook(ruta, data_only=True)
    ws = wb.active
    productos            = []
    encabezado_detectado = False
    mapa_columnas        = {}

    for fila in ws.iter_rows(values_only=True):
        if not fila:
            continue

        textos = [str(c) if c is not None else "" for c in fila]

        if not encabezado_detectado and _es_encabezado(textos):
            encabezado_detectado = True
            mapa_columnas = _mapear_columnas(textos)
            print(f"📊 [Importador] Mapa de columnas detectado (XLSX): {mapa_columnas}")
            continue

        if not encabezado_detectado:
            continue

        def get_val(llave: str) -> str:
            idx = mapa_columnas.get(llave, -1)
            return textos[idx] if idx != -1 and idx < len(textos) else ""

        sku  = _limpiar(get_val('sku'))
        desc = _limpiar(get_val('descripcion'))
        marc = _limpiar(get_val('marca'))
        mode = _limpiar(get_val('compatibilidad'))
        prec = _limpiar(get_val('precio'))
        stock_str = _limpiar(get_val('stock'))
        cat_str   = _limpiar(get_val('categoria'))

        if not sku:
            continue

        nombre = re.split(r'[\n\r]', desc)[0].strip() if desc else sku
        
        if not cat_str or cat_str.lower() in ("nbsp", "&nbsp;", "none"):
            cat_str = "Sin Categoría"

        productos.append({
            "sku":            sku,
            "nombre":         nombre,
            "descripcion":    desc[:1000] if desc else nombre,
            "marca":          marc[:100]  if marc else "",
            "compatibilidad": mode[:500]  if mode else "",
            "precio":         _precio_float(prec),
            "stock":          _stock_int(stock_str),
            "categoria":      cat_str[:60]
        })

    print(f"📦 [Importador] Total leídos del XLSX: {len(productos)} producto(s).")
    return productos