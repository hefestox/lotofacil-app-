import sqlite3
import bcrypt
from datetime import datetime

# Conexão com o banco
conn = sqlite3.connect("app.db")
cur = conn.cursor()

# Função para criar hash da senha
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

# Dados do usuário admin
username = "admin"
email = "admin@teste.com"
password = "123456"  # você pode alterar
role = "admin"
plan = "Ouro"  # opcional
credits = 100
created_at = datetime.utcnow().isoformat()

try:
    cur.execute("""
        INSERT INTO users (username, email, password_hash, role, plan, credits, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (username, email, hash_password(password), role, plan, credits, created_at))
    conn.commit()
    print("✅ Usuário admin criado com sucesso!")
except sqlite3.IntegrityError:
    print("⚠️ Usuário já existe.")

conn.close()

