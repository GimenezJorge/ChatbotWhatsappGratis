import os
import re
import json
from fastapi import HTTPException
from langchain_ollama import OllamaLLM
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from app.database import connect_to_db

# ================================
# Verificar Token
# ================================
access_token_env = os.getenv("ACCESS_TOKEN")
def verify_token(token: str):
    if token != access_token_env:
        raise HTTPException(status_code=401, detail="Token inválido")
    return True



# ================================
# Cargar configuración
# ================================

# Cargar el archivo config.json
def load_config():
    try:
        with open("config.json", "r", encoding="utf-8") as file:
            print("Archivo config.json cargado correctamente.")
            return json.load(file)
    except FileNotFoundError:
        print("Error: El archivo config.json no fue encontrado.")
        return None
    except json.JSONDecodeError:
        print("Error: El archivo config.json no es válido.")
        return None

# Cargar la configuración al inicio del programa
config = load_config()
if not config:
    exit("No se pudo cargar la configuración. Terminando el programa.")


# ================================
# Modelo de IA
# ================================

# Configuración inicial del modelo Ollama
model = OllamaLLM(model="gemma3:latest")

# Prompt con historial
prompt = ChatPromptTemplate.from_messages([
    ("system", "Eres un asistente útil."),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{input}")
])

# Cadena final
chain = prompt | model

# Historial en memoria
store = {}

def get_session_history(session_id: str):
    if session_id not in store:
        store[session_id] = InMemoryChatMessageHistory()
    return store[session_id]

with_message_history = RunnableWithMessageHistory(
    chain,
    get_session_history,
    input_messages_key="input",
    history_messages_key="history"
)

def log_historial_archivo(session_id:str)-> list:
    ruta_archivo = os.path.join("conversaciones",f"{session_id}.txt")
    if not os.path.exists(ruta_archivo):
        return []
    try:
        with open(ruta_archivo,'r',encoding='utf-8')as file:
            lineas = file.readlines()
        
        historial = []
        for linea in lineas:
            linea = linea.strip()
            if " - De " in linea:
                # Formato: "2025-08-27 19:51:29 - De whatsapp:+54911...: Mensaje"
                try:
                    timestamp_str = linea[:19]  # "2025-08-27 19:51:29"
                    resto = linea[20:]  

                    if "De " in resto and ": " in resto:
                        contenido = resto.split(": ", 1)[1]  # mensaje después del número
                        historial.append({
                            "timestamp": timestamp_str,
                            "role": "user",
                            "content": contenido
                        })
                except:
                    continue

            elif " - Bot: " in linea:
                # Formato: "2025-08-27 19:51:30 - Bot: Tienen 15 unidades"
                try:
                    timestamp_str = linea[:19]
                    contenido = linea.split(" - Bot: ", 1)[1]
                    historial.append({
                        "timestamp": timestamp_str,
                        "role": "bot",
                        "content": contenido
                    })
                except:
                    continue
        
        return historial
    except Exception as e:
        print(f"❌ Error leyendo historial del archivo: {e}")
        return []

# ================================
# Buscar productos
# ================================

def get_product_info(product_name: str):
    connection = connect_to_db()
    if not connection:
        return print("no se conecto a la bd")
    else:
        print("se conecto a la bd")

    cursor = connection.cursor(dictionary=True)
    # Consulta para productos que COMIENZAN con el nombre dado
    QUERY_START = """SELECT 
    p.id, 
    p.nombre AS producto, 
    p.descripcion, 
    p.precio_costo, 
    p.precio_venta, 
    p.stock, 
    m.nombre AS marca, 
    c.nombre AS categoria
    FROM productos p 
    INNER JOIN marcas m ON p.marca_id = m.id 
    INNER JOIN categorias c ON p.categoria_id = c.id
    WHERE LOWER(p.nombre) LIKE %s or LOWER(m.nombre) LIKE %s or LOWER(c.nombre) LIKE %s
    ORDER BY p.nombre ASC; """

    # Consulta para productos que CONTIENEN el nombre dado

    QUERY_CONTAINS = """SELECT 
    p.id, 
    p.nombre AS producto, 
    p.descripcion, 
    p.precio_costo, 
    p.precio_venta, 
    p.stock, 
    m.nombre AS marca, 
    c.nombre AS categoria
    FROM productos p 
    INNER JOIN marcas m ON p.marca_id = m.id 
    INNER JOIN categorias c ON p.categoria_id = c.id
    WHERE LOWER(p.nombre) LIKE %s
    AND NOT LOWER(p.nombre) LIKE %s
    ORDER BY p.nombre ASC;"""

    product_name_lower = product_name.strip().lower()

    words = product_name.strip().lower().split()
    if words:
        first_word = words[0]
    else:
        first_word = product_name.strip().lower()

    # Usar la consulta externa
    cursor.execute(QUERY_START, (f"{first_word}%",f"{first_word}%",f"{first_word}%"))
    start_results = cursor.fetchall()

    if start_results:
        cursor.close()
        connection.close()
        return start_results

    # Si no hay coincidencias al inicio, buscar que contenga el término
    cursor.execute(QUERY_CONTAINS, (f"%{product_name_lower}%", f"{product_name_lower}%"))
    contain_results = cursor.fetchall()

    cursor.close()
    connection.close()

    if contain_results:
        return contain_results

    return f"No se encontró ningún producto relacionado con '{product_name}'."

