from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from flask_mail import Mail, Message
from flask import render_template_string
import qrcode
import os
import hmac
import hashlib
import base64
import base64
import io
import csv
import requests
import resend

SHOPIFY_WEBHOOK_SECRET = ...
def update_shopify_order_note(order_id, ticket_url):

    try:

        url = f"https://{SHOPIFY_STORE}/admin/api/{SHOPIFY_API_VERSION}/orders/{order_id}.json"

        headers = {
            "X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN,
            "Content-Type": "application/json"
        }

        payload = {
            "order": {
                "id": order_id,
                "note": f"TICKET_URL: {ticket_url}"
            }
        }  

        response = requests.put(
            url,
            json=payload,
            headers=headers
        )

        print("SHOPIFY_NOTE_UPDATED:", response.status_code)

    except Exception as e:

        print("SHOPIFY_NOTE_ERROR:", e)


def get_commission(event_name, rate_name):

    try:

        with open("percPR.csv", newline='', encoding='utf-8') as csvfile:

            reader = csv.DictReader(csvfile)

            for row in reader:

                product_name = row.get("nome_del_prodotto", "").strip().lower()

                full_search = f"{event_name} {rate_name}".strip().lower()

                print("CSV_PRODUCT:", product_name)
                print("SEARCH:", full_search)

                if (
                    event_name.lower() in product_name
                    and
                    rate_name.lower() in product_name
                ):

                    try:

                        commission_raw = row.get(
                            "importo_della_commissione",
                            "0"
                        )

                        commission_raw = (
                            commission_raw
                            .replace("€", "")
                            .replace(",", ".")
                            .strip()
                        )

                        commission = float(commission_raw)

                        print("COMMISSION FOUND:", commission)

                        return commission

                    except:

                        return 0

    except Exception as e:

        print("COMMISSION_ERROR:", e)

    return 0

app = Flask(__name__)
resend.api_key = os.getenv("RESEND_API_KEY")
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False

app.config['MAIL_USERNAME'] = 'bonaeventsapp@gmail.com'
app.config['MAIL_PASSWORD'] = 'jfjv xhut fxgb jckk'
app.config['MAIL_DEFAULT_SENDER'] = 'bonaeventsapp@gmail.com'

mail = Mail(app)
def send_ticket_email(
    customer,
    email,
    event,
    rate,
    ticket_code
):
    print("SEND_EMAIL_FUNCTION_CALLED")
    ticket_url = f"https://staff.bonaevents.site/ticket-view/{ticket_code}"

    html = f"""
    <div style="background:#0f0f0f;padding:40px;font-family:Arial;color:white;text-align:center;">

        <h1 style="color:#ff1e1e;">
            🎫 BonaEvents Ticket
        </h1>

        <p>
            Il tuo ticket è stato confermato.
        </p>

        <div style="
            background:#1a1a1a;
            padding:25px;
            border-radius:15px;
            max-width:500px;
            margin:auto;
            margin-top:30px;
        ">

            <h2>{event}</h2>

            <p>
                <b>Ticket:</b> {rate}
            </p>

            <p>
                <b>Codice:</b> {ticket_code}
            </p>

            <a href="{ticket_url}"
               style="
               display:inline-block;
               margin-top:20px;
               padding:15px 25px;
               background:#ff1e1e;
               color:white;
               text-decoration:none;
               border-radius:10px;
               font-weight:bold;
               ">
               VISUALIZZA TICKET
            </a>

        </div>

    </div>
    """
    print("SENDING_RESEND_EMAIL")
    resend.Emails.send({

        "from": "BonaEvents <tickets@bonaevents.site>",

        "to": [email],

        "subject": f"🎫 Ticket {event}",

        "html": html

    })

    print("RESEND_EMAIL_SENT")
    print("EMAIL_READY:", email)


app.secret_key = "bonaevents_secret"

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

