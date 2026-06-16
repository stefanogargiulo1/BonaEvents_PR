from flask import Flask, render_template, request, redirect, url_for, session, jsonify, make_response
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
import pandas as pd
from flask import send_file
from io import BytesIO
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

        rate_clean = rate_name.lower()

        if " / " in rate_clean:
            rate_clean = rate_clean.split(" / ", 1)[1].strip()

        print("RATE_CLEAN:", rate_clean)

        with open("percPR.csv", newline='', encoding='utf-8') as csvfile:

            reader = csv.DictReader(csvfile)

            for row in reader:

                product_name = row.get(
                    "nome_del_prodotto",
                    ""
                ).strip().lower()

                print("CSV_PRODUCT:", product_name)

                if (
                    event_name.lower() in product_name
                    and
                    rate_clean in product_name
                ):

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

    shopify_order_id = str(payload.get("id"))

    print("SHOPIFY_ORDER_ID:", shopify_order_id)

    customer = payload.get("customer", {}) or {}

    customer_name = (
        f"{customer.get('first_name', '')} "
        f"{customer.get('last_name', '')}"
    ).strip()

    email = customer.get("email", "")
    phone = customer.get("phone", "")

    line_items = payload.get("line_items", [])

    pr_username = "SHOPIFY"
    sale_source = "SHOPIFY_DIRECT"

    for item in line_items:

        print("ITEM_PROPERTIES:", item.get("properties", []))

        for prop in item.get("properties", []):

            if prop.get("name") == "_ref_pr":

                ref_pr = prop.get("value", "").strip()

                if ref_pr:

                    pr_username = ref_pr
                    sale_source = "SHOPIFY_REF"

                    print("REFERRAL_FOUND:", ref_pr)

                    break

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id
        FROM tickets
        WHERE shopify_order_id = %s
        LIMIT 1
    """, (shopify_order_id,))

    existing_ticket = cursor.fetchone()

    if existing_ticket:

        print("ORDER_ALREADY_PROCESSED:", shopify_order_id)

        conn.close()

        return "already processed", 200

    generated = []

    for item in line_items:
        
        print("LINE_ITEM:", item)
        event_name = item.get("title", "Evento")

        variant_title = item.get("variant_title", "Standard")
        ticket_price = float(
            item.get("price", 0)
        )

        event_date = ""
        variant_name = variant_title

        if " / " in variant_title:

            parts = variant_title.split(" / ", 1)

            event_date = parts[0].strip()
            variant_name = parts[1].strip()

        print("EVENT_DATE:", event_date)
        print("RATE:", variant_name)
        commission_amount = get_commission(
            event_name,
            variant_name
        )

        print("COMMISSION:", commission_amount)

        quantity = int(item.get("quantity", 1))

        PACK_EVENTS = {
            "3 Days Pack (12-14 Giugno)": [
                ("Cookies and cream mango", "12/06/2026"),
                ("The wolf of wall street Principotes", "13/06/2026"),
                ("Flamingo pool party mercury hotel", "14/06/2026")
            ],

            "4 Days Pack (11-14 Giugno)": [
                ("Boat party Open Bar Collaborazione", "11/06/2026"),
                ("La guerre Principotes (ita vs Francia)", "11/06/2026"),
                ("Cookies and cream mango", "12/06/2026"),
                ("The wolf of wall street Principotes", "13/06/2026"),
                ("Flamingo pool party mercury hotel", "14/06/2026")
            ]
        }

        events_to_generate = [(event_name, event_date)]

        if event_name in PACK_EVENTS:
            events_to_generate = PACK_EVENTS[event_name]
            print("PACK_DETECTED:", event_name)
        
        if event_name in PACK_EVENTS:

            ticket_price = round(
                ticket_price / len(events_to_generate),
                2
            )

            print(
                "PACK_PRICE_SPLIT:",
                ticket_price
            )

        for generated_event_name, generated_event_date in events_to_generate:

            for i in range(quantity):

                cursor.execute(
                    "SELECT COUNT(*) AS count FROM tickets"
                )

                total = cursor.fetchone()["count"] + 1

                year = datetime.now().year

                ticket_code = (
                    f"BE-{year}-{total:06d}"
                )

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
                        shopify_order_id,
                        event_date,
                        pr_username,
                        sale_source,
                        commission_amount,
                        ticket_price,
                        used,
                        validated_at
                    )

                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, NULL)
                    """, (
                        ticket_code,
                        generated_event_name,
                        variant_name,
                        customer_name,
                        email,
                        phone,
                        shopify_order_id,
                        generated_event_date,
                        pr_username,
                        sale_source,
                        commission_amount,
                        ticket_price
                    ))

                cursor.execute("""
                    UPDATE events
                    SET inventory = inventory - 1
                    WHERE lower(title) = lower(%s)
                    AND variant = %s
                """, (
                    event_name,
                    variant_title
                ))


                print(
                    "SHOPIFY_STOCK_DECREASED:",
                    event_name,
                    variant_title
                )

                if event_name in PACK_EVENTS:

                    cursor.execute("""
                        UPDATE events
                        SET inventory = inventory - 1
                        WHERE lower(title) = lower(%s)
                    """, (
                        generated_event_name,
                    ))

                    print(
                        "PACK_EVENT_STOCK_DECREASED:",
                        generated_event_name
                    )
                
                print("TICKET_SAVED:", ticket_code)

                generated.append(ticket_code)
                send_ticket_email(
                    customer_name,
                    email,
                    generated_event_name,  
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
            shopify_order_id TEXT,
            event_date TEXT,
            pr_username TEXT,
            sale_source TEXT,
            commission_amount REAL DEFAULT 0,
            used INTEGER DEFAULT 0,
            validated_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    try:
        cursor.execute("""
            ALTER TABLE tickets
            ADD COLUMN shopify_order_id TEXT
        """)
    except:
        pass
    
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

    try:
        cursor.execute("""
            ALTER TABLE tickets
            ADD COLUMN sale_source TEXT
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

    try:
        cursor.execute("""
            ALTER TABLE events
            ADD COLUMN is_active BOOLEAN DEFAULT TRUE
        """)
        conn.commit()

    except:
        conn.rollback()


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
    INSERT INTO users (
        username,
        password,
        role,
        status,
        approved_at
    )
    VALUES (
        'DontShop',
        'DontShop2026!',
        'dontshop',
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
    return session.get("role") in ["admin", "dontshop"]


def can_create_tickets():
    return session.get("role") in ["admin", "dontshop", "pr", "team_leader"]


def can_scan_tickets():
    return session.get("role") in ["admin", "dontshop", "scanner"]


def fetch_shopify_events():

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM events
        ORDER BY title ASC, id ASC
    """)

    rows = cursor.fetchall()

    conn.close()

    grouped = {}

    for row in rows:

        title = row["title"]
        print("FIRST_VARIANT:", row["variant"])

        if title not in grouped:

            grouped[title] = {
                "id": row["id"],
                "title": row["title"],
                "handle": row["handle"],
                "image": row["image"],
                "is_active": row["is_active"],
                "variants": [],
                "stock": 0
            }

        grouped[title]["variants"].append({
            "title": row["variant"],
            "price": row["price"]
        })

        grouped[title]["stock"] += int(row["inventory"] or 0)

        grouped[title]["min_price"] = min(
            grouped[title].get("min_price", row["price"]),
            row["price"]
        )
    
    for event in grouped.values():

        dates = set()

        for v in event["variants"]:

            if " / " in v["title"]:

                date_part = v["title"].split(" / ")[0]

                dates.add(date_part)

        event["dates_count"] = len(dates)
        event["variants_count"] = len(event["variants"])

    return list(grouped.values())


init_db()

print("DB_PATH:", DB_NAME)


@app.route("/r/<pr_username>")
def referral_redirect(pr_username):

    response = make_response(
        redirect("https://bonaevents.site")
    )

    response.set_cookie(
        "ref_pr",
        pr_username,
        max_age=43200
    )

    return response


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

        if not username or not password or role not in ["pr", "scanner", "team_leader"]:
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

    if session.get("role") == "pr":

        events = [
            event
            for event in events
            if event.get("is_active", True)
        ]

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            pr_username,
            COUNT(*) as vendite
        FROM tickets
        WHERE
            pr_username IS NOT NULL
            AND pr_username != 'SHOPIFY'
            AND sale_source IN ('CASH', 'SHOPIFY_REF')
        GROUP BY pr_username
        ORDER BY vendite DESC
        LIMIT 3
    """)

    top_pr = cursor.fetchall()

    conn.close()
    print("TOP_PR:", top_pr)
    print("DASHBOARD_EVENTS:", events)
    print("DASHBOARD_EVENTS_COUNT:", len(events))

    return render_template(
        "events.html",
        events=events,
        role=session.get("role"),
        username=session.get("user"),
        top_pr=top_pr
    )

@app.route("/toggle-event/<int:event_id>")
def toggle_event(event_id):

    if "user_id" not in session:
        return redirect("/")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE events
        SET is_active = NOT is_active
        WHERE id = %s
    """, (event_id,))

    conn.commit()
    conn.close()

    return redirect("/dashboard")

