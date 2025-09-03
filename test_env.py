# test_env.py
from dotenv import load_dotenv
import os

load_dotenv(".env")
print("USER:", os.getenv("MYSQL_USER"))
print("HOST:", os.getenv("MYSQL_HOST"))