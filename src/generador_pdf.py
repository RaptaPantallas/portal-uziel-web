# =============================================================================
# src/generador_pdf.py
# Motor de Generación de PDFs — Importadora Uziel C.A.
# Autor: Jesús | Librería: ReportLab | Python 3.11.8
# =============================================================================
#
# DESCRIPCIÓN:
#   Dos funciones exportables:
#
#   1. generar_ficha_tecnica(sku) → bool
#      Genera una ficha técnica de una sola página para un producto específico.
#      Conservada por compatibilidad con versiones anteriores.
#
#   2. generar_pdf_catalogo(lista_skus) → tuple[bool, str]
#      Genera un catálogo PDF con una página por producto para los SKUs dados.
#      Retorna (éxito: bool, ruta_archivo: str).
#
#   Usados por: main.py (módulo PIM, botones de PDF)
# =============================================================================

import io
import os
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from src.database import ConexionBD


def _extraer_ruta_relativa(ruta_archivo):
    """Extrae la ruta relativa de un activo digital dentro de almacen_activos/."""
    if not ruta_archivo:
        return None
    ruta = str(ruta_archivo).replace('\\', '/')
    if 'almacen_activos/' in ruta:
        idx = ruta.index('almacen_activos/')
        return ruta[idx + len('almacen_activos/'):]
    if ruta.startswith('/') or (len(ruta) > 2 and ruta[1] == ':'):
        return os.path.basename(ruta)
    return ruta


# =============================================================================
# ████████  CONFIGURACIÓN DEL PDF — EDITAR AQUÍ  ████████
# =============================================================================

NOMBRE_EMPRESA = "IMPORTADORA UZIEL C.A."
PIE_DE_PAGINA  = "Documento generado automáticamente por el Sistema de Información Uziel."

# Márgenes y posición de la imagen
MARGEN_X        = 50
X_IMAGEN        = 310
Y_IMAGEN_OFFSET = 340
ANCHO_IMAGEN    = 230
ALTO_IMAGEN     = 230

# Layout compacto del catálogo (varios productos por página)
ANCHO_THUMB     = 55          # Tamaño del thumbnail
ALTO_THUMB      = 55
ALTO_FILA       = 75          # Altura por producto
X_DETALLE       = 120         # X donde empieza el texto del producto
ANCHO_LABEL     = 85          # Ancho de las etiquetas (SKU:, Marca:, etc.)

# Colores RGB (valores 0.0 – 1.0)
COLOR_AZUL_EMP   = (0.18, 0.27, 0.86)   # Encabezado empresa  (#2e45db)
COLOR_NEGRO      = (0.17, 0.22, 0.31)   # Texto general       (#2c3850)
COLOR_VERDE_PREC = (0.15, 0.68, 0.37)   # Precio destacado    (#27ae5f)
COLOR_GRIS       = (0.55, 0.60, 0.68)   # Textos secundarios
COLOR_LINEA      = (0.87, 0.88, 0.93)   # Líneas divisorias   (#dde1ec)
COLOR_BADGE_BG   = (0.23, 0.36, 0.86)   # Fondo badge SKU     (#3b5bdb)

# Fuentes
FUENTE_EMP  = 22
FUENTE_PROD = 16
FUENTE_DATOS = 11
FUENTE_PREC  = 13
FUENTE_PIE   = 9

# =============================================================================


# ---------------------------------------------------------------------------
# FUNCIÓN AUXILIAR — Dibuja una página de producto
# ---------------------------------------------------------------------------

