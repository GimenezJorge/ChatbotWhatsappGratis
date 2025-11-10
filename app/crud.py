# ==============================================================================
# Asistente inteligente para atención de clientes de supermercados
# Procesa los mensajes recibidos por WhatsApp, detecta intenciones y productos,
# consulta la base de datos y gestiona pedidos usando modelos de IA locales.
# ==============================================================================

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

# def log_historial_archivo(session_id: str) -> list:
#     ruta_archivo = os.path.join("conversaciones", f"{session_id}.txt")
#     if not os.path.exists(ruta_archivo):
#         return []

#     historial = []
#     rol_actual = None
#     contenido_actual = []
#     timestamp_actual = None

#     with open(ruta_archivo, "r", encoding="utf-8") as file:
#         for linea in file:
#             linea = linea.rstrip()
#             if " - De " in linea or " - Bot: " in linea:
#                 # Guardar el bloque anterior antes de pasar al siguiente
#                 if rol_actual and contenido_actual:
#                     historial.append({
#                         "timestamp": timestamp_actual,
#                         "role": rol_actual,
#                         "content": "\n".join(contenido_actual).strip()
#                     })
#                     contenido_actual = []

#                 timestamp_actual = linea[:19]

#                 if " - De " in linea:
#                     rol_actual = "user"
#                     contenido_actual.append(linea.split(" - De ", 1)[1].split(": ", 1)[1])
#                 else:
#                     rol_actual = "bot"
#                     contenido_actual.append(linea.split(" - Bot: ", 1)[1])
#             else:
#                 # Línea que continúa el mensaje anterior
#                 contenido_actual.append(linea)

#         # Guardar el último bloque
#         if rol_actual and contenido_actual:
#             historial.append({
#                 "timestamp": timestamp_actual,
#                 "role": rol_actual,
#                 "content": "\n".join(contenido_actual).strip()
#             })

#     return historial





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
# FUNCIÓN AUXILIAR: mostrar los productos guardados en memoria
# =============================================================================

def mostrar_productos_en_memoria(session_id: str):
    session_data = get_datos_traidos_desde_bd(session_id)
    productos_previos = session_data.get("productos_mostrados", {})

    print("📌 Productos actualmente guardados en memoria:")
    if productos_previos:
        for clave, lista in productos_previos.items():
            print(f"  🔹 '{clave}' → {len(lista)} producto(s):")
            for p in lista:
                print(f"     • {p['producto']} — ${p['precio_venta']}")
    else:
        print("  (vacío)")



# =============================================================================
# FUNCIÓN AUXILIAR: Generar respuesta con lista de productos usando IA
# =============================================================================
def generar_lista_productos_con_ia(modelo_output, user_input, productos, session_id):
    """
    Usa la IA para generar una respuesta natural con los productos encontrados.
    Si la IA falla, devuelve una lista simple sin texto prearmado.
    """
    try:
        prompt_lista = f"""
El cliente preguntó o mencionó: "{user_input}"

Estos son los productos disponibles relacionados con su consulta:

{''.join([f"• {p['producto']} — ${p['precio_venta']}\n" for p in productos])}

Mostrá la lista con viñetas (•) de forma amable y natural,
con un tono cálido y simpático, sin hacer preguntas ni ofrecer acciones.
Cerrá con un comentario corto y natural sobre los productos (por ejemplo, sobre que hay variedad o que se ven buenos),
pero sin invitar a comprar ni agregar al pedido, ni a realizar ninguna otra accion.
"""
        result_lista = modelo_output.invoke(prompt_lista)
        respuesta = result_lista.content if hasattr(result_lista, "content") else str(result_lista)
    except Exception as e:
        print(f"⚠️ Error al generar respuesta con IA: {e}")
        respuesta = (
            "Estos son los productos disponibles:\n\n" +
            "\n".join([f"• {p['producto']} — ${p['precio_venta']}" for p in productos])
        )
    return respuesta.strip()



# =============================================================================
# COMPARACIÓN CON PRODUCTOS MOSTRADOS (MISMO TEXTO DEL PROMPT ORIGINAL)
# =============================================================================