@app.route("/event-stats/<event_name>")
def event_stats(event_name):

    if not is_logged_in():
        return redirect(url_for("login"))

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) as sold
        FROM tickets
        WHERE event = %s
    """, (event_name,))

    sold = cursor.fetchone()["sold"]

    cursor.execute("""
        SELECT COALESCE(SUM(inventory),0) as available
        FROM events
        WHERE title = %s
    """, (event_name,))

    available = cursor.fetchone()["available"]

    cursor.execute("""
        SELECT COUNT(*) as checked
        FROM tickets
        WHERE event = %s
        AND used = 1
    """, (event_name,))

    checked = cursor.fetchone()["checked"]

    cursor.execute("""
        SELECT
            pr_username,
            COUNT(*) as vendite
        FROM tickets
        WHERE event = %s
        AND pr_username IS NOT NULL
        AND pr_username != 'SHOPIFY'
        GROUP BY pr_username
        ORDER BY vendite DESC
        LIMIT 10
    """, (event_name,))

    top_pr = cursor.fetchall()

    cursor.execute("""
        SELECT
            COALESCE(SUM(ticket_price),0) as revenue
        FROM tickets
        WHERE event = %s
    """, (event_name,))

    revenue = cursor.fetchone()["revenue"] or 0

    cursor.execute("""
        SELECT
            sale_source,
            COALESCE(SUM(ticket_price),0) as revenue
        FROM tickets
        WHERE event = %s
        GROUP BY sale_source
    """, (event_name,))

    sources = cursor.fetchall()

    cursor.execute("""
        SELECT
            rate,
            COUNT(*) as total
        FROM tickets
        WHERE event = %s
        GROUP BY rate
        ORDER BY total DESC
    """, (event_name,))

    rates = cursor.fetchall()

    total_capacity = sold + available

    fill_percentage = 0

    if total_capacity > 0:
        fill_percentage = round(
            (sold / total_capacity) * 100,
            1
        )

    conn.close()

    return render_template(
        "event_stats.html",
        event_name=event_name,
        sold=sold,
        available=available,
        fill_percentage=fill_percentage,
        checked=checked,
        top_pr=top_pr,
        revenue=revenue,
        sources=sources,
        rates=rates

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

    if not ticket:
        conn.close()
        return "Ticket non trovato"

    image_url = ""
    description = ""

    cursor.execute("""
        SELECT image, description
        FROM events
        WHERE lower(title) = lower(%s)
        LIMIT 1
    """, (ticket["event"],))

    event_row = cursor.fetchone()

    if event_row:
        image_url = event_row["image"]
        description = event_row["description"] or ""

    conn.close()

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
        qr_base64=qr_base64,
        image_url=image_url,
        description=description
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
        SELECT *
        FROM users
        WHERE username != 'DontShop'
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

    cursor.execute("""
        SELECT username
        FROM users
        WHERE role = 'team_leader'
        ORDER BY username
    """)

    team_leaders = cursor.fetchall()

    conn.close()

    return render_template("admin_users.html", users=users, team_leaders=team_leaders)


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


@app.route("/admin/users/<int:user_id>/set-team-leader/<leader>")
def set_team_leader(user_id, leader):

    if not is_logged_in():
        return redirect(url_for("login"))

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()

    if leader == "none":
        leader = None

    cursor.execute("""
        UPDATE users
        SET team_leader_username = %s
        WHERE id = %s
    """, (
        leader,
        user_id
    ))

    conn.commit()
    conn.close()

    return redirect("/admin/users")


@app.route("/admin/user/<int:user_id>", methods=["GET", "POST"])
def edit_user(user_id):

    if not is_logged_in():
        return redirect(url_for("login"))

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    if request.method == "POST":

        cursor.execute("""
            UPDATE users
            SET
                password = %s,
                role = %s,
                status = %s,
                team_leader_username = %s
            WHERE id = %s
        """, (
            request.form["password"],
            request.form["role"],
            request.form["status"],
            request.form["team_leader_username"] or None,
            user_id
        ))

        conn.commit()

        return redirect(
            url_for(
                "edit_user",
                user_id=user_id
            )
        )

    cursor.execute("""
        SELECT *
        FROM users
        WHERE id = %s
    """, (user_id,))

    user = cursor.fetchone()

    cursor.execute("""
        SELECT username
        FROM users
        WHERE role = 'team_leader'
        ORDER BY username
    """)

    team_leaders = cursor.fetchall()

    conn.close()

    return render_template(
        "edit_user.html",
        user=user,
        team_leaders=team_leaders
    )


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
        
        quantity = int(
            request.form.get(
                "quantity",
                1
            )
        )

        PACK_EVENTS = {
            "3 Days Pack (12-14 Giugno)": [
                ("Cookies and cream mango", "12/06/2026"),
                ("The wolf of wall street Principotes", "13/06/2026"),
                ("Flamingo pool party mercury hotel", "14/06/2026")
            ],

            "4 Days Pack (11-14 Giugno)": [
                ("Boat party Open Bar Collaborazione", "11/06/2026"),
                ("La guerre Principotes (ita vs Francia)", "11/06/2026"),
                ("Cookies and cream mango", "12/06/2026"),
                ("The wolf of wall street Principotes", "13/06/2026"),
                ("Flamingo pool party mercury hotel", "14/06/2026")
            ]
        }

        event_date = ""
        if " / " in rate:
            event_date = rate.split(" / ")[0].strip()

        commission_amount = get_commission(
            event_name,
            rate
        )

        print("EVENT:", event_name)
        print("RATE:", rate)
        print("COMMISSION_RESULT:", commission_amount)
        customer = request.form.get("customer")
        email = request.form.get("email")
        phone = request.form.get("phone")
        pr_username = session.get("user")

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) AS count FROM tickets")
        total = cursor.fetchone()["count"] + 1

        cursor.execute("""
            SELECT inventory, price
            FROM events
            WHERE title = %s
            AND variant = %s
        """, (
            event_name,
            rate
        ))

        stock_row = cursor.fetchone()

        ticket_price = float(
            stock_row["price"] or 0
        )

        events_to_generate = [
            (event_name, event_date)
        ]

        if event_name in PACK_EVENTS:

            events_to_generate = PACK_EVENTS[event_name]

            ticket_price = round(
                ticket_price / len(events_to_generate),
                2
            )

            print(
                "PACK_PRICE_SPLIT_CASH:",
                ticket_price
            )

        if not stock_row:

            conn.close()

            return "Variante non trovata", 400

        if stock_row["inventory"] < quantity:

            conn.close()

            return f"""
            Disponibilità insufficiente.
            Rimasti: {stock_row['inventory']}
            """, 400

        year = datetime.now().year

        generated_tickets = []

        for generated_event_name, generated_event_date in events_to_generate:
                
            for i in range(quantity):

                ticket_code = (
                    f"BE-{year}-{total + len(generated_tickets):06d}"
                )

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
                        sale_source,
                        commission_amount,
                        ticket_price,
                        used,
                        validated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, NULL)
                """, (
                    ticket_code,
                    generated_event_name,
                    rate,
                    customer,
                    email,
                    phone,
                    generated_event_date,
                    pr_username,
                    "CASH",
                    commission_amount,
                    ticket_price
                ))

                generated_tickets.append({
                    "ticket_code": ticket_code,
                    "qr_image": f"qrcodes/{ticket_code}.png",
                    "ticket_url": url_for(
                        "view_ticket",
                        ticket_code=ticket_code,
                        _external=True
                    )
                })
                if email:

                    send_ticket_email(
                        customer,
                        email,
                        generated_event_name,
                        rate,
                        ticket_code
                    )
        cursor.execute("""
            UPDATE events
            SET inventory = inventory - %s
            WHERE title = %s
            AND variant = %s
        """, (
            quantity,
            event_name,
            rate
        ))

        if event_name in PACK_EVENTS:

            for generated_event_name, generated_event_date in events_to_generate:

                cursor.execute("""
                    UPDATE events
                    SET inventory = inventory - %s
                    WHERE lower(title) = lower(%s)
                """, (
                    quantity,
                    generated_event_name
                ))

        conn.commit()
        conn.close()
        

        ticket_url = url_for(
            "view_ticket",
            ticket_code=ticket_code,
            _external=True
        )

        print("GENERATED_TICKETS =", generated_tickets)
        print("COUNT =", len(generated_tickets))

        return render_template(
            "success.html",
            generated_tickets=generated_tickets,
            event=event_name,
            rate=rate,
            customer=customer,
            email=email,
            phone=phone
        )

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT variant, price, inventory
        FROM events
        WHERE title = %s
        ORDER BY variant
    """, (event_name,))

    rows = cursor.fetchall()

    dates = {}

    for row in rows:

        parts = row["variant"].split(" / ")

        if len(parts) < 2:
            continue

        event_date = parts[0]
        rate = parts[1]

        if event_date not in dates:
            dates[event_date] = []

        dates[event_date].append({
            "rate": rate,
            "price": row["price"],
            "inventory": row["inventory"],
            "full_variant": row["variant"]
        })

    for event_date in dates:
        dates[event_date].sort(
            key=lambda x: x["rate"]
        )

    try:

        dates = dict(
            sorted(
                dates.items(),
                key=lambda x: datetime.strptime(
                    x[0],
                    "%d/%m/%Y"
                )
            )
        )

    except:

        dates = dict(
            sorted(dates.items())
        )

    conn.close()

    return render_template(
        "ticket.html",
        event_name=event_name,
        dates=dates
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

    for ticket in tickets:

        if ticket.get("created_at"):

            ticket["created_at_formatted"] = (
                str(ticket["created_at"])
                .replace("+00:00", "")
                [:16]
            )

    conn.close()

    return render_template(
        "tickets.html",
        tickets=tickets
    )

@app.route("/pr-dashboard")
def pr_dashboard():

    if "user" not in session:
        return redirect(url_for("login"))
    
    if session.get("role") not in ["pr", "team_leader"]:
        return redirect(url_for("dashboard"))

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
    team_stats = []

    if session.get("role") == "team_leader":

        cursor.execute("""
            SELECT username
            FROM users
            WHERE team_leader_username = %s
        """, (session.get("user"),))

        team_members = cursor.fetchall()

        for member in team_members:

            cursor.execute("""
                SELECT
                    COUNT(*) as total_tickets,
                    COALESCE(SUM(commission_amount),0) as total_commissions
                FROM tickets
                WHERE pr_username = %s
            """, (member["username"],))

            member_stats = cursor.fetchone()

            team_stats.append({
                "username": member["username"],
                "tickets": member_stats["total_tickets"],
                "commissions": member_stats["total_commissions"]
            })

    conn.close()

    return render_template(
        "pr_dashboard.html",
        tickets=tickets,
        stats=stats,
        team_stats=team_stats,
        referral_link=f"https://bonaevents.site/?ref={session.get('user')}"
    )

@app.route("/scan")
def scan():

    if not is_logged_in():
        return redirect(url_for("login"))

    if not can_scan_tickets():
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            title,
            split_part(variant, ' / ', 1) AS event_date,
            inventory
        FROM events
        ORDER BY title, event_date
    """)

    rows = cursor.fetchall()

    events = {}

    for row in rows:

        title = row["title"]

        if title not in events:

            events[title] = []

        exists = False

        for d in events[title]:

            if d["date"] == row["event_date"]:

                exists = True
                break

        if not exists:

            events[title].append({
                "date": row["event_date"],
                "inventory": row["inventory"]
            })

    for event_name in events:

        events[event_name].sort(
            key=lambda x: datetime.strptime(
                x["date"],
                "%d/%m/%Y"
            )
        )

    conn.close()

    return render_template(
        "scan.html",
        events=events
    )


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

    selected_event = data.get("selected_event", "")
    selected_date = data.get("selected_date", "")

    if ticket["event"] != selected_event:

        conn.close()

        return jsonify({
            "success": False,
            "status": "wrong_event",
            "message":
                f"Ticket valido ma per evento diverso: {ticket['event']}"
        }), 200

    if ticket["event_date"] != selected_date:

        conn.close()

        return jsonify({
            "success": False,
            "status": "wrong_date",
            "message":
                f"Ticket valido ma per data diversa: {ticket['event_date']}"
        }), 200


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
            "event_date": updated_ticket["event_date"],
            "customer": updated_ticket["customer"],
            "rate": updated_ticket["rate"],
            "email": updated_ticket["email"],
            "phone": updated_ticket["phone"],
            "pr_username": updated_ticket["pr_username"],
            "sale_source": updated_ticket["sale_source"],
            "validated_at": updated_ticket["validated_at"]
        }
    }), 200

