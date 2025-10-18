from fastapi import APIRouter, Request
from ..crud import get_response
import os
from datetime import datetime

router = APIRouter()

# Carpeta para guardar conversaciones
CARPETA_CONVERSACIONES = "conversaciones"
os.makedirs(CARPETA_CONVERSACIONES, exist_ok=True)

@router.post("/process-message")
async def process_message(request: Request):
    try:
        data = await request.json()  # parsea el JSON directamente
        from_number = data.get("from")
        body = data.get("body")

        if not from_number or not body:
            return {"status": "error", "message": "Datos incompletos"}

        # Guardar conversación en archivo
        session_id = from_number.replace("+", "").replace(":", "_")
        ruta_archivo = os.path.join(CARPETA_CONVERSACIONES, f"{session_id}.txt")

        with open(ruta_archivo, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - De {from_number}: {body}\n")

        # Generar respuesta usando tu función de IA
        try:
            bot_response = get_response(body, session_id)
        except Exception as e:
            print(f"❌ Error en IA: {e}")
            bot_response = "Estoy teniendo problemas para responder."

        # Guardar respuesta
        with open(ruta_archivo, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Bot: {bot_response}\n")

        return {"status": "ok", "response": bot_response}

    except Exception as e:
        print(f"❌ Error procesando mensaje: {e}")
        return {"status": "error", "message": str(e)}