def comparar_con_producto_mostrado(user_input: str, session_id: str) -> str:
    try:
        session_data = get_datos_traidos_desde_bd(session_id)
        productos_mostrados = session_data.get("productos_mostrados", {})

        if not productos_mostrados:
            print("⚠️  No hay productos mostrados en esta sesión, no se puede comparar.")
            return None

        # Armamos lista textual con los productos mostrados hasta el momento
        productos_previos_texto = "Estos son los productos que ya se le mostraron al cliente:\n"
        for lista in productos_mostrados.values():
            for p in lista:
                productos_previos_texto += f"- {p['producto']}\n"

        # Le pasamos todo el contexto a la IA, pero usando la función estructurada
        contexto = f"""
Considerá este contexto previo:
{productos_previos_texto}

Analizá la nueva frase del cliente:
"{user_input}"

Si el producto mencionado no coincide exactamente con los anteriores,
buscá el nombre más parecido entre los productos mostrados y devolvelo como producto detectado.
No inventes nombres nuevos.
"""

        detected = detect_product_with_ai(contexto, session_id)
        productos = detected.get("productos", [])
        intencion = detected.get("intencion")


        if not productos:
            print("🤖 IA: no se encontró coincidencia con los productos mostrados.")
            return None

        producto_detectado = productos[0]
        print(f"🤖 IA: coincidencia encontrada → Intención: {intencion} | Producto: {producto_detectado}")
        

        return producto_detectado

    except Exception as e:
        print(f"⚠️ Error en comparar_con_producto_mostrado: {e}")
        return None





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

#def get_product_info(product_name: str):
def get_product_info(product_name: str, session_id: str, solo_nombre=False):
    connection = connect_to_db()
    if not connection:
        return print("no se conecto a la bd")
    else:
        print(f"🗃️  Se conectó a la BD (buscando: '{product_name}')")

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

        # Guardar en memoria los productos de la categoría mostrados al cliente
        session_data = get_datos_traidos_desde_bd(session_id)
        session_data["productos_mostrados"][product_name.lower()] = productos_categoria
        # Actualizar texto de productos mostrados para IA input
        regenerar_productos_textuales(session_id)



        cursor.close()
        connection.close()

        return productos_categoria


    # =====================================================
    # Si no es categoría, buscar por nombre o marca
    # =====================================================
    if solo_nombre:
        # 🔍 Búsqueda restringida: solo por nombre del producto
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
            WHERE LOWER(p.nombre) LIKE %s
            ORDER BY p.nombre ASC;
        """, (f"%{product_name.lower()}%",))
    else:
        # 🔍 Búsqueda general (nombre, marca o categoría)
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

def buscar_ingredientes_para_comida(nombre_plato: str, session_id: str):
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

    Ejemplo de salida válida para pizza:
    harina, levadura, queso, tomate, aceite
    Ejemplo de salida válida para torta: harina, azúcar, huevos, manteca, leche, polvo de hornear
    Ejemplo de salida válida para empanada: harina, carne, cebolla, huevo, aceitunas
    """

    try:
        respuesta_ia = modelo_input.invoke(prompt_ingredientes).strip()
        respuesta_ia = re.sub(r"<think>.*?</think>", "", respuesta_ia, flags=re.DOTALL).strip()
        print(f"🤖 Ingredientes detectados por IA: {respuesta_ia}")

        if respuesta_ia.upper() == "NINGUNO":
            return None

        ingredientes = [i.strip().lower() for i in re.split(r",|\n|y", respuesta_ia) if i.strip()]
        encontrados = []

        # 2️⃣ Buscamos los ingredientes reales en la base usando la sesión actual
        for ingrediente in ingredientes:
            # 🔍 Para ingredientes, buscamos solo por nombre (sin categoría ni marca)
            resultados = get_product_info(ingrediente, session_id, solo_nombre=True)
            if isinstance(resultados, list) and len(resultados) > 0:
                encontrados.extend(resultados)


        if not encontrados:
            return None

        # =====================================================
        # Guardar los ingredientes encontrados en memoria
        # igual que se hace con los productos mostrados comunes.
        # Pero sin actualizar producto_actual todavía.
        # =====================================================
        session_data = get_datos_traidos_desde_bd(session_id)
        nombre_comida = nombre_plato.lower().strip()

        # ⚙️ Evitar duplicados si ya existen
        if nombre_comida not in session_data["productos_mostrados"]:
            session_data["productos_mostrados"][nombre_comida] = encontrados
            datos_traidos_desde_bd[session_id] = session_data
            print(f"📦 Ingredientes guardados en memoria bajo '{nombre_comida}' ({len(encontrados)} productos)")
        else:
            print(f"⚠️ Ingredientes para '{nombre_comida}' ya estaban guardados, se evita duplicar")

        # No actualizamos producto_actual aquí.
        # Se definirá más adelante, cuando el cliente confirme cuál quiere.
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
- Productos mencionados (si hay)

