# src/generador_pdf.py
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from src.database import ConexionBD

def generar_ficha_tecnica(sku):
    bd = ConexionBD()
    datos = bd.obtener_producto_con_imagen(sku)
    
    if not datos:
        print(f"🔴 No se encontró el SKU {sku} en la base de datos.")
        return False
        
    nombre, marca, compatibilidad, precio, ruta_img = datos
    
    # Nombre del archivo PDF de salida
    nombre_pdf = f"Ficha_Tecnica_{sku}.pdf"
    
    # Crear el lienzo (Canvas)
    c = canvas.Canvas(nombre_pdf, pagesize=letter)
    ancho, alto = letter
    
    # 1. Dibujar el Encabezado
    c.setFont("Helvetica-Bold", 24)
    c.setFillColorRGB(0.18, 0.52, 0.75) # Color Azul Uziel
    c.drawString(50, alto - 80, "IMPORTADORA UZIEL C.A.")
    
    # 2. Dibujar Título del Producto
    c.setFont("Helvetica-Bold", 18)
    c.setFillColorRGB(0, 0, 0) # Negro
    c.drawString(50, alto - 130, nombre)
    
    # 3. Dibujar Datos Técnicos
    c.setFont("Helvetica", 12)
    c.drawString(50, alto - 160, f"SKU: {sku}")
    c.drawString(50, alto - 180, f"Marca: {marca}")
    c.drawString(50, alto - 200, f"Compatibilidad: {compatibilidad}")
    
    c.setFont("Helvetica-Bold", 14)
    c.setFillColorRGB(0.15, 0.68, 0.37) # Verde para el precio
    c.drawString(50, alto - 230, f"Precio Corporativo: ${precio}")
    
    # 4. Dibujar la Imagen (DAM)
    if ruta_img and os.path.exists(ruta_img):
        # Insertar la foto ajustando su tamaño a 300x300 pixeles
        c.drawImage(ruta_img, 300, alto - 350, width=250, height=250, preserveAspectRatio=True, mask='auto')
    else:
        c.setFont("Helvetica-Oblique", 10)
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.drawString(300, alto - 200, "[Sin imagen disponible en el DAM]")
    
    # 5. Pie de página y Guardar
    c.setFont("Helvetica", 10)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(50, 50, "Documento generado automáticamente por el Sistema de Información Uziel.")
    
    c.save()
    print(f"🟢 Ficha técnica generada exitosamente: {nombre_pdf}")
    return True

# --- ZONA DE PRUEBA ---
if __name__ == "__main__":
    # Vamos a probar con el SKU de la bomba de gasolina
    generar_ficha_tecnica("BMB-GAS-CORS-01")