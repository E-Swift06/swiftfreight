from flask_wtf.csrf import CSRFProtect, generate_csrf, CSRFError
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from zoneinfo import ZoneInfo
import psycopg
import random
import string
import os
import io
import qrcode

from reportlab.graphics.barcode import code128
from reportlab.lib.units import mm
from reportlab.platypus import Image, SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set.")
    return psycopg.connect(DATABASE_URL)


def malaysia_now_str():
    return datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).strftime("%Y-%m-%d %H:%M:%S")


print("RUNNING FILE:", os.path.abspath(__file__))
print("RUNNING FOLDER:", os.getcwd())

app.config["SECRET_KEY"] = "e5efa50ab6585163beb3611654a0f57e461e0394a3c4c2ce5f2e124ade3935e5"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False
app.config["WTF_CSRF_TIME_LIMIT"] = 3600
csrf = CSRFProtect(app)

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ------------------------------
# Database helper functions
# ------------------------------
def init_db():
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS bookings (
                    id SERIAL PRIMARY KEY,
                    sender_name TEXT NOT NULL,
                    sender_phone TEXT NOT NULL,
                    recipient_name TEXT NOT NULL,
                    recipient_phone TEXT NOT NULL,
                    address TEXT NOT NULL,
                    weight DOUBLE PRECISION NOT NULL,
                    dimensions TEXT NOT NULL,
                    service_type TEXT NOT NULL,
                    tracking_number TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'Shipment Created',
                    current_location TEXT DEFAULT 'Pending Pickup',
                    updated_at TEXT DEFAULT '',
                    email TEXT
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS tracking_logs (
                    id SERIAL PRIMARY KEY,
                    tracking_number TEXT NOT NULL,
                    status TEXT NOT NULL,
                    location TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL
                )
            """)


def upgrade_db():
    pass


def create_default_admin():
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id FROM admins WHERE username = %s", ("admin",))
            existing = c.fetchone()

            if not existing:
                hashed_password = generate_password_hash("1234")
                c.execute(
                    "INSERT INTO admins (username, password_hash) VALUES (%s, %s)",
                    ("admin", hashed_password)
                )


def add_tracking_log(tracking_number, status, location):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO tracking_logs (tracking_number, status, location, updated_at)
                VALUES (%s, %s, %s, %s)
            """, (
                tracking_number,
                status,
                location,
                malaysia_now_str()
            ))


def save_booking(
    sender_name,
    sender_phone,
    recipient_name,
    recipient_phone,
    address,
    weight,
    dimensions,
    service_type,
    tracking_number,
    user_email=None
):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO bookings (
                    sender_name,
                    sender_phone,
                    recipient_name,
                    recipient_phone,
                    address,
                    weight,
                    dimensions,
                    service_type,
                    tracking_number,
                    status,
                    current_location,
                    updated_at,
                    email
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                sender_name,
                sender_phone,
                recipient_name,
                recipient_phone,
                address,
                weight,
                dimensions,
                service_type,
                tracking_number,
                "Shipment Created",
                "Pending Pickup",
                malaysia_now_str(),
                user_email
            ))

    add_tracking_log(tracking_number, "Shipment Created", "Pending Pickup")


def generate_tracking_number():
    prefix = "SF"
    body = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
    return f"{prefix}-{body}"


# ------------------------------
# Read / write helper functions
# ------------------------------
def read_text_file(filename, default_value):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return default_value


def write_text_file(filename, value):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(value)


# Initialize database
init_db()
upgrade_db()
create_default_admin()


# ------------------------------
# HOME
# ------------------------------
@app.route("/")
def home():
    title = read_text_file("settings.txt", "MY SHIPPING COMPANY")
    hero_title = read_text_file("hero_title.txt", "Fast, Secure & Reliable Shipping")
    hero_text = read_text_file(
        "hero_text.txt",
        "Air freight, sea freight, express delivery and international logistics solutions for your business and personal needs."
    )
    logo = read_text_file("logo.txt", "")
    banner = read_text_file("banner.txt", "")
    phone = read_text_file("phone.txt", "")
    email = read_text_file("email.txt", "support@swiftfreight.com")
    location = read_text_file("location.txt", "Miri, Malaysia")
    whatsapp = read_text_file("whatsapp.txt", "")

    if logo == "":
        logo = None
    if banner == "":
        banner = None

    return render_template(
        "index.html",
        title=title,
        hero_title=hero_title,
        hero_text=hero_text,
        logo=logo,
        banner=banner,
        phone=phone,
        email=email,
        location=location,
        whatsapp=whatsapp
    )


