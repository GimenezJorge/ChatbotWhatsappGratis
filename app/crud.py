# =============================================================================
# Asistente inteligente para atención de clientes de supermercados
# Procesa los mensajes recibidos por WhatsApp, detecta intenciones y productos,
# consulta la base de datos y gestiona pedidos usando modelos de IA locales.
# =============================================================================

import os
import re
from fastapi import HTTPException

from langchain_ollama import OllamaLLM, ChatOllama
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.pedidos import agregar_a_pedido
from app.database import connect_to_db
from app.info_super import leer_info_supermercado


# =============================================================================
# VERIFICACIÓN DEL TOKEN DE ACCESO
# =============================================================================

access_token_env = os.getenv("ACCESS_TOKEN")
def verify_token(token: str):
    if token != access_token_env:
        raise HTTPException(status_code=401, detail="Token inválido")
    return True


# =============================================================================
# MODELOS DE IA
# =============================================================================

modelo_input = OllamaLLM(model="gemma3_input:latest")
modelo_output = ChatOllama(model="gemma3_output:latest")


# =============================================================================
# CONFIGURACIÓN DEL PROMPT Y DEL HISTORIAL
# =============================================================================

prompt = ChatPromptTemplate.from_messages([
    MessagesPlaceholder(variable_name="history"),
    ("human", "{input}")
])

chain = prompt | modelo_output


# =============================================================================
# HISTORIAL EN MEMORIA
# =============================================================================

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


# =============================================================================
# LECTURA DE HISTORIAL DESDE ARCHIVO
# =============================================================================

def log_historial_archivo(session_id: str) -> list:
    ruta_archivo = os.path.join("conversaciones", f"{session_id}.txt")
    if not os.path.exists(ruta_archivo):
        return []
    try:
        with open(ruta_archivo, 'r', encoding='utf-8') as file:
            lineas = file.readlines()

        historial = []
        for linea in lineas:
            linea = linea.strip()
            if " - De " in linea:
                try:
                    timestamp_str = linea[:19]
                    resto = linea[20:]
                    if "De " in resto and ": " in resto:
                        contenido = resto.split(": ", 1)[1]
                        historial.append({
                            "timestamp": timestamp_str,
                            "role": "user",
                            "content": contenido
                        })
                except:
                    continue

            elif " - Bot: " in linea:
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
        print(f"Error leyendo historial del archivo: {e}")
        return []




# ==================================================================================
# DATOS TRAÍDOS DESDE BD (guarda los productos ya consultados y mostrados al cliente)
# ==================================================================================

datos_traidos_desde_bd = {}

def get_datos_traidos_desde_bd(session_id: str):
    if session_id not in datos_traidos_desde_bd:
        datos_traidos_desde_bd[session_id] = {
            "productos_mostrados": {},               # los productos que ya se consultaron
            "ultimo_producto_agregado": None,        # el último producto confirmado
            "producto_pendiente_confirmacion": None  # si está esperando confirmación
        }
    return datos_traidos_desde_bd[session_id]







# =============================================================================
# BÚSQUEDA DE PRODUCTOS EN LA BASE DE DATOS
# =============================================================================

def get_product_info(product_name: str):
    connection = connect_to_db()
    if not connection:
        return print("no se conecto a la bd")
    else:
        print("se conecto a la bd")

    cursor = connection.cursor(dictionary=True)

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
    words = product_name_lower.split()
    first_word = words[0] if words else product_name_lower

    cursor.execute(QUERY_START, (f"{first_word}%", f"{first_word}%", f"{first_word}%"))
    start_results = cursor.fetchall()
    if start_results:
        cursor.close()
        connection.close()
        return start_results

    cursor.execute(QUERY_CONTAINS, (f"%{product_name_lower}%", f"{product_name_lower}%"))
    contain_results = cursor.fetchall()
    cursor.close()
    connection.close()

    if contain_results:
        return contain_results

    return f"No se encontró ningún producto relacionado con '{product_name}'."


# =============================================================================
# DETECCIÓN DE INTENCIÓN Y PRODUCTOS CON IA
# =============================================================================

