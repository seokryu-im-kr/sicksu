import hmac
import hashlib
import io
import base64
from datetime import datetime, timezone, timedelta
from functools import wraps

import qrcode
from flask import (
    Flask, render_template, request, redirect, url_for, flash, jsonify, abort
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import os

from models import db, User, CheckIn, KST, now_kst

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", os.urandom(32).hex())
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///sick.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "로그인이 필요합니다."

SECRET_WORD = os.getenv("SECRET_WORD", "bonapetit")


# ── Helpers ──────────────────────────────────────────────

def today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def generate_today_secret(date_str: str) -> str:
    return hmac.new(
        SECRET_WORD.encode(), date_str.encode(), hashlib.sha256
    ).hexdigest()[:16]


def make_qr_base64(data: str) -> str:
    img = qrcode.make(data, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not (current_user.is_admin or current_user.is_superadmin):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def password_change_check(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.must_change_password:
            return redirect(url_for("change_password"))
        return f(*args, **kwargs)
    return decorated


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ── Auth Routes ──────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("today_qr"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.is_active_user and check_password_hash(user.password_hash, password):
            login_user(user)
            if user.must_change_password:
                return redirect(url_for("change_password"))
            return redirect(url_for("today_qr"))
        flash("아이디 또는 비밀번호가 올바르지 않습니다.", "error")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")

        if not check_password_hash(current_user.password_hash, current_pw):
            flash("현재 비밀번호가 올바르지 않습니다.", "error")
        elif new_pw != confirm_pw:
            flash("새 비밀번호가 일치하지 않습니다.", "error")
        elif len(new_pw) < 4:
            flash("비밀번호는 최소 4자 이상이어야 합니다.", "error")
        else:
            # zxcvbn strength check for user-initiated password change
            try:
                import zxcvbn as zxcvbn_mod
                result = zxcvbn_mod.zxcvbn(new_pw)
                if result["score"] < 2:
                    feedback = result.get("feedback", {})
                    warning = feedback.get("warning", "")
                    suggestions = feedback.get("suggestions", [])
                    msg = "비밀번호가 너무 약합니다."
                    if warning:
                        msg += f" {warning}"
                    if suggestions:
                        msg += " " + " ".join(suggestions)
                    flash(msg, "error")
                    return render_template("change_password.html")
            except ImportError:
                pass

            current_user.password_hash = generate_password_hash(new_pw)
            current_user.must_change_password = False
            db.session.commit()
            flash("비밀번호가 변경되었습니다.", "success")
            return redirect(url_for("today_qr"))
    return render_template("change_password.html")


# ── User Routes ──────────────────────────────────────────

@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("today_qr"))
    return redirect(url_for("login"))


@app.route("/today-qr")
@password_change_check
def today_qr():
    date_str = today_kst()
    secret = generate_today_secret(date_str)
    csv_data = f"{date_str},{current_user.username},{secret}"
    qr_b64 = make_qr_base64(csv_data)
    gen_time = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    return render_template("today_qr.html", qr_b64=qr_b64, gen_time=gen_time)


@app.route("/status")
@password_change_check
def status():
    month_filter = request.args.get("month", "")
    query = CheckIn.query.filter_by(user_id=current_user.id)
    if month_filter:
        query = query.filter(CheckIn.date.like(f"{month_filter}-%"))
    checkins = query.order_by(CheckIn.date.desc()).all()
    return render_template("status.html", checkins=checkins, month_filter=month_filter)


@app.route("/reader")
def reader():
    return render_template("reader.html")


# ── API Routes ───────────────────────────────────────────

@app.route("/api/checkin", methods=["POST"])
def api_checkin():
    data = request.get_json()
    if not data or "qr_data" not in data:
        return jsonify({"status": "fail", "message": "데이터가 없습니다."}), 400

    qr_data = data["qr_data"].strip()
    parts = qr_data.split(",")
    if len(parts) != 3:
        return jsonify({"status": "fail", "message": "QR코드 형식이 올바르지 않습니다."}), 400

    qr_date, username, qr_secret = parts[0], parts[1], parts[2]

    # Validate date
    date_str = today_kst()
    if qr_date != date_str:
        return jsonify({"status": "fail", "message": "오늘 날짜의 QR코드가 아닙니다."}), 400

    # Validate secret
    expected_secret = generate_today_secret(date_str)
    if not hmac.compare_digest(qr_secret, expected_secret):
        return jsonify({"status": "fail", "message": "QR코드 인증에 실패했습니다."}), 400

    # Find user
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"status": "fail", "message": "존재하지 않는 사용자입니다."}), 400
    if not user.is_active_user:
        return jsonify({"status": "fail", "message": "비활성화된 사용자입니다."}), 400

    # Check duplicate
    existing = CheckIn.query.filter_by(user_id=user.id, date=date_str).first()
    if existing:
        return jsonify({"status": "duplicate", "message": f"{username}님은 오늘 이미 체크인했습니다."}), 200

    # Create check-in
    checkin = CheckIn(user_id=user.id, date=date_str, secret_valid=True)
    db.session.add(checkin)
    db.session.commit()

    return jsonify({"status": "success", "message": f"{username}님 체크인 완료!"}), 200


# ── Admin Routes ─────────────────────────────────────────

@app.route("/admin")
@admin_required
def admin_dashboard():
    date_str = today_kst()
    total_users = User.query.filter_by(is_active_user=True).count()
    today_checkins = CheckIn.query.filter_by(date=date_str).count()
    total_checkins = CheckIn.query.count()
    recent_checkins = CheckIn.query.order_by(CheckIn.created_at.desc()).limit(10).all()
    return render_template(
        "admin/dashboard.html",
        total_users=total_users,
        today_checkins=today_checkins,
        total_checkins=total_checkins,
        recent_checkins=recent_checkins,
        today=date_str,
    )


@app.route("/admin/users")
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=users)


