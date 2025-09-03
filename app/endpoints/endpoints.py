from datetime import datetime
from fastapi import Depends, Request, APIRouter
from ..crud import verify_token
import os
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from ..schemas import SendMessageRequest
from ..crud import get_response

# Crear el router
router = APIRouter()

# Credenciales
twilio_whatsapp_number = os.getenv("TWILIO_WHATSAPP_NUMBER")
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")

# Carpeta para conversaciones
CARPETA_CONVERSACIONES = "conversaciones"
os.makedirs(CARPETA_CONVERSACIONES, exist_ok=True)

# Lista para guardar mensajes recibidos en memoria
mensajes_recibidos = []

# Cliente de Twilio
client = Client(account_sid, auth_token)

@router.get("/test")
def test():
    return {"message": "Funciona!"}

# Enviar mensaje manualmente
@router.post("/send")
def send_whatsapp(request_data: SendMessageRequest, token: str = Depends(verify_token)):
    message = client.messages.create(
        from_=twilio_whatsapp_number,
        body=request_data.message,
        to=f"whatsapp:{request_data.to}"
    )
    return {"status": "success", "sid": message.sid}

# Recibir mensajes entrantes de WhatsApp
@router.post("/webhook")
async def webhook(request: Request):
    try:
        # Leer cuerpo como bytes
        body_bytes = await request.body()
        print("🔍 Raw body (bytes):", body_bytes)

        if not body_bytes:
            print("❌ Cuerpo vacío")
            return {"status": "error", "message": "Cuerpo vacío"}

        # Parsear manualmente
        from urllib.parse import parse_qs
        body_str = body_bytes.decode("utf-8")
        form_data = parse_qs(body_str)
        from_number = form_data.get("From", [None])[0]
        body = form_data.get("Body", [None])[0]

        print(f"📄 From: {from_number}")
        print(f"📄 Body: {body}")

        if not from_number or not body:
            print("⚠️ Datos faltantes")
            return {"error": "Datos incompletos", "status": "Failed"}

        # Guardar en archivo
        session_id = from_number.replace("whatsapp:", "").replace("+", "").replace(":", "_")
        ruta_archivo = os.path.join(CARPETA_CONVERSACIONES, f"{session_id}.txt")

        with open(ruta_archivo, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - De {from_number}: {body}\n")

        print(f"✅ Archivo guardado: {ruta_archivo}")

        # Generar respuesta
        try:
            bot_response = get_response(body,session_id)
        except Exception as e:
            print(f"❌ Error en IA: {e}")
            bot_response = "Estoy teniendo problemas para responder."

        # Guardar respuesta
        with open(ruta_archivo, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Bot: {bot_response}\n")

        # Enviar con Twilio
        client.messages.create(
            from_=twilio_whatsapp_number,
            body=bot_response,
            to=from_number
        )
        print(f"✅ Respuesta enviada a {from_number}")

        return {"status": "ok"}

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return {"error": str(e)}

# Endpoint para ver mensajes en memoria
@router.get("/mensajes")
def ver_mensajes():
    return {"mensajes": mensajes_recibidos}
