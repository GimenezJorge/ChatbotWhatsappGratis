def leer_info_supermercado():
	with open("info_supermercado.txt", "r", encoding="utf-8") as f:
		contenido = f.read().strip()
		print("--------------------------------- LEIDO info_supermercado.txt  ---------------------------------")
	return contenido
