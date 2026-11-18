
from pathlib import Path
from uuid import uuid4
import subprocess
import base64

from flask import Flask, render_template, request, jsonify, redirect
from werkzeug.utils import secure_filename

import firebase_admin
from firebase_admin import credentials, auth as firebase_auth, firestore
import imageio_ffmpeg


# ==========================================
# 1. FLASK APPLICATION SETUP
# ==========================================

BASE_DIR = Path(__file__).resolve().parent

app = Flask(__name__)
app.secret_key = "change-this-to-a-random-secret-key"

# Maximum upload size: 500 MB
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024

UPLOAD_FOLDER = BASE_DIR / "uploads"
PROCESSED_FOLDER = BASE_DIR / "processed"
THUMBNAIL_FOLDER = BASE_DIR / "thumbnails"

UPLOAD_FOLDER.mkdir(exist_ok=True)
PROCESSED_FOLDER.mkdir(exist_ok=True)
THUMBNAIL_FOLDER.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {
    "mp4", "mov", "avi", "mkv", "webm", "mpeg", "mpg", "wmv"
}


# ==========================================
# 2. FIREBASE ADMIN SDK SETUP
# ==========================================

SERVICE_KEY_PATH = BASE_DIR / "serviceAccountKey.json"

if not SERVICE_KEY_PATH.exists():
    raise FileNotFoundError(
        "serviceAccountKey.json was not found. "
        "Place it in the main CloudVideoProcessor folder."
    )

if not firebase_admin._apps:
    credential = credentials.Certificate(str(SERVICE_KEY_PATH))
    firebase_admin.initialize_app(credential)

db = firestore.client()


# ==========================================
# 3. WEBSITE PAGES
# ==========================================

@app.route("/")
def home():
    return redirect("/login")


@app.route("/register")
def register():
    return render_template("register.html")


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


# ==========================================
# 4. VERIFY FIREBASE USER TOKEN
# ==========================================

def verify_user():

    authorization = request.headers.get("Authorization", "")

    if not authorization.startswith("Bearer "):
        return None

    id_token = authorization.split("Bearer ", 1)[1]

    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
        return decoded_token

    except Exception as error:
        print("Authentication error:", error)
        return None


# ==========================================
# 5. SAVE USER PROFILE TO FIRESTORE
# ==========================================

@app.route("/api/profile", methods=["POST"])
def save_profile():

    user = verify_user()

    if not user:
        return jsonify({
            "success": False,
            "message": "Authentication failed. Please log in again."
        }), 401

    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()

    if not name:
        return jsonify({
            "success": False,
            "message": "Please enter your name."
        }), 400

    uid = user["uid"]
    email = user.get("email", "")

    try:
        db.collection("users").document(uid).set({
            "name": name,
            "email": email,
            "uid": uid
        }, merge=True)

        return jsonify({
            "success": True,
            "message": "User profile saved successfully."
        })

    except Exception as error:
        print("Firestore error:", error)

        return jsonify({
            "success": False,
            "message": "Could not save your profile."
        }), 500


# ==========================================
# 6. GET LOGGED-IN USER PROFILE
# ==========================================

@app.route("/api/me", methods=["GET"])
def get_profile():

    user = verify_user()

    if not user:
        return jsonify({
            "success": False,
            "message": "You are not authenticated."
        }), 401

    uid = user["uid"]

    try:
        user_document = db.collection("users").document(uid).get()

        if user_document.exists:
            profile = user_document.to_dict()
        else:
            profile = {
                "name": user.get("name", "User"),
                "email": user.get("email", "")
            }

        return jsonify({
            "success": True,
            "user": profile
        })

    except Exception as error:
        print("Firestore error:", error)

        return jsonify({
            "success": False,
            "message": "Could not retrieve your profile."
        }), 500


# ==========================================
# 7. VIDEO UPLOAD API
# ==========================================

