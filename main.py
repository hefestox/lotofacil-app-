from main import create_user, db_execute
ok, msg, uid = create_user("admin","admin@ex.com","senha123","Administrador",None,None)
db_execute("UPDATE users SET role='admin' WHERE id = ?", (uid,))
print(ok, msg, uid)