print("DATABASE_URL:", os.getenv("DATABASE_URL"))


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = "tickets.db"
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE", "bonaeventsapp.myshopify.com").replace("https://", "").replace("http://", "").strip().strip("/")
SHOPIFY_ADMIN_TOKEN = os.getenv("SHOPIFY_ADMIN_TOKEN", "")
SHOPIFY_STOREFRONT_TOKEN = os.getenv("SHOPIFY_STOREFRONT_TOKEN", "")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-04")

SHOPIFY_WEBHOOK_SECRET = os.getenv("SHOPIFY_WEBHOOK_SECRET", "")

def verify_shopify_webhook(raw_data, hmac_header):
    digest = hmac.new(
        SHOPIFY_WEBHOOK_SECRET.encode("utf-8"),
        raw_data,
        hashlib.sha256
    ).digest()
    computed_hmac = base64.b64encode(digest)
    return hmac.compare_digest(computed_hmac, hmac_header.encode("utf-8"))

@app.route("/webhooks/products-create", methods=["POST"])
def products_create_webhook():
    raw_data = request.get_data()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256", "")

    if not verify_shopify_webhook(raw_data, hmac_header):
        print("WEBHOOK_INVALID_HMAC")
        return "Invalid HMAC", 401

    payload = request.get_json(silent=True) or {}
    print("WEBHOOK_PRODUCTS_CREATE:", payload)
    return "OK", 200
@app.route("/webhooks/orders-create", methods=["POST"])
def orders_create_webhook():

    payload = request.get_json(silent=True) or {}

    print("NEW_ORDER_WEBHOOK:", payload)

    customer = payload.get("customer", {}) or {}

    customer_name = (
        f"{customer.get('first_name', '')} "
        f"{customer.get('last_name', '')}"
    ).strip()

    email = customer.get("email", "")
    phone = customer.get("phone", "")

    line_items = payload.get("line_items", [])

    conn = get_db_connection()
    cursor = conn.cursor()

    generated = []

    for item in line_items:

        event_name = item.get("title", "Evento")
        variant_name = item.get("variant_title", "Standard")
        event_date = ""

        for prop in item.get("properties", []):

            if prop.get("name") == "Data Evento":

                event_date = prop.get("value", "")
                break

        print("EVENT_DATE:", event_date)

        quantity = int(item.get("quantity", 1))

        for i in range(quantity):

            cursor.execute("SELECT COUNT(*) AS count FROM tickets")
            total = cursor.fetchone()["count"] + 1

            year = datetime.now().year
            ticket_code = f"BE-{year}-{total:06d}"

            qr = qrcode.QRCode(
                version=1,
                box_size=20,
                border=5
            )
            print("INSIDE_FOR_LOOP")

            qr.add_data(ticket_code)
            qr.make(fit=True)

            img = qr.make_image(
                fill_color="black",
                back_color="white"
            ).convert("RGB")

            os.makedirs("static/qrcodes", exist_ok=True)

            qr_path = f"static/qrcodes/{ticket_code}.png"

            img.save(qr_path)

            print("EVENT_DATE_BEFORE_SAVE:", event_date)
            cursor.execute("""
                INSERT INTO tickets (
                    ticket_code,
                    event,
                    rate,
                    customer,
                    email,
                    phone,
                    event_date,
                    pr_username,
                    commission_amount,
                    used,
                    validated_at
                )

                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, NULL)
                """, (
                    ticket_code,
                    event_name,
                    variant_name,
                    customer_name,
                    email,
                    phone,
                    event_date,
                    "SHOPIFY",
                    0
                ))

            print("TICKET_SAVED:", ticket_code)

            generated.append(ticket_code)
            send_ticket_email(
                customer_name,
                email, 
                event_name, 
                variant_name, 
                ticket_code
            )
                
            ticket_url = f"https://staff.bonaevents.site/ticket-view/{ticket_code}"
            order_id = payload.get("id")

            update_shopify_order_note(
                order_id,
                ticket_url
            )


            # msg = Message(
             #   subject=f"BonaEvents Ticket - {event_name}",
               # sender=app.config['MAIL_USERNAME'],
               # recipients=[email]
           # )

          #  msg.body = f"""
          #  TICKET BONAEVENTS

          #  Evento: {event_name}

          #  Cliente: {customer_name}

          #  Codice Ticket: {ticket_code}

          #  Visualizza Ticket:
          #  {ticket_url}
          #  """

          #  print("SENDING_EMAIL_TO:", email)
           # mail.send(msg)
          #  print("EMAIL_SENT")

    conn.commit()
    conn.close()

    print("TICKETS_GENERATED:", generated)

    return "OK", 200

