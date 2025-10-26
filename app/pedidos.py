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
        mensaje = f"Agregué {cantidad} {producto} al pedido. (Total: ${total_actual:.2f})"

    print(f"[DEBUG] Pedido actualizado para {session_id}: {pedido}")
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