Frase del cliente: "{user_input}"
"""


        # Si hay contexto, productos mostrados o producto_actual, incluirlos en el prompt
        producto_actual = session_data.get("producto_actual", None)

        if resumen_input or productos_previos_texto or producto_actual:
            prompt = f"""
Considerá este contexto previo:
        {resumen_input}

        {productos_previos_texto}

        {"En los últimos mensajes el cliente habló sobre " + producto_actual + 
". En caso de que el cliente use una frase referencial (por ejemplo: ese, esa, eso, otro igual, la misma), se está refiriendo a " + producto_actual + "." if producto_actual else ""}

Analizá la nueva frase del cliente:
        "{user_input}"

Si el producto mencionado no coincide exactamente con los anteriores,
buscá el nombre más parecido entre los productos mostrados y devolvelo como producto detectado.
No inventes nombres nuevos.

Detectá:
- Intención expresada
- Productos mencionados (si hay)
"""



        # Llamada a la IA input
        raw_response = modelo_input.invoke(prompt).strip()
        cleaned = re.sub(r"<think>.*?</think>", "", raw_response, flags=re.DOTALL | re.IGNORECASE)

        # Extraer intención y productos
        intent_match = re.search(r"intenci[oó]n\s*(detectada|:)?\s*[:\-]?\s*([A-Z_]+)", cleaned, re.IGNORECASE)
        prod_match = re.search(r"productos\s*(mencionados|:)?\s*[:\-]?\s*([^\n\r]+)", cleaned, re.IGNORECASE)

        intent = intent_match.group(2).upper() if intent_match else None
        products_text = prod_match.group(2).strip() if prod_match else ""

        if not products_text or products_text.lower().startswith("ninguno"):
            products = []
        else:
            products = [p.strip() for p in re.split(r",|\s+y\s+|\n", products_text) if p.strip()]

        print("🧩 Resultado de la detección de input:")
        print(f"  🔹 Intención: {intent or 'No detectada'}")
        print(f"  🔹 Productos: {products or 'Ninguno'}")

        return {
            "intencion": intent,
            "productos": products
        }


    except Exception as e:
        print(f"Error en detect_product_with_ai: {e}")
        return {
            "intencion": None,
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

        # Si existe un producto_actual, incluirlo como referencia explícita
        producto_actual = session_data.get("producto_actual", None)
        if producto_actual:
            resumen_prompt += f"""

El producto del que se estuvo hablando recientemente es {producto_actual}.
En caso de que el cliente use frases referenciales (por ejemplo: ese, esa, eso, otro igual, la misma),
se está refiriendo a {producto_actual}.
"""



        resumen_obj = modelo_output.invoke(resumen_prompt)
        resumen = resumen_obj.content if hasattr(resumen_obj, "content") else str(resumen_obj)
        resumen = resumen.strip()

        session_data["ultimo_resumen"] = resumen

        # 🧠 Resumen corto para IA input
        resumen_input_prompt = f"""
