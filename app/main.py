from fastapi import FastAPI
from dotenv import load_dotenv
from app.endpoints.endpoints import router

load_dotenv()


app = FastAPI()

app.include_router(router)

# Ruta raíz
@app.get("/")
def root():
    return {
        "message": "👋 Bienvenido a la API de WhatsApp",
        "docs": "Visita /docs para ver la documentación "
    }

#mini test:
# from fastapi import Body

# @app.post("/process-message")
# def process_message_test(data: dict = Body(...)):
#     """
#     Endpoint temporal para recibir mensajes desde bot.js
#     Espera un JSON con: { "from": "54911XXXXXXX", "body": "mensaje" }
#     """
#     from_number = data.get("from")
#     body = data.get("body")
    
#     # Llamamos a tu función original get_response
#     response_text = get_response(body, session_id=from_number)
    
#     return {"status": "ok", "response": response_text}
