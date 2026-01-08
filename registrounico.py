from app import app, db, Usuario

with app.app_context():  # Esto es crucial
    db.create_all()
    if not Usuario.query.filter_by(correo="admin@colegio.com").first():
        admin = Usuario(
            nombre="Administrador",
            correo="admin@colegio.com",
            rol="admin"
        )
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
        print("Administrador creado ✅")
    else:
        print("El administrador ya existe")
