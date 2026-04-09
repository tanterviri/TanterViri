import os
from flask import Flask, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Папка, куда сохраняем загруженные картинки (внутри static)
app.config["UPLOAD_FOLDER"] = "static/uploads"
# Ограничение размера файла (2 МБ)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

# Память для лайков: {filename: set(user_id)}
likes = {}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_user_id():
    # простой вариант – по IP
    return request.remote_addr


@app.route("/", methods=["GET"])
def index():
    # Собираем список загруженных файлов
    uploads_dir = app.config["UPLOAD_FOLDER"]
    os.makedirs(uploads_dir, exist_ok=True)
    files = [
        f for f in os.listdir(uploads_dir)
        if os.path.isfile(os.path.join(uploads_dir, f))
    ]

    # превращаем likes в {filename: count}
    like_counts = {name: len(users) for name, users in likes.items()}

    return render_template("index.html", uploaded_files=files, like_counts=like_counts)


@app.route("/upload", methods=["POST"])
def upload():
    # Проверяем, есть ли файл в запросе
    if "image" not in request.files:
        return redirect(url_for("index"))

    file = request.files["image"]
    if file.filename == "":
        return redirect(url_for("index"))

    # Проверка расширения и сохранение
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        uploads_dir = app.config["UPLOAD_FOLDER"]
        os.makedirs(uploads_dir, exist_ok=True)
        filepath = os.path.join(uploads_dir, filename)
        file.save(filepath)

    return redirect(url_for("index"))


@app.route("/like", methods=["POST"])
def like():
    image_id = request.form.get("image_id")
    if not image_id:
        return jsonify({"error": "no_id"}), 400

    user_id = get_user_id()

    if image_id not in likes:
        likes[image_id] = set()

    # переключаем лайк/анлайк
    if user_id in likes[image_id]:
        likes[image_id].remove(user_id)
    else:
        likes[image_id].add(user_id)

    return jsonify({
        "count": len(likes[image_id]),
        "liked": user_id in likes[image_id]
    })


if __name__ == "__main__":
    app.run(debug=True)