def _dibujar_pagina_producto(c, sku: str, datos: tuple, ancho: float, alto: float):
    """
    Dibuja en el canvas 'c' una página completa con la ficha de un producto.

    Args:
        c     : Canvas de ReportLab (ya posicionado en la página correcta).
        sku   : Código SKU del producto.
        datos : Tupla (nombre, marca, compatibilidad, precio, ruta_imagen).
        ancho : Ancho de la página en puntos.
        alto  : Alto de la página en puntos.
    """
    nombre, marca, compatibilidad, precio, ruta_img = datos

    # ---- Banda de encabezado ----
    c.setFillColorRGB(*COLOR_AZUL_EMP)
    c.rect(0, alto - 90, ancho, 90, fill=True, stroke=False)

    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", FUENTE_EMP)
    c.drawString(MARGEN_X, alto - 52, NOMBRE_EMPRESA)
    c.setFont("Helvetica", 10)
    c.setFillColorRGB(0.8, 0.88, 1.0)
    c.drawString(MARGEN_X, alto - 72, "Catálogo de Productos — Ficha Técnica")

    # ---- Badge de SKU ----
    badge_x = ancho - 160
    badge_y = alto - 68
    c.setFillColorRGB(1, 1, 1)
    c.roundRect(badge_x, badge_y, 130, 22, 5, fill=True, stroke=False)
    c.setFillColorRGB(*COLOR_AZUL_EMP)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(badge_x + 65, badge_y + 7, f"SKU: {sku}")

    # ---- Nombre del producto ----
    c.setFillColorRGB(*COLOR_NEGRO)
    c.setFont("Helvetica-Bold", FUENTE_PROD)
    c.drawString(MARGEN_X, alto - 120, nombre)

    # ---- Línea divisoria ----
    c.setStrokeColorRGB(*COLOR_LINEA)
    c.setLineWidth(1)
    c.line(MARGEN_X, alto - 130, ancho / 2 - 20, alto - 130)

    # ---- Datos técnicos ----
    c.setFont("Helvetica-Bold", FUENTE_DATOS)
    c.setFillColorRGB(*COLOR_GRIS)
    c.drawString(MARGEN_X, alto - 152, "MARCA")
    c.drawString(MARGEN_X, alto - 178, "COMPATIBILIDAD")
    c.drawString(MARGEN_X, alto - 204, "PRECIO CORPORATIVO")

    c.setFont("Helvetica", FUENTE_DATOS + 1)
    c.setFillColorRGB(*COLOR_NEGRO)
    c.drawString(MARGEN_X + 130, alto - 152, str(marca))
    # Compatibilidad puede ser larga: truncar con "..." si excede
    compat_str = str(compatibilidad)
    if len(compat_str) > 55:
        compat_str = compat_str[:52] + "..."
    c.drawString(MARGEN_X + 130, alto - 178, compat_str)

    # Precio en verde y grande
    c.setFont("Helvetica-Bold", FUENTE_PREC)
    c.setFillColorRGB(*COLOR_VERDE_PREC)
    precio_str = f"$ {precio}" if precio is not None else "—"
    c.drawString(MARGEN_X + 130, alto - 204, precio_str)

    # ---- Fotografía del producto ----
    c.setFillColorRGB(*COLOR_NEGRO)
    ruta_local = None
    if ruta_img:
        if os.path.exists(ruta_img):
            ruta_local = ruta_img
        else:
            ruta_rel = _extraer_ruta_relativa(ruta_img)
            if ruta_rel:
                ruta_alt = os.path.join("almacen_activos", ruta_rel)
                if os.path.exists(ruta_alt):
                    ruta_local = ruta_alt

    if ruta_local:
        try:
            c.drawImage(
                ruta_local,
                X_IMAGEN,
                alto - Y_IMAGEN_OFFSET,
                width=ANCHO_IMAGEN,
                height=ALTO_IMAGEN,
                preserveAspectRatio=True,
                mask="auto"
            )
        except Exception:
            _dibujar_placeholder_imagen(c, X_IMAGEN, alto - Y_IMAGEN_OFFSET, ANCHO_IMAGEN, ALTO_IMAGEN)
    else:
        _dibujar_placeholder_imagen(c, X_IMAGEN, alto - Y_IMAGEN_OFFSET, ANCHO_IMAGEN, ALTO_IMAGEN)

    # ---- Pie de página ----
    _dibujar_pie(c, ancho)


# ---------------------------------------------------------------------------
# FUNCIÓN AUXILIAR — Placeholder para "sin imagen"
# ---------------------------------------------------------------------------

def _dibujar_placeholder_imagen(c, x, y, ancho, alto):
    """Dibuja un recuadro gris con texto 'Sin imagen'."""
    c.setStrokeColorRGB(*COLOR_LINEA)
    c.setFillColorRGB(0.96, 0.97, 0.99)
    c.roundRect(x, y, ancho, alto, 8, fill=True, stroke=True)
    c.setFont("Helvetica-Oblique", 10)
    c.setFillColorRGB(*COLOR_GRIS)
    c.drawCentredString(x + ancho / 2, y + alto / 2, "Sin imagen")


# ---------------------------------------------------------------------------
# FUNCIÓN AUXILIAR — Pie de página
# ---------------------------------------------------------------------------

def _dibujar_pie(c, ancho):
    """Dibuja el pie de página estándar."""
    c.setFont("Helvetica", FUENTE_PIE)
    c.setFillColorRGB(*COLOR_GRIS)
    c.drawString(MARGEN_X, 35, PIE_DE_PAGINA)
    c.drawRightString(ancho - MARGEN_X, 35,
                      datetime.now().strftime("Generado el %d/%m/%Y a las %H:%M"))


# ---------------------------------------------------------------------------
# FUNCIÓN AUXILIAR — Dibuja una fila compacta de producto (catálogo continuo)
# ---------------------------------------------------------------------------

