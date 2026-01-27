from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='Individual')
    vehicle_number = db.Column(db.String(20), nullable=True)
    
    def __repr__(self):
        return f'<User {self.username}>'

class ParkingZone(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(200), nullable=False)
    total_slots = db.Column(db.Integer, nullable=False)
    occupied_slots = db.Column(db.Integer, default=0)
    price_per_hour = db.Column(db.Float, nullable=False)
    rating = db.Column(db.Float, default=4.5)
    lat = db.Column(db.Float, nullable=True)
    lon = db.Column(db.Float, nullable=True)

    def __repr__(self):
        return f'<ParkingZone {self.name}>'

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # Simplified for demo
    zone_id = db.Column(db.Integer, db.ForeignKey('parking_zone.id'), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='Active') # Active, Completed
    total_cost = db.Column(db.Float, default=0.0)
    
    zone = db.relationship('ParkingZone', backref='bookings')

    def __repr__(self):
        return f'<Booking {self.id}>'
