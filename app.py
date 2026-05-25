from flask import Flask, render_template, request, redirect, url_for, session

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

    return render_template("index.html")


@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))