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

# access_token_env = os.getenv("ACCESS_TOKEN")
# def verify_token(token: str):
#     print("\n-1-\n")
#     if token != access_token_env:
#         raise HTTPException(status_code=401, detail="Token inválido")
#     return True


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
# store = {}

# def get_session_history(session_id: str):
#     if session_id not in store:
#         store[session_id] = InMemoryChatMessageHistory()
#         historial_guardado = log_historial_archivo(session_id)
#         if historial_guardado:
#             print(f"📂 Cargando historial previo de {session_id} ({len(historial_guardado)} mensajes)")

#             for msg in historial_guardado:
#                 # Se agregan los mensajes al historial en memoria
#                 if msg["role"] == "user":
#                     store[session_id].add_user_message(msg["content"])
#                 elif msg["role"] == "bot":
#                     store[session_id].add_ai_message(msg["content"])

#     return store[session_id]


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

    historial = []
    rol_actual = None
    contenido_actual = []
    timestamp_actual = None

    with open(ruta_archivo, "r", encoding="utf-8") as file:
        for linea in file:
            linea = linea.rstrip()
            if " - De " in linea or " - Bot: " in linea:
                # Guardar el bloque anterior antes de pasar al siguiente
                if rol_actual and contenido_actual:
                    historial.append({
                        "timestamp": timestamp_actual,
                        "role": rol_actual,
                        "content": "\n".join(contenido_actual).strip()
                    })
                    contenido_actual = []

                timestamp_actual = linea[:19]

                if " - De " in linea:
                    rol_actual = "user"
                    contenido_actual.append(linea.split(" - De ", 1)[1].split(": ", 1)[1])
                else:
                    rol_actual = "bot"
                    contenido_actual.append(linea.split(" - Bot: ", 1)[1])
            else:
                # Línea que continúa el mensaje anterior
                contenido_actual.append(linea)

        # Guardar el último bloque
        if rol_actual and contenido_actual:
            historial.append({
                "timestamp": timestamp_actual,
                "role": rol_actual,
                "content": "\n".join(contenido_actual).strip()
            })

    return historial





# ==================================================================================
# DATOS TRAÍDOS DESDE BD (guarda los productos ya consultados y mostrados al cliente)
# ==================================================================================

datos_traidos_desde_bd = {}