def get_db_connection():

    database_url = os.getenv("DATABASE_URL")

    conn = psycopg2.connect(
        database_url,
        cursor_factory=RealDictCursor
    )

    return conn




def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id SERIAL PRIMARY KEY,
            ticket_code TEXT UNIQUE NOT NULL,
            event TEXT NOT NULL,
            rate TEXT,
            customer TEXT,
            email TEXT,
            phone TEXT,
            event_date TEXT,
            pr_username TEXT,
            commission_amount REAL DEFAULT 0,
            used INTEGER DEFAULT 0,
            validated_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    try:
        cursor.execute("""
            ALTER TABLE tickets
            ADD COLUMN pr_username TEXT
        """)
        conn.commit()

    except:
        conn.rollback()

    try:
        cursor.execute("""
            ALTER TABLE tickets
            ADD COLUMN event_date TEXT
        """)
        conn.commit()

    except:
        conn.rollback()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            status TEXT DEFAULT 'approved',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            approved_at TEXT
        )
    """)
       
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            handle TEXT,
            image TEXT,
            variant TEXT,
            price REAL,
            inventory INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)


    cursor.execute("""
    INSERT INTO users (
        username,
        password,
        role,
        status,
        approved_at
    )
    VALUES (
        'admin',
        'admin123',
        'admin',
        'approved',
        CURRENT_TIMESTAMP
    )
    ON CONFLICT (username) DO NOTHING
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

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM events
        ORDER BY title ASC
    """)

    rows = cursor.fetchall()

    conn.close()

    grouped = {}

    for row in rows:

        title = row["title"]

        if title not in grouped:

            grouped[title] = {
                "title": row["title"],
                "handle": row["handle"],
                "image": row["image"],
                "variants": []
            }

        grouped[title]["variants"].append({
            "title": row["variant"],
            "price": row["price"]
        })

    return list(grouped.values())


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
            WHERE username = %s AND password = %s
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

        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
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
            VALUES (%s, %s, %s, 'pending', NULL)
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

@app.route("/ticket-view/<ticket_code>")
def view_ticket(ticket_code):

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM tickets
        WHERE ticket_code = %s
    """, (ticket_code,))

    ticket = cursor.fetchone()

    conn.close()

    if not ticket:
        return "Ticket non trovato"

    qr = qrcode.make(ticket["ticket_code"])

    buffer = io.BytesIO()

    qr.save(buffer, format="PNG")

    qr_base64 = base64.b64encode(
        buffer.getvalue()
    ).decode("utf-8")

    return render_template(
        "view_ticket.html",
        event=ticket["event"],
        customer=ticket["customer"],
        rate=ticket["rate"],
        ticket_code=ticket["ticket_code"],
        event_date=ticket["event_date"],
        qr_base64=qr_base64
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
        WHERE id = %s AND username != 'admin'
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
        WHERE id = %s AND username != 'admin'
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
        WHERE id = %s AND username != 'admin'
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
        commission_amount = get_commission(event_name, rate)
        customer = request.form.get("customer")
        email = request.form.get("email")
        phone = request.form.get("phone")
        pr_username = session.get("user")

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) AS count FROM tickets")
        total = cursor.fetchone()["count"] + 1

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
                event_date,
                pr_username,
                commission_amount,
                used,
                validated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, NULL)
        """, (
            ticket_code,
            event_name,
            rate,
            customer,
            email,
            phone,
            None,
            pr_username,
            commission_amount
        ))

        conn.commit()
        conn.close()
        if email:

            send_ticket_email(
                customer,
                email,
                event_name,
                rate,
                ticket_code
            )

        ticket_url = url_for(
            "view_ticket",
            ticket_code=ticket_code,
            _external=True
        )

        return render_template(
            "success.html",
            ticket_code=ticket_code,
            qr_image=f"qrcodes/{ticket_code}.png",
            event=event_name,
            rate=rate,
            customer=customer,
            email=email,
            phone=phone,
            ticket_url=ticket_url
        )

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT variant, price
        FROM events
        WHERE title = %s
    """, (event_name,))

    variants = cursor.fetchall()

    conn.close()

    return render_template(
        "ticket.html",
        event_name=event_name,
        variants=variants
    )