def detect_product_with_ai(user_input):
    try:
        prompt = f"""
        Analiza la siguiente frase del cliente y detectá:
        - Intención expresada
        - Nivel de confianza (0 a 100)
        - Productos mencionados (si hay)

        Frase del cliente: "{user_input}"
        """

        raw_response = modelo_input.invoke(prompt).strip()
        cleaned = re.sub(r"<think>.*?</think>", "", raw_response, flags=re.DOTALL | re.IGNORECASE)

        intent_match = re.search(r"intenci[oó]n\s*(detectada|:)?\s*[:\-]?\s*([A-Z_]+)", cleaned, re.IGNORECASE)
        conf_match = re.search(r"confianza\s*[:\-]?\s*(\d+)", cleaned, re.IGNORECASE)
        prod_match = re.search(r"productos\s*(mencionados|:)?\s*[:\-]?\s*(.*)", cleaned, re.IGNORECASE | re.DOTALL)

        intent = intent_match.group(2).upper() if intent_match else None
        confidence = int(conf_match.group(1)) if conf_match else None
        products_text = prod_match.group(2).strip() if prod_match else ""

        if not products_text or products_text.lower().startswith("ninguno"):
            products = []
        else:
            products = [p.strip() for p in re.split(r",|\s+y\s+|\n", products_text) if p.strip()]

        print("🧩 Resultado IA Detector:")
        print(f"  - Intención: {intent or 'No detectada'}")
        print(f"  - Confianza: {confidence or 'No indicada'}")
        print(f"  - Productos: {products or 'Ninguno'}")

        return {
            "intencion": intent,
            "confianza": confidence,
            "productos": products
        }

    except Exception as e:
        print(f"Error en detect_product_with_ai: {e}")
        return {
            "intencion": None,
            "confianza": None,
            "productos": []
        }


# =============================================================================
# GENERACIÓN DE LA RESPUESTA DEL BOT
# =============================================================================