def _dibujar_fila_producto(c, sku: str, nombre: str, marca: str,
                            compatibilidad: str, precio, ruta_img: str,
                            ancho: float, y: float, idx: int = 0) -> float:
    """Dibuja una fila de producto con thumbnail y datos. Retorna la nueva Y."""
    # Fondo alternado sutil
    if idx % 2 == 0:
        c.setFillColorRGB(0.97, 0.98, 1.0)
    else:
        c.setFillColorRGB(1, 1, 1)
    c.rect(MARGEN_X, y - ALTO_FILA, ancho - 2 * MARGEN_X, ALTO_FILA, fill=True, stroke=False)

    # ---- Thumbnail ----
    thumb_y = y - ALTO_THUMB - 10
    ruta_local = None
    if ruta_img:
        if os.path.exists(ruta_img):
            ruta_local = ruta_img
        else:
            ruta_rel = _extraer_ruta_relativa(ruta_img)
            if ruta_rel:
                ruta_alt = os.path.join("almacen_activos", ruta_rel)
                if os.path.exists(ruta_alt):
                    ruta_local = ruta_alt

    if ruta_local:
        try:
            c.roundRect(MARGEN_X, thumb_y, ANCHO_THUMB, ALTO_THUMB, 4, fill=False, stroke=True)
            c.drawImage(ruta_local, MARGEN_X, thumb_y,
                        width=ANCHO_THUMB, height=ALTO_THUMB,
                        preserveAspectRatio=True, mask="auto")
        except Exception:
            _dibujar_placeholder_imagen(c, MARGEN_X, thumb_y, ANCHO_THUMB, ALTO_THUMB)
    else:
        _dibujar_placeholder_imagen(c, MARGEN_X, thumb_y, ANCHO_THUMB, ALTO_THUMB)

    # ---- Información del producto ----
    x_texto = X_DETALLE
    precio_str = f"$ {precio}" if precio is not None else "—"
    labels = ["SKU:", "Producto:", "Marca:", "Compatibilidad:", "Precio:"]
    valores = [sku, nombre, str(marca), str(compatibilidad), precio_str]
    ancho_label = 68
    y_linea = y - 16

    for i, (label, valor) in enumerate(zip(labels, valores)):
        c.setFont("Helvetica-Bold", 8)
        c.setFillColorRGB(*COLOR_GRIS)
        c.drawString(x_texto, y_linea, label)
        c.setFont("Helvetica", 8.5)
        c.setFillColorRGB(*COLOR_NEGRO)

        texto = str(valor)
        if i == 4:
            c.setFillColorRGB(*COLOR_VERDE_PREC)
            c.setFont("Helvetica-Bold", 9)
        elif i == 3 and c.stringWidth(texto, "Helvetica", 8.5) > (ancho - x_texto - ancho_label - MARGEN_X):
            while c.stringWidth(texto + "...", "Helvetica", 8.5) > (ancho - x_texto - ancho_label - MARGEN_X):
                texto = texto[:-1]
            texto += "..."

        c.drawString(x_texto + ancho_label, y_linea, texto)
        y_linea -= 12

    # ---- Línea separadora ----
    c.setStrokeColorRGB(*COLOR_LINEA)
    c.setLineWidth(0.5)
    c.line(MARGEN_X, y - ALTO_FILA, ancho - MARGEN_X, y - ALTO_FILA)

    return y - ALTO_FILA


# ---------------------------------------------------------------------------
# FUNCIÓN AUXILIAR — Encabezado del catálogo
# ---------------------------------------------------------------------------

