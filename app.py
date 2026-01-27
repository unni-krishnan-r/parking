from flask import Flask, render_template, request, redirect, url_for, session, flash
from models import db, User, ParkingZone, Booking
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import os
import math

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///parkeasy.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'parkeasy_secret_key'

db.init_app(app)

# --- Helpers ---
def get_current_user_id():
    return session.get('user_id')

def haversine(lat1, lon1, lat2, lon2):
    # Radius of earth in kilometers
    R = 6371
    
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2) * math.sin(dLat/2) + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dLon/2) * math.sin(dLon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    d = R * c # Distance in km
    return d

@app.before_request
def require_login():
    # List of endpoints that don't require login
    allowed_routes = ['login', 'register', 'static']
    if request.endpoint and request.endpoint not in allowed_routes and 'user_id' not in session:
        # Allow static files to be served without login
        if not request.endpoint.startswith('static'):
            return redirect(url_for('login'))

# --- Auth Routes ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'error')
            
    return render_template('login.html', page='auth')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        vehicle_number = request.form.get('vehicle_number')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('register'))
            
        hashed_pw = generate_password_hash(password)
        new_user = User(username=username, email=email, password=hashed_pw, vehicle_number=vehicle_number)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html', page='auth')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect(url_for('login'))

# --- App Routes ---

@app.route('/')
@app.route('/dashboard')
def dashboard():
    search_query = request.args.get('q', '')
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    
    if search_query:
        zones = ParkingZone.query.filter(ParkingZone.name.ilike(f'%{search_query}%')).all()
    else:
        zones = ParkingZone.query.all()
    
    # Calculate availability and distance
    for zone in zones:
        zone.percent = round((zone.occupied_slots / zone.total_slots) * 100) if zone.total_slots > 0 else 100
        
        if lat is not None and lon is not None and zone.lat is not None and zone.lon is not None:
            dist = haversine(lat, lon, zone.lat, zone.lon)
            zone.distance_km = round(dist, 1)
        else:
            zone.distance_km = None
            
    # Sort by distance if location provided
    if lat is not None and lon is not None:
        zones.sort(key=lambda x: x.distance_km if x.distance_km is not None else float('inf'))
        
    return render_template('dashboard.html', zones=zones, page='home', search_query=search_query)

@app.route('/explore')
def explore():
    zones = ParkingZone.query.all()
    return render_template('explore.html', page='explore', zones=zones)

@app.route('/active')
def active():
    user_id = get_current_user_id()
    active_booking = Booking.query.filter_by(user_id=user_id, status='Active').order_by(Booking.start_time.desc()).first()
    
    if not active_booking:
        return render_template('active_empty.html', page='active')
    
    now = datetime.utcnow()
    duration = now - active_booking.start_time
    duration_minutes = int(duration.total_seconds() / 60)
    current_cost = round((duration.total_seconds() / 3600) * active_booking.zone.price_per_hour, 2)
    
    return render_template('active.html', 
                           booking=active_booking, 
                           duration_minutes=duration_minutes, 
                           current_cost=current_cost, 
                           page='active')

@app.route('/api/nearby-parking')
def api_nearby_parking():
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    
    zones = ParkingZone.query.all()
    results = []
    
    for zone in zones:
        dist = None
        if lat and lon:
            dist = haversine(lat, lon, zone.lat, zone.lon)
            
        results.append({
            'id': zone.id,
            'name': zone.name,
            'lat': zone.lat,
            'lon': zone.lon,
            'price': int(zone.price_per_hour),
            'slots': zone.total_slots - zone.occupied_slots,
            'rating': getattr(zone, 'rating', 4.5), # Default if not in model
            'distance': round(dist, 1) if dist else None
        })
        
    return {'zones': results}

@app.route('/history')
def history():
    user_id = get_current_user_id()
    bookings = Booking.query.filter_by(user_id=user_id, status='Completed').order_by(Booking.end_time.desc()).all()
    return render_template('history.html', bookings=bookings, page='history')

@app.route('/rate/<int:booking_id>', methods=['POST'])
def rate_booking(booking_id):
    # Just a flash message for demo since we haven't migrated DB for ratings
    # In a real app: rating = request.form.get('rating'); Save to DB.
    flash("Thanks for your feedback! ⭐⭐⭐⭐⭐", "success")
    return redirect(url_for('history'))

@app.route('/profile')
def profile():
    user_id = get_current_user_id()
    user = User.query.get(user_id)
    return render_template('profile.html', page='profile', user=user)

# --- Actions ---

