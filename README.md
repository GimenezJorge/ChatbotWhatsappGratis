ASISTENTE VIRTUAL DE SUPERMERCADO

Asistente virtual inteligente que permite a los clientes consultar productos, armar pedidos y recibir asistencia vía WhatsApp, usando IA local (Ollama) y base de datos MySQL.


REQUISITOS:

- **Python 3.10+**
- **Node.js 18+** (para `whatsapp-web.js`)
- **MySQL 8.0+** (o MariaDB)
- **Ollama** (con el modelo `gemma3:latest`)


INSTALACION:

1. Clonar el repositorio

git clone https://github.com/tu-usuario/Chatbot-WhatsApp.git
cd Chatbot-WhatsApp


2. Instalacion del modelo gemma3:latest (Ollama)

  ollama pull gemma3

  Para verificar si ya tenes el modelo

  ollama list

3. Crear modelos personalizados (Prompts enbebidos)

3.1. Abrir un cmd
3.2. Moverse a la carpeta prompts_finales/
3.3. Pegar los comandos en la consola

Modelo input:
  ollama create gemma3_input:latest -f Modelfile-input

Modelo output:
  ollama create gemma3_output:latest -f Modelfile-output

4. CREAR UN .ENV

MYSQL_HOST=""
MYSQL_USER=""
MYSQL_PASSWORD=""
MYSQL_DATABASE=""
MYSQL_PORT=""

ACCESS_TOKEN=123

5. Instructivo para hacer andar el Chatbot-Ollama

INSTALAR LAS DEPENDENCIAS

pip install -r requirements.txt

npm install

6. Levanta el servidor FastAPI en una terminal:

uvicorn app.main:app --reload --port 8000

7. Levanta el servidor Node en otra terminal:

node bot.js
