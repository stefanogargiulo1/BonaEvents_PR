from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
from datetime import datetime
import qrcode
import os
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
import json


app = Flask(__name__)
app.secret_key = "bonaevents_secret"


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.getenv("DB_NAME", os.path.join(BASE_DIR, "tickets.db"))
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE", "bonaeventsapp.myshopify.com").replace("https://", "").replace("http://", "").strip().strip("/")
SHOPIFY_ADMIN_TOKEN = os.getenv("SHOPIFY_ADMIN_TOKEN", "")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-04")


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    return any(col[1] == column_name for col in columns)


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_code TEXT UNIQUE NOT NULL,
            event TEXT NOT NULL,
            rate TEXT,
            customer TEXT,
            email TEXT,
            phone TEXT,
            used INTEGER DEFAULT 0,
            validated_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            status TEXT DEFAULT 'approved',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            approved_at TEXT
        )
    """)

    if not column_exists(cursor, "users", "status"):
        cursor.execute("ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'approved'")

    if not column_exists(cursor, "users", "created_at"):
        cursor.execute("ALTER TABLE users ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP")

    if not column_exists(cursor, "users", "approved_at"):
        cursor.execute("ALTER TABLE users ADD COLUMN approved_at TEXT")

    cursor.execute("""
        INSERT OR IGNORE INTO users (
            id,
            username,
            password,
            role,
            status,
            approved_at
        )
        VALUES (
            1,
            'admin',
            'admin123',
            'admin',
            'approved',
            CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        UPDATE users
        SET role = 'admin', status = 'approved'
        WHERE username = 'admin'
    """)

    conn.commit()
    conn.close()


def is_logged_in():
    return "user" in session


def is_admin():
    return session.get("role") == "admin"


def can_create_tickets():
    return session.get("role") in ["admin", "pr"]


def can_scan_tickets():
    return session.get("role") in ["admin", "scanner"]


def fetch_shopify_events():
    if not SHOPIFY_ADMIN_TOKEN or not SHOPIFY_STORE:
        print("SHOPIFY_TOKEN_OR_STORE_MISSING")
        return []

    url = f"https://{SHOPIFY_STORE}/admin/api/{SHOPIFY_API_VERSION}/shop.json"
    req = urlrequest.Request(url, method="GET")
    req.add_header("X-Shopify-Access-Token", SHOPIFY_ADMIN_TOKEN)

    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            print("SHOPIFY_SHOP_OK:", data.get("shop", {}).get("name"))
            return [data.get("shop", {}).get("name", "OK")]
    except Exception as e:
        print("SHOPIFY_FETCH_ERROR:", type(e).__name__, e)
        return []


init_db()
print("DB_PATH:", DB_NAME)


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM users
            WHERE username = ? AND password = ?
        """, (username, password))

        user = cursor.fetchone()
        conn.close()

        if not user:
            return render_template("login.html", error="Credenziali non valide")

        if user["status"] == "pending":
            return render_template("login.html", error="Account in attesa di approvazione")

        if user["status"] == "rejected":
            return render_template("login.html", error="Account rifiutato dall'amministratore")

        if user["status"] != "approved":
            return render_template("login.html", error="Account non autorizzato")

        session["user"] = user["username"]
        session["role"] = user["role"]
        session["user_id"] = user["id"]

        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "").strip().lower()

        if not username or not password or role not in ["pr", "scanner"]:
            return render_template(
                "register.html",
                error="Compila tutti i campi e scegli un ruolo valido"
            )

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            return render_template("register.html", error="Username già esistente")

        cursor.execute("""
            INSERT INTO users (
                username,
                password,
                role,
                status,
                approved_at
            )
            VALUES (?, ?, ?, 'pending', NULL)
        """, (username, password, role))

        conn.commit()
        conn.close()

        return render_template(
            "register.html",
            success="Registrazione inviata. Account in attesa di approvazione admin."
        )

    return render_template("register.html")


@app.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("login"))

    events = fetch_shopify_events()
    print("DASHBOARD_EVENTS:", events)
    print("DASHBOARD_EVENTS_COUNT:", len(events))

    return render_template(
        "events.html",
        events=events,
        role=session.get("role"),
        username=session.get("user")
    )


@app.route("/admin/users")
def admin_users():
    if not is_logged_in():
        return redirect(url_for("login"))

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM users
        ORDER BY
            CASE status
                WHEN 'pending' THEN 1
                WHEN 'approved' THEN 2
                WHEN 'rejected' THEN 3
                ELSE 4
            END,
            created_at DESC
    """)
    users = cursor.fetchall()
    conn.close()

    return render_template("admin_users.html", users=users)


@app.route("/admin/users/<int:user_id>/approve", methods=["POST"])
def approve_user(user_id):
    if not is_logged_in():
        return redirect(url_for("login"))

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE users
        SET status = 'approved',
            approved_at = CURRENT_TIMESTAMP
        WHERE id = ? AND username != 'admin'
    """, (user_id,))

    conn.commit()
    conn.close()

    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/reject", methods=["POST"])