@app.route("/admin/users/create", methods=["POST"])
@admin_required
def admin_create_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    must_change = request.form.get("must_change_password") == "on"

    if not username or not password:
        flash("아이디와 비밀번호를 입력하세요.", "error")
        return redirect(url_for("admin_users"))

    if User.query.filter_by(username=username).first():
        flash("이미 존재하는 아이디입니다.", "error")
        return redirect(url_for("admin_users"))

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        must_change_password=must_change,
    )
    db.session.add(user)
    db.session.commit()
    flash(f"사용자 '{username}'이(가) 생성되었습니다.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/toggle", methods=["POST"])
@admin_required
def admin_toggle_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    if user.is_superadmin:
        flash("슈퍼어드민은 비활성화할 수 없습니다.", "error")
        return redirect(url_for("admin_users"))
    user.is_active_user = not user.is_active_user
    db.session.commit()
    status_text = "활성화" if user.is_active_user else "비활성화"
    flash(f"'{user.username}' 사용자가 {status_text}되었습니다.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    if user.is_superadmin:
        flash("슈퍼어드민은 삭제할 수 없습니다.", "error")
        return redirect(url_for("admin_users"))
    username = user.username
    CheckIn.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    flash(f"'{username}' 사용자가 삭제되었습니다.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/grant-admin", methods=["POST"])
@admin_required
def admin_grant_admin(user_id):
    if not current_user.is_superadmin:
        abort(403)
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    user.is_admin = not user.is_admin
    db.session.commit()
    status_text = "부여" if user.is_admin else "해제"
    flash(f"'{user.username}' 어드민 권한이 {status_text}되었습니다.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/edit", methods=["POST"])
@admin_required
def admin_edit_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    if user.is_superadmin and not current_user.is_superadmin:
        abort(403)

    new_password = request.form.get("password", "").strip()
    must_change = request.form.get("must_change_password") == "on"

    if new_password:
        user.password_hash = generate_password_hash(new_password)
    user.must_change_password = must_change
    db.session.commit()
    flash(f"'{user.username}' 사용자 정보가 수정되었습니다.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/records")
@admin_required
def admin_records():
    page = request.args.get("page", 1, type=int)
    per_page = 30
    date_filter = request.args.get("date", "")
    month_filter = request.args.get("month", "")
    user_filter = request.args.get("username", "")

    query = CheckIn.query.join(User)
    if date_filter:
        query = query.filter(CheckIn.date == date_filter)
    elif month_filter:
        query = query.filter(CheckIn.date.like(f"{month_filter}-%"))
    if user_filter:
        query = query.filter(User.username.ilike(f"%{user_filter}%"))

    pagination = query.order_by(CheckIn.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template(
        "admin/records.html",
        records=pagination.items,
        pagination=pagination,
        date_filter=date_filter,
        month_filter=month_filter,
        user_filter=user_filter,
    )


# ── Init ─────────────────────────────────────────────────

def init_db():
    with app.app_context():
        db.create_all()
        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD", "admin1234")
        if not User.query.filter_by(username=admin_username).first():
            admin = User(
                username=admin_username,
                password_hash=generate_password_hash(admin_password),
                is_admin=True,
                is_superadmin=True,
            )
            db.session.add(admin)
            db.session.commit()
            print(f"슈퍼어드민 '{admin_username}' 생성 완료")


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=18888, debug=True)
