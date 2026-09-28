from datetime import date, datetime

from app import db
from app.utils import to_kg


class WeightEntry(db.Model):
    __table_args__ = (db.UniqueConstraint("user_id", "entry_date", name="uq_user_entry_date"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    entry_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    weight = db.Column(db.Float, nullable=False)
    note = db.Column(db.String(280), nullable=True)

    def __repr__(self):
        return f"<WeightEntry user={self.user_id} {self.entry_date} {self.weight}>"


class User(db.Model):
    MAX_CODE_ATTEMPTS = 5
    HEIGHT_UNITS = ("cm", "m")

    id = db.Column(db.Integer, primary_key=True)
    # SHA-256 of the trimmed, lowercased email (the same hash Gravatar's REST
    # API uses, see https://docs.gravatar.com/rest/hash/). We never persist
    # the plaintext address so a database breach doesn't expose it.
    email_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    code_hash = db.Column(db.String(255), nullable=True)
    code_expires_at = db.Column(db.DateTime, nullable=True)
    code_attempts = db.Column(db.Integer, nullable=False, default=0)

    height_cm = db.Column(db.Float, nullable=True)
    height_unit = db.Column(db.String(2), nullable=False, default="cm")
    dark_mode = db.Column(db.Boolean, nullable=False, default=False)

    entries = db.relationship(
        "WeightEntry", backref="user", cascade="all, delete-orphan", lazy="dynamic"
    )

    @property
    def is_verified(self):
        return self.verified_at is not None

    def gravatar_url(self, size=80, default="mp"):
        return f"https://www.gravatar.com/avatar/{self.email_hash}?s={size}&d={default}"

    def latest_weight_kg(self, weight_unit):
        entry = self.entries.order_by(WeightEntry.entry_date.desc()).first()
        if entry is None:
            return None
        return to_kg(entry.weight, weight_unit)

    def bmi(self, weight_unit):
        if not self.height_cm:
            return None
        weight_kg = self.latest_weight_kg(weight_unit)
        if weight_kg is None:
            return None
        height_m = self.height_cm / 100
        return weight_kg / (height_m ** 2)

    def __repr__(self):
        return f"<User {self.email_hash[:8]}…>"