def _dibujar_encabezado_catalogo(c, ancho: float, alto: float, primera: bool = False):
    """Dibuja el encabezado estándar del catálogo."""
    # Banda azul
    c.setFillColorRGB(*COLOR_AZUL_EMP)
    c.rect(0, alto - 90, ancho, 90, fill=True, stroke=False)

    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", FUENTE_EMP)
    c.drawString(MARGEN_X, alto - 52, NOMBRE_EMPRESA)
    c.setFont("Helvetica", 10)
    c.setFillColorRGB(0.8, 0.88, 1.0)
    c.drawString(MARGEN_X, alto - 72, "Catálogo de Productos — Listado General")

    # Subtítulo
    if primera:
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColorRGB(0.85, 0.90, 1.0)
        c.drawString(MARGEN_X, alto - 82, f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    # Sin encabezados de columna (cada fila ya tiene sus etiquetas)


# ---------------------------------------------------------------------------
# FUNCIÓN 1 — Ficha técnica de un solo producto (compatibilidad anterior)
# ---------------------------------------------------------------------------

def generar_ficha_tecnica(sku: str) -> bool:
    """
    Genera una ficha técnica en PDF para el producto indicado.

    Args:
        sku (str): Código SKU del producto.

    Returns:
        bool: True si el PDF fue generado exitosamente, False en caso contrario.
    """
    bd    = ConexionBD()
    datos = bd.obtener_producto_con_imagen(sku)

    if not datos:
        print(f" [PDF] SKU '{sku}' no encontrado en la base de datos.")
        return False

    nombre_pdf  = f"Ficha_Tecnica_{sku}.pdf"
    ancho, alto = letter

    c = canvas.Canvas(nombre_pdf, pagesize=letter)
    _dibujar_pagina_producto(c, sku, datos, ancho, alto)
    try:
        c.save()
    except Exception as e:
        print(f" [PDF] Error al guardar ficha técnica: {e}")
        return False

    print(f" [PDF] Ficha técnica generada: '{nombre_pdf}'")
    return True


# ---------------------------------------------------------------------------
# FUNCIÓN 2 — Catálogo multi-producto (nueva)
# ---------------------------------------------------------------------------

def generar_pdf_catalogo(lista_skus: list[str], ruta_guardar: str = None) -> tuple[bool, str]:
    """
    Genera un catálogo PDF compacto con todos los productos listados.
    Varios productos por página, con thumbnail opcional de 55x55.
    
    Args:
        lista_skus (list[str]): Lista de códigos SKU a incluir en el catálogo.
        ruta_guardar (str, optional): Ruta personalizada donde guardar el PDF.

    Returns:
        tuple[bool, str]:
            - True y la ruta del archivo si el PDF fue generado exitosamente.
            - False y una cadena vacía si ningún SKU fue encontrado.
    """
    bd = ConexionBD()

    paginas = []
    for sku in lista_skus:
        datos = bd.obtener_producto_con_imagen(sku.strip().upper())
        if datos:
            paginas.append((sku.strip().upper(), datos))
        else:
            print(f"  [PDF Catálogo] SKU '{sku}' no encontrado — se omitirá.")

    if not paginas:
        print(" [PDF Catálogo] Ningún SKU válido encontrado. PDF no generado.")
        return False, ""

    if not ruta_guardar:
        timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_pdf  = f"Catalogo_Uziel_{timestamp}.pdf"
    else:
        nombre_pdf  = ruta_guardar

    ancho, alto = letter

    c = canvas.Canvas(nombre_pdf, pagesize=letter)

    # Primera página
    _dibujar_encabezado_catalogo(c, ancho, alto, primera=True)
    y = alto - 125

    for idx, (sku, datos) in enumerate(paginas):
        nombre, marca, compatibilidad, precio, ruta_img = datos

        # ¿Cabe en esta página?
        if y < ALTO_FILA + 50:
            _dibujar_pie(c, ancho)
            c.showPage()
            _dibujar_encabezado_catalogo(c, ancho, alto)
            y = alto - 125

        try:
            y = _dibujar_fila_producto(c, sku, nombre, marca, compatibilidad,
                                        precio, ruta_img, ancho, y, idx)
        except Exception as e:
            print(f"  [PDF Catálogo] Error al dibujar producto '{sku}': {e}")
            y -= ALTO_FILA

    _dibujar_pie(c, ancho)
    try:
        c.save()
    except Exception as e:
        print(f" [PDF Catálogo] Error al guardar PDF: {e}")
        return False, str(e)

    print(f" [PDF Catálogo] {len(paginas)} producto(s) incluidos. Archivo: '{nombre_pdf}'")
    return True, nombre_pdf


# ---------------------------------------------------------------------------
# FUNCIÓN 3 — PDF de cotización (para el portal web)
# ---------------------------------------------------------------------------

def generar_pdf_cotizacion(datos: dict) -> io.BytesIO:
    """
    Genera el PDF de una cotización y lo devuelve en un buffer de memoria.

    Args:
        datos (dict): Resultado de ConexionBD.obtener_cotizacion_con_items().
                      Claves: 'cabecera' (tuple), 'items' (list[tuple]).
                      cabecera: (id, numero, cliente_rif, cliente_nombre,
                                 estado, notas, total_usd, creado_por, fecha_creacion)
                      items   : (id, sku, nombre_producto, cantidad,
                                 precio_unitario, subtotal)

    Returns:
        io.BytesIO: Buffer con el PDF listo para enviar al navegador.
    """
    cab   = datos['cabecera']
    items = datos['items']

    # Desempacar cabecera
    _, numero, cliente_rif, cliente_nombre, estado, notas, total_usd, creado_por, fecha_creacion = cab

    ancho, alto = letter
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)

    # ---- Cabecera Limpia con Logo y Datos Corporativos ----
    logo_path = os.path.join("almacen_activos", "Logo", "logo.png")
    if os.path.exists(logo_path):
        try:
            c.drawImage(logo_path, MARGEN_X, alto - 75, width=110, height=35, preserveAspectRatio=True, mask="auto")
        except Exception:
            c.setFont("Helvetica-Bold", 16)
            c.setFillColorRGB(*COLOR_AZUL_EMP)
            c.drawString(MARGEN_X, alto - 55, "EDJ7 AUTOPARTS")
    else:
        c.setFont("Helvetica-Bold", 16)
        c.setFillColorRGB(*COLOR_AZUL_EMP)
        c.drawString(MARGEN_X, alto - 55, "EDJ7 AUTOPARTS")

    # Datos corporativos de la empresa
    c.setFont("Helvetica-Bold", 8)
    c.setFillColorRGB(*COLOR_NEGRO)
    c.drawString(MARGEN_X, alto - 90, "IMPORTADORA UZIEL C.A.")
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(*COLOR_GRIS)
    c.drawString(MARGEN_X, alto - 100, "RIF: J-41234567-8 | Tlf: +58 (212) 555-0199 | Correo: contacto@importadorauziel.com")

    # Título del documento y Número de Cotización
    c.setFont("Helvetica-Bold", 14)
    c.setFillColorRGB(*COLOR_AZUL_EMP)
    c.drawRightString(ancho - MARGEN_X, alto - 50, "PRESUPUESTO COMERCIAL")
    c.setFont("Helvetica-Bold", 10)
    c.setFillColorRGB(*COLOR_NEGRO)
    c.drawRightString(ancho - MARGEN_X, alto - 65, f"N° {numero}")
    
    # Línea separadora azul brillante (#0ea5e9 = 0.05, 0.65, 0.91)
    c.setStrokeColorRGB(0.05, 0.65, 0.91)
    c.setLineWidth(1.5)
    c.line(MARGEN_X, alto - 110, ancho - MARGEN_X, alto - 110)

    # ---- Datos del cliente ----
    y = alto - 130
    c.setFillColorRGB(*COLOR_NEGRO)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGEN_X, y, "CLIENTE")

    c.setStrokeColorRGB(*COLOR_LINEA)
    c.setLineWidth(1)
    c.line(MARGEN_X, y - 4, ancho - MARGEN_X, y - 4)

    y -= 20
    c.setFont("Helvetica-Bold", FUENTE_DATOS)
    c.setFillColorRGB(*COLOR_GRIS)
    c.drawString(MARGEN_X, y, "Empresa:")
    c.setFont("Helvetica", FUENTE_DATOS + 1)
    c.setFillColorRGB(*COLOR_NEGRO)
    c.drawString(MARGEN_X + 70, y, str(cliente_nombre))

    c.setFont("Helvetica-Bold", FUENTE_DATOS)
    c.setFillColorRGB(*COLOR_GRIS)
    c.drawString(MARGEN_X + 300, y, "RIF:")
    c.setFont("Helvetica", FUENTE_DATOS + 1)
    c.setFillColorRGB(*COLOR_NEGRO)
    c.drawString(MARGEN_X + 320, y, str(cliente_rif))

    y -= 16
    c.setFont("Helvetica-Bold", FUENTE_DATOS)
    c.setFillColorRGB(*COLOR_GRIS)
    c.drawString(MARGEN_X, y, "Estado:")
    c.setFont("Helvetica", FUENTE_DATOS + 1)
    c.setFillColorRGB(*COLOR_NEGRO)
    c.drawString(MARGEN_X + 70, y, str(estado))

    c.setFont("Helvetica-Bold", FUENTE_DATOS)
    c.setFillColorRGB(*COLOR_GRIS)
    c.drawString(MARGEN_X + 300, y, "Fecha:")
    c.setFont("Helvetica", FUENTE_DATOS + 1)
    c.setFillColorRGB(*COLOR_NEGRO)
    fecha_str = fecha_creacion.strftime("%d/%m/%Y") if hasattr(fecha_creacion, 'strftime') else str(fecha_creacion)[:10]
    c.drawString(MARGEN_X + 320, y, fecha_str)

    # ---- Tabla de ítems ----
    y -= 30
    c.setFillColorRGB(*COLOR_AZUL_EMP)
    c.rect(MARGEN_X, y - 2, ancho - 2 * MARGEN_X, 18, fill=True, stroke=False)

    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(MARGEN_X + 4,  y + 4, "SKU")
    c.drawString(MARGEN_X + 75, y + 4, "DESCRIPCIÓN")
    c.drawString(MARGEN_X + 285, y + 4, "CANT.")
    c.drawString(MARGEN_X + 340, y + 4, "PRECIO UNIT.")
    c.drawString(MARGEN_X + 430, y + 4, "SUBTOTAL")

    y -= 18
    alt_fila = True
    for item in items:
        _, sku, nombre_prod, cantidad, precio_unit, subtotal = item

        if y < 100:
            c.showPage()
            y = alto - 60

        if alt_fila:
            c.setFillColorRGB(0.95, 0.96, 0.99)
        else:
            c.setFillColorRGB(1, 1, 1)
        c.rect(MARGEN_X, y - 2, ancho - 2 * MARGEN_X, 16, fill=True, stroke=False)
        alt_fila = not alt_fila

        c.setFillColorRGB(*COLOR_NEGRO)
        c.setFont("Helvetica", 9)
        c.drawString(MARGEN_X + 4,  y + 3, str(sku))

        # Truncar nombre si es muy largo
        nombre_corto = str(nombre_prod)
        if len(nombre_corto) > 38:
            nombre_corto = nombre_corto[:35] + "..."
        c.drawString(MARGEN_X + 75, y + 3, nombre_corto)

        c.drawCentredString(MARGEN_X + 305, y + 3, str(cantidad))

        c.setFont("Helvetica", 9)
        c.drawRightString(MARGEN_X + 420, y + 3, f"$ {float(precio_unit):,.2f}")
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(MARGEN_X + 490, y + 3, f"$ {float(subtotal):,.2f}")

        # Línea divisoria entre filas
        c.setStrokeColorRGB(*COLOR_LINEA)
        c.setLineWidth(0.4)
        c.line(MARGEN_X, y - 2, ancho - MARGEN_X, y - 2)

        y -= 18

    # ---- Total ----
    y -= 10
    c.setFillColorRGB(*COLOR_AZUL_EMP)
    c.setLineWidth(1.5)
    c.line(MARGEN_X + 300, y, ancho - MARGEN_X, y)
    y -= 16
    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(*COLOR_NEGRO)
    c.drawString(MARGEN_X + 300, y, "TOTAL USD:")
    c.setFillColorRGB(*COLOR_VERDE_PREC)
    c.drawRightString(ancho - MARGEN_X, y, f"$ {float(total_usd):,.2f}")

    # ---- Notas ----
    if notas:
        y -= 28
        c.setFillColorRGB(*COLOR_NEGRO)
        c.setFont("Helvetica-Bold", FUENTE_DATOS)
        c.drawString(MARGEN_X, y, "Notas / Observaciones:")
        c.setFont("Helvetica", FUENTE_DATOS)
        y -= 14
        # Envolver texto largo
        palabras = str(notas).split()
        linea = ""
        for palabra in palabras:
            prueba = (linea + " " + palabra).strip()
            if c.stringWidth(prueba, "Helvetica", FUENTE_DATOS) < (ancho - 2 * MARGEN_X - 10):
                linea = prueba
            else:
                c.drawString(MARGEN_X, y, linea)
                y -= 12
                linea = palabra
                if y < 80:
                    break
        if linea:
            c.drawString(MARGEN_X, y, linea)

    # ---- Pie de página ----
    c.setFont("Helvetica", FUENTE_PIE)
    c.setFillColorRGB(*COLOR_GRIS)
    c.drawString(MARGEN_X, 35, PIE_DE_PAGINA)
    c.drawRightString(ancho - MARGEN_X, 35,
                      datetime.now().strftime("Generado el %d/%m/%Y a las %H:%M"))

    c.save()
    buffer.seek(0)
    print(f" [PDF Cotiz] PDF de '{numero}' generado en memoria.")
    return buffer