# ================================
# Detectar producto con IA
# ================================

def detect_product_with_ai(user_input):
    with open("prompts//prompt_input.txt", "r", encoding="utf-8") as file:
        prompt = file.read()
        print("Se cargó correctamente el archivo.txt")
    
    prompt += f"""

Frase del usuario: "{user_input}"
Producto mencionado: 
"""
    try:
        # Invocar al modelo
        raw_response = model.invoke(prompt).strip()

        # Limpiar la respuesta
        # Eliminar etiquetas <think>...<think>
        cleaned = re.sub(r"<think>.*?</think>", "", raw_response, flags=re.DOTALL | re.IGNORECASE)
        
        # Extraer la parte después de "Productos mencionados:"
        if "Productos mencionados:" in cleaned:
            products_text = cleaned.split("Productos mencionados:")[1].strip()
        else:
            products_text = cleaned  # por si el modelo responde directamente

        # Dividir por comas, saltos de línea o "y"

        # Divide por coma, " y ", o saltos de línea
        product_list = re.split(r',|\s+y\s+|\n', products_text, flags=re.IGNORECASE)
        
        # Limpiar cada producto
        product_list = [
            p.strip().rstrip(".").strip()
            for p in product_list
            if p.strip() and p.lower() not in ["ninguno", "ninguna", "no"]
        ]

        # Validar que no esté vacío
        if not product_list:
            return None

        print(f"✅ Productos detectados: {product_list}")
        return product_list  # Devuelve lista

    except Exception as e:
        print(f"❌ Error en detect_product_with_ai: {e}")
        return None

# ================================
# Obtener respuesta del bot
# ================================

def get_response(user_input: str, session_id: str) -> str:
    user_input_lower = user_input.lower().strip()

    
    # 1. Verificar coincidencias en config.json
    for category, data in config.items():
        if category == "prompt":
            continue
        keywords = data.get("keywords", [])
        if any(keyword in user_input_lower for keyword in keywords):
            return data.get("message", "Sin información disponible.")

    # 2. Detectar producto con IA
    detected_product = detect_product_with_ai(user_input)
    if detected_product:
        print(f"Producto detectado por IA: {detected_product}")
        all_products = []
        for product_name in detected_product:
            products = get_product_info(product_name)
            if isinstance(products,list):
                all_products.extend(products)
        products = all_products if all_products else "No se encontraron productos relacionados."
    else:
        print("Ningún producto detectado por IA.")
        products = None

    # 3. Si hay productos encontrados
    if products and isinstance(products, list):
        context = "Tenemos estos tipos de productos disponibles:\n"
        for product in products:
            stock_status = "Disponible" if product.get("stock", 0) > 0 else "Agotado"
            name = product.get('producto', 'Producto sin nombre')
            description = product.get('descripcion', 'Sin descripción')
            brand = product.get('marca', 'Marca desconocida')
            price = product.get('precio_venta', 'Precio no disponible')
            category = product.get('categoria', 'Categoría desconocida')

            context += (
                f"- **{name}**\n"
                f"  - Descripción: {description}\n"
                f"  - Marca: {brand}\n"
                f"  - Categoría: {category}\n"
                f"  - Precio: ${price}\n"
                f"  - Stock: {product.get('stock', 0)} unidades ({stock_status})\n\n"
            )

        full_prompt = f"""
        {context}
        El usuario pregunta: "{user_input}"
        Respuesta clara y amigable:
        """
        try:
            result = with_message_history.invoke(
                {"input": full_prompt},
                config={"configurable": {"session_id": session_id}}
            )
            # ✅ Aseguramos que sea string, sin depender de .content
            bot_response = result.content if hasattr(result, "content") else str(result)
            return bot_response.strip()
        except Exception as e:
            print(f"❌ Error al generar respuesta (productos): {e}")
            return "No pude procesar esa consulta. Intenta más tarde."

    elif isinstance(products, str):
        return products

    # 4. Respuesta predeterminada
    try:
        # Leer el contexto base del sistema desde archivo
        with open("prompts/prompt_output.txt", "r", encoding="utf-8") as fileOut:
            promptOutput = fileOut.read().strip()
    except Exception as e:
        print(f"❌ No se pudo leer prompt_output.txt: {e}")
        promptOutput = "Eres un asistente útil. Responde de forma amable y clara."

    # Usa el contexto de config.json si existe
    system_context = config.get("prompt", {}).get("message", promptOutput)

    # Construye el input limpio → solo lo que dice el usuario
    final_input = f"{system_context}\n\nPregunta del usuario: {user_input}"

    try:
        result = with_message_history.invoke(
            {"input": final_input},
            config={"configurable": {"session_id": session_id}}
        )
        bot_response = result.content if hasattr(result, "content") else str(result)
        return bot_response.strip()
    except Exception as e:
        print(f"❌ Error al generar respuesta predeterminada: {e}")
        return "Estoy teniendo problemas para responder."