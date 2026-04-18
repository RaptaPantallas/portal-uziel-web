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
    c.drawString(MARGEN_X + 130, alto - 204, f"$ {precio}")

    # ---- Fotografía del producto ----
    c.setFillColorRGB(*COLOR_NEGRO)
    if ruta_img and os.path.exists(ruta_img):
        c.drawImage(
            ruta_img,
            X_IMAGEN,
            alto - Y_IMAGEN_OFFSET,
            width=ANCHO_IMAGEN,
            height=ALTO_IMAGEN,
            preserveAspectRatio=True,
            mask="auto"
        )
    else:
        # Marco de "sin imagen"
        c.setStrokeColorRGB(*COLOR_LINEA)
        c.setFillColorRGB(0.96, 0.97, 0.99)
        c.roundRect(X_IMAGEN, alto - Y_IMAGEN_OFFSET,
                    ANCHO_IMAGEN, ALTO_IMAGEN, 8, fill=True, stroke=True)
        c.setFont("Helvetica-Oblique", 10)
        c.setFillColorRGB(*COLOR_GRIS)
        c.drawCentredString(
            X_IMAGEN + ANCHO_IMAGEN / 2,
            alto - Y_IMAGEN_OFFSET + ALTO_IMAGEN / 2,
            "Sin imagen en el DAM"
        )

    # ---- Pie de página ----
    c.setFont("Helvetica", FUENTE_PIE)
    c.setFillColorRGB(*COLOR_GRIS)
    c.drawString(MARGEN_X, 35, PIE_DE_PAGINA)
    # Número de página
    c.drawRightString(ancho - MARGEN_X, 35,
                      datetime.now().strftime("Generado el %d/%m/%Y a las %H:%M"))


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
        print(f"🔴 [PDF] SKU '{sku}' no encontrado en la base de datos.")
        return False

    nombre_pdf  = f"Ficha_Tecnica_{sku}.pdf"
    ancho, alto = letter

    c = canvas.Canvas(nombre_pdf, pagesize=letter)
    _dibujar_pagina_producto(c, sku, datos, ancho, alto)
    c.save()

    print(f"🟢 [PDF] Ficha técnica generada: '{nombre_pdf}'")
    return True


# ---------------------------------------------------------------------------
# FUNCIÓN 2 — Catálogo multi-producto (nueva)
# ---------------------------------------------------------------------------

def generar_pdf_catalogo(lista_skus: list[str]) -> tuple[bool, str]:
    """
    Genera un catálogo PDF con una página por producto para cada SKU indicado.

    El archivo se nombra automáticamente con la fecha y hora de generación
    para evitar sobreescribir versiones anteriores.

    Args:
        lista_skus (list[str]): Lista de códigos SKU a incluir en el catálogo.

    Returns:
        tuple[bool, str]:
            - True y la ruta del archivo si el PDF fue generado exitosamente.
            - False y una cadena vacía si ningún SKU fue encontrado.
    """
    bd = ConexionBD()

    # Recopilar datos de todos los SKUs válidos
    paginas = []
    for sku in lista_skus:
        datos = bd.obtener_producto_con_imagen(sku.strip().upper())
        if datos:
            paginas.append((sku.strip().upper(), datos))
        else:
            print(f"⚠️  [PDF Catálogo] SKU '{sku}' no encontrado — se omitirá.")

    if not paginas:
        print("🔴 [PDF Catálogo] Ningún SKU válido encontrado. PDF no generado.")
        return False, ""

    # Nombre de archivo con timestamp para evitar colisiones
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_pdf  = f"Catalogo_Uziel_{timestamp}.pdf"
    ancho, alto = letter

    c = canvas.Canvas(nombre_pdf, pagesize=letter)

    for idx, (sku, datos) in enumerate(paginas):
        if idx > 0:
            c.showPage()   # Nueva página por cada producto después del primero
        _dibujar_pagina_producto(c, sku, datos, ancho, alto)

    c.save()

    print(f"🟢 [PDF Catálogo] {len(paginas)} producto(s) incluidos. Archivo: '{nombre_pdf}'")
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

    # ---- Banda de encabezado ----
    c.setFillColorRGB(*COLOR_AZUL_EMP)
    c.rect(0, alto - 90, ancho, 90, fill=True, stroke=False)

    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", FUENTE_EMP)
    c.drawString(MARGEN_X, alto - 52, NOMBRE_EMPRESA)
    c.setFont("Helvetica", 10)
    c.setFillColorRGB(0.8, 0.88, 1.0)
    c.drawString(MARGEN_X, alto - 72, "Cotización / Presupuesto Comercial")

    # Badge número de cotización
    badge_x = ancho - 190
    badge_y = alto - 68
    c.setFillColorRGB(1, 1, 1)
    c.roundRect(badge_x, badge_y, 160, 22, 5, fill=True, stroke=False)
    c.setFillColorRGB(*COLOR_AZUL_EMP)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(badge_x + 80, badge_y + 7, numero)

    # ---- Datos del cliente ----
    y = alto - 115
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
    print(f"🟢 [PDF Cotiz] PDF de '{numero}' generado en memoria.")
    return buffer


# =============================================================================
# ZONA DE PRUEBA — Ejecutar directamente para probar
# =============================================================================

if __name__ == "__main__":
    skus_prueba = ["BMB-GAS-CORS-01"]
    print(f"Generando catálogo para: {skus_prueba}")
    exito, ruta = generar_pdf_catalogo(skus_prueba)
    if exito:
        print(f"✅ PDF generado: {ruta}")
    else:
        print("❌ No se pudo generar el PDF. Verifica los SKUs y la conexión a BD.")