A partir de estos mensajes recientes, listá únicamente los nombres de productos mencionados,
sin incluir precios, cantidades, montos ni símbolos de dinero.
Separalos por comas.

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
        def print_long_text(text, max_length=300):
            for i in range(0, len(text), max_length):
                print(text[i:i+max_length])
        print_long_text(resumen)
        print()


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
    print("===================================================================================")
    print(f"\n🧑 Mensaje real del usuario: {user_input}")

    # Mostrar producto_actual actual de la sesión
    session_data = get_datos_traidos_desde_bd(session_id)
    producto_actual = session_data.get("producto_actual", None)

    if producto_actual:
        if isinstance(producto_actual, list):
            print("📌 Productos actuales:", ", ".join(producto_actual))
        else:
            print(f"📌 Producto actual: {producto_actual}")
    else:
        print("📌 Producto actual: (ninguno asignado todavía)")




    #detected = detect_product_with_ai(user_input)
    detected = detect_product_with_ai(user_input, session_id)

    intencion = detected.get("intencion")
    productos_detectados = detected.get("productos", [])






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

    # Guardar la última intención válida y su producto detectado (ahora como producto_actual)
    if intencion in intenciones_validas:
        session_data["ultima_intencion_detectada"] = intencion

        # Verificamos si hay productos detectados válidos
        productos_validos = [
            p for p in productos_detectados
            if p.lower() not in ["ninguno", "ninguna", "nada", "ninguno detectado"]
        ]

        if productos_validos:
            # Si hay más de uno, guardamos la lista completa
            if len(productos_validos) > 1:
                session_data["producto_actual"] = productos_validos
                print(f"🧭 Productos actuales actualizados a lista: {productos_validos}")
            else:
                session_data["producto_actual"] = productos_validos[0]
                print(f"🧭 Producto actual actualizado a: {session_data['producto_actual']}")
        elif session_data.get("producto_actual"):
            # Si no se detectó nada, mantenemos el último producto conocido
            print(f"♻️  Manteniendo producto_actual previo: {session_data['producto_actual']}")
        else:
            print("🕐 No se actualizó producto_actual)")






    # 🚫 Si la última intención fue FINALIZAR_PEDIDO, no pasar más por la IA
    if session_data.get("ultima_intencion_detectada") == "FINALIZAR_PEDIDO":

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
    # elif intencion in ["CHARLAR", "CONSULTAR_INFO"]:
    #     ultima_intencion = session_data.get("ultima_intencion_detectada")
    #     if ultima_intencion in intenciones_validas:
    #         print(f"⚙️  Corrigiendo intención: {intencion} → {ultima_intencion}")
    #         intencion = ultima_intencion


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
        print(f"🧠 Intención '{intencion}'")
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

        # 🧠 Recorremos todos los productos detectados (por ejemplo: "coca" y "sprite")
        for product_name in productos_detectados:
            #products = get_product_info(product_name, session_id)
            products = get_product_info(product_name, session_id)



            # Si la BD devuelve un solo producto, lo fijamos como producto_actual
            if isinstance(products, list) and len(products) == 1:
                producto_encontrado = products[0]["producto"]
                session_data["producto_actual"] = producto_encontrado
                print(f"🧭 Producto actual fijado automáticamente: {producto_encontrado}")

            elif isinstance(products, list) and len(products) > 1:
                # No cambiamos el producto_actual todavía, solo informamos que se mostraron varios
                print(f"🧭 Se mostraron {len(products)} productos para '{product_name}', pero no se actualiza producto_actual hasta que el cliente confirme uno.")



            # Mostrar los productos encontrados (sean 1 o varios)
            if isinstance(products, list) and len(products) > 0:
                session_data["productos_mostrados"][product_name.lower()] = products
                all_products.extend(products)
                mostrar_productos_en_memoria(session_id)
            # ================================================================
            # COMPARACIÓN POST-BD (una vez mostrados los productos)
            # ================================================================
            if productos_detectados:
                coincidencia = comparar_con_producto_mostrado(productos_detectados[0], session_id)
                if coincidencia:
                    session_data["producto_actual"] = coincidencia
                    print(f"📌 Producto actual actualizado tras búsqueda en BD: {coincidencia}")
                else:
                    print("📌 No se encontró coincidencia tras BD; se mantiene el producto_actual previo.")






            # Si no se encontró el producto, intentar buscar ingredientes

            if (not products) or (isinstance(products, str) and "no se encontró" in products.lower()):
                print(f"❌ No se encontró '{product_name}' en la base. Buscando ingredientes...")
                ingredientes = buscar_ingredientes_para_comida(product_name, session_id)

                if ingredientes:
                    print(f"✅ Ingredientes encontrados para {product_name}: {len(ingredientes)} productos")

                    try:
                        prompt_ingredientes = f"""
            El cliente preguntó o mencionó: "{user_input}"

            Informale de manera amable que actualmente no contamos con {product_name} como producto listo para vender. 
            Luego, explicale que puede prepararlo fácilmente y que tenemos todo lo necesario para hacerlo en casa.

            Estos son los ingredientes disponibles relacionados con su consulta:
            {''.join([f"• {p['producto']} — ${p['precio_venta']}\n" for p in ingredientes])}

            Mostrá esta lista con viñetas (•), de forma natural y amable.
            Cerrá con una frase corta, simpática y positiva sobre cocinar o preparar algo casero,
            sin ofrecer acciones ni hacer preguntas.
            """
                        result_ingredientes = modelo_output.invoke(prompt_ingredientes)
                        respuesta = result_ingredientes.content if hasattr(result_ingredientes, "content") else str(result_ingredientes)

                    except Exception as e:
                        print(f"⚠️ Error al generar respuesta con IA para ingredientes: {e}")
                        respuesta = (
                            f"Lamentablemente no tenemos {product_name} en este momento, "
                            "pero podés prepararlo vos mismo con estos ingredientes:\n\n" +
                            "\n".join([f"• {p['producto']} — ${p['precio_venta']}" for p in ingredientes])
                        )
                    # 🧠 Guardar ingredientes mostrados en memoria para futuras coincidencias
                    session_data = get_datos_traidos_desde_bd(session_id)
                    session_data["productos_mostrados"][product_name.lower()] = ingredientes
                    mostrar_productos_en_memoria(session_id)
                    regenerar_productos_textuales(session_id)

                    return finalizar_respuesta(session_id, respuesta)

                else:
                    print(f"🚫 No se encontraron ingredientes relacionados con '{product_name}'.")
                    prompt_no_ingredientes = f"""
            El cliente preguntó o mencionó: "{user_input}"

            No tenemos {product_name} disponible.
            Respondé con una frase breve, empática y natural, sin ofrecer acciones ni hacer preguntas.
            Por ejemplo, podés mostrar empatía o humor suave, pero sin inventar productos ni ofrecer nada más.
            No hagas preguntas ni ofrezcas acciones.
            Cerrá con una frase corta y natural sobre los productos, sin invitar a comprar ni a continuar.
            """
                    result_no_ing = modelo_output.invoke(prompt_no_ingredientes)
                    respuesta = result_no_ing.content if hasattr(result_no_ing, "content") else str(result_no_ing)
                    return finalizar_respuesta(session_id, respuesta)



    # SI SE DETECTA LA INTENCIÓN: AGREGAR_PRODUCTO
    if intencion == "AGREGAR_PRODUCTO":
        session_data = get_datos_traidos_desde_bd(session_id)

        # ================================================================
        # COMPARACIÓN CON PRODUCTOS MOSTRADOS (para actualizar el producto actual)
        # ================================================================
        if session_data.get("productos_mostrados"):
            coincidencia = comparar_con_producto_mostrado(user_input, session_id)
            if coincidencia:
                session_data["producto_actual"] = coincidencia
                print(f"🔁 Producto actual actualizado durante 'AGREGAR_PRODUCTO': {coincidencia}")
            else:
                print("🔁 No se encontró coincidencia durante 'AGREGAR_PRODUCTO'; se mantiene el producto_actual previo.")
        else:
            print("⚠️ No hay productos mostrados aún para comparar en 'AGREGAR_PRODUCTO'.")


        # 🧠 Si la IA no detectó producto o devolvió "ninguna", pero hay uno actual, usar ese
        if (
            (not productos_detectados or all(p.lower() in ["ninguno", "ninguna"] for p in productos_detectados))
            and session_data.get("producto_actual")
        ):
            producto_actual = session_data["producto_actual"]
            productos_detectados = [producto_actual] if isinstance(producto_actual, str) else producto_actual
            print(f"♻️  Usando producto_actual como fallback para agregar: {productos_detectados}")

        # Si aún así no hay productos, salir
        if not productos_detectados:
            prompt_aclaracion = f"""
El cliente expresó que quiere agregar algo, pero no especificó qué producto.
Respondé con una frase amable y natural, pidiéndole que te diga cuál producto quiere agregar, 
sin usar signos de pregunta ni tono interrogativo.


- Dale, decime cuál querés que te agregue 😄
- Genial, contame qué producto querés sumar 🛒
- Perfecto, decime qué te gustaría agregar 😉
- Buenísimo, decime el nombre del producto así lo sumo 👍
- Ok, decime cuál querés agregar al pedido 😊

⚠️ Importante:
No digas literalmente ninguno de los ejemplos anteriores.
Inspirate en el estilo, pero generá tu propia frase original y natural.
Respondé con una sola oración breve de ese tipo.
"""
            result_aclaracion = modelo_output.invoke(prompt_aclaracion)
            respuesta_aclaracion = result_aclaracion.content if hasattr(result_aclaracion, "content") else str(result_aclaracion)
            return finalizar_respuesta(session_id, respuesta_aclaracion)



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




        if productos_detectados:
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
                products = get_product_info(product_name, session_id)


            if isinstance(products, list) and len(products) > 0:
                session_data = get_datos_traidos_desde_bd(session_id)
                session_data["productos_mostrados"][product_name.lower()] = products
                mostrar_productos_en_memoria(session_id)

                try:
                    respuesta = generar_lista_productos_con_ia(modelo_output, user_input, products, session_id)
                except Exception as e:
                    print(f"⚠️ Error al generar lista con IA: {e}")
                    respuesta = generar_lista_productos_con_ia(modelo_output, user_input, products, session_id)

                return finalizar_respuesta(session_id, respuesta)



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
        print("🧾 Mostrando pedido actual para el cliente...")
        resumen = mostrar_pedido(session_id)

        if not resumen or resumen.strip() == "":
            prompt_ia = """
            El cliente pidió ver su pedido, pero todavía no tiene productos agregados.
            Respondé de manera breve, amable y clara.
            No ofrezcas nuevos temas, solo mantené el foco en que aún no hay productos.
            """
        else:
            prompt_ia = f"""
            El cliente pidió ver su pedido. Mostrale el resumen actual de su carrito de forma amable y natural,
            pero sin extenderte ni iniciar nuevas conversaciones. Mantené el foco en mostrar lo que tiene actualmente
            y ofrecer continuar o finalizar. Mostrá el resumen textual a continuación sin modificarlo:

            {resumen}
            """

        try:
            respuesta_ia = modelo_output.invoke(prompt_ia)
            respuesta = respuesta_ia.content if hasattr(respuesta_ia, "content") else str(respuesta_ia)
        except Exception as e:
            print(f"⚠️ Error generando respuesta IA para MOSTRAR_PEDIDO: {e}")
            respuesta = resumen if resumen.strip() else "Todavía no tenés productos en tu pedido 🛒"

        return finalizar_respuesta(session_id, respuesta)



    # SI SE DETECTA LA INTENCIÓN: VACIAR_PEDIDO
    if intencion == "VACIAR_PEDIDO":
        from app.pedidos import vaciar_pedido

        vaciar_pedido(session_id)
        session_data["producto_actual"] = None  # 🧹 limpiar foco actual
        print("🧹 Producto actual limpiado (pedido vaciado)")

        try:
            prompt_vaciar = """
El cliente acaba de vaciar su pedido. 
Respondé con una frase breve, cálida y natural, sin ofrecer nuevos productos ni hacer preguntas.
Con este estilo:
- Listo, vacié tu pedido 👌
- Perfecto 😄, ya está todo limpio
- Ya quedó vacío, podés empezar uno nuevo cuando quieras 👍
- Pedido reseteado, misión cumplida 😎

⚠️ Importante:
No digas literalmente ninguno de los ejemplos anteriores.
Inspirate en el estilo, pero generá tu propia frase original y natural.
Respondé con una sola oración breve de ese tipo.
"""
            respuesta_vaciar = modelo_output.invoke(prompt_vaciar)
            mensaje_vaciado = (
                respuesta_vaciar.content
                if hasattr(respuesta_vaciar, "content")
                else str(respuesta_vaciar)
            )
        except Exception as e:
            print(f"⚠️ Error al generar mensaje de vaciado con IA: {e}")
            mensaje_vaciado = "Listo 👍, vacié tu pedido completo. Podés empezar uno nuevo cuando quieras."

        return finalizar_respuesta(session_id, mensaje_vaciado)


    # SI SE DETECTA LA INTENCIÓN: FINALIZAR_PEDIDO
    if intencion == "FINALIZAR_PEDIDO":

        resumen = mostrar_pedido(session_id)

        # Mostrar resumen y pedir nombre + dirección con IA
        try:
            prompt_finalizar = f"""
El cliente está finalizando su pedido. Mostrale un mensaje cálido y natural con el resumen.
Usá un tono simpático, cercano y profesional. Terminá pidiéndole su nombre y dirección en una sola frase.

- Genial 👍 te dejo el resumen del pedido, así coordinamos la entrega 😉
- Perfecto 🙌 este es tu pedido, decime tu nombre y dirección para el envío 🚚
- Listo 😄 te muestro el pedido y coordinamos el envío enseguida.

⚠️ Importante:
No digas literalmente ninguno de los ejemplos anteriores.
Inspirate en el estilo, pero generá tu propia frase original y natural.
Respondé con una sola oración breve de ese tipo.

    {resumen}
    """
            respuesta_finalizar = modelo_output.invoke(prompt_finalizar)
            mensaje_finalizacion = (
                respuesta_finalizar.content
                if hasattr(respuesta_finalizar, "content")
                else str(respuesta_finalizar)
            )
        except Exception as e:
            print(f"⚠️ Error al generar mensaje de finalización con IA: {e}")
            mensaje_finalizacion = (
                f"Perfecto 👍 Este es el resumen de tu pedido:\n\n"
                f"{resumen}\n\n"
                f"Por favor, decime tu nombre y dirección para coordinar la entrega. 😊"
            )

        # Marcamos que está esperando los datos del cliente
        session_data = get_datos_traidos_desde_bd(session_id)
        session_data["esperando_datos_cliente"] = True

        # 🧹 Limpiar producto_actual al finalizar pedido
        session_data["producto_actual"] = None
        print("🧹 Producto actual limpiado (finalización de pedido)")


        return finalizar_respuesta(session_id, mensaje_finalizacion)


    # SI EL CLIENTE RESPONDE CON SUS DATOS (nombre + dirección)
    session_data = get_datos_traidos_desde_bd(session_id)
    if session_data.get("esperando_datos_cliente"):

        datos_cliente = user_input.strip()
        numero_cliente = session_id

        finalizar_pedido(session_id, datos_cliente, numero_cliente)
        session_data["esperando_datos_cliente"] = False

        mensaje_confirmacion = (
            "Perfecto 🙌 Tu pedido fue confirmado correctamente y ya está en camino 🚚"
        )

        return finalizar_respuesta(session_id, mensaje_confirmacion)





    # SI SE DETECTAN PRODUCTOS EN EL INPUT DEL CLIENTE
    # Solo si la intención NO es CHARLAR (para evitar repetir listas cuando el cliente solo charla o pide opinión)
    if productos_detectados and intencion != "CHARLAR":
        print(f"🛍️  Producto o categoria detectado: {productos_detectados}")
        all_products = []

        # Recuperar los datos de sesión (productos ya consultados)
        session_data = get_datos_traidos_desde_bd(session_id)

        for product_name in productos_detectados:
            products = get_product_info(product_name, session_id)


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
            No hagas preguntas ni ofrezcas acciones.
            Cerrá con una frase corta y natural sobre los productos, sin invitar a comprar ni a continuar.
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


