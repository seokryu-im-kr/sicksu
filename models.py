from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timezone, timedelta

db = SQLAlchemy()

KST = timezone(timedelta(hours=9))


def now_kst():
    return datetime.now(KST)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_superadmin = db.Column(db.Boolean, default=False)
    is_active_user = db.Column(db.Boolean, default=True)
    must_change_password = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=now_kst)

    checkins = db.relationship("CheckIn", backref="user", lazy=True)

    @property
    def is_active(self):
        return self.is_active_user


class CheckIn(db.Model):
    __tablename__ = "checkins"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    date = db.Column(db.String(10), nullable=False)  # YYYY-MM-DD
    secret_valid = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=now_kst)

    __table_args__ = (
        db.UniqueConstraint("user_id", "date", name="uq_user_date"),
    )