# ------------------------------
# TRACK
# ------------------------------
@app.route("/track", methods=["GET", "POST"])
def track():
    title = read_text_file("settings.txt", "MY SHIPPING COMPANY")
    logo = read_text_file("logo.txt", "")
    phone = read_text_file("phone.txt", "")
    email = read_text_file("email.txt", "support@swiftfreight.com")
    location = read_text_file("location.txt", "Miri, Malaysia")
    whatsapp = read_text_file("whatsapp.txt", "")

    if logo == "":
        logo = None

    if request.method == "POST":
        tracking_number = request.form.get("tracking_number", "").strip()

        if not tracking_number:
            flash("Please enter a tracking number.")
            return redirect(url_for("track"))

        with get_conn() as conn:
            with conn.cursor() as c:
                c.execute("""
                    SELECT sender_name, sender_phone, recipient_name, recipient_phone,
                           address, weight, dimensions, service_type, tracking_number,
                           status, current_location, updated_at
                    FROM bookings
                    WHERE tracking_number = %s
                """, (tracking_number,))
                booking = c.fetchone()

                c.execute("""
                    SELECT status, location, updated_at
                    FROM tracking_logs
                    WHERE tracking_number = %s
                    ORDER BY id DESC
                """, (tracking_number,))
                logs = c.fetchall()

        if booking:
            booking_info = {
                "sender_name": booking[0],
                "sender_phone": booking[1],
                "recipient_name": booking[2],
                "recipient_phone": booking[3],
                "address": booking[4],
                "weight": booking[5],
                "dimensions": booking[6],
                "service_type": booking[7],
                "tracking_number": booking[8],
                "status": booking[9],
                "current_location": booking[10],
                "updated_at": booking[11]
            }

            return render_template(
                "track_result.html",
                booking=booking_info,
                logs=logs,
                title=title,
                logo=logo,
                phone=phone,
                email=email,
                location=location,
                whatsapp=whatsapp
            )

        flash("Tracking number not found.")
        return redirect(url_for("track"))

    return render_template(
        "track.html",
        title=title,
        logo=logo,
        phone=phone,
        email=email,
        location=location,
        whatsapp=whatsapp
    )


# ------------------------------
# BOOKING
# ------------------------------
@app.route("/booking", methods=["GET", "POST"])
def booking():
    title = read_text_file("settings.txt", "MY SHIPPING COMPANY")
    logo = read_text_file("logo.txt", "")
    phone = read_text_file("phone.txt", "")
    email = read_text_file("email.txt", "support@swiftfreight.com")
    location = read_text_file("location.txt", "Miri, Malaysia")
    whatsapp = read_text_file("whatsapp.txt", "")

    if logo == "":
        logo = None

    if request.method == "POST":
        if not session.get("user_logged_in") and not session.get("logged_in"):
            flash("Please log in first before creating a shipment.")
            return redirect(url_for("user_login"))

    if session.get("user_logged_in"):
        user_email = session.get("user_email", "").strip().lower()
    else:
        user_email = None

        sender_name = request.form.get("sender_name", "").strip()
        sender_phone = request.form.get("sender_phone", "").strip()
        recipient_name = request.form.get("recipient_name", "").strip()
        recipient_phone = request.form.get("recipient_phone", "").strip()
        address = request.form.get("address", "").strip()
        weight = request.form.get("weight", "").strip()
        dimensions = request.form.get("dimensions", "").strip()
        service_type = request.form.get("service_type", "").strip()

        if not all([sender_name, sender_phone, recipient_name, recipient_phone, address, weight, dimensions, service_type]):
            flash("All fields are required.")
            return redirect(url_for("booking"))

        try:
            weight_value = float(weight)
        except ValueError:
            flash("Weight must be a number.")
            return redirect(url_for("booking"))

        tracking_number = generate_tracking_number()

        save_booking(
            sender_name,
            sender_phone,
            recipient_name,
            recipient_phone,
            address,
            weight_value,
            dimensions,
            service_type,
            tracking_number,
            user_email
        )

        flash(f"Booking created successfully for {user_email}. Tracking Number: {tracking_number}")
        return redirect(url_for("booking"))

    return render_template(
        "booking.html",
        title=title,
        logo=logo,
        phone=phone,
        email=email,
        location=location,
        whatsapp=whatsapp
    )


# ------------------------------
# ADMIN LOGIN
# ------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        with get_conn() as conn:
            with conn.cursor() as c:
                c.execute("SELECT password_hash FROM admins WHERE username = %s", (username,))
                row = c.fetchone()

        if row and check_password_hash(row[0], password):
            session.clear()
            session["logged_in"] = True
            session["admin_username"] = username
            return redirect(url_for("admin"))

        error = "Wrong login details."

    return f"""
    <html>
    <head>
        <title>Admin Login</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: #f5f5f5;
                margin: 0;
                padding: 40px;
            }}
            .box {{
                max-width: 420px;
                margin: auto;
                background: white;
                padding: 30px;
                border-radius: 12px;
                box-shadow: 0 4px 14px rgba(0,0,0,0.08);
            }}
            h2 {{
                margin-top: 0;
            }}
            label {{
                display: block;
                font-weight: bold;
                margin-bottom: 6px;
            }}
            input {{
                width: 100%;
                padding: 12px;
                margin-bottom: 16px;
                border: 1px solid #ccc;
                border-radius: 8px;
                box-sizing: border-box;
            }}
            button {{
                background: #d40511;
                color: white;
                border: none;
                padding: 12px 20px;
                border-radius: 8px;
                font-weight: bold;
                cursor: pointer;
            }}
            .error {{
                color: red;
                margin-top: 14px;
            }}
        </style>
    </head>
    <body>
        <div class="box">
            <h2>Admin Login</h2>
            <form method="POST">
                <input type="hidden" name="csrf_token" value="{generate_csrf()}">
                <label>Username</label>
                <input name="username">
                <label>Password</label>
                <input name="password" type="password">
                <button type="submit">Login</button>
            </form>
            <p class="error">{error}</p>
        </div>
    </body>
    </html>
    """