def get_datos_traidos_desde_bd(session_id: str):
    if session_id not in datos_traidos_desde_bd:
        datos_traidos_desde_bd[session_id] = {
            "productos_mostrados": {},               # los productos que ya se consultaron
            #"ultimo_producto_agregado": None,        # el último producto confirmado
            #"producto_pendiente_confirmacion": None  # si está esperando confirmación
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
        print("🗃️  se conecto a la bd")

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
        print(f"  • Intención: {intent or 'No detectada'}")
        print(f"  • Confianza: {confidence or 'No indicada'}")
        print(f"  • Productos: {products or 'Ninguno'}")

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


# ==============================================================================
# CIERRE COMÚN A TODOS LOS CAMINOS DEL GET_RESPONSE
# ==============================================================================
def finalizar_respuesta(session_id: str, respuesta: str) -> str:
    try:
        # Control para evitar doble ejecución
        session_data = get_datos_traidos_desde_bd(session_id)
        if session_data.get("finalizando", False):
            print("⚠️ finalizar_respuesta() omitido: se detectó doble ejecución.")
            return respuesta.strip()
        session_data["finalizando"] = True

        # Asegurarse de que la sesión exista en memoria
        if session_id not in store:
            store[session_id] = InMemoryChatMessageHistory()

        # Guardar la respuesta del bot en el historial actual
        store[session_id].add_ai_message(respuesta)

        # Leer los últimos mensajes del archivo (persistencia previa)
        historial = log_historial_archivo(session_id)
        ultimos_mensajes = historial[-12:] if len(historial) > 12 else historial

        if not ultimos_mensajes:
            session_data["finalizando"] = False
            return respuesta.strip()

        print("\n====================== 📜 CONTEXTO ACTUAL IA ======================")
        for msg in ultimos_mensajes:
            print(f"[{msg['role'].upper()}] {msg['content']}")
        print("=================================================================\n")

        # Generar resumen breve del contexto reciente
        resumen_prompt = f"""
        Estos son los últimos mensajes entre el cliente y el bot.

        Resumí en una o dos frases lo que realmente ocurrió en la conversación reciente.
        Enfocate en:
        - Qué producto(s) se mencionaron o agregaron.
        - Qué acción realizó el cliente (consultar, agregar, ver pedido, etc.).
        - En qué estado quedó el pedido (por ejemplo: productos agregados, total, consulta pendiente, etc.).

        Usá solo información textual que aparece en los mensajes, sin inventar nada nuevo.

        Mensajes:
        {''.join([f"{m['role']}: {m['content']}\n" for m in ultimos_mensajes])}
        """


        resumen_obj = modelo_output.invoke(resumen_prompt)
        resumen = resumen_obj.content if hasattr(resumen_obj, "content") else str(resumen_obj)
        resumen = resumen.strip()

        # Guardar el resumen también en memoria (como mensaje de sistema)
        session_data["ultimo_resumen"] = resumen
        print("\n🧠 Resumen automático actualizado:")
        print(resumen[:250], "\n")


    except Exception as e:
        print(f"⚠️ Error al generar o guardar resumen automático: {e}")

    # ==========================
    # ✅ Liberar el flag de control
    # ==========================
    session_data["finalizando"] = False

    # 6️⃣ Devolver siempre la respuesta final limpia
    return respuesta.strip()



# =============================================================================
# GENERACIÓN DE LA RESPUESTA DEL BOT
# =============================================================================

def get_response(user_input: str, session_id: str) -> str:
    user_input_lower = user_input.lower().strip()



    

    # ==========================
    # DETECCIÓN DE INTENCIÓN Y PRODUCTOS (solo mensaje actual)
    # ==========================
    print(f"\n🗣️ Mensaje real del usuario: {user_input}")

    detected = detect_product_with_ai(user_input)
    intencion = detected.get("intencion")
    confianza = detected.get("confianza") or 0
    productos_detectados = detected.get("productos", [])

    print(f"🧠 Intención detectada: {intencion} (confianza {confianza}%) — productos: {productos_detectados}") 

    # ==========================
    # DECISIÓN DE BÚSQUEDA EN BASE A LA INTENCIÓN
    # ==========================
    requiere_busqueda = intencion in ["AGREGAR_PRODUCTO", "CONSULTAR_INFO"]

    # Si la intención NO requiere buscar en la base, evitamos consultas innecesarias
    if not requiere_busqueda:
        print(f"🧠 Intención '{intencion}' no requiere búsqueda. Usando solo contexto.")
        result = with_message_history.invoke(
            {"input": user_input},
            config={"configurable": {"session_id": session_id}}
        )
        bot_response = result.content if hasattr(result, "content") else str(result)
        return finalizar_respuesta(session_id, bot_response)





    # SI SE DETECTA LA INTENCIÓN: AGREGAR_PRODUCTO
    if intencion == "AGREGAR_PRODUCTO" and productos_detectados:
        print(f"🛒 Intención de agregar producto detectada: {productos_detectados}")


        # 🧠 Recuperar los productos ya mostrados en esta sesión
        session_data = get_datos_traidos_desde_bd(session_id)
        productos_previos = session_data["productos_mostrados"]


        # 🧾 Mostrar en consola los productos actualmente guardados en la sesión
        print("\n📋 Productos actualmente mostrados al cliente:")
        if productos_previos:
            for clave, lista in productos_previos.items():
                print(f"  🔹 Clave '{clave}' → {len(lista)} producto(s):")
                for p in lista:
                    print(f"     • {p['producto']} — ${p['precio_venta']}")
        else:
            print("  (vacío)")



        # Creamos una lista con los nombres de productos que ya vio el cliente
        #productos_previos_lista = list(productos_previos.keys())




        if confianza < 90:
            producto_pendiente = productos_detectados[0] if productos_detectados else None
            print(f"🕐 Producto con baja confianza: {producto_pendiente}")

            mensaje_confirmacion = (
                f"¿Querés que te agregue {producto_pendiente} al pedido?"
                if producto_pendiente
                else "¿Querés que te agregue ese producto al pedido?"
            )

            return finalizar_respuesta(session_id, mensaje_confirmacion)

        # ✅ Si la confianza es alta y el producto fue detectado, agregar directamente
        if confianza >= 90 and productos_detectados:
            producto = productos_detectados[0]
            cantidad = convertir_a_numero_es(user_input_lower)

            for lista in session_data["productos_mostrados"].values():
                for p in lista:
                    if producto.lower() in p["producto"].lower():
                        nombre = p["producto"]
                        precio = p["precio_venta"]
                        mensaje_confirmacion = agregar_a_pedido(session_id, nombre, cantidad, precio)
                        print(f"✅ Producto agregado automáticamente: {nombre} x{cantidad}")
                        return finalizar_respuesta(session_id, mensaje_confirmacion)



        # 🧠 Recuperar los productos ya mostrados en esta sesión
        # session_data = get_datos_traidos_desde_bd(session_id)
        # productos_previos = session_data["productos_mostrados"]
        # productos_previos_lista = list(productos_previos.keys())

 
        # 🧠 Verificar con IA si el producto mencionado ya estaba en la lista textual mostrada
        # session_data = get_datos_traidos_desde_bd(session_id)
        # productos_textuales = session_data.get("productos_textuales", "")

        # if productos_textuales:
        #     prompt_verificacion = f"""
        #     Tenés esta lista de productos que se le mostraron antes al cliente:
        #     {productos_textuales}

        #     El cliente acaba de decir: "{user_input}"

        #     Tu tarea es decidir si el cliente se refiere a alguno de esos productos.

        #     ⚠️ IMPORTANTE:
        #     - Respondé SOLO con el nombre completo del producto EXACTO tal como aparece en la lista.
        #     - NO agregues texto, explicaciones ni análisis.
        #     - NO menciones intención, confianza ni nada similar.
        #     - Si no se refiere a ninguno, respondé exactamente con la palabra: NINGUNO.

        #     Ejemplos válidos:
        #     Cliente dice "quiero el marolio" → responde "Aceite de Girasol Marolio"
        #     Cliente dice "poneme uno de natura" → responde "Aceite de Girasol Natura 1L"
        #     Cliente dice "no sé todavía" → responde "NINGUNO"
        #     """




            # try:
            #     respuesta_verificacion = modelo_input.invoke(prompt_verificacion).strip()
            #     print(f"🤖 Resultado verificación IA (texto limpio): {respuesta_verificacion}")

            #     if respuesta_verificacion.lower() != "ninguno":
            #         # 🧠 Validar que haya alguna palabra en común entre lo que dijo el cliente y el producto detectado
            #         palabras_cliente = set(user_input.lower().split())
            #         palabras_producto = set(respuesta_verificacion.lower().split())
            #         coincidencias = palabras_cliente.intersection(palabras_producto)

            #         if not coincidencias:
            #             print(f"⚠️ Coincidencia descartada: '{respuesta_verificacion}' no coincide con '{user_input}'")
            #         else:
            #             # Buscar coincidencia dentro de los productos mostrados
            #             for productos in session_data["productos_mostrados"].values():
            #                 for p in productos:
            #                     if respuesta_verificacion.lower() in p["producto"].lower():
            #                         nombre = p["producto"]
            #                         precio = p["precio_venta"]
                                    
            #                         # Detectar cantidad (número o palabra, en español o inglés)
            #                         cantidad = convertir_a_numero_es(user_input_lower)
            #                         print(f"🧮 Cantidad detectada: {cantidad}")


            #                         mensaje_confirmacion = agregar_a_pedido(session_id, nombre, cantidad, precio)

            #                         print(f"✅ Producto agregado desde lista textual: {nombre}")
            #                         return finalizar_respuesta(session_id, mensaje_confirmacion)


            # except Exception as e:
            #     print(f"⚠️ Error en verificación IA: {e}")

            #nueva version, todavia no se si la voy a usar, tengo que probar:
            # 🧠 Verificar si el cliente se refiere a un producto mostrado recientemente (sin usar lista textual)
            # if productos_detectados:
            #     # El modelo ya entiende el contexto gracias al resumen, así que no hace falta verificar manualmente
            #     print("🔍 Producto detectado por IA con contexto, no se usa lista textual.")
            # else:
            #     print("⚠️ No se detectaron productos explícitos, se intentará deducir con contexto.")

            # 🧭 Si la IA no encontró coincidencia válida, o fue descartada, buscar en la base
            # print("🧭 No se encontró coincidencia en productos mostrados. Buscando en la base de datos...")

        # ⚙️ Si no estaba en los productos mostrados, buscar en la base de datos


        # 🧠 Verificar si el producto ya fue mostrado o está en el pedido actual
        session_data = get_datos_traidos_desde_bd(session_id)
        productos_previos = session_data["productos_mostrados"]


        # Si alguno de los productos detectados ya está en productos_mostrados, lo agregamos directamente
        for product_name in productos_detectados:
            for lista in productos_previos.values():
                for p in lista:
                    if product_name.lower() in p["producto"].lower():
                        cantidad = convertir_a_numero_es(user_input_lower)
                        nombre = p["producto"]
                        precio = p["precio_venta"]
                        mensaje_confirmacion = agregar_a_pedido(session_id, nombre, cantidad, precio)
                        print(f"✅ Producto agregado directamente desde contexto: {nombre} x{cantidad}")
                        return finalizar_respuesta(session_id, mensaje_confirmacion)


        for product_name in productos_detectados:
            products = get_product_info(product_name)




            if isinstance(products, list) and len(products) > 0:
                # Guardar también en los productos mostrados de la sesión
                session_data = get_datos_traidos_desde_bd(session_id)
                session_data["productos_mostrados"][product_name.lower()] = products





                # 🧠 Pedirle a la IA que genere la lista con formato de viñetas
                try:
                    prompt_lista = f"""
                    Mostrale al cliente los siguientes productos de manera clara, breve y fácil de leer.
                    Usá una lista con viñetas (•) y mantené un tono amable y natural.
                    Al final, preguntale cuál de esos productos desea agregar al pedido.

                    Productos disponibles:
                    {''.join([f"{p['producto']} - ${p['precio_venta']}\n" for p in products])}
                    """

                    result_lista = modelo_output.invoke(prompt_lista)
                    
                    context = (
                        result_lista.content
                        if hasattr(result_lista, "content") and isinstance(result_lista.content, str)
                        else str(result_lista)
                    ).strip()


                    store[session_id].add_ai_message(context)
                except Exception as e:
                    print(f"⚠️ Error al generar lista con IA: {e}")
                    # fallback manual si la IA falla
                    context = "Tenemos estos productos disponibles:\n\n" + \
                            "\n".join([f"• {p['producto']} — ${p['precio_venta']}" for p in products]) + \
                            "\n\n¿Querés agregar alguno a tu pedido? 😊"

                return finalizar_respuesta(session_id, context)



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
        return finalizar_respuesta(session_id, bot_response)



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
                return finalizar_respuesta(session_id, bot_response)
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
                return finalizar_respuesta(session_id, bot_response)

        from app.pedidos import mostrar_pedido
        try:
            resumen = mostrar_pedido(session_id)
            return finalizar_respuesta(session_id, resumen)
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
            return finalizar_respuesta(session_id, bot_response)


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



        products = all_products if all_products else "No se encontraron productos relacionados."
    else:
        products = None




    # SI ENCUENTRA PRODUCTOS EN LA BASE
    if products and isinstance(products, list):
        try:
            # Preparamos un prompt para que la IA genere la respuesta natural con los productos encontrados
            prompt_lista = f"""
            El cliente preguntó: "{user_input}"

            Estos son los productos encontrados en la base de datos relacionados con su consulta:
            {''.join([f"• {p['producto']} — ${p['precio_venta']}\n" for p in products])}

            Mostrale la lista al cliente de manera clara, breve y ordenada.
            Mantené el formato de viñetas (•) y un tono amable y natural.
            Al final, preguntale cuál de esos productos desea agregar a su pedido.
            """

            result_lista = modelo_output.invoke(prompt_lista)
            respuesta = result_lista.content if hasattr(result_lista, "content") else str(result_lista)

        except Exception as e:
            print(f"⚠️ Error al generar lista con IA: {e}")
            # fallback manual (solo si la IA falla)
            respuesta = (
                "Tenemos estos productos disponibles:\n\n"
                + "\n".join([f"• {p['producto']} — ${p['precio_venta']}" for p in products])
                + "\n\n¿Querés agregar alguno de esos productos a tu pedido? 😊"
            )

        return finalizar_respuesta(session_id, respuesta)

    # SI EL CLIENTE NO NOMBRA PRODUCTOS NI DEMUESTRA NINGUNA INTENCION

    try:
        result = with_message_history.invoke(
            {"input": user_input},
            config={"configurable": {"session_id": session_id}}
        )
        bot_response = result.content if hasattr(result, "content") else str(result)
        return finalizar_respuesta(session_id, bot_response)

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
        return finalizar_respuesta(session_id, bot_response)


