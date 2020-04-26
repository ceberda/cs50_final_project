import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)



db = SQL("sqlite:///finance_mgmt.db")

@app.route("/")
@login_required
def index():
    """Empty State"""
    return render_template("index.html")

    """Show Account Data"""



@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")



@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # when the requested via GET, should display registration form
    if request.method == "GET":
        return render_template("register.html")

    # when form is submitted via POST
    elif request.method == "POST":

        # The username input is blank
        if not request.form.get("username"):
            return apology("Must provide username", 400)

        # The password input is blank
        elif not request.form.get("password"):
            return apology("Must provide password", 400)

        # The username already exist
        elif len( db.execute("SELECT * FROM users WHERE username = :username",
                        username=request.form.get("username")) ) > 0:
            return apology("username already exist", 400)

        # Passwords do not match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords do not match", 400)

        # INSERT the new user into users, storing a hash of the user’s password with generate_password_hash
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                    username=request.form.get("username"),
                    hash=generate_password_hash(request.form.get("password")))

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

@app.route("/settings", methods=["GET", "POST"])
def change_password():
    if request.method == "GET":
        return render_template("settings.html")

     # when form is submitted via POST
    elif request.method == "POST":

        # The current password input is blank
        if not request.form.get("password"):
            return apology("Must provide your current password", 400)

        # The new password input is blank
        if not request.form.get("new_password"):
            return apology("Must provide a new password", 400)

        # Passwords do not match
        if request.form.get("new_password") != request.form.get("new_confirmation"):
            return apology("Passwords do not match", 400)


        # Query database for hash
        rows = db.execute("SELECT hash FROM users WHERE id = :user_id",
                        user_id = session["user_id"] )

        # Current password in form does not equal stored password
        if not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("Your current password is not correct", 400)

        # Check if current password = new password
        if check_password_hash(rows[0]["hash"], request.form.get("new_password")):
            return apology("That's your current password, try a different one", 400)

        # UPDATE hash / password for the logged in user
        db.execute("UPDATE users SET hash =:hash WHERE id = :user_id",
                    user_id = session["user_id"],
                    hash=generate_password_hash(request.form.get("new_password")))

        # Redirect user to home page
        flash('Success, your password has been changed!')
        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)


