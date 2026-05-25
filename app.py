from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
from datetime import datetime
import qrcode
import os

app = Flask(__name__)
app.secret_key = "bonaevents_secret"

USERNAME = "pr1"
PASSWORD = "1234"

DB_NAME = os.getenv("DB_NAME", "tickets.db")


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


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

    conn.commit()
    conn.close()


init_db()


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == USERNAME and password == PASSWORD:
            session["user"] = username
            return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    events = [
        "Boat Party",
        "White Party",
        "La French",
        "Foam Madness",
        "Pool Party",
        "Azur Beach Party",
        "Bona Loca",
        "Sunset Rooftop"
    ]

    return render_template("events.html", events=events)


@app.route("/ticket/<event_name>", methods=["GET", "POST"])
def ticket(event_name):
    if "user" not in session:
        return redirect(url_for("login"))

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

        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

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

    return render_template("ticket.html", event_name=event_name)


@app.route("/scan")
def scan():
    if "user" not in session:
        return redirect(url_for("login"))

    return render_template("scan.html")


@app.route("/validate-ticket", methods=["POST"])
def validate_ticket():
    if "user" not in session:
        return jsonify({
            "success": False,
            "message": "Non autorizzato"
        }), 401

    data = request.get_json(silent=True)
    if not data or "ticket_code" not in data:
        return jsonify({
            "success": False,
            "message": "Codice ticket mancante"
        }), 400

    ticket_code = data["ticket_code"].strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM tickets WHERE ticket_code = ?", (ticket_code,))
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
        SET used = 1, validated_at = ?
        WHERE ticket_code = ? AND used = 0
    """, (validated_at, ticket_code))

    conn.commit()

    if cursor.rowcount == 0:
        cursor.execute("SELECT * FROM tickets WHERE ticket_code = ?", (ticket_code,))
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

    cursor.execute("SELECT * FROM tickets WHERE ticket_code = ?", (ticket_code,))
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


if __name__ == "__main__":
    app.run(debug=True)