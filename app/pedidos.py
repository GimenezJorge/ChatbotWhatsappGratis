# Diccionario global que guarda los pedidos activos por sesión
pedidos_por_cliente = {}

def agregar_a_pedido(session_id: str, producto: str, cantidad: int, precio_unitario: float) -> str:
    from decimal import Decimal

    if session_id not in pedidos_por_cliente:
        pedidos_por_cliente[session_id] = []

    pedido = pedidos_por_cliente[session_id]

    # Buscar si el producto ya está en el pedido
    producto_existente = next((p for p in pedido if p["producto"].lower() == producto.lower()), None)

    if producto_existente:
        # Si ya existe, sumar la cantidad
        producto_existente["cantidad"] += cantidad
        producto_existente["subtotal"] = float(Decimal(producto_existente["precio_unitario"]) * producto_existente["cantidad"])
        total_actual = sum(p["subtotal"] for p in pedido)
        mensaje = f"Se actualizaron las unidades de {producto} (ahora x{producto_existente['cantidad']}).               Total: ${total_actual:.2f}"
    else:
        # Si no existe, agregarlo nuevo
        subtotal = float(Decimal(precio_unitario) * cantidad)
        pedido.append({
            "producto": producto,
            "cantidad": cantidad,
            "precio_unitario": float(precio_unitario),
            "subtotal": subtotal
        })
        total_actual = sum(p["subtotal"] for p in pedido)
        mensaje = f"🛒 Agregué {cantidad} {producto} al pedido. (Total: ${total_actual:.2f}), cuando quieras finalizar tu pedido me avisas 😊"

    print(f"Pedido actualizado!({session_id})")
    return mensaje



def mostrar_pedido(session_id: str) -> str:
    if session_id not in pedidos_por_cliente or not pedidos_por_cliente[session_id]:
        return "Parece que todavía no tenés productos en tu pedido."

    items = pedidos_por_cliente[session_id]
    total = sum(i["subtotal"] for i in items)

    listado = "\n".join([
        f"{i['producto']} ${i['precio_unitario']:.2f}({i['cantidad']}) : ${i['subtotal']:.2f}"
        for i in items
    ])

    return (
        f"Actualmente tu pedido tiene:\n\n"
        f"{listado}\n\n"
        f"🧾 Total: ${total:.2f}\n"
        f"¿Querés agregar algo más o cerrar el pedido?"
    )



def vaciar_pedido(session_id: str) -> str:
    if session_id not in pedidos_por_cliente or not pedidos_por_cliente[session_id]:
        return "todavía no agregaste productos a tu pedido 😕"

    pedidos_por_cliente[session_id] = []
    print(f"Pedido vaciado ({session_id})")
    return "Vacié tu pedido. Podés empezar un nuevo pedido cuando quieras. 🧺"




def finalizar_pedido(session_id: str, datos_cliente: str, numero_cliente: str) -> str:
    import requests
    from app.pedidos import mostrar_pedido

    if session_id not in pedidos_por_cliente or not pedidos_por_cliente[session_id]:
        return "Todavía no tenés ningún producto en tu pedido 😕"

    # Obtener el resumen actual del pedido
    resumen = mostrar_pedido(session_id)

    # Armar el mensaje que se enviará al encargado
    mensaje = (
        "🧾 *NUEVO PEDIDO RECIBIDO*\n\n"
        f"{resumen}\n\n"
        f"📍 *Datos del cliente:* {datos_cliente}\n"
        f"📞 *WhatsApp:* +{numero_cliente}\n\n"
        "Por favor, comuníquese con el cliente para coordinar la entrega. Gracias 🙌"
    )

    try:
        url = "http://localhost:3000/enviar-mensaje"
        #payload = {"numero": "5491125123781", "mensaje": mensaje}  # número del encargado
        payload = {"numero": "5491162195267", "mensaje": mensaje}  # número del encargado
        requests.post(url, json=payload)
        print("📤 Pedido enviado correctamente al encargado.")
    except Exception as e:
        print(f"⚠️ Error enviando pedido al encargado: {e}")
        return "Hubo un problema al enviar el pedido al encargado 😕. Intentá de nuevo más tarde."

    # Vaciar el pedido del cliente
    pedidos_por_cliente[session_id] = []
    print(f"Pedido finalizado ({session_id})")
    return "Perfecto 👍 Tu pedido fue confirmado correctamente y ya está en camino 🚚"



# ============================================================
# PEDIDO DE PRUEBA AL INICIAR (solo para testing local)
# ============================================================

# def inicializar_pedido_prueba():
#     session_id_prueba = "5491112345678"  # simulá un número de cliente
#     pedidos_por_cliente[session_id_prueba] = [
#         {
#             "producto": "Aceite Lira Girasol 1L",
#             "cantidad": 2,
#             "precio_unitario": 310.00,
#             "subtotal": 620.00
#         },
#         {
#             "producto": "Fideos Lucchetti 500g",
#             "cantidad": 1,
#             "precio_unitario": 250.00,
#             "subtotal": 250.00
#         }
#     ]
#     print(f"🧺 Pedido de prueba inicializado para {session_id_prueba}")


# # Llamar automáticamente al iniciar el servidor
# inicializar_pedido_prueba()
