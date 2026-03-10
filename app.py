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

@app.route('/add_parking_zone', methods=['GET', 'POST'])
def add_parking_zone():
    if request.method == 'POST':
        name = request.form.get('name')
        location = request.form.get('location')
        total_slots = request.form.get('total_slots', type=int)
        price_per_hour = request.form.get('price_per_hour', type=float)
        lat = request.form.get('lat', type=float)
        lon = request.form.get('lon', type=float)

        zone = ParkingZone(
            name=name,
            location=location,
            total_slots=total_slots,
            price_per_hour=price_per_hour,
            lat=lat,
            lon=lon,
            status='pending'
        )
        db.session.add(zone)
        db.session.commit()
        flash('Parking zone submitted for approval!', 'info')
        return redirect(url_for('explore'))
    return render_template('add_parking_zone.html')

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

@app.route('/admin/pending_zones')
def admin_pending_zones():
    zones = ParkingZone.query.filter_by(status='pending').all()
    return render_template('admin_pending_zones.html', zones=zones)

@app.route('/admin/approve_zone/<int:zone_id>', methods=['POST'])
def approve_zone(zone_id):
    zone = ParkingZone.query.get_or_404(zone_id)
    zone.status = 'approved'
    db.session.commit()
    flash('Zone approved!', 'success')
    return redirect(url_for('admin_pending_zones'))

@app.route('/admin/reject_zone/<int:zone_id>', methods=['POST'])
def reject_zone(zone_id):
    zone = ParkingZone.query.get_or_404(zone_id)
    zone.status = 'rejected'
    db.session.commit()
    flash('Zone rejected.', 'error')
    return redirect(url_for('admin_pending_zones'))

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
            'location': zone.location,
            'lat': zone.lat,
            'lon': zone.lon,
            'price': int(zone.price_per_hour),
            'slots': zone.total_slots - zone.occupied_slots,
            'total_slots': zone.total_slots,
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

import random
import json

