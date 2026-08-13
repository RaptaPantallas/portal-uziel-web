# =============================================================================
# src/bcv_manager.py
# Gestor de Tasa BCV (Dólar API)
# =============================================================================

import urllib.request
import json
import threading
import time

class BCVManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(BCVManager, cls).__new__(cls)
                cls._instance.tasa_actual = 0.0
                cls._instance.ultima_actualizacion = 0
                cls._instance.cache_ttl = 3600  # 1 hora
                # Iniciar hilo para obtener la tasa silenciosamente en background
                hilo = threading.Thread(target=cls._instance._fetch_tasa_silencioso, daemon=True)
                hilo.start()
        return cls._instance

    def _fetch_tasa_silencioso(self):
        self.obtener_tasa_bcv()
        
    def obtener_tasa_bcv(self) -> float:
        """Devuelve la tasa del BCV. Usa cache por 1 hora."""
        ahora = time.time()
        
        # Si la cache es válida y ya tenemos una tasa, la usamos
        if (ahora - self.ultima_actualizacion < self.cache_ttl) and self.tasa_actual > 0:
            return self.tasa_actual
            
        try:
            url = "https://ve.dolarapi.com/v1/dolares/oficial"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                if "promedio" in data and data["promedio"]:
                    tasa = float(data["promedio"])
                    self.tasa_actual = tasa
                    self.ultima_actualizacion = ahora
                    return tasa
        except Exception as e:
            print(f" [BCV] Error obteniendo tasa: {e}")
            
        # Si falla, retorna la última conocida o 0.0
        return self.tasa_actual

    def formatear_precio(self, precio_usd, bd=None) -> str:
        """
        Formatea el precio en USD. 
        Si bd está presente y la config 'mostrar_bcv' es '1', añade la conversión a Bs.
        """
        if precio_usd is None or precio_usd == "":
            return "—"
            
        try:
            precio_usd = float(precio_usd)
        except ValueError:
            return str(precio_usd)

        mostrar_bs = False
        if bd:
            # Consultamos la configuración desde la BD
            mostrar_bs = (bd.obtener_configuracion("mostrar_bcv", "0") == "1")

        if mostrar_bs:
            tasa = self.obtener_tasa_bcv()
            if tasa > 0:
                precio_bs = precio_usd * tasa
                return f"REF {precio_usd:,.2f}$ / Bs {precio_bs:,.2f}"
                
        return f"${precio_usd:,.2f}"

    def extraer_usd(self, precio_str: str) -> float:
        """Extrae el valor numérico en USD desde una cadena formateada con o sin BCV."""
        if not precio_str or precio_str == "—":
            return 0.0
        try:
            if "REF" in precio_str:
                # Formato: "REF 2.50$ / Bs 90.62"
                parte_usd = precio_str.split("$")[0].replace("REF", "").strip().replace(",", "")
                return float(parte_usd)
            else:
                # Formato: "$2.50"
                parte_usd = precio_str.replace("$", "").strip().replace(",", "")
                return float(parte_usd)
        except Exception:
            return 0.0

# Instancia global para ser usada a lo largo de la app
bcv = BCVManager()
