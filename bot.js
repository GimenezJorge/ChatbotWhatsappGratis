// --- dependencias principales ---
const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const axios = require('axios');
require('dotenv').config();

const ACCESS_TOKEN = process.env.ACCESS_TOKEN;

// --- configuración del cliente ---
const client = new Client({
	authStrategy: new LocalAuth({
		dataPath: 'C:\\SESION-WSP',
		clientId: 'main',
	}),
	// sesion de whatsapp web invisible: 
	// puppeteer: {
	// 	headless: true,
	// 	args: ['--no-sandbox', '--disable-setuid-sandbox', '--headless=new'],
	// 	executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
	// },
	puppeteer: {
		headless: false,
		args: ['--no-sandbox', '--disable-setuid-sandbox'],
		executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
	},

});

// --- utilidades ---
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function waitForConnected(maxTries = 10) {
	for (let i = 1; i <= maxTries; i++) {
		const st = await client.getState().catch(() => null);
		console.log(`🔌 getState [${i}/${maxTries}] =`, st);
		if (st === 'CONNECTED') return true;
		await sleep(1000);
	}
	return false;
}

// --- eventos base ---
client.on('qr', (qr) => {
	console.log('📱 Escaneá el QR (preferí el del navegador si aparece en pantalla):');
	qrcode.generate(qr, { small: true });
});

client.on('loading_screen', (pct, msg) => console.log('⏳ loading_screen:', pct, msg));
client.on('change_state', (s) => console.log('🔄 change_state:', s));
client.on('auth_failure', (m) => console.log('❌ auth_failure:', m));
client.on('disconnected', (r) => console.log('⚠️ disconnected:', r));
client.on('authenticated', () => console.log('✅ Autenticación exitosa'));

// --- cliente listo ---
client.on('ready', async () => {
	console.log('✅ READY. Esperando conexión estable...');
	const connected = await waitForConnected();
	if (!connected) {
		console.log('⚠️ No llegó a CONNECTED, no envío mensaje.');
		return;
	}

	try {
		const numero = '5491162195267';
		let chatId = null;

		const numberId = await client.getNumberId(numero).catch(() => null);
		chatId = numberId ? numberId._serialized : `${numero}@c.us`;
		console.log('📤 Chat ID seleccionado:', chatId);

		// await client.sendMessage(chatId, 'hola amigo, este es un mensaje de prueba 😎');
		// console.log('📤 Mensaje enviado a', chatId);
	} catch (e) {
		console.error('❌ Error al enviar mensaje:', e);
	}
});

// --- enviar mensajes reales a FastAPI ---
client.on('message', async (msg) => {
	try {
		const fromNumber = msg.from.replace('@c.us', '');
		const body = msg.body;

		console.log(`📩 Mensaje de ${fromNumber}: ${body}`);

		const response = await axios.post(
			'http://localhost:8000/process-message',
			{ from: fromNumber, body },
			{ headers: { 'Authorization': `Bearer ${ACCESS_TOKEN}` } }
		);

		if (response.data?.status === 'ok') {
			const reply = response.data.response;
			await client.sendMessage(msg.from, reply);
			console.log(`✅ Respuesta enviada: ${reply}`);
		} else {
			console.log('⚠️ Respuesta inválida del endpoint:', response.data);
			await client.sendMessage(msg.from, "Lo siento, no pude procesar tu mensaje.");
		}
	} catch (err) {
		console.error('❌ Error procesando mensaje:', err.message);
		await client.sendMessage(msg.from, "Lo siento, ocurrió un error al procesar tu mensaje.");
	}
});

// --- cierre limpio con Ctrl + C ---
process.on('SIGINT', async () => {
	console.log('\n👋 Cerrando sesión y saliendo...');
	try {
		await client.destroy();
	} catch (e) {
		console.warn('⚠️ Error al cerrar:', e.message);
	}
	process.exit(0);
});

// --- iniciar cliente ---
client.initialize();
