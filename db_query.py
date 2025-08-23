# test_db_run.py
import sqlite3
import bcrypt
from datetime import datetime
import db  # importa seu db.py existente

# ==========================
# Criação da tabela users
# ==========================
def init_db():
    db.db_execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        plan TEXT NOT NULL DEFAULT 'Bronze',
        full_name TEXT,
        pix_key TEXT,
        stage INTEGER NOT NULL DEFAULT 1,
        received_stage_donations INTEGER NOT NULL DEFAULT 0,
        referrer_id INTEGER,
        created_at TEXT NOT NULL
    );
    """)
    print("Tabela users criada ou já existente.")

# ==========================
# Inserir usuário de teste
# ==========================
def insert_test_user():
    username = "teste"
    email = "teste@email.com"
    password = "123456"
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    full_name = "Usuário Teste"
    pix_key = "00011122233"
    created_at = datetime.utcnow().isoformat()

    try:
        db.db_execute("""
        INSERT INTO users (username, email, password_hash, full_name, created_at)
        VALUES (?,?,?,?,?)
        """, (username, email, password_hash, full_name, created_at))
        print("Usuário teste inserido com sucesso!")
    except sqlite3.IntegrityError as e:
        print(f"Erro ao inserir usuário teste: {e}")

# ==========================
# Listar usuários
# ==========================
def list_users():
    users = db.db_query("SELECT id, username, email, full_name FROM users", as_df=True)
    print("Usuários cadastrados:")
    print(users)

# ==========================
# Rodar testes
# ==========================
if __name__ == "__main__":
    init_db()
    insert_test_user()
    list_users()