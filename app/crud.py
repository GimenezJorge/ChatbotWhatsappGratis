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

from app.pedidos import agregar_a_pedido, mostrar_pedido, finalizar_pedido
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


    # =====================================================
    # Verificar si el texto coincide con una categoría
    # =====================================================
    cursor.execute("SELECT id, nombre FROM categorias WHERE LOWER(nombre) = %s;", (product_name_lower,))
    categoria_row = cursor.fetchone()

    if categoria_row:
        print(f"📂 Coincidencia con categoría detectada: {categoria_row['nombre']}")
        categoria_id = categoria_row["id"]

        cursor.execute("""
            SELECT 
                p.id,
                p.nombre AS producto,
                p.descripcion,
                p.precio_venta,
                m.nombre AS marca,
                c.nombre AS categoria
            FROM productos p
            INNER JOIN marcas m ON p.marca_id = m.id
            INNER JOIN categorias c ON p.categoria_id = c.id
            WHERE p.categoria_id = %s
            ORDER BY p.nombre ASC;
        """, (categoria_id,))

        productos_categoria = cursor.fetchall()
        cursor.close()
        connection.close()
        return productos_categoria



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
# DETECCIÓN DE COMIDAS COMPUESTAS Y BÚSQUEDA DE SUS INGREDIENTES
# =============================================================================

def buscar_ingredientes_para_comida(nombre_plato: str):
    """
    Si un producto no se encuentra en la base, esta función intenta detectar
    si el nombre corresponde a una comida compuesta (ej: pizza, ensalada, torta)
    y busca los ingredientes en la base de datos.
    """

    # 1️⃣ Pedimos a la IA que identifique los ingredientes
    prompt_ingredientes = f"""
    Tu tarea es detectar los ingredientes principales necesarios para preparar "{nombre_plato}".

    ⚠️ No respondas con formato de detección de intención, confianza o productos mencionados.
    Solo devolvé los ingredientes, separados por comas.

    Si el texto NO se refiere a una comida o plato preparado (por ejemplo, si fuera "jabón" o "aceite de auto"),
    respondé exactamente con la palabra: NINGUNO.

    Usá términos comunes en Argentina:
    - manteca (no mantequilla)
    - porotos (no alubias)
    - zapallo (no calabaza)
    - choclo (no maíz)
    - panceta (no tocino)

    Ejemplo de salida válida:
    pizza → harina, levadura, queso, salsa de tomate, aceite, sal
    torta → harina, azúcar, huevos, manteca, leche, polvo de hornear
    empanada → harina, carne, cebolla, huevo, aceitunas
    """



    try:
        respuesta_ia = modelo_input.invoke(prompt_ingredientes).strip()
        respuesta_ia = re.sub(r"<think>.*?</think>", "", respuesta_ia, flags=re.DOTALL).strip()
        print(f"🤖 Ingredientes detectados por IA: {respuesta_ia}")

        if respuesta_ia.upper() == "NINGUNO":
            return None

        # Convertimos los ingredientes en lista
        ingredientes = [i.strip().lower() for i in re.split(r",|\n|y", respuesta_ia) if i.strip()]
        encontrados = []

        # 2️⃣ Buscamos los ingredientes reales en la base
        for ingrediente in ingredientes:
            resultados = get_product_info(ingrediente)
            if isinstance(resultados, list) and len(resultados) > 0:
                encontrados.extend(resultados)

        if not encontrados:
            return None

        return encontrados

    except Exception as e:
        print(f"⚠️ Error en buscar_ingredientes_para_comida: {e}")
        return None



# =============================================================================
# DETECCIÓN DE INTENCIÓN Y PRODUCTOS CON IA
# =============================================================================