# ------------------------------
# ADMIN LOGOUT
# ------------------------------
@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    session.pop("admin_username", None)
    return redirect(url_for("login"))


# ------------------------------
# ADMIN
# ------------------------------
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    message = ""

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        hero_title = request.form.get("hero_title", "").strip()
        hero_text = request.form.get("hero_text", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        location = request.form.get("location", "").strip()
        whatsapp = request.form.get("whatsapp", "").strip()

        write_text_file("settings.txt", title)
        write_text_file("hero_title.txt", hero_title)
        write_text_file("hero_text.txt", hero_text)
        write_text_file("phone.txt", phone)
        write_text_file("email.txt", email)
        write_text_file("location.txt", location)
        write_text_file("whatsapp.txt", whatsapp)

        logo_file = request.files.get("logo")
        if logo_file and logo_file.filename:
            logo_path = os.path.join(app.config["UPLOAD_FOLDER"], logo_file.filename)
            logo_file.save(logo_path)
            write_text_file("logo.txt", logo_file.filename)

        banner_file = request.files.get("banner")
        if banner_file and banner_file.filename:
            banner_path = os.path.join(app.config["UPLOAD_FOLDER"], banner_file.filename)
            banner_file.save(banner_path)
            write_text_file("banner.txt", banner_file.filename)

        message = "Website updated successfully."

    title = read_text_file("settings.txt", "MY SHIPPING COMPANY")
    hero_title = read_text_file("hero_title.txt", "Fast, Secure & Reliable Shipping")
    hero_text = read_text_file(
        "hero_text.txt",
        "Air freight, sea freight, express delivery and international logistics solutions for your business and personal needs."
    )
    phone = read_text_file("phone.txt", "")
    email = read_text_file("email.txt", "support@swiftfreight.com")
    location = read_text_file("location.txt", "Miri, Malaysia")
    whatsapp = read_text_file("whatsapp.txt", "")
    logo = read_text_file("logo.txt", "")
    banner = read_text_file("banner.txt", "")

    logo_preview = f"/static/uploads/{logo}" if logo else ""
    banner_preview = f"/static/uploads/{banner}" if banner else ""

    return f"""
    <html>
    <head>
        <title>Admin Dashboard</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: linear-gradient(180deg, #f7f8fa 0%, #eef1f5 100%);
                margin: 0;
                color: #222;
            }}
            .topbar {{
                background: linear-gradient(135deg, #111, #2a2a2a);
                color: white;
                padding: 18px 28px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                box-shadow: 0 4px 16px rgba(0,0,0,0.12);
                position: sticky;
                top: 0;
                z-index: 50;
            }}
            .topbar h1 {{
                margin: 0;
                font-size: 24px;
                letter-spacing: 0.8px;
            }}
            .topbar-links {{
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
            }}
            .topbar-links a {{
                color: white;
                text-decoration: none;
                font-weight: bold;
                font-size: 14px;
                background: rgba(255,255,255,0.08);
                padding: 10px 14px;
                border-radius: 10px;
                transition: all 0.2s ease;
            }}
            .topbar-links a:hover {{
                background: rgba(255,255,255,0.18);
                transform: translateY(-1px);
            }}
            .wrapper {{
                max-width: 1280px;
                margin: 36px auto;
                padding: 0 20px;
            }}
            .message {{
                background: #ecfdf3;
                border: 1px solid #b7ebc6;
                color: #137333;
                padding: 14px 16px;
                border-radius: 14px;
                margin-bottom: 24px;
                font-weight: bold;
                box-shadow: 0 4px 12px rgba(19,115,51,0.08);
            }}
            .admin-grid {{
                display: grid;
                grid-template-columns: 1.65fr 0.95fr;
                gap: 24px;
                align-items: start;
            }}
            .card {{
                background: white;
                border-radius: 22px;
                box-shadow: 0 12px 32px rgba(0,0,0,0.07);
                overflow: hidden;
                border: 1px solid #ececec;
            }}
            .card-header {{
                padding: 20px 24px;
                border-bottom: 1px solid #eee;
                background: linear-gradient(to right, #ffffff, #fafafa);
            }}
            .card-header h2 {{
                margin: 0;
                font-size: 22px;
                color: #111;
            }}
            .card-body {{
                padding: 26px;
            }}
            .section-title {{
                font-size: 12px;
                letter-spacing: 2px;
                color: #d40511;
                font-weight: 700;
                margin: 6px 0 16px;
                text-transform: uppercase;
            }}
            label {{
                display: block;
                font-weight: bold;
                margin-bottom: 7px;
                margin-top: 14px;
                color: #333;
            }}
            input, textarea {{
                width: 100%;
                box-sizing: border-box;
                border: 1px solid #dcdcdc;
                border-radius: 14px;
                padding: 13px 14px;
                font-size: 15px;
                background: #fafafa;
                transition: border 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
            }}
            textarea {{
                resize: vertical;
                min-height: 120px;
            }}
            input:focus, textarea:focus {{
                outline: none;
                border-color: #d40511;
                background: #fff;
                box-shadow: 0 0 0 4px rgba(212, 5, 17, 0.08);
            }}
            .two-col {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 18px;
            }}
            .upload-box {{
                border: 1px dashed #cfcfcf;
                border-radius: 16px;
                padding: 18px;
                background: linear-gradient(180deg, #fbfbfb 0%, #f7f7f7 100%);
                margin-top: 8px;
            }}
            .preview-link {{
                display: inline-block;
                margin-top: 12px;
                font-size: 14px;
                color: #d40511;
                text-decoration: none;
                font-weight: bold;
            }}
            .preview-link:hover {{
                text-decoration: underline;
            }}
            .save-btn {{
                background: linear-gradient(135deg, #d40511, #b30000);
                color: white;
                border: none;
                padding: 14px 24px;
                border-radius: 14px;
                font-weight: bold;
                font-size: 15px;
                cursor: pointer;
                margin-top: 26px;
                box-shadow: 0 10px 22px rgba(212, 5, 17, 0.18);
                transition: all 0.22s ease;
            }}
            .save-btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 14px 28px rgba(212, 5, 17, 0.24);
            }}
            .info-list {{
                display: grid;
                gap: 14px;
            }}
            .info-item {{
                background: linear-gradient(180deg, #fcfcfc 0%, #f8f8f8 100%);
                border: 1px solid #eeeeee;
                border-radius: 16px;
                padding: 16px 18px;
            }}
            .info-item h3 {{
                margin: 0 0 6px;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 1.5px;
                color: #888;
            }}
            .info-item p {{
                margin: 0;
                font-size: 15px;
                line-height: 1.55;
                word-break: break-word;
                color: #111;
                font-weight: 600;
            }}
            .quick-actions {{
                display: grid;
                gap: 12px;
                margin-top: 20px;
            }}
            .quick-actions a {{
                display: block;
                background: linear-gradient(135deg, #111, #222);
                color: white;
                text-decoration: none;
                padding: 13px 14px;
                border-radius: 14px;
                font-weight: bold;
                text-align: center;
                transition: all 0.2s ease;
            }}
            .quick-actions a:hover {{
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(0,0,0,0.12);
            }}
            .quick-actions a.red {{
                background: linear-gradient(135deg, #d40511, #b30000);
            }}
            @media (max-width: 900px) {{
                .admin-grid {{
                    grid-template-columns: 1fr;
                }}
                .two-col {{
                    grid-template-columns: 1fr;
                }}
                .topbar {{
                    flex-direction: column;
                    align-items: flex-start;
                    gap: 12px;
                }}
                .topbar-links {{
                    width: 100%;
                }}
                .topbar-links a {{
                    font-size: 13px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="topbar">
            <h1>SwiftFreight Admin</h1>
            <div class="topbar-links">
                <a href="/">View Website</a>
                <a href="/booking">Booking Page</a>
                <a href="/track">Tracking Page</a>
                <a href="/admin/bookings">Bookings</a>
                <a href="/admin/shipment-update">Shipment Update</a>
                <a href="/admin/restore-booking">Restore Booking</a>
                <a href="/logout">Logout</a>
            </div>
        </div>

        <div class="wrapper">
            {f'<div class="message">{message}</div>' if message else ''}

            <div class="admin-grid">
                <div class="card">
                    <div class="card-header">
                        <h2>Website Settings</h2>
                    </div>
                    <div class="card-body">
                        <form method="POST" enctype="multipart/form-data">
                            <input type="hidden" name="csrf_token" value="{generate_csrf()}">

                            <div class="section-title">Branding</div>

                            <label>Website Title</label>
                            <input name="title" value="{title}">

                            <label>Homepage Heading</label>
                            <input name="hero_title" value="{hero_title}">

                            <label>Homepage Paragraph</label>
                            <textarea name="hero_text" rows="5">{hero_text}</textarea>

                            <div class="section-title">Contact Details</div>

                            <div class="two-col">
                                <div>
                                    <label>Phone Number</label>
                                    <input name="phone" value="{phone}">
                                </div>
                                <div>
                                    <label>Email Address</label>
                                    <input name="email" value="{email}">
                                </div>
                            </div>

                            <label>Location</label>
                            <input name="location" value="{location}">

                            <label>WhatsApp Number</label>
                            <input name="whatsapp" value="{whatsapp}">

                            <div class="section-title">Images</div>

                            <label>Upload Logo</label>
                            <div class="upload-box">
                                <input type="file" name="logo">
                                {f'<a class="preview-link" href="{logo_preview}" target="_blank">View current logo</a>' if logo_preview else '<div style="font-size:14px;color:#888;margin-top:10px;">No logo uploaded yet</div>'}
                            </div>

                            <label>Upload Banner</label>
                            <div class="upload-box">
                                <input type="file" name="banner">
                                {f'<a class="preview-link" href="{banner_preview}" target="_blank">View current banner</a>' if banner_preview else '<div style="font-size:14px;color:#888;margin-top:10px;">No banner uploaded yet</div>'}
                            </div>

                            <button type="submit" class="save-btn">Save Changes</button>
                        </form>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <h2>Current Website Info</h2>
                    </div>
                    <div class="card-body">
                        <div class="info-list">
                            <div class="info-item">
                                <h3>Title</h3>
                                <p>{title}</p>
                            </div>

                            <div class="info-item">
                                <h3>Homepage Heading</h3>
                                <p>{hero_title}</p>
                            </div>

                            <div class="info-item">
                                <h3>Phone</h3>
                                <p>{phone}</p>
                            </div>

                            <div class="info-item">
                                <h3>Email</h3>
                                <p>{email}</p>
                            </div>

                            <div class="info-item">
                                <h3>Location</h3>
                                <p>{location}</p>
                            </div>

                            <div class="info-item">
                                <h3>WhatsApp</h3>
                                <p>{whatsapp}</p>
                            </div>
                        </div>

                        <div class="quick-actions">
                            <a href="/" target="_blank">Open Website</a>
                            <a href="/admin/shipment-update" class="red">Manage Shipment Status</a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """


# ------------------------------
# SHIPMENT UPDATE
# ------------------------------
@app.route("/admin/shipment-update", methods=["GET", "POST"])
def shipment_update():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    message = ""
    shipment = None
    tracking_number_value = ""

    if request.method == "GET":
        tracking_number_value = request.args.get("tracking_number", "").strip()

        if tracking_number_value:
            with get_conn() as conn:
                with conn.cursor() as c:
                    c.execute("""
                        SELECT id, tracking_number, status, current_location, updated_at
                        FROM bookings
                        WHERE tracking_number = %s
                    """, (tracking_number_value,))
                    shipment = c.fetchone()

            if not shipment:
                message = "Shipment not found."

    if request.method == "POST":
        action = request.form.get("action")

        if action == "search":
            tracking_number_value = request.form.get("tracking_number", "").strip()

            with get_conn() as conn:
                with conn.cursor() as c:
                    c.execute("""
                        SELECT id, tracking_number, status, current_location, updated_at
                        FROM bookings
                        WHERE tracking_number = %s
                    """, (tracking_number_value,))
                    shipment = c.fetchone()

            if not shipment:
                message = "Shipment not found."

        elif action == "update":
            tracking_number_value = request.form.get("tracking_number", "").strip()
            status = request.form.get("status", "").strip()
            current_location = request.form.get("current_location", "").strip()
            updated_at = malaysia_now_str()

            with get_conn() as conn:
                with conn.cursor() as c:
                    c.execute("""
                        UPDATE bookings
                        SET status = %s, current_location = %s, updated_at = %s
                        WHERE tracking_number = %s
                    """, (status, current_location, updated_at, tracking_number_value))

                    c.execute("""
                        SELECT id, tracking_number, status, current_location, updated_at
                        FROM bookings
                        WHERE tracking_number = %s
                    """, (tracking_number_value,))
                    shipment = c.fetchone()

            add_tracking_log(tracking_number_value, status, current_location)
            message = "Shipment updated successfully."

    return render_template(
        "shipment_update.html",
        shipment=shipment,
        message=message,
        tracking_number_value=tracking_number_value
    )


# ------------------------------
# BOOKINGS LIST (WITH SEARCH)
# ------------------------------
@app.route("/admin/bookings")
def admin_bookings():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()

    query = """
        SELECT id, tracking_number, sender_name, recipient_name, service_type,
               status, current_location, updated_at
        FROM bookings
        WHERE 1=1
    """
    params = []

    if search:
        query += """
            AND (
                tracking_number ILIKE %s
                OR sender_name ILIKE %s
                OR recipient_name ILIKE %s
            )
        """
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    if status:
        query += " AND status = %s"
        params.append(status)

    query += " ORDER BY id DESC"

    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(query, params)
            bookings = c.fetchall()

    return render_template(
        "bookings_list.html",
        bookings=bookings,
        search=search,
        status=status
    )


# ------------------------------
# INVOICE PAGE
# ------------------------------
@app.route("/invoice/<tracking_number>")
def invoice(tracking_number):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT sender_name, sender_phone, recipient_name, recipient_phone,
                       address, weight, dimensions, service_type, tracking_number,
                       status, current_location, updated_at
                FROM bookings
                WHERE tracking_number = %s
            """, (tracking_number,))
            booking = c.fetchone()

    if not booking:
        return "Invoice not found", 404

    booking_info = {
        "sender_name": booking[0],
        "sender_phone": booking[1],
        "recipient_name": booking[2],
        "recipient_phone": booking[3],
        "address": booking[4],
        "weight": booking[5],
        "dimensions": booking[6],
        "service_type": booking[7],
        "tracking_number": booking[8],
        "status": booking[9],
        "current_location": booking[10],
        "updated_at": booking[11]
    }

    company_name = read_text_file("settings.txt", "MY SHIPPING COMPANY")
    company_phone = read_text_file("phone.txt", "")
    company_email = read_text_file("email.txt", "support@swiftfreight.com")
    company_location = read_text_file("location.txt", "Miri, Malaysia")

    return render_template(
        "invoice.html",
        booking=booking_info,
        company_name=company_name,
        company_phone=company_phone,
        company_email=company_email,
        company_location=company_location
    )


# ------------------------------
# AWB PAGE
# ------------------------------
@app.route("/awb/<tracking_number>")
def awb(tracking_number):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT sender_name, sender_phone, recipient_name, recipient_phone,
                       address, weight, dimensions, service_type, tracking_number,
                       status, current_location, updated_at
                FROM bookings
                WHERE tracking_number = %s
            """, (tracking_number,))
            booking = c.fetchone()

    if not booking:
        return "AWB not found", 404

    booking_info = {
        "sender_name": booking[0],
        "sender_phone": booking[1],
        "recipient_name": booking[2],
        "recipient_phone": booking[3],
        "address": booking[4],
        "weight": booking[5],
        "dimensions": booking[6],
        "service_type": booking[7],
        "tracking_number": booking[8],
        "status": booking[9],
        "current_location": booking[10],
        "updated_at": booking[11]
    }

    company_name = read_text_file("settings.txt", "MY SHIPPING COMPANY")
    company_phone = read_text_file("phone.txt", "")
    company_email = read_text_file("email.txt", "support@swiftfreight.com")
    company_location = read_text_file("location.txt", "Miri, Malaysia")

    return render_template(
        "awb.html",
        booking=booking_info,
        company_name=company_name,
        company_phone=company_phone,
        company_email=company_email,
        company_location=company_location
    )