@app.route('/book/<int:zone_id>')
def book_slot(zone_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    zone = ParkingZone.query.get_or_404(zone_id)
    return render_template('booking.html', zone=zone)

@app.route('/start_session/<int:zone_id>')
def start_session(zone_id):
    user_id = get_current_user_id()
    
    existing = Booking.query.filter_by(user_id=user_id, status='Active').first()
    if existing:
        flash("You already have an active session!", "error")
        return redirect(url_for('active'))

    zone = ParkingZone.query.get_or_404(zone_id)
    if zone.occupied_slots >= zone.total_slots:
        flash("Zone is full!", "error")
        return redirect(url_for('dashboard'))

    new_booking = Booking(user_id=user_id, zone_id=zone_id)
    zone.occupied_slots += 1
    
    db.session.add(new_booking)
    db.session.commit()
    
    return redirect(url_for('active'))

@app.route('/end_session/<int:booking_id>')
def end_session(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.status != 'Active':
        return redirect(url_for('history'))
        
    booking.end_time = datetime.utcnow()
    booking.status = 'Completed'
    
    duration = booking.end_time - booking.start_time
    hours = duration.total_seconds() / 3600
    cost = round(hours * booking.zone.price_per_hour, 2)
    booking.total_cost = max(cost, 2.00)
    
    booking.zone.occupied_slots = max(0, booking.zone.occupied_slots - 1)
    
    db.session.commit()
    return render_template('payment.html', booking=booking)

# --- Init ---
if __name__ == '__main__':
    with app.app_context():
        # Re-create DB if schema changed (Simulating migration by just creating all)
        # In prod, we'd use Flask-Migrate. Here we might need to recreate if we added columns.
        # But we can't easily drop tables without losing data. 
        # For this demo, let's assume the user can delete the file if it crashes, 
        # or we try to create_all which works if tables don't exist.
        db.create_all()
        
        if not ParkingZone.query.first():
            zones = [
                # Kochi
                ParkingZone(name="Lulu Mall Main Deck", location="Edappally, Kochi", total_slots=3000, occupied_slots=1200, price_per_hour=40.00, lat=10.0271, lon=76.3082),
                ParkingZone(name="Marine Drive Parking", location="Marine Drive, Kochi", total_slots=200, occupied_slots=150, price_per_hour=30.00, lat=9.9776, lon=76.2759),
                ParkingZone(name="Kochi Metro Station", location="Aluva, Kochi", total_slots=500, occupied_slots=120, price_per_hour=20.00, lat=10.1098, lon=76.3496),
                
                # Thiruvananthapuram (Trivandrum)
                ParkingZone(name="Mall of Travancore", location="Chackai, Trivandrum", total_slots=1500, occupied_slots=400, price_per_hour=40.00, lat=8.4907, lon=76.9312),
                ParkingZone(name="Thampanoor Central", location="Thampanoor, Trivandrum", total_slots=300, occupied_slots=280, price_per_hour=25.00, lat=8.4876, lon=76.9532),
                ParkingZone(name="Kovalam Beach Parking", location="Kovalam", total_slots=100, occupied_slots=80, price_per_hour=50.00, lat=8.3976, lon=76.9743),

                # Kozhikode (Calicut)
                ParkingZone(name="HiLITE Mall", location="Palazhi, Calicut", total_slots=2000, occupied_slots=1800, price_per_hour=35.00, lat=11.2464, lon=75.8341),
                ParkingZone(name="Kozhikode Beach", location="Beach Rd, Calicut", total_slots=150, occupied_slots=140, price_per_hour=20.00, lat=11.2618, lon=75.7664),

                # Thrissur
                ParkingZone(name="Sobha City Mall", location="Puzhakkal, Thrissur", total_slots=1200, occupied_slots=500, price_per_hour=30.00, lat=10.5562, lon=76.1824),
                ParkingZone(name="Vadakkumnathan South", location="Round South, Thrissur", total_slots=250, occupied_slots=200, price_per_hour=25.00, lat=10.5230, lon=76.2144),

                # Other Major Spots
                ParkingZone(name="Munnar Central", location="Munnar Town", total_slots=80, occupied_slots=60, price_per_hour=60.00, lat=10.0889, lon=77.0595),
                ParkingZone(name="Alappuzha Boat Jetty", location="Finishing Point, Alappuzha", total_slots=120, occupied_slots=100, price_per_hour=30.00, lat=9.4925, lon=76.3387)
            ]
            db.session.add_all(zones)
            db.session.commit()

    # Host='0.0.0.0' allows access from other devices on the network
    app.run(debug=True, host='0.0.0.0', port=5000)