def detect_product_with_ai(user_input, session_id="main"):
    try:
        session_data = get_datos_traidos_desde_bd(session_id)
        resumen_input = session_data.get("resumen_input", "").strip()
        productos_mostrados = session_data.get("productos_mostrados", {})

        # Construir lista textual con los productos ya mostrados
        productos_previos_texto = ""
        if productos_mostrados:
            productos_previos_texto = "Estos son los productos que ya se le mostraron al cliente:\n"
            for lista in productos_mostrados.values():
                for p in lista:
                    productos_previos_texto += f"- {p['producto']}\n"

        # Prompt base
        prompt = f"""
Analizá la siguiente frase del cliente y detectá:
- Intención expresada
- Nivel de confianza (0 a 100)
- Productos mencionados (si hay)

Frase del cliente: "{user_input}"
"""

        # Si hay contexto o productos mostrados, incluirlos en el prompt
        if resumen_input or productos_previos_texto:
            prompt = f"""
Considerá este contexto previo:
{resumen_input}

{productos_previos_texto}

Analizá la nueva frase del cliente:
"{user_input}"

Si el producto mencionado no coincide exactamente con los anteriores,
buscá el nombre más parecido entre los productos mostrados y devolvelo como producto detectado.
No inventes nombres nuevos.

Detectá:
- Intención expresada
- Nivel de confianza (0 a 100)
- Productos mencionados (si hay)
"""

        # Llamada a la IA input
        raw_response = modelo_input.invoke(prompt).strip()
        cleaned = re.sub(r"<think>.*?</think>", "", raw_response, flags=re.DOTALL | re.IGNORECASE)

        # Extraer intención, confianza y productos
        intent_match = re.search(r"intenci[oó]n\s*(detectada|:)?\s*[:\-]?\s*([A-Z_]+)", cleaned, re.IGNORECASE)
        conf_match = re.search(r"confianza\s*[:\-]?\s*(\d+)", cleaned, re.IGNORECASE)
        prod_match = re.search(r"productos\s*(mencionados|:)?\s*[:\-]?\s*([^\n\r]+)", cleaned, re.IGNORECASE)

        intent = intent_match.group(2).upper() if intent_match else None
        confidence = int(conf_match.group(1)) if conf_match else None
        products_text = prod_match.group(2).strip() if prod_match else ""

        if not products_text or products_text.lower().startswith("ninguno"):
            products = []
        else:
            products = [p.strip() for p in re.split(r",|\s+y\s+|\n", products_text) if p.strip()]

        print("🧩 Resultado de la deteccion de input:")
        print(f"  🔹 Intención: {intent or 'No detectada'}")
        print(f"  🔹 Confianza: {confidence or 'No indicada'}")
        print(f"  🔹 Productos: {products or 'Ninguno'}")

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
        session_data = get_datos_traidos_desde_bd(session_id)
        if session_data.get("finalizando", False):
            print("⚠️ finalizar_respuesta() omitido: se detectó doble ejecución.")
            return respuesta.strip()
        session_data["finalizando"] = True

        if session_id not in store:
            store[session_id] = InMemoryChatMessageHistory()

        store[session_id].add_ai_message(respuesta)



        historial = log_historial_archivo(session_id)
        ultimos_mensajes = historial[-12:] if len(historial) > 12 else historial

        if not ultimos_mensajes:
            session_data["finalizando"] = False
            return respuesta.strip()

        #print("\n====================== 📜 CONTEXTO ACTUAL IA ======================")
        #for msg in ultimos_mensajes:
        #    print(f"[{msg['role'].upper()}] {msg['content']}")
        #print("=================================================================\n")

        # ⚠️ Recordatorio para evitar falsas asunciones de carrito
        recordatorio_contexto = """
IMPORTANTE:
El siguiente contexto se provee solo como referencia conversacional.
NO representa el estado real del pedido ni las acciones realmente ejecutadas.
Si en los mensajes aparece que se agregó, quitó o mostró un pedido,
no asumas que el carrito existe o que esos cambios fueron reales.
En esos casos, siempre debés usar las funciones del sistema para conocer o modificar el pedido:
- agregar_a_pedido()
- quitar_de_pedido()
- mostrar_pedido()
- vaciar_pedido()
"""

        resumen_prompt = f"""
Estos son los últimos mensajes entre el cliente y el bot.

Generá un resumen claro y completo de lo ocurrido recientemente en la conversación.
Debe tener la longitud necesaria para reflejar correctamente el contexto actual, pero sin extenderse innecesariamente.

Enfocate en:
- Qué producto(s) se mencionaron, consultaron, agregaron o quitaron.
- Qué acción realizó el cliente (consultar, agregar, ver pedido, vaciar, finalizar, etc.).
- En qué estado quedó el pedido (productos agregados, etc.).

⚠️ No incluyas precios, montos ni valores numéricos.
Solo describí productos, acciones y contexto conversacional.
Usá únicamente información textual real que aparezca en los mensajes, sin inventar nada nuevo.

Mensajes:
{''.join([f"{m['role']}: {m['content']}\n" for m in ultimos_mensajes])}

{recordatorio_contexto}
"""

        resumen_obj = modelo_output.invoke(resumen_prompt)
        resumen = resumen_obj.content if hasattr(resumen_obj, "content") else str(resumen_obj)
        resumen = resumen.strip()

        session_data["ultimo_resumen"] = resumen

        # 🧠 Resumen corto para IA input
        resumen_input_prompt = f"""
A partir de estos mensajes recientes, listá solo los nombres de los productos mencionados.
No incluyas precios, acciones ni saludos.
Si no se mencionaron productos, devolvé exactamente la palabra: NINGUNO.

⚠️ Nota:
Si en los mensajes se dice que se agregó o se mostró un pedido,
NO asumas que el carrito realmente existe.
El estado real se obtiene siempre llamando a las funciones del sistema.

Mensajes:
{''.join([f"{m['role']}: {m['content']}\n" for m in ultimos_mensajes])}
"""

        try:
            resumen_input_obj = modelo_output.invoke(resumen_input_prompt)
            resumen_input = resumen_input_obj.content if hasattr(resumen_input_obj, "content") else str(resumen_input_obj)
            resumen_input = resumen_input.strip()

            session_data["resumen_input"] = resumen_input

            print("\n🧩 Resumen de productos detectados (para IA input):")
            print(resumen_input)

        except Exception as e:
            print(f"⚠️ Error al generar resumen para IA input: {e}")

        print("\n🧩 Resumen (para IA output):")
        print(resumen[:250], "\n")

    except Exception as e:
        print(f"⚠️ Error al generar o guardar resumen automático: {e}")

    session_data["finalizando"] = False
    return respuesta.strip()