# ------------------------------
# INVOICE PDF DOWNLOAD
# ------------------------------
@app.route("/invoice-pdf/<tracking_number>")
def invoice_pdf(tracking_number):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Title"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#d40511"),
        spaceAfter=14
    )
    heading_style = ParagraphStyle(
        "Heading",
        parent=styles["Heading3"],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#d40511"),
        spaceAfter=8
    )
    normal_style = styles["Normal"]

    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT sender_name, sender_phone, recipient_name, recipient_phone,
                       address, weight, dimensions, service_type, tracking_number,
                       status, current_location, updated_at
                FROM bookings
                WHERE tracking_number = %s
            """, (tracking_number,))
            booking = c.fetchone()

    if not booking:
        return "Invoice not found", 404

    company_name = read_text_file("settings.txt", "MY SHIPPING COMPANY")
    company_phone = read_text_file("phone.txt", "")
    company_email = read_text_file("email.txt", "support@swiftfreight.com")
    company_location = read_text_file("location.txt", "Miri, Malaysia")

    booking_info = {
        "sender_name": booking[0],
        "sender_phone": booking[1],
        "recipient_name": booking[2],
        "recipient_phone": booking[3],
        "address": booking[4],
        "weight": booking[5],
        "dimensions": booking[6],
        "service_type": booking[7],
        "tracking_number": booking[8],
        "status": booking[9],
        "current_location": booking[10],
        "updated_at": booking[11] if booking[11] else "Not available"
    }

    story = []
    story.append(Paragraph("COMMERCIAL INVOICE", title_style))
    story.append(Paragraph(f"<b>{company_name}</b>", normal_style))
    story.append(Paragraph(company_location, normal_style))
    story.append(Paragraph(f"Phone: {company_phone}", normal_style))
    story.append(Paragraph(f"Email: {company_email}", normal_style))
    story.append(Spacer(1, 18))

    invoice_info = [
        ["Invoice No.", f"INV-{booking_info['tracking_number']}"],
        ["Tracking No.", booking_info["tracking_number"]],
        ["Date", booking_info["updated_at"]],
        ["Status", booking_info["status"]],
    ]

    info_table = Table(invoice_info, colWidths=[120, 320])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f3f3")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 20))

    story.append(Paragraph("SHIPPER / SENDER", heading_style))
    sender_table = Table([
        ["Name", booking_info["sender_name"]],
        ["Phone", booking_info["sender_phone"]],
    ], colWidths=[100, 340])
    sender_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#fafafa")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(sender_table)
    story.append(Spacer(1, 16))

    story.append(Paragraph("CONSIGNEE / RECIPIENT", heading_style))
    recipient_table = Table([
        ["Name", Paragraph(booking_info["recipient_name"], normal_style)],
        ["Phone", Paragraph(booking_info["recipient_phone"], normal_style)],
        ["Address", Paragraph(booking_info["address"], normal_style)],
    ], colWidths=[100, 340])
    recipient_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#fafafa")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(recipient_table)
    story.append(Spacer(1, 20))

    shipment_table = Table([
        ["Description", "Service Type", "Weight", "Dimensions"],
        [
            Paragraph("General Cargo / Shipment", normal_style),
            Paragraph(booking_info["service_type"], normal_style),
            Paragraph(f"{booking_info['weight']} kg", normal_style),
            Paragraph(booking_info["dimensions"], normal_style)
        ],
    ], colWidths=[150, 110, 80, 130])

    shipment_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d40511")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(shipment_table)
    story.append(Spacer(1, 20))

    story.append(Paragraph("CURRENT SHIPMENT LOCATION", heading_style))
    location_table = Table([
        ["Location", booking_info["current_location"] if booking_info["current_location"] else "Pending Pickup"]
    ], colWidths=[100, 340])
    location_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#fafafa")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(location_table)
    story.append(Spacer(1, 24))

    story.append(Paragraph(
        "This is a system-generated commercial invoice for shipment reference purposes.",
        normal_style
    ))

    doc.build(story)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"invoice_{tracking_number}.pdf",
        mimetype="application/pdf"
    )


# ------------------------------
# AWB PDF DOWNLOAD
# ------------------------------
@app.route("/awb-pdf/<tracking_number>")
def awb_pdf(tracking_number):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        textColor=colors.HexColor("#d40511"),
        fontSize=20,
        spaceAfter=12
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading3"],
        textColor=colors.HexColor("#d40511"),
        fontSize=11,
        spaceAfter=8
    )
    normal = styles["Normal"]

    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT sender_name, sender_phone, recipient_name, recipient_phone,
                       address, weight, dimensions, service_type, tracking_number,
                       status, current_location, updated_at
                FROM bookings
                WHERE tracking_number = %s
            """, (tracking_number,))
            booking = c.fetchone()

    if not booking:
        return "AWB not found", 404

    company_name = read_text_file("settings.txt", "SWIFTFREIGHT")
    company_phone = read_text_file("phone.txt", "")
    company_email = read_text_file("email.txt", "support@swiftfreight.com")
    company_location = read_text_file("location.txt", "Miri, Malaysia")

    story = []
    story.append(Paragraph("AIR WAYBILL", title_style))
    story.append(Paragraph(f"<b>{company_name}</b>", normal))
    story.append(Paragraph(company_location, normal))
    story.append(Paragraph(f"{company_phone} | {company_email}", normal))
    story.append(Spacer(1, 16))

    tracking_table = Table([
        ["Tracking Number", booking[8]],
        ["Status", booking[9]],
        ["Updated", booking[11] if booking[11] else "Not available"]
    ], colWidths=[150, 290])

    tracking_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f3f3")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))

    story.append(tracking_table)
    story.append(Spacer(1, 18))

    story.append(Paragraph("BARCODE", section_style))
    barcode = code128.Code128(booking[8], barHeight=18 * mm, barWidth=0.45)
    story.append(barcode)
    story.append(Spacer(1, 18))

    story.append(Paragraph("QR CODE", section_style))

    qr_data = f"""
Tracking Number: {booking[8]}
Sender: {booking[0]}
Recipient: {booking[2]}
Status: {booking[9]}
Location: {booking[10] if booking[10] else "Pending Pickup"}
Service: {booking[7]}
Weight: {booking[5]} kg
""".strip()

    qr = qrcode.make(qr_data)
    qr_path = f"static/uploads/qr_{booking[8]}.png"
    qr.save(qr_path)

    qr_img = Image(qr_path, width=100, height=100)
    story.append(qr_img)
    story.append(Spacer(1, 18))

    story.append(Paragraph("SHIPPER", section_style))
    sender_table = Table([
        ["Name", Paragraph(booking[0], normal)],
        ["Phone", Paragraph(booking[1], normal)],
    ], colWidths=[120, 320])

    sender_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#fafafa")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))

    story.append(sender_table)
    story.append(Spacer(1, 14))

    story.append(Paragraph("CONSIGNEE", section_style))
    receiver_table = Table([
        ["Name", Paragraph(booking[2], normal)],
        ["Phone", Paragraph(booking[3], normal)],
        ["Address", Paragraph(booking[4], normal)],
    ], colWidths=[120, 320])

    receiver_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#fafafa")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))

    story.append(receiver_table)
    story.append(Spacer(1, 18))

    story.append(Paragraph("SHIPMENT DETAILS", section_style))

    shipment_table = Table([
        ["Service", "Weight", "Dimensions"],
        [booking[7], f"{booking[5]} kg", booking[6]],
    ], colWidths=[150, 100, 190])

    shipment_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d40511")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))

    story.append(shipment_table)
    story.append(Spacer(1, 20))

    story.append(Paragraph("CURRENT LOCATION", section_style))
    location_table = Table([
        ["Location", booking[10] if booking[10] else "Pending Pickup"]
    ], colWidths=[120, 320])

    location_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#fafafa")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))

    story.append(location_table)
    story.append(Spacer(1, 24))

    story.append(Paragraph(
        "This Air Waybill serves as an official shipment document.",
        normal
    ))

    doc.build(story)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"awb_{tracking_number}.pdf",
        mimetype="application/pdf"
    )