@app.route("/import-shopify-csv")
def import_shopify_csv():

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM events")
    conn.commit()

    csv_path = "PRODOTTI.csv"

    imported = 0

    with open(csv_path, newline='', encoding='utf-8') as csvfile:

        reader = csv.DictReader(csvfile)

        print("COLONNE CSV:")
        print(reader.fieldnames)

        last_title = ""
        last_handle = ""
        last_image = ""

        for row in reader:

            print("ROW:", row)

            title = row.get("Title", "").strip()
            handle = row.get("Handle", "").strip()

            event_date = row.get("Option1 Value", "").strip()
            rate = row.get("Option2 Value", "").strip()

            variant = f"{event_date} / {rate}"

            price = row.get("Variant Price", "0").strip()
            inventory = row.get(
                "Variant Inventory Qty",
                "0"
            ).strip()

            try:
                inventory = int(inventory)
            except:
                inventory = 0
            commission = row.get("importo_della_commissione", "0").strip()
            image = row.get("Image Src", "").strip()
            description = row.get("Body (HTML)", "").strip()

            if title:
                print("TITLE:", title)
                print("IMAGE:", image)

            if title:
                print("TITLE FOUND:", title)
                print("IMAGE FOUND:", image)

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


            print(
                "IMPORTING:",
                title,
                variant,
                price
            )
            

            cursor.execute("""
                INSERT INTO events (
                    title,
                    handle,
                    image,
                    description,
                    variant,
                    price,
                    inventory,
                    commission_amount     
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                title,
                handle,
                image,
                description,
                variant,
                price,
                inventory,
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


@app.route("/export-sales")
def export_sales():

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

    df = pd.DataFrame(tickets)

    output = BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        df.to_excel(
            writer,
            index=False,
            sheet_name="Vendite"
        )

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name=f"vendite_{datetime.now().strftime('%d-%m-%Y')}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.route("/reset-sales")
def reset_sales():

    if not is_logged_in():
        return redirect(url_for("login"))

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM tickets
    """)

    conn.commit()
    conn.close()

    return redirect(url_for("tickets"))

