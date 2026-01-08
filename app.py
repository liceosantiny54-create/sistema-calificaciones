# ================= IMPORTS =================
from flask import Flask, render_template, redirect, url_for, request, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from generar_boletin import generar_boletin_pdf
from datetime import datetime
import zipfile
import os

# ================= APP =================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'clave-secreta-segura'

# 🔧 ASEGURAR CARPETA INSTANCE (RENDER)
os.makedirs(app.instance_path, exist_ok=True)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ================= MODELOS =================
class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    rol = db.Column(db.String(20), nullable=False)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

class Alumno(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    grado = db.Column(db.String(50), nullable=False)

class Nota(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    alumno_id = db.Column(db.Integer, db.ForeignKey('alumno.id'), nullable=False)
    materia = db.Column(db.String(50), nullable=False)
    bloque = db.Column(db.Integer, nullable=False)
    puntaje = db.Column(db.Float, nullable=False)

    alumno = db.relationship('Alumno')

    __table_args__ = (
        db.UniqueConstraint('alumno_id', 'materia', 'bloque', name='uq_nota_unica'),
    )

class Materia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    grado = db.Column(db.String(50), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('nombre', 'grado', name='uq_materia_grado'),
    )

class Auditoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    accion = db.Column(db.String(50), nullable=False)
    descripcion = db.Column(db.String(200), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

    usuario = db.relationship('Usuario')

# ================= AUDITORÍA =================
def registrar_auditoria(accion, descripcion):
    if current_user.is_authenticated:
        db.session.add(Auditoria(
            usuario_id=current_user.id,
            accion=accion,
            descripcion=descripcion
        ))
        db.session.commit()

# ================= LOGIN =================
login_manager = LoginManager(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# ================= RUTAS =================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = Usuario.query.filter_by(correo=request.form["correo"]).first()
        if user and user.check_password(request.form["password"]):
            login_user(user)
            registrar_auditoria("LOGIN", user.correo)
            return redirect(url_for("admin" if user.rol == "admin" else "docente"))
        flash("Credenciales incorrectas", "error")
    return render_template("login.html")

@app.route("/admin")
@login_required
def admin():
    if current_user.rol != "admin":
        return redirect(url_for("login"))
    alumnos = Alumno.query.order_by(Alumno.grado, Alumno.nombre).all()
    grados = sorted(set(a.grado for a in alumnos))
    return render_template("admin.html", alumnos=alumnos, grados=grados)

@app.route("/admin/crear_docente", methods=["GET", "POST"])
@login_required
def crear_docente():
    if current_user.rol != "admin":
        return redirect(url_for("login"))
    if request.method == "POST":
        if not Usuario.query.filter_by(correo=request.form["correo"]).first():
            docente = Usuario(
                nombre=request.form["nombre"],
                correo=request.form["correo"],
                rol="docente"
            )
            docente.set_password(request.form["password"])
            db.session.add(docente)
            db.session.commit()
            registrar_auditoria("CREAR_DOCENTE", docente.correo)
            flash("Docente creado", "success")
    return render_template("crear_docente.html")

# ================= DOCENTE =================
@app.route("/docente", methods=["GET", "POST"])
@login_required
def docente():
    if current_user.rol != "docente":
        return redirect(url_for("login"))

    alumnos = Alumno.query.with_entities(Alumno.nombre, Alumno.grado).all()
    grado = request.form.get("grado")
    materias = []

    if grado:
        materias = Materia.query.filter_by(grado=grado).order_by(Materia.nombre).all()

    if request.method == "POST" and request.form.get("materia"):
        alumno = Alumno.query.filter_by(nombre=request.form["nombre"]).first()

        if not alumno:
            alumno = Alumno(nombre=request.form["nombre"], grado=grado)
            db.session.add(alumno)
            db.session.commit()

        if Nota.query.filter_by(
            alumno_id=alumno.id,
            materia=request.form["materia"],
            bloque=request.form["bloque"]
        ).first():
            flash("Nota duplicada", "error")
            return redirect(url_for("docente"))

        db.session.add(Nota(
            alumno_id=alumno.id,
            materia=request.form["materia"],
            bloque=int(request.form["bloque"]),
            puntaje=float(request.form["puntaje"])
        ))
        db.session.commit()

        registrar_auditoria("CREAR_NOTA", alumno.nombre)
        flash("Nota registrada", "success")

    return render_template("docente.html", alumnos=alumnos, materias=materias)

@app.route("/logout")
@login_required
def logout():
    registrar_auditoria("LOGOUT", current_user.correo)
    logout_user()
    return redirect(url_for("login"))

# ================= INICIALIZACIÓN BD =================
with app.app_context():
    db.create_all()

    if not Usuario.query.filter_by(correo="admin@colegio.com").first():
        admin = Usuario(nombre="Administrador", correo="admin@colegio.com", rol="admin")
        admin.set_password("admin123")
        db.session.add(admin)

    materias = [
        ("Matemática", "Primero Primaria"),
        ("Lenguaje", "Primero Primaria"),
        ("Ciencias", "Primero Primaria"),
        ("Matemática", "Segundo Primaria"),
        ("Lenguaje", "Segundo Primaria"),
        ("Sociales", "Segundo Primaria"),
    ]

    for nombre, grado in materias:
        if not Materia.query.filter_by(nombre=nombre, grado=grado).first():
            db.session.add(Materia(nombre=nombre, grado=grado))

    db.session.commit()

