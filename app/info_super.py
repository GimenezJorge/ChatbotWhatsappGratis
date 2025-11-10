import os

def leer_info_supermercado():
    ruta_archivo = os.path.join(os.path.dirname(__file__), "..", "info_supermercado.txt")
    try:
        with open(ruta_archivo, "r", encoding="utf-8") as f:
            contenido = f.read().strip()
        return contenido
    except FileNotFoundError:
        return "No se encontró el archivo info_supermercado.txt."