@app.route("/confirm-reset-sales")
def confirm_reset_sales():

    if not is_logged_in():
        return redirect(url_for("login"))

    if not is_admin():
        return redirect(url_for("dashboard"))

    return """
    <html>
    <head>
        <title>Conferma Azzeramento</title>
    </head>

    <body style="
        background:#0f172a;
        color:white;
        font-family:Arial;
        display:flex;
        justify-content:center;
        align-items:center;
        height:100vh;
    ">

        <div style="
            background:#1e293b;
            padding:40px;
            border-radius:20px;
            text-align:center;
            max-width:500px;
        ">

            <h1>⚠️ Attenzione</h1>

            <p style="margin-top:20px;">
                Verrà scaricato il file Excel con tutte le vendite.
            </p>

            <p>
                Successivamente tutti i ticket verranno eliminati.
            </p>

            <div style="margin-top:30px;">

                <button
                    onclick="exportAndReset()"
                    style="
                    background:#dc2626;
                    color:white;
                    padding:12px 20px;
                    border:none;
                    border-radius:10px;
                    cursor:pointer;
                    margin-right:10px;
                    font-weight:bold;
                    ">
                    CONFERMA
                </button>

                <a href="/tickets"
                   style="
                   background:#334155;
                   color:white;
                   padding:12px 20px;
                   text-decoration:none;
                   border-radius:10px;
                   ">
                   ANNULLA
                </a>

            </div>

        </div>
        
        <script>

        function exportAndReset() {
            window.open("/export-sales", "_blank");
            setTimeout(function() {
                window.location.href = "/reset-sales";
            }, 1500);
        }

        </script>

    </body>
    </html>
    """


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/shopify/callback")
def shopify_callback():
    return "Shopify callback OK"


if __name__ == "__main__":
    app.run(debug=True)