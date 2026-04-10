import os
from flask import (
    Flask, render_template, request,
    redirect, url_for, jsonify, session
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)

# СЕКРЕТНЫЙ КЛЮЧ ДЛЯ СЕССИЙ
app.config["SECRET_KEY"] = "очень-секретный-ключ-замени-потом"

# SQLite-файл ЛЕЖИТ В ПАПКЕ ПРОЕКТА (db.sqlite рядом с hello.py)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///db.sqlite"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# Папка, куда сохраняем загруженные картинки (внутри static)
app.config["UPLOAD_FOLDER"] = "static/uploads"
# Ограничение размера файла (2 МБ)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


# ---- МОДЕЛИ ----

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image_name = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


# ---- СЛУЖЕБНОЕ ----

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_current_user():
    username = session.get("username")
    if not username:
        return None
    return User.query.filter_by(username=username).first()


def is_admin():
    # здесь можно подставить твой ник вместо 'admin'
    return session.get("username") == "TANTER"


def login_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


# ---- РЕГИСТРАЦИЯ / ЛОГИН ----

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            return render_template("register.html", error="Нужны ник и пароль")

        # Проверяем, нет ли такого ника
        if User.query.filter_by(username=username).first():
            return render_template("register.html", error="Такой ник уже существует")

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        session["username"] = username
        return redirect(url_for("index"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            return render_template("login.html", error="Неверный ник или пароль")

        session["username"] = username
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("login"))


# ---- ГЛАВНАЯ / ГАЛЕРЕЯ ----

@app.route("/", methods=["GET"])
@login_required
def index():
    uploads_dir = app.config["UPLOAD_FOLDER"]
    os.makedirs(uploads_dir, exist_ok=True)
    files = [
        f for f in os.listdir(uploads_dir)
        if os.path.isfile(os.path.join(uploads_dir, f))
    ]

    # считаем лайки: {image_name: count}
    like_counts = {}
    for row in (
        db.session.query(Like.image_name, db.func.count(Like.id))
        .group_by(Like.image_name)
        .all()
    ):
        like_counts[row[0]] = row[1]

    return render_template(
        "index.html",
        uploaded_files=files,
        like_counts=like_counts,
        username=session.get("username"),
    )


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    if "image" not in request.files:
        return redirect(url_for("index"))

    file = request.files["image"]
    if file.filename == "":
        return redirect(url_for("index"))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        uploads_dir = app.config["UPLOAD_FOLDER"]
        os.makedirs(uploads_dir, exist_ok=True)
        filepath = os.path.join(uploads_dir, filename)
        file.save(filepath)

    return redirect(url_for("index"))


# ---- ЛАЙКИ ----

@app.route("/like", methods=["POST"])
@login_required
def like():
    image_id = request.form.get("image_id")
    if not image_id:
        return jsonify({"error": "no_id"}), 400

    user = get_current_user()
    if not user:
        return jsonify({"error": "not_auth"}), 403

    existing = Like.query.filter_by(image_name=image_id, user_id=user.id).first()

    if existing:
        # если уже лайкнул — убираем лайк
        db.session.delete(existing)
        db.session.commit()
    else:
        new_like = Like(image_name=image_id, user_id=user.id)
        db.session.add(new_like)
        db.session.commit()

    # пересчёт количества лайков
    count = Like.query.filter_by(image_name=image_id).count()
    liked = Like.query.filter_by(image_name=image_id, user_id=user.id).first() is not None

    return jsonify({"count": count, "liked": liked})


# ---- УДАЛЕНИЕ ИЗОБРАЖЕНИЯ (ТОЛЬКО АДМИН) ----

@app.route("/delete_image", methods=["POST"])
@login_required
def delete_image():
    if not is_admin():
        return jsonify({"error": "forbidden"}), 403

    image_id = request.form.get("image_id")
    if not image_id:
        return jsonify({"error": "no_id"}), 400

    uploads_dir = app.config["UPLOAD_FOLDER"]
    filepath = os.path.join(uploads_dir, image_id)

    # удаляем файл, если есть
    if os.path.exists(filepath):
        os.remove(filepath)

    # удаляем все лайки, связанные с этим изображением
    Like.query.filter_by(image_name=image_id).delete()
    db.session.commit()

    return jsonify({"success": True})


# ---- СОЗДАНИЕ ТАБЛИЦ ПРИ ПЕРВОМ ЗАПУСКЕ ----

with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)