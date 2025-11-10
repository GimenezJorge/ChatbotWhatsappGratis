# Asistente virtual de supermercado

Asistente virtual inteligente que permite a los clientes consultar productos, armar pedidos y recibir asistencia vía WhatsApp, usando IA local (Ollama) y base de datos MySQL.

---

## Requisitos

- **Python 3.10+**
- **Node.js 18+** (para `whatsapp-web.js`)
- **MySQL 8.0+** (o MariaDB)
- **Ollama** (con el modelo `gemma3:latest`)
- **Google Chrome** (requerido por Puppeteer en `whatsapp-web.js`)

---

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/Chatbot-WhatsApp.git
cd Chatbot-WhatsApp
```

### 2. Cambiar ruta del Chrome por tu ubicación

> executablePath: "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"

### 3. Instalacion del modelo gemma3:latest (Ollama)

> ollama pull gemma3

- Para verificar si ya tenes el modelo

> ollama list

### 4. Crear modelos personalizados (Prompts enbebidos)

1. Abrir un cmd
2. Moverse a la carpeta prompts_finales/
3. Pegar los comandos en la consola

- Modelo input:
  > ollama create gemma3_input:latest -f Modelfile-input
- Modelo output:
  > ollama create gemma3_output:latest -f Modelfile-output

## Instructivo para hacer andar el Chatbot-Ollama

Opcion 1:
Ejecutar el script .bat

> start.bat

- Este script realiza la descarga de dependencias (del requirements.txt), inicia el servidor FastAPI en el puerto 8000, ejecuta WhatsApp Web a través de una librería de Node en el puerto 3000 y levanta el servicio de Ollama para que la IA esté disponible.

## Instala las dependencias:

> pip install -r requirements.txt

## Levanta el servidor FastAPI:

> uvicorn app.main:app --reload --port 8000

## Levanta el servidor Node:

> node bot.js

## Enviroments credentials

```
Database credentials
> MYSQL_HOST=""
> MYSQL_USER=""
> MYSQL_PASSWORD=""
> MYSQL_DATABASE=""
> MYSQL_PORT=""
```

## Project Structure

```
version1/
├── app/
│ ├── **init**.py
│ ├── endpoints/
│ │ └── endpoints.py
│ ├── crud.py
│ ├── database.py
│ ├── main.py
│ └── schemas.py
│
├── prompts_finales/
│ ├── Modelfile-input
│ └── Modelfile-output
├── conversaciones/
├── script/
├── test/
├── .env
├── .gitattributes
├── .gitignore
├── README.md
├── bot.js
├── requirements.txt
└── start.bat

```