@app.route("/api/upload", methods=["POST"])
def upload_video():

    user = verify_user()

    if not user:
        return jsonify({
            "success": False,
            "message": "Please log in before uploading a video."
        }), 401

    if "video" not in request.files:
        return jsonify({
            "success": False,
            "message": "No video file was selected."
        }), 400

    video = request.files["video"]

    if video.filename == "":
        return jsonify({
            "success": False,
            "message": "Please select a video."
        }), 400

    original_name = secure_filename(video.filename)

    if "." not in original_name:
        return jsonify({
            "success": False,
            "message": "Invalid video filename."
        }), 400

    extension = original_name.rsplit(".", 1)[1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        return jsonify({
            "success": False,
            "message": "Unsupported video format."
        }), 400

    uid = user["uid"]

    user_folder = UPLOAD_FOLDER / uid
    user_folder.mkdir(parents=True, exist_ok=True)

    unique_filename = f"{uuid4().hex}.{extension}"
    save_path = user_folder / unique_filename

    try:
        video.save(str(save_path))

        file_size = save_path.stat().st_size

        video_data = {
            "uid": uid,
            "original_filename": original_name,
            "stored_filename": unique_filename,
            "extension": extension,
            "size_bytes": file_size,
            "status": "uploaded",
            "created_at": firestore.SERVER_TIMESTAMP
        }

        document = (
            db.collection("users")
            .document(uid)
            .collection("videos")
            .document(unique_filename)
        )

        document.set(video_data)

        return jsonify({
            "success": True,
            "message": "Video uploaded successfully!",
            "video": {
                "id": unique_filename,
                "filename": original_name,
                "size_bytes": file_size,
                "status": "uploaded"
            }
        })

    except Exception as error:

        if save_path.exists():
            save_path.unlink()

        print("Video upload error:", error)

        return jsonify({
            "success": False,
            "message": "Video upload failed. Please try again."
        }), 500


# ==========================================
# 8. GENERATE VIDEO THUMBNAIL API
# ==========================================

@app.route("/api/thumbnail", methods=["POST"])
def generate_thumbnail():

    user = verify_user()

    if not user:
        return jsonify({
            "success": False,
            "message": "Please log in first."
        }), 401

    data = request.get_json(silent=True) or {}
    video_id = data.get("video_id", "")

    # Validate video ID
    if (
        not isinstance(video_id, str)
        or not video_id
        or Path(video_id).name != video_id
        or "/" in video_id
        or "\\" in video_id
    ):
        return jsonify({
            "success": False,
            "message": "Invalid video ID."
        }), 400

    uid = user["uid"]

    try:
        # Find video in this user's Firestore collection
        video_ref = (
            db.collection("users")
            .document(uid)
            .collection("videos")
            .document(video_id)
        )

        video_document = video_ref.get()

        if not video_document.exists:
            return jsonify({
                "success": False,
                "message": "Video not found in your account."
            }), 404

        video_data = video_document.to_dict()
        extension = video_data.get("extension", "").lower()

        if extension not in ALLOWED_EXTENSIONS:
            return jsonify({
                "success": False,
                "message": "Unsupported video format."
            }), 400

        # Locate uploaded video
        video_path = UPLOAD_FOLDER / uid / video_id

        if not video_path.is_file():
            return jsonify({
                "success": False,
                "message": "Uploaded video file not found."
            }), 404

        # Create user's thumbnail folder
        user_thumbnail_folder = THUMBNAIL_FOLDER / uid
        user_thumbnail_folder.mkdir(parents=True, exist_ok=True)

        thumbnail_filename = f"{Path(video_id).stem}.jpg"
        thumbnail_path = user_thumbnail_folder / thumbnail_filename

        # Get FFmpeg executable
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

        # Extract frame at 1 second
        command = [
            ffmpeg_path,
            "-y",
            "-ss", "1",
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",
            "-vf", "scale=640:-1",
            str(thumbnail_path)
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True
        )

        # If video is shorter than one second, retry at 0 seconds
        if result.returncode != 0 or not thumbnail_path.is_file():
            
            if thumbnail_path.exists():
                thumbnail_path.unlink()

            command[command.index("1")] = "0"

            result = subprocess.run(
                command,
                capture_output=True,
                text=True
            )

        if result.returncode != 0 or not thumbnail_path.is_file():
            print("FFmpeg error:", result.stderr)

            return jsonify({
                "success": False,
                "message": "Could not generate thumbnail."
            }), 500

        # Save thumbnail information in Firestore
        video_ref.update({
            "thumbnail_filename": thumbnail_filename,
            "thumbnail_status": "generated"
        })

        # Convert thumbnail to Base64 for browser preview
        thumbnail_base64 = base64.b64encode(
            thumbnail_path.read_bytes()
        ).decode("utf-8")

        return jsonify({
            "success": True,
            "message": "Thumbnail generated successfully!",
            "thumbnail": (
                "data:image/jpeg;base64," + thumbnail_base64
            ),
            "filename": thumbnail_filename
        })

    except Exception as error:

        print("Thumbnail generation error:", error)

        return jsonify({
            "success": False,
            "message": "Thumbnail generation failed."
        }), 500


# ==========================================
# 9. HANDLE FILE TOO LARGE
# ==========================================

@app.errorhandler(413)
def file_too_large(error):

    return jsonify({
        "success": False,
        "message": "Video is too large. Maximum allowed size is 500 MB."
    }), 413


# ==========================================
# 10. RUN THE APPLICATION
# ==========================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
