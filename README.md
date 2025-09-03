# Levantar el programa en Visual

```bash
> uvicorn app.main:app --reload --port 8000
```
# Levantar Ngrok

- Descargar Ngrok, Registrarse e iniciar la aplicacion y en la consola poner:

```bash
> ngrok http 8000
```

# Levantar Twilio

1. Messaging → Try it out → Send a WhatsApp message

2. Escanear el codigo QR que te da Twilio

3. Poner el comando que el propio Twilio te da.

```bash
> join explain-neighbor
```

# Credenciales .env

## Database

```bash
> MYSQL_HOST=""
> MYSQL_USER=""
> MYSQL_PASSWORD=""
> MYSQL_DATABASE=""
> MYSQL_PORT=""
```

## Twilio

```bash
> From=
> Body=
> TWILIO_ACCOUNT_SID=
> TWILIO_AUTH_TOKEN=
> TWILIO_WHATSAPP_NUMBER=
> ACCESS_TOKEN=
```
