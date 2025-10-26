# =============================================================================
# Asistente inteligente para atención de clientes de supermercados
# Procesa los mensajes recibidos por WhatsApp, detecta intenciones y productos,
# consulta la base de datos y gestiona pedidos usando modelos de IA locales.
# =============================================================================

import os
import re
from text_to_num import text2num
from word2number import w2n
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
# FUNCIÓN AUXILIAR PARA REGENERAR LA LISTA TEXTUAL DE PRODUCTOS MOSTRADOS
# (para que la IA pueda comparar el producto detectado con los productos ya mostrados)
# =============================================================================

def regenerar_productos_textuales(session_id: str):
    session_data = get_datos_traidos_desde_bd(session_id)
    productos_textuales = "Estos son los productos que se le mostraron hasta ahora al cliente:\n"
    for lista in session_data["productos_mostrados"].values():
        for p in lista:
            productos_textuales += f"- {p['producto']}\n"
    session_data["productos_textuales"] = productos_textuales

    print("\n📦 Productos textuales actualizados:")
    print(productos_textuales)

# =============================================================================
# FUNCION AUXILIAR PARA RECONOCER LAS CANTIDADES INGRESADAS POR EL USUARIO
# =============================================================================

def convertir_a_numero_es(user_input: str) -> int:
    texto = user_input.lower().strip()

    mapa_numeros = {
        "uno": 1, "una": 1, "un": 1,
        "dos": 2, "par": 2, "un par": 2,
        "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
        "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
        "media docena": 6, "una docena": 12, "docena": 12
    }

    # Buscar expresiones comunes
    for palabra, numero in mapa_numeros.items():
        if palabra in texto:
            return numero

    # Buscar número en cifras
    match = re.search(r"\b\d+\b", texto)
    if match:
        return int(match.group())

    # Intentar convertir usando text2num (modo español)
    try:
        return text2num(texto, "es")
    except Exception:
        pass

    # 4️⃣ Fallback: intentar word2number (inglés)
    try:
        return w2n.word_to_num(texto)
    except Exception:
        return 1


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


    # ==========================
    # DETECCIÓN DE CONTEXTO RECIENTE
    # ==========================
    session_data = get_datos_traidos_desde_bd(session_id)
    historial = log_historial_archivo(session_id)
    ultimo_mensaje_bot = ""

    # Buscar el último mensaje enviado por el bot
    for h in reversed(historial):
        if h["role"] == "bot":
            ultimo_mensaje_bot = h["content"].lower()
            break

    # Si el último mensaje del bot ofrecía agregar productos,
    # y el usuario responde algo corto o referencial,
    # asumimos que mantiene la intención anterior (AGREGAR_PRODUCTO)
    palabras_referenciales = ["ese", "esa", "eso", "el", "la", "dale", "agregalo", "sumalo", "ok"]
    if any(p in user_input_lower for p in palabras_referenciales) and "¿querés agregar" in ultimo_mensaje_bot:
        print("🔁 Se asume continuidad: el cliente sigue con intención de AGREGAR_PRODUCTO")
        detected = {"intencion": "AGREGAR_PRODUCTO", "confianza": 95, "productos": [user_input_lower]}
        intencion = detected.get("intencion")
        confianza = detected.get("confianza")
        productos_detectados = detected.get("productos")
    else:
        detected = detect_product_with_ai(user_input)
        intencion = detected.get("intencion")
        confianza = detected.get("confianza") or 0
        productos_detectados = detected.get("productos", [])

    print(f"🧠 Intención final detectada: {intencion} (confianza {confianza}%) — productos: {productos_detectados}")

    # SI SE DETECTA LA INTENCIÓN: AGREGAR_PRODUCTO
    if intencion == "AGREGAR_PRODUCTO" and productos_detectados:
        print(f"🛒 Intención de agregar producto detectada: {productos_detectados}")


        # 🧠 Recuperar los productos ya mostrados en esta sesión
        session_data = get_datos_traidos_desde_bd(session_id)
        productos_previos = session_data["productos_mostrados"]

        # Creamos una lista con los nombres de productos que ya vio el cliente
        productos_previos_lista = list(productos_previos.keys())




        if confianza < 90:
            session_data = get_datos_traidos_desde_bd(session_id)
            producto_pendiente = productos_detectados[0] if productos_detectados else None
            session_data["producto_pendiente_confirmacion"] = producto_pendiente

            print(f"🕐 Producto pendiente de confirmación: {producto_pendiente}")

            mensaje_confirmacion = (
                f"¿Querés que te agregue {producto_pendiente} al pedido?"
                if producto_pendiente
                else "¿Querés que te agregue ese producto al pedido?"
            )

            return mensaje_confirmacion


        # 🧠 Recuperar los productos ya mostrados en esta sesión
        session_data = get_datos_traidos_desde_bd(session_id)
        productos_previos = session_data["productos_mostrados"]
        productos_previos_lista = list(productos_previos.keys())

 
        # 🧠 Verificar con IA si el producto mencionado ya estaba en la lista textual mostrada
        session_data = get_datos_traidos_desde_bd(session_id)
        productos_textuales = session_data.get("productos_textuales", "")

        if productos_textuales:
            prompt_verificacion = f"""
            Tenés esta lista de productos que se le mostraron antes al cliente:
            {productos_textuales}

            El cliente acaba de decir: "{user_input}"

            Tu tarea es decidir si el cliente se refiere a alguno de esos productos.

            ⚠️ IMPORTANTE:
            - Respondé SOLO con el nombre completo del producto EXACTO tal como aparece en la lista.
            - NO agregues texto, explicaciones ni análisis.
            - NO menciones intención, confianza ni nada similar.
            - Si no se refiere a ninguno, respondé exactamente con la palabra: NINGUNO.

            Ejemplos válidos:
            Cliente dice "quiero el marolio" → responde "Aceite de Girasol Marolio"
            Cliente dice "poneme uno de natura" → responde "Aceite de Girasol Natura 1L"
            Cliente dice "no sé todavía" → responde "NINGUNO"
            """


            try:
                respuesta_verificacion = modelo_input.invoke(prompt_verificacion).strip()
                print(f"🤖 Resultado verificación IA (texto limpio): {respuesta_verificacion}")

                if respuesta_verificacion.lower() != "ninguno":
                    # 🧠 Validar que haya alguna palabra en común entre lo que dijo el cliente y el producto detectado
                    palabras_cliente = set(user_input.lower().split())
                    palabras_producto = set(respuesta_verificacion.lower().split())
                    coincidencias = palabras_cliente.intersection(palabras_producto)

                    if not coincidencias:
                        print(f"⚠️ Coincidencia descartada: '{respuesta_verificacion}' no coincide con '{user_input}'")
                    else:
                        # Buscar coincidencia dentro de los productos mostrados
                        for productos in session_data["productos_mostrados"].values():
                            for p in productos:
                                if respuesta_verificacion.lower() in p["producto"].lower():
                                    nombre = p["producto"]
                                    precio = p["precio_venta"]
                                    
                                    # Detectar cantidad (número o palabra, en español o inglés)
                                    cantidad = convertir_a_numero_es(user_input_lower)
                                    print(f"🧮 Cantidad detectada: {cantidad}")


                                    mensaje_confirmacion = agregar_a_pedido(session_id, nombre, cantidad, precio)

                                    print(f"✅ Producto agregado desde lista textual: {nombre}")
                                    return mensaje_confirmacion


            except Exception as e:
                print(f"⚠️ Error en verificación IA: {e}")

            # 🧭 Si la IA no encontró coincidencia válida, o fue descartada, buscar en la base
            print("🧭 No se encontró coincidencia en productos mostrados. Buscando en la base de datos...")

        # ⚙️ Si no estaba en los productos mostrados, buscar en la base de datos
        for product_name in productos_detectados:
            products = get_product_info(product_name)

            if isinstance(products, list) and len(products) > 0:
                # Guardar también en los productos mostrados de la sesión
                session_data = get_datos_traidos_desde_bd(session_id)
                session_data["productos_mostrados"][product_name.lower()] = products

                # Regenerar la versión textual para la IA
                regenerar_productos_textuales(session_id)


                # Mostrar al cliente los productos encontrados con el formato habitual
                context = "Tenemos estos productos disponibles:\n\n"
                for p in products:
                    name = p.get('producto', 'Producto sin nombre')
                    price = p.get('precio_venta', 'Precio no disponible')
                    context += f"• {name} ... ${price}\n"

                context += "\nMe indicas cual de estos productos querés agregar a tu pedido? 😊"
                return context



        # Si no se encuentra el producto ni en la lista ni en la base, se pide confirmación
        mensaje_ia = (
            f"El cliente mencionó '{user_input}'. No estás completamente seguro si se refiere a "
            f"alguno de los productos mostrados anteriormente. "
            f"Formulá una pregunta natural y breve para confirmar si desea agregarlo al pedido."
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

        if confianza < 90:
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

        # Recuperar los datos de sesión (productos ya consultados)
        session_data = get_datos_traidos_desde_bd(session_id)

        for product_name in productos_detectados:
            products = get_product_info(product_name)

            # Guardar los productos traídos en memoria
            if isinstance(products, list):
                session_data["productos_mostrados"][product_name.lower()] = products
                all_products.extend(products)

        # Actualizar la lista textual para la IA
        if all_products:
            regenerar_productos_textuales(session_id)


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