def generate_mock_parking_layout(zone_id, total_slots):
    """
    Generates a hierarchical geometric layout for the canvas renderer,
    simulating a realistic parking lot with roads, aisles, block groups, and arrows.
    """
    random.seed(zone_id)
    zones = []
    
    # Target slots per zone - smaller chunks for better visualization
    target_slots_per_zone = 120 
    num_zones = max(1, math.ceil(total_slots / target_slots_per_zone))
    zone_cols = max(1, math.ceil(math.sqrt(num_zones)))
    
    slots_allocated = 0
    zone_margin = 400 # Lots of space between zones
    
    for z in range(num_zones):
        slots_in_this_zone = target_slots_per_zone
        if z == num_zones - 1:
            slots_in_this_zone = total_slots - slots_allocated
            
        col = z % zone_cols
        row = z // zone_cols
        
        zone_name = chr(65 + (z % 26))
        if z >= 26:
            zone_name += str(z // 26)
            
        slots = []
        roads = []
        decorations = []
        
        # INCREASED Dimensions for a realistic looking lot and better clickability
        slot_width = 50
        slot_height = 100
        aisle_width = 200 # Wide driving lane between rows (Slots | Lane | Slots)
        vertical_road_width = 160 # Main road dividing blocks
        gap = 6
        block_size = 10 # Number of cars in a contiguous row before a break
        
        # We process aisles. 1 aisle = 2 rows facing it (top & bottom of aisle).
        slots_per_aisle = block_size * 4 
        req_aisles = max(1, math.ceil(slots_in_this_zone / slots_per_aisle))
        
        # Calculate actual Zone bounds based on geometric layout
        actual_zw = (block_size * 2 * (slot_width + gap)) + vertical_road_width + 100
        # Aisle, then Block (Top/Bot), then Aisle, then Block...
        actual_zh = (req_aisles * (slot_height * 2 + aisle_width)) + aisle_width + 100
        
        zx = zone_margin + col * (actual_zw + zone_margin)
        zy = zone_margin + row * (actual_zh + zone_margin)
        
        start_x = zx + 50
        # Offset down to give room for top entry road
        start_y = zy + 50 + aisle_width 
        
        s_count = 0
        available_count = 0
        
        # Central Vertical Road
        roads.append({
            "x": start_x + (block_size * (slot_width + gap)),
            "y": zy,
            "width": vertical_road_width,
            "height": actual_zh
        })
        
        # Entrance Decoration at the top of the vertical road
        decorations.append({"type": "text", "text": "ENTRANCE", "x": start_x + (block_size * (slot_width + gap)) + vertical_road_width/2, "y": zy + 40})
        # Exit Decoration at the bottom of the vertical road
        decorations.append({"type": "text", "text": "EXIT", "x": start_x + (block_size * (slot_width + gap)) + vertical_road_width/2, "y": zy + actual_zh - 40})
        
        for r in range(req_aisles):
            # The horizontal road / aisle
            lane_y = start_y + r * (slot_height * 2 + aisle_width) - aisle_width
            
            roads.append({
                "x": start_x - 50, # bleed road out left visually
                "y": lane_y,
                "width": actual_zw,
                "height": aisle_width
            })
            
            # Directional Arrows on Aisle
            # Right-bound arrow in bottom half of aisle
            decorations.append({"type": "arrow_right", "x": start_x + (block_size * (slot_width+gap)) / 2, "y": lane_y + aisle_width * 0.7})
            # Left-bound arrow in top half of aisle
            decorations.append({"type": "arrow_left", "x": start_x + actual_zw - 100 - (block_size * (slot_width+gap)) / 2, "y": lane_y + aisle_width * 0.3})
            
            # Slots below this lane (facing up into the lane)
            y_t = lane_y + aisle_width
            # Slots above the NEXT lane (facing down into the next lane)
            # which are immediately below y_t physically back-to-back
            y_b = y_t + slot_height
            
            # Left Block (Top and Bottom Rows)
            for c in range(block_size):
                sx = start_x + c * (slot_width + gap)
                # left-top
                if s_count < slots_in_this_zone:
                    status = random.choices(['available', 'occupied', 'disabled', 'reserved'], weights=[60, 30, 5, 5])[0]
                    if status == 'available': available_count += 1
                    slots.append({"id": f"Z{z}LRT{r}{c}", "name": f"{s_count+1}", "x": sx, "y": y_t, "width": slot_width, "height": slot_height, "status": status, "type": 'ev' if random.random() > 0.9 else 'standard'})
                    s_count += 1
                # left-bottom (back to back with left-top)
                if s_count < slots_in_this_zone:
                    status = random.choices(['available', 'occupied', 'disabled', 'reserved'], weights=[60, 30, 5, 5])[0]
                    if status == 'available': available_count += 1
                    slots.append({"id": f"Z{z}LRB{r}{c}", "name": f"{s_count+1}", "x": sx, "y": y_b, "width": slot_width, "height": slot_height, "status": status, "type": 'ev' if random.random() > 0.9 else 'standard'})
                    s_count += 1

            # Right Block (Top and Bottom Rows)
            right_start_x = start_x + (block_size * (slot_width + gap)) + vertical_road_width
            for c in range(block_size):
                sx = right_start_x + c * (slot_width + gap)
                # right-top
                if s_count < slots_in_this_zone:
                    status = random.choices(['available', 'occupied', 'disabled', 'reserved'], weights=[60, 30, 5, 5])[0]
                    if status == 'available': available_count += 1
                    slots.append({"id": f"Z{z}RRT{r}{c}", "name": f"{s_count+1}", "x": sx, "y": y_t, "width": slot_width, "height": slot_height, "status": status, "type": 'ev' if random.random() > 0.9 else 'standard'})
                    s_count += 1
                # right-bottom
                if s_count < slots_in_this_zone:
                    status = random.choices(['available', 'occupied', 'disabled', 'reserved'], weights=[60, 30, 5, 5])[0]
                    if status == 'available': available_count += 1
                    slots.append({"id": f"Z{z}RRB{r}{c}", "name": f"{s_count+1}", "x": sx, "y": y_b, "width": slot_width, "height": slot_height, "status": status, "type": 'ev' if random.random() > 0.9 else 'standard'})
                    s_count += 1
                    
        # Final bottom lane to enclose the last row
        final_lane_y = start_y + req_aisles * (slot_height * 2 + aisle_width) - aisle_width
        roads.append({
            "x": start_x - 50,
            "y": final_lane_y,
            "width": actual_zw,
            "height": aisle_width
        })
        decorations.append({"type": "arrow_right", "x": start_x + (block_size * (slot_width+gap)) / 2, "y": final_lane_y + aisle_width * 0.5})

        zones.append({
            "id": f"zone_{z}",
            "name": f"Zone {zone_name}",
            "x": zx,
            "y": zy,
            "width": actual_zw,
            "height": actual_zh,
            "available_slots": available_count,
            "total_slots": slots_in_this_zone,
            "slots": slots,
            "roads": roads,
            "decorations": decorations
        })
        
        slots_allocated += slots_in_this_zone

    max_w = max([z['x'] + z['width'] for z in zones]) if zones else 1000
    max_h = max([z['y'] + z['height'] for z in zones]) if zones else 1000
    
    facility_decorations = [
        {"type": "text", "text": "MAIN FACILITY ENTRANCE", "x": (max_w + zone_margin) / 2, "y": zone_margin / 2, "fontSize": 120, "color": "#fbbf24"},
        {"type": "text", "text": "↓ WAY IN ↓", "x": (max_w + zone_margin) / 2, "y": zone_margin / 2 + 100, "fontSize": 60, "color": "rgba(255,255,255,0.5)"}
    ]
    
    facility_roads = []
    # Main Central Arterial Road driving down the middle
    if num_zones > 0:
        facility_roads.append({
            "x": zone_margin + (max_w - zone_margin) / 2 - 200,
            "y": 0,
            "width": 400, # Very wide avenue
            "height": max_h + zone_margin
        })
        # Horizontal connecting roads forming the grid between rows of zones
        for row in range(math.ceil(num_zones / zone_cols)):
            zy = zone_margin + row * (actual_zh + zone_margin)
            facility_roads.append({
                "x": zone_margin,
                "y": zy - 200, # Road right above the zone
                "width": max_w - zone_margin,
                "height": 200
            })
                
    return {
        "world": {"width": max_w + zone_margin, "height": max_h + zone_margin},
        "zones": zones,
        "facility_decorations": facility_decorations,
        "facility_roads": facility_roads
    }

@app.route('/book/<int:zone_id>')
def book_slot(zone_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    zone = ParkingZone.query.get_or_404(zone_id)
    layout_data = generate_mock_parking_layout(zone.id, zone.total_slots)
    
    return render_template('booking.html', zone=zone, layout_json=json.dumps(layout_data))

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