# =============================================================================
# GENERADOR DE REPORTES SEMANALES / MENSUALES
# =============================================================================

def generar_reporte_pdf(datos: dict, tipo: str = "Semanal", productos_list: list = None) -> io.BytesIO:
    """
    Genera un PDF de reporte de actividad (semanal, mensual o personalizado).

    Args:
        datos: Dict devuelto por ConexionBD.obtener_datos_reporte()
        tipo: "Semanal", "Mensual" o "Personalizado"
        productos_list: Lista opcional de productos (tuplas) para incluir en el PDF

    Returns:
        io.BytesIO: Buffer con el PDF listo para enviar/guardar.
    """
    ancho, alto = letter
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)

    MARGEN = 50
    ANCHO_UTIL = ancho - 2 * MARGEN

    def encabezado(titulo_extra=""):
        logo_path = os.path.join("almacen_activos", "Logo", "logo.png")
        if os.path.exists(logo_path):
            try:
                c.drawImage(logo_path, MARGEN, alto - 75, width=110, height=35, preserveAspectRatio=True, mask="auto")
            except Exception:
                c.setFont("Helvetica-Bold", 16)
                c.setFillColorRGB(*COLOR_AZUL_EMP)
                c.drawString(MARGEN, alto - 55, "EDJ7 AUTOPARTS")
        else:
            c.setFont("Helvetica-Bold", 16)
            c.setFillColorRGB(*COLOR_AZUL_EMP)
            c.drawString(MARGEN, alto - 55, "EDJ7 AUTOPARTS")

        # Datos corporativos de la empresa
        c.setFont("Helvetica-Bold", 8)
        c.setFillColorRGB(*COLOR_NEGRO)
        c.drawString(MARGEN, alto - 90, "IMPORTADORA UZIEL C.A.")
        c.setFont("Helvetica", 7)
        c.setFillColorRGB(*COLOR_GRIS)
        c.drawString(MARGEN, alto - 100, "RIF: J-41234567-8 | Tlf: +58 (212) 555-0199 | Correo: contacto@importadorauziel.com")

        # Título del reporte
        c.setFont("Helvetica-Bold", 14)
        c.setFillColorRGB(*COLOR_AZUL_EMP)
        titulo = f"REPORTE {tipo.upper()} DE ACTIVIDAD"
        if titulo_extra:
            titulo += f" — {titulo_extra.upper()}"
        c.drawRightString(ancho - MARGEN, alto - 55, titulo)
        
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(*COLOR_GRIS)
        c.drawRightString(ancho - MARGEN, alto - 70, f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

        # Línea separadora azul brillante
        c.setStrokeColorRGB(0.05, 0.65, 0.91)
        c.setLineWidth(1.5)
        c.line(MARGEN, alto - 110, ancho - MARGEN, alto - 110)

    def pie():
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(*COLOR_GRIS)
        c.drawString(MARGEN, 35, PIE_DE_PAGINA)
        c.drawRightString(ancho - MARGEN, 35, datetime.now().strftime("Generado el %d/%m/%Y a las %H:%M"))

    def seccion(titulo, y):
        c.setFillColorRGB(*COLOR_AZUL_EMP)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(MARGEN, y, titulo.upper())
        c.setStrokeColorRGB(*COLOR_LINEA)
        c.setLineWidth(1)
        c.line(MARGEN, y - 4, ancho - MARGEN, y - 4)
        return y - 20

    def texto_linea(texto, y, bold=False, color=None, size=10):
        if y < 60:
            pie()
            c.showPage()
            encabezado()
            return alto - 130
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        if color:
            c.setFillColorRGB(*color)
        else:
            c.setFillColorRGB(*COLOR_NEGRO)
        c.drawString(MARGEN + 10, y, texto)
        return y - 14

    # --- Portada ---
    encabezado()
    y = alto - 130

    # Periodo
    fi = datos["fecha_inicio"]
    ff = datos["fecha_fin"]
    if hasattr(fi, 'strftime'):
        fi_str = fi.strftime("%d/%m/%Y")
    else:
        fi_str = str(fi)[:10]
    if hasattr(ff, 'strftime'):
        ff_str = ff.strftime("%d/%m/%Y")
    else:
        ff_str = str(ff)[:10]

    c.setFont("Helvetica-Bold", 16)
    c.setFillColorRGB(*COLOR_NEGRO)
    c.drawString(MARGEN, y, f"Periodo: {fi_str} — {ff_str}")

    y -= 30
    c.setFont("Helvetica", 11)
    c.setFillColorRGB(*COLOR_GRIS)
    c.drawString(MARGEN, y, "Resumen general de actividad en el periodo seleccionado.")

    # Tarjetas de resumen
    y -= 40
    tarjetas = [
        (" Clientes Nuevos", len(datos["clientes_nuevos"]), "#2563eb"),
        (" Productos Nuevos", len(datos["productos_nuevos"]), "#27ae5f"),
        (" Fotos Vinculadas", len(datos["activos_nuevos"]), "#e67e22"),
        (" Tareas Creadas", len(datos["tareas_creadas"]), "#8e44ad"),
        (" Tareas Completadas", len(datos["tareas_completadas"]), "#27ae5f"),
        (" Cotizaciones", len(datos["cotizaciones_creadas"]), "#e74c3c"),
    ]

    c.setStrokeColorRGB(*COLOR_LINEA)
    c.setLineWidth(0.5)
    for i, (label, valor, color_hex) in enumerate(tarjetas):
        col = i % 3
        row = i // 3
        x = MARGEN + col * (ANCHO_UTIL // 3)
        cy = y - row * 55

        c.setFillColorRGB(0.97, 0.98, 1.0)
        c.roundRect(x, cy - 40, ANCHO_UTIL // 3 - 10, 48, 6, fill=True, stroke=False)
        c.setFillColorRGB(*COLOR_NEGRO)
        c.setFont("Helvetica", 9)
        c.drawCentredString(x + (ANCHO_UTIL // 3 - 10) // 2, cy - 14, label)
        c.setFont("Helvetica-Bold", 22)
        c.setFillColorRGB(*{
            "#2563eb": (0.15, 0.39, 0.92),
            "#27ae5f": (0.15, 0.68, 0.37),
            "#e67e22": (0.90, 0.49, 0.13),
            "#8e44ad": (0.56, 0.27, 0.68),
            "#e74c3c": (0.91, 0.30, 0.24),
        }.get(color_hex, (0.15, 0.68, 0.37)))
        c.drawCentredString(x + (ANCHO_UTIL // 3 - 10) // 2, cy - 4, str(valor))

    y -= row * 55 + 55

    # --- Detalle por sección ---
    pie()
    c.showPage()
    encabezado("Detalle")
    y = alto - 130

    # 1. Clientes nuevos
    y = seccion(f" Clientes Nuevos ({len(datos['clientes_nuevos'])})", y)
    if datos["clientes_nuevos"]:
        for cli in datos["clientes_nuevos"]:
            texto = f"• {cli[1]} — RIF: {cli[0]} — Tlf: {cli[2]}"
            y = texto_linea(texto, y, size=9)
    else:
        y = texto_linea("No se registraron nuevos clientes en este periodo.", y, color=COLOR_GRIS)

    # 2. Productos nuevos
    if y < 120:
        pie(); c.showPage(); encabezado("Detalle (cont.)"); y = alto - 130
    y = seccion(f" Productos Nuevos ({len(datos['productos_nuevos'])})", y)
    if datos["productos_nuevos"]:
        for prod in datos["productos_nuevos"]:
            texto = f"• {prod[0]} — {prod[1]} — {prod[3]} — ${float(prod[4]):.2f}" if prod[4] else f"• {prod[0]} — {prod[1]} — {prod[3]}"
            y = texto_linea(texto, y, size=9)
    else:
        y = texto_linea("No se registraron nuevos productos en este periodo.", y, color=COLOR_GRIS)

    # 3. Fotos vinculadas
    if y < 120:
        pie(); c.showPage(); encabezado("Detalle (cont.)"); y = alto - 130
    y = seccion(f" Fotos Vinculadas ({len(datos['activos_nuevos'])})", y)
    if datos["activos_nuevos"]:
        for act in datos["activos_nuevos"]:
            texto = f"• SKU: {act[2]} ({act[3]}) — Ángulo: {act[1]}"
            y = texto_linea(texto, y, size=9)
    else:
        y = texto_linea("No se vincularon fotografías en este periodo.", y, color=COLOR_GRIS)

    # 4. Tareas creadas
    if y < 120:
        pie(); c.showPage(); encabezado("Detalle (cont.)"); y = alto - 130
    y = seccion(f" Tareas Creadas ({len(datos['tareas_creadas'])})", y)
    if datos["tareas_creadas"]:
        for t in datos["tareas_creadas"]:
            texto = f"• [{t[3]}] {t[2]} — Cliente: {t[1]} — Estado: {t[4]}"
            y = texto_linea(texto, y, size=9)
    else:
        y = texto_linea("No se crearon tareas en este periodo.", y, color=COLOR_GRIS)

    # 5. Tareas completadas
    if y < 120:
        pie(); c.showPage(); encabezado("Detalle (cont.)"); y = alto - 130
    y = seccion(f" Tareas Completadas ({len(datos['tareas_completadas'])})", y)
    if datos["tareas_completadas"]:
        for t in datos["tareas_completadas"]:
            texto = f"• {t[2]} — Asignado a: {t[3]} — Límite: {t[4]}"
            y = texto_linea(texto, y, size=9)
    else:
        y = texto_linea("No se completaron tareas en este periodo.", y, color=COLOR_GRIS)

    # 6. Cotizaciones
    if y < 120:
        pie(); c.showPage(); encabezado("Detalle (cont.)"); y = alto - 130
    y = seccion(f" Cotizaciones ({len(datos['cotizaciones_creadas'])})", y)
    if datos["cotizaciones_creadas"]:
        for cot in datos["cotizaciones_creadas"]:
            texto = f"• {cot[1]} — {cot[2]} — ${float(cot[3]):,.2f} — {cot[4]}"
            y = texto_linea(texto, y, size=9)
    else:
        y = texto_linea("No se crearon cotizaciones en este periodo.", y, color=COLOR_GRIS)

    # --- Productos agregados en el periodo ---
    if productos_list:
        if y < 120:
            pie(); c.showPage(); encabezado("Productos (cont.)"); y = alto - 130
        else:
            y -= 10
        y = seccion(f" Productos Agregados ({len(productos_list)})", y)

        c.setFont("Helvetica-Bold", 8)
        c.setFillColorRGB(*COLOR_AZUL_EMP)
        c.rect(MARGEN, y - 2, ancho - 2 * MARGEN, 14, fill=True, stroke=False)
        c.setFillColorRGB(1, 1, 1)
        c.drawString(MARGEN + 6, y + 3, "SKU")
        c.drawString(MARGEN + 110, y + 3, "NOMBRE")
        c.drawString(MARGEN + 310, y + 3, "MARCA")
        c.drawString(MARGEN + 410, y + 3, "PRECIO")
        y -= 16

        for idx, prod in enumerate(productos_list):
            if y < 60:
                pie(); c.showPage(); encabezado("Productos (cont.)"); y = alto - 130
            if idx % 2 == 0:
                c.setFillColorRGB(0.97, 0.98, 1.0)
            else:
                c.setFillColorRGB(1, 1, 1)
            c.rect(MARGEN, y - 2, ancho - 2 * MARGEN, 14, fill=True, stroke=False)

            c.setFillColorRGB(*COLOR_NEGRO)
            c.setFont("Courier", 8)
            c.drawString(MARGEN + 6, y + 3, str(prod[0]))
            c.setFont("Helvetica", 8)
            nombre = str(prod[1])
            if len(nombre) > 35:
                nombre = nombre[:32] + "..."
            c.drawString(MARGEN + 110, y + 3, nombre)
            c.drawString(MARGEN + 310, y + 3, str(prod[2]))
            c.setFillColorRGB(*COLOR_VERDE_PREC)
            precio = f"${float(prod[4]):,.2f}" if prod[4] else "—"
            c.drawRightString(ancho - MARGEN - 6, y + 3, precio)
            y -= 14

    # --- Totales generales ---
    if y < 120:
        pie(); c.showPage(); encabezado("Totales Generales"); y = alto - 130
    else:
        y -= 20
    y = seccion(" Totales Generales del Sistema", y)
    totales = [
        f"Total de clientes registrados:  {datos['total_clientes']}",
        f"Total de productos en catálogo: {datos['total_productos']}",
        f"Tareas pendientes actualmente:  {datos['total_tareas_pendientes']}",
        f"Total de cotizaciones emitidas: {datos['total_cotizaciones']}",
    ]
    for t in totales:
        y = texto_linea(t, y, bold=True, size=10)

    # --- Bitácora de Auditoría ---
    if y < 150:
        pie(); c.showPage(); encabezado("Bitácora"); y = alto - 130
    else:
        y -= 20
    
    y = seccion(" Bitácora de Auditoría (Acciones de Usuarios)", y)
    
    logs = datos.get("logs_auditoria", [])
    if logs:
        # Dibujar cabecera de tabla
        c.setFont("Helvetica-Bold", 8)
        c.setFillColorRGB(*COLOR_AZUL_EMP)
        c.rect(MARGEN, y - 2, ancho - 2 * MARGEN, 14, fill=True, stroke=False)
        c.setFillColorRGB(1, 1, 1)
        c.drawString(MARGEN + 6, y + 3, "FECHA / HORA")
        c.drawString(MARGEN + 110, y + 3, "USUARIO")
        c.drawString(MARGEN + 200, y + 3, "ACCIÓN")
        c.drawString(MARGEN + 310, y + 3, "DETALLE")
        y -= 16

        for idx, log in enumerate(logs):
            if y < 60:
                pie(); c.showPage(); encabezado("Bitácora (cont.)"); y = alto - 130
                # Redibujar cabecera de tabla
                c.setFont("Helvetica-Bold", 8)
                c.setFillColorRGB(*COLOR_AZUL_EMP)
                c.rect(MARGEN, y - 2, ancho - 2 * MARGEN, 14, fill=True, stroke=False)
                c.setFillColorRGB(1, 1, 1)
                c.drawString(MARGEN + 6, y + 3, "FECHA / HORA")
                c.drawString(MARGEN + 110, y + 3, "USUARIO")
                c.drawString(MARGEN + 200, y + 3, "ACCIÓN")
                c.drawString(MARGEN + 310, y + 3, "DETALLE")
                y -= 16
                
            if idx % 2 == 0:
                c.setFillColorRGB(0.97, 0.98, 1.0)
            else:
                c.setFillColorRGB(1, 1, 1)
            c.rect(MARGEN, y - 2, ancho - 2 * MARGEN, 14, fill=True, stroke=False)

            c.setFillColorRGB(*COLOR_NEGRO)
            c.setFont("Helvetica", 8)
            
            # Formatear fecha
            fecha_val = log[4]
            fecha_str = fecha_val.strftime("%d/%m/%Y %H:%M:%S") if hasattr(fecha_val, 'strftime') else str(fecha_val)[:19]
            
            c.drawString(MARGEN + 6, y + 3, fecha_str)
            c.drawString(MARGEN + 110, y + 3, str(log[1]))
            c.drawString(MARGEN + 200, y + 3, str(log[2]))
            
            # Truncar detalle si es muy largo
            detalle = str(log[3])
            if len(detalle) > 55:
                detalle = detalle[:52] + "..."
            c.drawString(MARGEN + 310, y + 3, detalle)
            y -= 14
    else:
        y = texto_linea("No se registraron acciones en la bitácora durante este periodo.", y, color=COLOR_GRIS)

    pie()
    c.save()
    buffer.seek(0)
    return buffer


# =============================================================================
# ZONA DE PRUEBA — Ejecutar directamente para probar
# =============================================================================

if __name__ == "__main__":
    skus_prueba = ["BMB-GAS-CORS-01"]
    print(f"Generando catálogo para: {skus_prueba}")
    exito, ruta = generar_pdf_catalogo(skus_prueba)
    if exito:
        print(f" PDF generado: {ruta}")
    else:
        print(" No se pudo generar el PDF. Verifica los SKUs y la conexión a BD.")
