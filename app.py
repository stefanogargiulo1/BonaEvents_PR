from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3

app = Flask(__name__)

app.secret_key = "bonaevents_secret"


# LOGIN TEST
USERNAME = "pr1"
PASSWORD = "1234"


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

        # SALVA TICKET NEL DATABASE
        conn = sqlite3.connect("tickets.db")

        cursor = conn.cursor()

        cursor.execute("""

        INSERT INTO tickets (
            event,
            rate,
            customer,
            email,
            phone
        )

        VALUES (?, ?, ?, ?, ?)

        """, (

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


@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)