def get_response(user_input: str, session_id: str) -> str:
    user_input_lower = user_input.lower().strip()

    detected = detect_product_with_ai(user_input)
    intencion = detected.get("intencion")
    confianza = detected.get("confianza") or 0
    productos_detectados = detected.get("productos", [])

    # SI SE DETECTA LA INTENCIÓN: AGREGAR_PRODUCTO
    if intencion == "AGREGAR_PRODUCTO" and productos_detectados:
        print(f"🛒 Intención de agregar producto detectada: {productos_detectados}")

        if confianza < 70:
            try:
                mensaje_confirmacion = (
                    f"El cliente dijo: '{user_input}'. "
                    f"Detectaste intención de AGREGAR_PRODUCTO con confianza {confianza}%. "
                    "Pedí confirmación de manera natural y amable, "
                    "preguntándole si desea agregar ese producto al pedido."
                )
                result = with_message_history.invoke(
                    {"input": mensaje_confirmacion},
                    config={"configurable": {"session_id": session_id}}
                )
                bot_response = result.content if hasattr(result, "content") else str(result)
                return bot_response.strip()
            except Exception as e:
                print(f"Error al pedir confirmación con baja confianza: {e}")
                return "¿Querías que te agregue ese producto al pedido?"

        for product_name in productos_detectados:
            products = get_product_info(product_name)
            if isinstance(products, list) and len(products) > 0:
                product_match = next(
                    (p for p in products if product_name.lower() in p['producto'].lower()),
                    products[0]
                )
                nombre = product_match.get('producto', product_name)
                precio = product_match.get('precio_venta', 0.0)
                mensaje_confirmacion = agregar_a_pedido(session_id, nombre, 1, precio)
                print(f"✅ Producto agregado al pedido: {mensaje_confirmacion}")
                return mensaje_confirmacion

        mensaje_ia = (
            f"El sistema detectó que el cliente podría querer agregar '{product_name}' a su pedido, "
            f"pero no está completamente seguro. "
            f"Formulá una pregunta amable y natural para confirmar si desea agregarlo."
        )
        result = with_message_history.invoke(
            {"input": mensaje_ia},
            config={"configurable": {"session_id": session_id}}
        )
        bot_response = result.content if hasattr(result, "content") else str(result)
        return bot_response.strip()

    # SI SE DETECTA LA INTENCIÓN: MOSTRAR_PEDIDO
    if intencion == "MOSTRAR_PEDIDO":
        print("🧾 Intención de mostrar pedido detectada.")

        if confianza < 70:
            try:
                mensaje_confirmacion = (
                    f"El cliente dijo: '{user_input}'. "
                    f"Detectaste intención de MOSTRAR_PEDIDO con confianza {confianza}%. "
                    "Pedí confirmación de manera natural y amable, "
                    "preguntándole si desea que le muestres su pedido actual."
                )
                result = with_message_history.invoke(
                    {"input": mensaje_confirmacion},
                    config={"configurable": {"session_id": session_id}}
                )
                bot_response = result.content if hasattr(result, "content") else str(result)
                return bot_response.strip()
            except Exception as e:
                print(f"Error al pedir confirmación con baja confianza: {e}")
                mensaje_ia = (
                    f"El sistema no está seguro si el cliente quiso ver su pedido. "
                    f"Formulá una pregunta amable y breve para confirmar si desea verlo."
                )
                result = with_message_history.invoke(
                    {"input": mensaje_ia},
                    config={"configurable": {"session_id": session_id}}
                )
                bot_response = result.content if hasattr(result, "content") else str(result)
                return bot_response.strip()

        from app.pedidos import mostrar_pedido
        try:
            resumen = mostrar_pedido(session_id)
            return resumen
        except Exception as e:
            print(f"Error al mostrar el pedido: {e}")
            mensaje_ia = (
                f"Ocurrió un problema al intentar mostrar el pedido del cliente. "
                f"Respondé de forma amable y natural, explicando que hubo un inconveniente "
                f"y ofreciendo volver a intentar o ayudar con otra consulta."
            )
            result = with_message_history.invoke(
                {"input": mensaje_ia},
                config={"configurable": {"session_id": session_id}}
            )
            bot_response = result.content if hasattr(result, "content") else str(result)
            return bot_response.strip()

    # SI SE DETECTAN PRODUCTOS EN EL INPUT DEL CLIENTE
    if productos_detectados:
        print(f"Productos detectados: {productos_detectados}")
        all_products = []
        for product_name in productos_detectados:
            products = get_product_info(product_name)
            if isinstance(products, list):
                all_products.extend(products)
        products = all_products if all_products else "No se encontraron productos relacionados."
    else:
        products = None

    # SI ENCUENTRA PRODUCTOS EN LA BASE
    if products and isinstance(products, list):
        context = "Tenemos estos productos disponibles:\n\n"
        for product in products:
            name = product.get('producto', 'Producto sin nombre')
            price = product.get('precio_venta', 'Precio no disponible')
            context += f"- {name} — ${price}\n"

        return context + "\n¿Querés agregar alguno de esos productos a tu pedido?"

    elif isinstance(products, str):
        try:
            mensaje_ia = (
                f"El sistema no encontró productos relacionados con la búsqueda del cliente. "
                f"Frase original: '{user_input}'. "
                f"Respondé con amabilidad, explicando que no se encontró ese producto, "
                f"y ofrecé ayudarlo con algo similar o que aclare lo que busca."
            )
            result = with_message_history.invoke(
                {"input": mensaje_ia},
                config={"configurable": {"session_id": session_id}}
            )
            bot_response = result.content if hasattr(result, "content") else str(result)
            return bot_response.strip()
        except Exception as e:
            print(f"Error al generar respuesta cuando no hay productos: {e}")
            mensaje_ia_error = (
                f"Ocurrió un error al intentar responder la búsqueda '{user_input}'. "
                f"Respondé al cliente de manera amable, explicando que hubo un inconveniente al buscar el producto "
                f"y ofreciendo mostrar opciones similares o volver a intentar."
            )
            result = with_message_history.invoke(
                {"input": mensaje_ia_error},
                config={"configurable": {"session_id": session_id}}
            )
            bot_response = result.content if hasattr(result, "content") else str(result)
            return bot_response.strip()

    # SI EL CLIENTE NO NOMBRA PRODUCTOS NI DEMUESTRA NINGUNA INTENCION
    if 'final_input' not in locals():
        final_input = user_input
    try:
        result = with_message_history.invoke(
            {"input": final_input},
            config={"configurable": {"session_id": session_id}}
        )
        bot_response = result.content if hasattr(result, "content") else str(result)
        return bot_response.strip()
    except Exception as e:
        print(f"Error al generar respuesta predeterminada: {e}")
        mensaje_ia_error = (
            f"Hubo un error general al intentar responder al cliente: '{user_input}'. "
            f"Respondé de manera amable y natural, pidiendo disculpas por el inconveniente "
            f"y ofreciendo continuar la conversación."
        )
        result = with_message_history.invoke(
            {"input": mensaje_ia_error},
            config={"configurable": {"session_id": session_id}}
        )
        bot_response = result.content if hasattr(result, "content") else str(result)
        return bot_response.strip()