# ------------------------------
# USER SIGNUP
# ------------------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    error = ""

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not full_name or not email or not password:
            error = "All fields are required."
        else:
            with get_conn() as conn:
                with conn.cursor() as c:
                    c.execute("SELECT id FROM users WHERE LOWER(TRIM(email)) = %s", (email,))
                    existing_user = c.fetchone()

                    if existing_user:
                        error = "Email already registered."
                    else:
                        password_hash = generate_password_hash(password)
                        c.execute("""
                            INSERT INTO users (full_name, email, password_hash)
                            VALUES (%s, %s, %s)
                        """, (full_name, email, password_hash))

                        flash("Account created successfully. Please log in.")
                        return redirect(url_for("user_login"))

    return render_template("signup.html", error=error)


# ------------------------------
# USER LOGIN
# ------------------------------
@app.route("/user-login", methods=["GET", "POST"])
def user_login():
    error = ""

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        with get_conn() as conn:
            with conn.cursor() as c:
                c.execute("""
                    SELECT id, full_name, password_hash
                    FROM users
                    WHERE LOWER(TRIM(email)) = %s
                """, (email,))
                user = c.fetchone()

        if user and check_password_hash(user[2], password):
            session.clear()
            session["user_logged_in"] = True
            session["user_id"] = user[0]
            session["user_name"] = user[1]
            session["user_email"] = email
            return redirect(url_for("home"))

        error = "Invalid login details."

    return render_template("user_login.html", error=error)


