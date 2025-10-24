# Diccionario global que guarda los pedidos activos por sesión
pedidos_por_cliente = {}

def agregar_a_pedido(session_id: str, producto: str, cantidad: int, precio_unitario: float) -> str:
	if session_id not in pedidos_por_cliente:
		pedidos_por_cliente[session_id] = []

	# Crear el ítem del pedido
	item = {
		"producto": producto,
		"cantidad": cantidad,
		"precio_unitario": precio_unitario,
		"subtotal": cantidad * precio_unitario
	}

	pedidos_por_cliente[session_id].append(item)
	total_actual = sum(i["subtotal"] for i in pedidos_por_cliente[session_id])
	print(f"[DEBUG] Pedido actualizado para {session_id}: {pedidos_por_cliente[session_id]}")

	return f"Se agregó {cantidad} unidad(es) de '{producto}' al pedido. Total parcial: ${total_actual:.2f}"




















def mostrar_pedido(session_id: str) -> str:	
	if session_id not in pedidos_por_cliente or not pedidos_por_cliente[session_id]:
		return "Parece que todavía no tenés productos en tu pedido."

	items = pedidos_por_cliente[session_id]
	total = sum(i["subtotal"] for i in items)

	listado = "\n".join([
		f"* {i['producto']} — ${i['precio_unitario']:.2f} x{i['cantidad']} = ${i['subtotal']:.2f}"
		for i in items
	])

	return (
		f"Actualmente tu pedido tiene:\n\n"
		f"{listado}\n\n"
		f"🧾 Total acumulado: ${total:.2f}\n"
		f"¿Querés agregar algo más o cerrar el pedido?"
	)
