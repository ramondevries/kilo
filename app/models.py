from datetime import date, datetime

from app import db


class WeightEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    entry_date = db.Column(db.Date, nullable=False, unique=True, default=date.today, index=True)
    weight = db.Column(db.Float, nullable=False)
    note = db.Column(db.String(280), nullable=True)

    def __repr__(self):
        return f"<WeightEntry {self.entry_date} {self.weight}>"


class User(db.Model):
    MAX_CODE_ATTEMPTS = 5

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    code_hash = db.Column(db.String(255), nullable=True)
    code_expires_at = db.Column(db.DateTime, nullable=True)
    code_attempts = db.Column(db.Integer, nullable=False, default=0)

    @property
    def is_verified(self):
        return self.verified_at is not None

    def __repr__(self):
        return f"<User {self.email}>"
