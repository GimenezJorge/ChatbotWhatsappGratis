import mysql.connector
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

# Credenciales en .env
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_PORT = os.getenv("MYSQL_PORT")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")

SQLALCHEMY_DATABASE_URL = f"mysql+mysqlconnector://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"

# Validación individual de variables de entorno
if not all([MYSQL_USER, MYSQL_PASSWORD, MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE]):
    raise ValueError("Faltan credenciales en el archivo .env Asegúrate de definir: MYSQL_USER, MYSQL_PASSWORD, MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE")

# Crear una instancia de motor para la base de datos
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Crear una clase de sesión para interactuar con la base de datos
SessionLocal = sessionmaker(autocommit=False,autoflush=False,bind=engine)

def connect_to_db():
    try:
        connection = mysql.connector.connect(
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASSWORD"),
            host=os.getenv("MYSQL_HOST"),
            port=os.getenv("MYSQL_PORT"),
            database=os.getenv("MYSQL_DATABASE")
        )
        return connection
    except Exception as e:
        print(f"Error en la conexión a la base de datos: {e}")
        return None


# Test de conexión
if __name__ == "__main__":
    try:
        db = SessionLocal()
        print("Conexión exitosa a la base de datos!")
        db.close()
    except Exception as e:
        print(f"Error al conectar a la base de datos: {e}")
        