# ------------------------------
# USER LOGOUT
# ------------------------------
@app.route("/user-logout")
def user_logout():
    session.pop("user_logged_in", None)
    session.pop("user_id", None)
    session.pop("user_name", None)
    session.pop("user_email", None)
    return redirect(url_for("home"))


# ------------------------------
# MY SHIPMENTS
# ------------------------------
@app.route("/my-shipments")
def my_shipments():
    if not session.get("user_logged_in"):
        return redirect(url_for("user_login"))

    user_email = session.get("user_email", "").strip().lower()

    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT tracking_number, sender_name, recipient_name, status, updated_at
                FROM bookings
                WHERE LOWER(TRIM(COALESCE(email, ''))) = %s
                ORDER BY id DESC
            """, (user_email,))
            shipments = c.fetchall()

    return render_template(
        "my_shipments.html",
        shipments=shipments,
        title=read_text_file("settings.txt", "SWIFTFREIGHT")
    )


# ------------------------------
# TEST ROUTE
# ------------------------------
@app.route("/test-tracking")
def test_tracking():
    return generate_tracking_number()


# ------------------------------
# ERROR PAGES
# ------------------------------
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template("500.html"), 500


@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    return render_template("csrf_error.html"), 400


# ------------------------------
# RESTORE BOOKING
# ------------------------------
@app.route("/admin/restore-booking", methods=["GET", "POST"])
def restore_booking():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    message = ""

    if request.method == "POST":
        sender_name = request.form.get("sender_name", "").strip()
        sender_phone = request.form.get("sender_phone", "").strip()
        recipient_name = request.form.get("recipient_name", "").strip()
        recipient_phone = request.form.get("recipient_phone", "").strip()
        address = request.form.get("address", "").strip()
        weight = request.form.get("weight", "").strip()
        dimensions = request.form.get("dimensions", "").strip()
        service_type = request.form.get("service_type", "").strip()
        tracking_number = request.form.get("tracking_number", "").strip()
        status = request.form.get("status", "").strip() or "Shipment Created"
        current_location = request.form.get("current_location", "").strip() or "Pending Pickup"
        user_email = request.form.get("email", "").strip().lower()

        if not all([sender_name, recipient_name, recipient_phone, address, weight, dimensions, service_type, tracking_number]):
            message = "Please fill in all required fields."
        else:
            try:
                weight_value = float(weight)

                with get_conn() as conn:
                    with conn.cursor() as c:
                        c.execute("SELECT id FROM bookings WHERE tracking_number = %s", (tracking_number,))
                        existing = c.fetchone()

                        if existing:
                            message = "This tracking number already exists."
                        else:
                            c.execute("""
                                INSERT INTO bookings (
                                    sender_name,
                                    sender_phone,
                                    recipient_name,
                                    recipient_phone,
                                    address,
                                    weight,
                                    dimensions,
                                    service_type,
                                    tracking_number,
                                    status,
                                    current_location,
                                    updated_at,
                                    email
                                )
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """, (
                                sender_name,
                                sender_phone,
                                recipient_name,
                                recipient_phone,
                                address,
                                weight_value,
                                dimensions,
                                service_type,
                                tracking_number,
                                status,
                                current_location,
                                malaysia_now_str(),
                                user_email
                            ))

                if message == "":
                    add_tracking_log(tracking_number, status, current_location)
                    message = "Booking restored successfully."

            except ValueError:
                message = "Weight must be a number."

    return f"""
    <html>
    <head>
        <title>Restore Booking</title>
        <style>
            body {{ font-family: Arial, sans-serif; background: #f5f5f5; padding: 30px; }}
            .box {{ max-width: 700px; margin: auto; background: white; padding: 25px; border-radius: 12px; }}
            input, textarea {{ width: 100%; padding: 10px; margin-bottom: 12px; box-sizing: border-box; }}
            button {{ background: #111; color: white; border: none; padding: 12px 18px; border-radius: 8px; }}
            .msg {{ margin-bottom: 15px; color: green; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="box">
            <h2>Restore Missing Booking</h2>
            <p><a href="/admin">Back to Admin</a></p>
            {f'<div class="msg">{message}</div>' if message else ''}
            <form method="POST">
                <input type="hidden" name="csrf_token" value="{generate_csrf()}">

                <label>Tracking Number</label>
                <input name="tracking_number" value="SF-BP3HTID847" required>

                <label>Sender Name</label>
                <input name="sender_name" required>

                <label>Sender Phone</label>
                <input name="sender_phone">

                <label>Recipient Name</label>
                <input name="recipient_name" required>

                <label>Recipient Phone</label>
                <input name="recipient_phone" required>

                <label>Recipient Address</label>
                <textarea name="address" required></textarea>

                <label>Weight (kg)</label>
                <input name="weight" required>

                <label>Dimensions</label>
                <input name="dimensions" placeholder="e.g. 40x30x20 cm" required>

                <label>Service Type</label>
                <input name="service_type" placeholder="Air Freight / Express / Sea Freight" required>

                <label>Status</label>
                <input name="status" value="Shipment Created">

                <label>Current Location</label>
                <input name="current_location" value="Pending Pickup">

                <label>User Email (optional)</label>
                <input name="email">

                <button type="submit">Restore Booking</button>
            </form>
        </div>
    </body>
    </html>
    """

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)