# =============================================================================
# src/generador_pdf.py
# Motor de Generación de Fichas Técnicas PDF (Aplicación de Escritorio)
# Proyecto: Dashboard de Marketing - Importadora Uziel C.A.
# Autor: Jesús | Librería: ReportLab | Python 3.11.8
# =============================================================================
#
# DESCRIPCIÓN:
#   Genera una ficha técnica en formato PDF para un producto específico,
#   combinando sus datos del módulo PIM con su fotografía del módulo DAM.
#   El archivo se guarda en la carpeta donde se ejecuta el programa.
#
#   Usado por: main.py (botón "Generar Ficha Técnica PDF" en la pestaña PIM)
# =============================================================================

import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from src.database import ConexionBD


# =============================================================================
# ██████████████ CONFIGURACIÓN DEL PDF - EDITAR AQUÍ ██████████████
# =============================================================================

# Identidad corporativa
NOMBRE_EMPRESA = "IMPORTADORA UZIEL C.A."
PIE_DE_PAGINA = "Documento generado automáticamente por el Sistema de Información Uziel."

# Márgenes y posiciones (coordenadas en puntos PDF, 72 puntos = 1 pulgada)
MARGEN_X = 50            # Margen izquierdo del contenido
X_IMAGEN = 300           # Posición horizontal de la fotografía del producto
Y_IMAGEN_OFFSET = 350    # Cuánto bajar desde el tope de la página para la imagen
ANCHO_IMAGEN = 250       # Ancho de la imagen en el PDF (puntos)
ALTO_IMAGEN = 250        # Alto de la imagen en el PDF (puntos)

# Colores RGB (valores entre 0.0 y 1.0)
COLOR_AZUL_EMPRESA = (0.18, 0.52, 0.75)   # Encabezado de empresa
COLOR_NEGRO = (0, 0, 0)                    # Texto general
COLOR_VERDE_PRECIO = (0.15, 0.68, 0.37)   # Precio destacado
COLOR_GRIS_SECUNDARIO = (0.5, 0.5, 0.5)   # Textos secundarios (pie de página)

# Tamaños de fuente
FUENTE_EMPRESA = 24     # Nombre de la empresa en el encabezado
FUENTE_NOMBRE_PROD = 18 # Nombre del producto
FUENTE_DATOS = 12       # Datos técnicos (SKU, marca, etc.)
FUENTE_PRECIO = 14      # Precio destacado
FUENTE_PIE = 10         # Pie de página

# =============================================================================


def generar_ficha_tecnica(sku: str) -> bool:
    """
    Genera una ficha técnica en PDF para el producto indicado.

    El PDF incluye:
      - Encabezado con el nombre de la empresa
      - Nombre del producto
      - Datos técnicos: SKU, marca, compatibilidad
      - Precio corporativo destacado en verde
      - Fotografía del producto (si existe en el DAM)
      - Pie de página informativo

    El archivo se guarda en el directorio de trabajo actual con el nombre
    'Ficha_Tecnica_<SKU>.pdf' (Ej: Ficha_Tecnica_BMB-GAS-CORS-01.pdf).

    Args:
        sku (str): Código SKU del producto para el cual generar la ficha.

    Returns:
        bool: True si el PDF fue generado exitosamente, False si el SKU
              no existe en la base de datos o ocurre un error.
    """
    # Consultar los datos del producto incluyendo su imagen del DAM
    bd = ConexionBD()
    datos = bd.obtener_producto_con_imagen(sku)

    if not datos:
        print(f"🔴 [PDF] No se encontró el SKU '{sku}' en la base de datos.")
        return False

    nombre, marca, compatibilidad, precio, ruta_img = datos

    # Definir el nombre del archivo de salida
    nombre_pdf = f"Ficha_Tecnica_{sku}.pdf"

    # Obtener las dimensiones de la página carta (letter)
    ancho_pagina, alto_pagina = letter

    # ---- Crear el lienzo del PDF ----
    c = canvas.Canvas(nombre_pdf, pagesize=letter)

    # ---- 1. Encabezado: Nombre de la empresa ----
    c.setFont("Helvetica-Bold", FUENTE_EMPRESA)
    c.setFillColorRGB(*COLOR_AZUL_EMPRESA)
    c.drawString(MARGEN_X, alto_pagina - 80, NOMBRE_EMPRESA)

    # ---- 2. Nombre del producto ----
    c.setFont("Helvetica-Bold", FUENTE_NOMBRE_PROD)
    c.setFillColorRGB(*COLOR_NEGRO)
    c.drawString(MARGEN_X, alto_pagina - 130, nombre)

    # ---- 3. Datos técnicos ----
    c.setFont("Helvetica", FUENTE_DATOS)
    c.drawString(MARGEN_X, alto_pagina - 160, f"SKU:              {sku}")
    c.drawString(MARGEN_X, alto_pagina - 180, f"Marca:            {marca}")
    c.drawString(MARGEN_X, alto_pagina - 200, f"Compatibilidad:   {compatibilidad}")

    # ---- 4. Precio (destacado en verde) ----
    c.setFont("Helvetica-Bold", FUENTE_PRECIO)
    c.setFillColorRGB(*COLOR_VERDE_PRECIO)
    c.drawString(MARGEN_X, alto_pagina - 230, f"Precio Corporativo:   ${precio}")

    # ---- 5. Fotografía del producto (desde el DAM) ----
    c.setFillColorRGB(*COLOR_NEGRO)  # Restablecer color antes de la imagen

    if ruta_img and os.path.exists(ruta_img):
        # Insertar la fotografía con tamaño controlado y proporción preservada
        c.drawImage(
            ruta_img,
            X_IMAGEN,
            alto_pagina - Y_IMAGEN_OFFSET,
            width=ANCHO_IMAGEN,
            height=ALTO_IMAGEN,
            preserveAspectRatio=True,
            mask='auto'
        )
    else:
        # Si no hay foto, mostrar un mensaje de aviso en el espacio de la imagen
        c.setFont("Helvetica-Oblique", FUENTE_DATOS)
        c.setFillColorRGB(*COLOR_GRIS_SECUNDARIO)
        c.drawString(X_IMAGEN, alto_pagina - 200, "[Sin imagen disponible en el DAM]")

    # ---- 6. Pie de página ----
    c.setFont("Helvetica", FUENTE_PIE)
    c.setFillColorRGB(*COLOR_GRIS_SECUNDARIO)
    c.drawString(MARGEN_X, 50, PIE_DE_PAGINA)

    # ---- Guardar el archivo en disco ----
    c.save()
    print(f"🟢 [PDF] Ficha técnica generada: '{nombre_pdf}'")
    return True


# =============================================================================
# ZONA DE PRUEBA — Ejecutar directamente para probar
# =============================================================================

if __name__ == "__main__":
    # Cambia este SKU por uno que exista en tu base de datos
    sku_prueba = "BMB-GAS-CORS-01"
    print(f"Generando ficha técnica para SKU: {sku_prueba}")
    resultado = generar_ficha_tecnica(sku_prueba)
    if resultado:
        print("✅ PDF generado exitosamente. Revisa la carpeta del proyecto.")
    else:
        print("❌ No se pudo generar el PDF. Verifica el SKU y la conexión a BD.")