@app.route("/tickets")
def tickets():

    if not is_logged_in():
        return redirect(url_for("login"))

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM tickets
        ORDER BY created_at DESC
    """)

    tickets = cursor.fetchall()

    conn.close()

    return render_template(
        "tickets.html",
        tickets=tickets
    )

@app.route("/pr-dashboard")
def pr_dashboard():

    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT *
        FROM tickets
        WHERE pr_username = %s
        ORDER BY id DESC
    """, (session.get("user"),))

    tickets = cursor.fetchall()

    cursor.execute("""
        SELECT
            COUNT(*) as total_tickets,
            COALESCE(SUM(commission_amount), 0) as total_commissions
        FROM tickets
        WHERE pr_username = %s
    """, (session.get("user"),))

    stats = cursor.fetchone()

    conn.close()

    return render_template(
        "pr_dashboard.html",
        tickets=tickets,
        stats=stats
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
        WHERE ticket_code = %s
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
            validated_at = %s
        WHERE
            ticket_code = %s
            AND used = 0
    """, (
        validated_at,
        ticket_code
    ))

    conn.commit()

    if cursor.rowcount == 0:
        cursor.execute("""
            SELECT * FROM tickets
            WHERE ticket_code = %s
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
        WHERE ticket_code = %s
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

@app.route("/import-shopify-csv")
def import_shopify_csv():

    conn = get_db_connection()
    cursor = conn.cursor()

    csv_path = "PRODOTTI.csv"

    imported = 0

    with open(csv_path, newline='', encoding='utf-8') as csvfile:

        reader = csv.DictReader(csvfile)

        last_title = ""
        last_handle = ""
        last_image = ""

        for row in reader:

            title = row.get("Title", "").strip()
            handle = row.get("Handle", "").strip()
            variant = row.get("Option1 Value", "").strip()
            price = row.get("Variant Price", "0").strip()
            commission = row.get("importo_della_commissione", "0").strip()
            image = row.get("Image Src", "").strip()

            if title:
                last_title = title

            if handle:
                last_handle = handle

            if image:
                last_image = image

            title = last_title
            handle = last_handle
            image = last_image

            if not title:
                continue

            try:
                price = float(price)
            except:
                price = 0

            try:
                commission = float(commission)
            except:
                commission = 0

            cursor.execute("""
                INSERT INTO events (
                    title,
                    handle,
                    image,
                    variant,
                    price,
                    commission_amount     
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                title,
                handle,
                image,
                variant,
                price,
                commission
            ))

            imported += 1

    conn.commit()
    conn.close()

    return f"Import completato. Eventi importati: {imported}"

@app.route("/ticket-details/<ticket_code>")
def ticket_details(ticket_code):

    if not is_logged_in():
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM tickets
        WHERE ticket_code = %s
    """, (ticket_code,))

    ticket = cursor.fetchone()

    conn.close()

    if not ticket:
        return "Ticket non trovato", 404
    
    qr = qrcode.make(ticket["ticket_code"])
    buffer = io.BytesIO()
    qr.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(
        buffer.getvalue()
    ).decode("utf-8")

    return render_template(
        "ticket_details.html",
        ticket=ticket,
        qr_base64=qr_base64
    )



@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/shopify/callback")
def shopify_callback():
    return "Shopify callback OK"


if __name__ == "__main__":
    app.run(debug=True)