def reject_user(user_id):
    if not is_logged_in():
        return redirect(url_for("login"))

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE users
        SET status = 'rejected',
            approved_at = NULL
        WHERE id = ? AND username != 'admin'
    """, (user_id,))

    conn.commit()
    conn.close()

    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
def delete_user(user_id):
    if not is_logged_in():
        return redirect(url_for("login"))

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM users
        WHERE id = ? AND username != 'admin'
    """, (user_id,))

    conn.commit()
    conn.close()

    return redirect(url_for("admin_users"))


@app.route("/ticket/<event_name>", methods=["GET", "POST"])
def ticket(event_name):
    if not is_logged_in():
        return redirect(url_for("login"))

    if not can_create_tickets():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        rate = request.form.get("rate")
        customer = request.form.get("customer")
        email = request.form.get("email")
        phone = request.form.get("phone")

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM tickets")
        total = cursor.fetchone()[0] + 1

        year = datetime.now().year
        ticket_code = f"BE-{year}-{total:06d}"

        qr = qrcode.QRCode(
            version=1,
            box_size=20,
            border=5
        )
        qr.add_data(ticket_code)
        qr.make(fit=True)

        img = qr.make_image(
            fill_color="black",
            back_color="white"
        ).convert("RGB")

        os.makedirs("static/qrcodes", exist_ok=True)
        qr_path = f"static/qrcodes/{ticket_code}.png"
        img.save(qr_path)

        cursor.execute("""
            INSERT INTO tickets (
                ticket_code,
                event,
                rate,
                customer,
                email,
                phone,
                used,
                validated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 0, NULL)
        """, (
            ticket_code,
            event_name,
            rate,
            customer,
            email,
            phone
        ))

        conn.commit()
        conn.close()

        return render_template(
            "success.html",
            ticket_code=ticket_code,
            qr_image=f"qrcodes/{ticket_code}.png",
            event=event_name,
            rate=rate,
            customer=customer,
            email=email,
            phone=phone
        )

    return render_template(
        "ticket.html",
        event_name=event_name
    )


@app.route("/scan")
def scan():
    if not is_logged_in():
        return redirect(url_for("login"))

    if not can_scan_tickets():
        return redirect(url_for("dashboard"))

    return render_template("scan.html")


@app.route("/validate-ticket", methods=["POST"])
def validate_ticket():
    if not is_logged_in():
        return jsonify({
            "success": False,
            "message": "Non autorizzato"
        }), 401

    if not can_scan_tickets():
        return jsonify({
            "success": False,
            "message": "Permessi insufficienti"
        }), 403

    data = request.get_json(silent=True)

    if not data or "ticket_code" not in data:
        return jsonify({
            "success": False,
            "message": "Codice ticket mancante"
        }), 400

    ticket_code = data["ticket_code"].strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM tickets
        WHERE ticket_code = ?
    """, (ticket_code,))
    ticket = cursor.fetchone()

    if not ticket:
        conn.close()
        return jsonify({
            "success": False,
            "status": "invalid",
            "message": "Ticket non valido"
        }), 404

    validated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        UPDATE tickets
        SET
            used = 1,
            validated_at = ?
        WHERE
            ticket_code = ?
            AND used = 0
    """, (
        validated_at,
        ticket_code
    ))

    conn.commit()

    if cursor.rowcount == 0:
        cursor.execute("""
            SELECT * FROM tickets
            WHERE ticket_code = ?
        """, (ticket_code,))
        ticket = cursor.fetchone()
        conn.close()

        return jsonify({
            "success": False,
            "status": "already_used",
            "message": "Ticket già convalidato",
            "ticket": {
                "ticket_code": ticket["ticket_code"],
                "event": ticket["event"],
                "customer": ticket["customer"],
                "validated_at": ticket["validated_at"]
            }
        }), 200

    cursor.execute("""
        SELECT * FROM tickets
        WHERE ticket_code = ?
    """, (ticket_code,))
    updated_ticket = cursor.fetchone()

    conn.close()

    return jsonify({
        "success": True,
        "status": "valid",
        "message": "Ticket valido e convalidato correttamente",
        "ticket": {
            "ticket_code": updated_ticket["ticket_code"],
            "event": updated_ticket["event"],
            "customer": updated_ticket["customer"],
            "rate": updated_ticket["rate"],
            "email": updated_ticket["email"],
            "phone": updated_ticket["phone"],
            "validated_at": updated_ticket["validated_at"]
        }
    }), 200


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/shopify/callback")
def shopify_callback():
    return "Shopify callback OK"


if __name__ == "__main__":
    app.run(debug=True)