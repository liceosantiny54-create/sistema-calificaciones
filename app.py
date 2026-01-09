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

# 🔐 SECRET KEY DESDE VARIABLE DE ENTORNO
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")
if not app.config['SECRET_KEY']:
    raise RuntimeError("SECRET_KEY no definida en variables de entorno")

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

class Asignacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    docente_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    materia_id = db.Column(db.Integer, db.ForeignKey('materia.id'), nullable=False)
    grado = db.Column(db.String(50), nullable=False)

    docente = db.relationship('Usuario')
    materia = db.relationship('Materia')

    __table_args__ = (
        db.UniqueConstraint('docente_id', 'materia_id', 'grado', name='uq_asignacion_docente'),
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

# ================= CAMBIAR CONTRASEÑA ADMIN =================
@app.route("/admin/cambiar_password", methods=["GET", "POST"])
@login_required
def cambiar_password_admin():
    if current_user.rol != "admin":
        return redirect(url_for("login"))

    if request.method == "POST":
        actual = request.form["actual"]
        nueva = request.form["nueva"]
        confirmar = request.form["confirmar"]

        if not current_user.check_password(actual):
            flash("La contraseña actual es incorrecta", "error")
            return redirect(url_for("cambiar_password_admin"))

        if len(nueva) < 10:
            flash("La nueva contraseña debe tener al menos 10 caracteres", "error")
            return redirect(url_for("cambiar_password_admin"))

        if nueva != confirmar:
            flash("Las contraseñas no coinciden", "error")
            return redirect(url_for("cambiar_password_admin"))

        current_user.set_password(nueva)
        db.session.commit()

        registrar_auditoria("CAMBIO_PASSWORD", current_user.correo)
        flash("Contraseña actualizada correctamente", "success")
        return redirect(url_for("admin"))

    return render_template("cambiar_password.html")

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

@app.route("/admin/materias", methods=["GET", "POST"])
@login_required
def admin_materias():
    if current_user.rol != "admin":
        return redirect(url_for("login"))

    materias = Materia.query.order_by(Materia.grado, Materia.nombre).all()

    if request.method == "POST":
        nombre = request.form["nombre"]
        grado = request.form["grado"]

        if not Materia.query.filter_by(nombre=nombre, grado=grado).first():
            db.session.add(Materia(nombre=nombre, grado=grado))
            db.session.commit()
            registrar_auditoria("CREAR_MATERIA", f"{nombre} - {grado}")
            flash("Materia creada correctamente", "success")
        else:
            flash("La materia ya existe para ese grado", "error")

    return render_template("admin_materias.html", materias=materias)

@app.route("/docente", methods=["GET", "POST"])
@login_required
def docente():
    if current_user.rol != "docente":
        return redirect(url_for("login"))

    asignaciones = Asignacion.query.filter_by(
        docente_id=current_user.id
    ).all()

    grados = sorted(set(a.grado for a in asignaciones))
    materias_por_grado = {}

    for a in asignaciones:
        materias_por_grado.setdefault(a.grado, []).append(a.materia)

    if request.method == "POST":
        alumno = Alumno.query.filter_by(
            nombre=request.form["nombre"],
            grado=request.form["grado"]
        ).first()

        if not alumno:
            flash("Alumno no encontrado en ese grado", "error")
            return redirect(url_for("docente"))

        permitido = Asignacion.query.filter_by(
            docente_id=current_user.id,
            materia_id=request.form["materia_id"],
            grado=request.form["grado"]
        ).first()

        if not permitido:
            flash("No autorizado", "error")
            return redirect(url_for("docente"))

        if Nota.query.filter_by(
            alumno_id=alumno.id,
            materia=permitido.materia.nombre,
            bloque=request.form["bloque"]
        ).first():
            flash("Nota duplicada", "error")
            return redirect(url_for("docente"))

        db.session.add(Nota(
            alumno_id=alumno.id,
            materia=permitido.materia.nombre,
            bloque=int(request.form["bloque"]),
            puntaje=float(request.form["puntaje"])
        ))
        db.session.commit()

        registrar_auditoria("CREAR_NOTA", alumno.nombre)
        flash("Nota registrada", "success")

    return render_template(
        "docente.html",
        grados=grados,
        materias_por_grado=materias_por_grado
    )


@app.route("/admin/alumnos", methods=["GET", "POST"])
@login_required
def admin_alumnos():
    if current_user.rol != "admin":
        return redirect(url_for("login"))

    alumnos = Alumno.query.order_by(Alumno.grado, Alumno.nombre).all()

    if request.method == "POST":
        nombre = request.form["nombre"]
        grado = request.form["grado"]

        if not Alumno.query.filter_by(nombre=nombre).first():
            db.session.add(Alumno(nombre=nombre, grado=grado))
            db.session.commit()
            registrar_auditoria("CREAR_ALUMNO", nombre)
            flash("Alumno registrado correctamente", "success")
        else:
            flash("El alumno ya existe", "error")

    return render_template("admin_alumnos.html", alumnos=alumnos)

@app.route("/admin/asignaciones", methods=["GET", "POST"])
@login_required
def admin_asignaciones():
    if current_user.rol != "admin":
        return redirect(url_for("login"))

    docentes = Usuario.query.filter_by(rol="docente").all()
    materias = Materia.query.order_by(Materia.grado, Materia.nombre).all()
    asignaciones = Asignacion.query.all()

    if request.method == "POST":
        docente_id = request.form["docente_id"]
        materia_id = request.form["materia_id"]
        grado = request.form["grado"]

        existe = Asignacion.query.filter_by(
            docente_id=docente_id,
            materia_id=materia_id,
            grado=grado
        ).first()

        if not existe:
            db.session.add(Asignacion(
                docente_id=docente_id,
                materia_id=materia_id,
                grado=grado
            ))
            db.session.commit()
            registrar_auditoria("ASIGNAR_MATERIA", f"Docente {docente_id}")
            flash("Asignación creada", "success")
        else:
            flash("Asignación duplicada", "error")

    return render_template(
        "admin_asignaciones.html",
        docentes=docentes,
        materias=materias,
        asignaciones=asignaciones
    )

@app.route("/logout")
@login_required
def logout():
    registrar_auditoria("LOGOUT", current_user.correo)
    logout_user()
    return redirect(url_for("login"))

# ================= REPORTES ADMIN =================
@app.route("/admin/reporte/<int:alumno_id>")
@login_required
def generar_reporte_admin(alumno_id):
    if current_user.rol != "admin":
        return redirect(url_for("login"))

    alumno = Alumno.query.get_or_404(alumno_id)
    notas = Nota.query.filter_by(alumno_id=alumno.id).all()

    if not notas:
        flash("El alumno no tiene notas registradas", "error")
        return redirect(url_for("admin"))

    pdf = generar_boletin_pdf(alumno, notas)
    return send_file(pdf, as_attachment=True)

# ================= EDITAR NOTAS ADMIN =================
@app.route("/admin/editar_notas/<int:alumno_id>", methods=["GET", "POST"])
@login_required
def editar_notas(alumno_id):
    if current_user.rol != "admin":
        return redirect(url_for("login"))

    alumno = Alumno.query.get_or_404(alumno_id)
    notas = Nota.query.filter_by(alumno_id=alumno.id).all()

    if request.method == "POST":
        for nota in notas:
            nuevo = request.form.get(f"puntaje_{nota.id}")
            if nuevo:
                nota.puntaje = float(nuevo)

        db.session.commit()
        registrar_auditoria("EDITAR_NOTAS", alumno.nombre)
        flash("Notas actualizadas correctamente", "success")
        return redirect(url_for("admin"))

    return render_template("editar_notas.html", alumno=alumno, notas=notas)

# ================= DESCARGA MASIVA POR GRADO =================
@app.route("/admin/descargar_grado/<grado>")
@login_required
def descargar_pdfs_por_grado(grado):
    if current_user.rol != "admin":
        return redirect(url_for("login"))

    carpeta = "zip_temp"
    os.makedirs(carpeta, exist_ok=True)
    ruta_zip = os.path.join(carpeta, f"{grado}.zip")

    with zipfile.ZipFile(ruta_zip, "w") as zipf:
        alumnos = Alumno.query.filter_by(grado=grado).all()
        for alumno in alumnos:
            notas = Nota.query.filter_by(alumno_id=alumno.id).all()
            if notas:
                pdf = generar_boletin_pdf(alumno, notas)
                zipf.write(pdf, os.path.basename(pdf))

    registrar_auditoria("DESCARGA_ZIP", grado)
    return send_file(ruta_zip, as_attachment=True)

# ================= INICIALIZACIÓN BD =================
with app.app_context():
    db.create_all()

    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    if not admin_email or not admin_password:
        raise RuntimeError("ADMIN_EMAIL o ADMIN_PASSWORD no definidos")

    if not Usuario.query.filter_by(correo=admin_email).first():
        admin = Usuario(nombre="Administrador", correo=admin_email, rol="admin")
        admin.set_password(admin_password)
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





