from fastapi import FastAPI
from dotenv import load_dotenv
from app.endpoints.endpoints import router

load_dotenv()


app = FastAPI()

app.include_router(router)


@app.on_event("startup")
async def startup_event():
	print("\n=========================================================")
	print("=========================================================\n")

# Ruta raíz
@app.get("/")
def root():
    return {
        "message": "👋 Bienvenido a la API de WhatsApp",
        "docs": "Visita /docs para ver la documentación "
    }