# =============================================================================
# GENERACIÓN DE LA RESPUESTA DEL BOT
# =============================================================================

def get_response(user_input: str, session_id: str) -> str:
    user_input_lower = user_input.lower().strip()



    

    # ==========================
    # DETECCIÓN DE INTENCIÓN Y PRODUCTOS (solo mensaje actual)
    # ==========================
    print("===================================================================================================")
    print(f"\n🧑 Mensaje real del usuario: {user_input}")

    detected = detect_product_with_ai(user_input)
    intencion = detected.get("intencion")
    confianza = detected.get("confianza") or 0
    productos_detectados = detected.get("productos", [])

    print(f"🧠 Intención detectada: {intencion} (confianza {confianza}%) — productos: {productos_detectados}") 


    # ================================================================
    # CORRECCIÓN AUTOMÁTICA DE INTENCIÓN SEGÚN CONTEXTO PREVIO
    # ================================================================
    session_data = get_datos_traidos_desde_bd(session_id)

    intenciones_validas = [
        "AGREGAR_PRODUCTO",
        "QUITAR_PRODUCTO",
        "MOSTRAR_PEDIDO",
        "VACIAR_PEDIDO",
        "FINALIZAR_PEDIDO"
    ]

    # Guardar la última intención válida y su producto detectado
    if intencion in intenciones_validas:
        session_data["ultima_intencion_detectada"] = intencion
        session_data["ultimo_producto_detectado"] = (
            productos_detectados[0] if productos_detectados else None
        )



    # 🚫 Si la última intención fue FINALIZAR_PEDIDO, no pasar más por la IA
    if session_data.get("ultima_intencion_detectada") == "FINALIZAR_PEDIDO":
        from app.pedidos import finalizar_pedido

        # Tomar todo lo que el cliente haya escrito como datos de envío
        datos_cliente = user_input.strip()
        numero_cliente = session_id

        finalizar_pedido(session_id, datos_cliente, numero_cliente)

        mensaje_confirmacion = (
            "Perfecto 🙌 Tu pedido fue confirmado correctamente y ya está en camino 🚚"
        )

        # Devolvemos la respuesta sin usar la IA
        return finalizar_respuesta(session_id, mensaje_confirmacion)







    # Si ahora la IA detecta CHARLAR o CONSULTAR_INFO,
    # pero hay una intención previa válida, la reasigna automáticamente.
    elif intencion in ["CHARLAR", "CONSULTAR_INFO"]:
        ultima_intencion = session_data.get("ultima_intencion_detectada")
        if ultima_intencion in intenciones_validas:
            print(f"⚙️ Corrigiendo intención: {intencion} → {ultima_intencion}")
            intencion = ultima_intencion


    # ==========================
    # DECISIÓN SEGÚN INTENCIÓN
    # ==========================
    requiere_accion_directa = intencion in [
        "AGREGAR_PRODUCTO",
        "QUITAR_PRODUCTO",
        "MOSTRAR_PEDIDO",
        "VACIAR_PEDIDO",
        "FINALIZAR_PEDIDO"
    ]

    # Si la intención no es una acción directa ni una consulta o charla, usar la IA para responder
    if not requiere_accion_directa and intencion not in ["CONSULTAR_INFO", "CHARLAR"]:
        print(f"🧠 Intención '{intencion}' no requiere acción directa. Usando solo contexto.")
        result = with_message_history.invoke(
            {"input": user_input},
            config={"configurable": {"session_id": session_id}}
        )
        bot_response = result.content if hasattr(result, "content") else str(result)
        return finalizar_respuesta(session_id, bot_response)
    
    # ==========================
    # CONSULTAR_INFO — BÚSQUEDA DE PRODUCTOS O INGREDIENTES
    # ==========================
    if intencion == "CONSULTAR_INFO" and productos_detectados:
        print("🔍 Intención de consulta detectada. Buscando productos o posibles ingredientes...")

        session_data = get_datos_traidos_desde_bd(session_id)
        all_products = []

        for product_name in productos_detectados:
            products = get_product_info(product_name)

            # Si se encontraron productos, los mostramos normalmente
            if isinstance(products, list) and len(products) > 0:
                session_data["productos_mostrados"][product_name.lower()] = products
                all_products.extend(products)

            # 🧠 Si NO se encontró el producto, buscar posibles ingredientes
            elif isinstance(products, str) and "no se encontró" in products.lower():
                print(f"No se encontró '{product_name}' en la base. Buscando ingredientes...")
                ingredientes = buscar_ingredientes_para_comida(product_name)

                if ingredientes:
                    print(f"✅ Ingredientes encontrados para {product_name}: {len(ingredientes)} productos")

                    # Generar respuesta amable con IA
                    try:
                        prompt_ingredientes = f"""
                        El cliente preguntó por "{product_name}", pero no está disponible.
                        Mostrale una respuesta amable y natural, diciendo que ese producto no está en stock,
                        pero que puede prepararlo él mismo con estos ingredientes.
                        Mostrá los ingredientes en formato de lista (•).
                        Al final, preguntale de forma cordial si quiere consultar otro producto.

                        Ingredientes disponibles:
                        {''.join([f"• {p['producto']} — ${p['precio_venta']}\n" for p in ingredientes])}
                        """
                        result_ingredientes = modelo_output.invoke(prompt_ingredientes)
                        respuesta = result_ingredientes.content if hasattr(result_ingredientes, "content") else str(result_ingredientes)
                    except Exception as e:
                        print(f"⚠️ Error al generar lista de ingredientes con IA: {e}")
                        respuesta = (
                            f"Lamentablemente no tenemos {product_name} en este momento, "
                            "pero podés prepararla vos mismo con algunos de estos ingredientes:\n\n" +
                            "\n".join([f"• {p['producto']} — ${p['precio_venta']}" for p in ingredientes]) +
                            "\n\n¿Qué otro producto te gustaría consultar?"
                        )

                    return finalizar_respuesta(session_id, respuesta)

                else:
                    # No se encontraron ingredientes ni productos
                    mensaje = (
                        f"Lamentablemente no tenemos {product_name} en este momento "
                        "y no encontré ingredientes relacionados. "
                        "¿Querés consultar otro producto?"
                    )
                    return finalizar_respuesta(session_id, mensaje)

        # Si sí había productos normales, mostramos la lista como siempre
        if all_products:
            try:
                prompt_lista = f"""
                El cliente preguntó: "{user_input}"
                Estos son los productos encontrados en la base:
                {''.join([f"• {p['producto']} — ${p['precio_venta']}\n" for p in all_products])}
                Mostrale la lista con tono amable y natural, usando viñetas (•),
                y preguntale cuál de ellos quiere agregar a su pedido.
                """
                result_lista = modelo_output.invoke(prompt_lista)
                respuesta = result_lista.content if hasattr(result_lista, "content") else str(result_lista)
            except Exception as e:
                print(f"⚠️ Error al generar lista con IA: {e}")
                respuesta = (
                    "Tenemos estos productos disponibles:\n\n" +
                    "\n".join([f"• {p['producto']} — ${p['precio_venta']}" for p in all_products]) +
                    "\n\n¿Querés agregar alguno a tu pedido? 😊"
                )

            return finalizar_respuesta(session_id, respuesta)



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
                print(f"  🔹 Producto '{clave}' → {len(lista)} producto(s):")
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





        # 🧠 Verificar si alguno de los productos detectados ya fue mostrado
        encontrado_en_sesion = False
        for product_name in productos_detectados:
            for lista in session_data["productos_mostrados"].values():
                for p in lista:
                    if product_name.lower() in p["producto"].lower():
                        cantidad = convertir_a_numero_es(user_input_lower)
                        nombre = p["producto"]
                        precio = p["precio_venta"]
                        print(f"✅ Producto encontrado en sesión: {nombre} — se agrega sin buscar en BD")
                        mensaje_confirmacion = agregar_a_pedido(session_id, nombre, cantidad, precio)
                        encontrado_en_sesion = True
                        return finalizar_respuesta(session_id, mensaje_confirmacion)

        # Solo si no se encontró en sesión, recién ahí buscar en la base
        if not encontrado_en_sesion:
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




    # SI SE DETECTA LA INTENCIÓN: FINALIZAR_PEDIDO
    if intencion == "FINALIZAR_PEDIDO":
        from app.pedidos import mostrar_pedido, finalizar_pedido

        resumen = mostrar_pedido(session_id)

        # Mostrar resumen y pedir nombre + dirección en una sola pregunta (sin IA)
        mensaje_finalizacion = (
            f"Perfecto 👍 Este es el resumen de tu pedido:\n\n"
            f"{resumen}\n\n"
            f"Por favor, decime tu nombre y dirección para coordinar la entrega. 😊"
        )

        # Marcamos que está esperando los datos del cliente
        session_data = get_datos_traidos_desde_bd(session_id)
        session_data["esperando_datos_cliente"] = True

        return finalizar_respuesta(session_id, mensaje_finalizacion)


    # SI EL CLIENTE RESPONDE CON SUS DATOS (nombre + dirección)
    session_data = get_datos_traidos_desde_bd(session_id)
    if session_data.get("esperando_datos_cliente"):
        from app.pedidos import finalizar_pedido

        datos_cliente = user_input.strip()
        numero_cliente = session_id

        finalizar_pedido(session_id, datos_cliente, numero_cliente)
        session_data["esperando_datos_cliente"] = False

        mensaje_confirmacion = (
            "Perfecto 🙌 Tu pedido fue confirmado correctamente y ya está en camino 🚚"
        )

        return finalizar_respuesta(session_id, mensaje_confirmacion)





    # SI SE DETECTAN PRODUCTOS EN EL INPUT DEL CLIENTE
    if productos_detectados:
        print(f"🛍️ Producto o categoria detectado: {productos_detectados}")
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


