import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
import plaid
import datetime
from dateutil.relativedelta import relativedelta
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
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Database connection.
db = SQL("sqlite:///finance_mgmt.db")

# Plaid stuff. 
# Fill in your Plaid API keys - https://dashboard.plaid.com/account/keys
PLAID_CLIENT_ID = os.getenv('PLAID_CLIENT_ID')
PLAID_SECRET = os.getenv('PLAID_SECRET')
PLAID_PUBLIC_KEY = os.getenv('PLAID_PUBLIC_KEY')


# Use 'sandbox' to test with Plaid's Sandbox environment (username: user_good,
# password: pass_good)
# Use `development` to test with live users and credentials and `production`
# to go live
PLAID_ENV = os.getenv('PLAID_ENV', 'sandbox')
# PLAID_PRODUCTS is a comma-separated list of products to use when initializing
# Link. Note that this list must contain 'assets' in order for the app to be
# able to create and retrieve asset reports.
PLAID_PRODUCTS = os.getenv('PLAID_PRODUCTS', 'transactions')

# PLAID_COUNTRY_CODES is a comma-separated list of countries for which users
# will be able to select institutions from.
PLAID_COUNTRY_CODES = os.getenv('PLAID_COUNTRY_CODES', 'US')

# Parameters used for the OAuth redirect Link flow.
#
# Set PLAID_OAUTH_REDIRECT_URI to 'http://localhost:5000/oauth-response.html'
# The OAuth redirect flow requires an endpoint on the developer's website
# that the bank website should redirect to. You will need to whitelist
# this redirect URI for your client ID through the Plaid developer dashboard
# at https://dashboard.plaid.com/team/api.
PLAID_OAUTH_REDIRECT_URI = os.getenv('PLAID_OAUTH_REDIRECT_URI', '')
# Set PLAID_OAUTH_NONCE to a unique identifier such as a UUID for each Link
# session. The nonce will be used to re-open Link upon completion of the OAuth
# redirect. The nonce must be at least 16 characters long.
PLAID_OAUTH_NONCE = os.getenv('PLAID_OAUTH_NONCE', '')

client = plaid.Client(client_id = PLAID_CLIENT_ID, secret=PLAID_SECRET,
                      public_key=PLAID_PUBLIC_KEY, environment=PLAID_ENV, api_version='2019-05-29')


def format_error(e):
  return {'error': {'display_message': e.display_message, 'error_code': e.code, 'error_type': e.type, 'error_message': e.message } }

@app.route("/")
@login_required
def index():
    """ Get the account info. """
    # Get the user's firstname to display on dashboard 
    users = db.execute("SELECT firstname FROM users WHERE id = :user_id", user_id = session["user_id"])

    # institutions:
    #     [ { 
    #         institution_name: <>, 
    #         institution_id: <>, 
    #         total_balance: <>, 
    #         accounts: [ { official_name: <>, ... } ] 
    #      } ]
    institutions = db.execute("SELECT institution_name, institution_id, timestamp FROM financial_institution WHERE user_id = :user_id ORDER BY institution_name", user_id = session["user_id"] )

    for institution in institutions:
        accounts = db.execute("SELECT official_name, mask, type, current_balance FROM accounts WHERE user_id = :user_id AND institution_id = :institution_id", 
                              user_id = session["user_id"],
                              institution_id = institution['institution_id'] )
        institution['accounts'] = accounts

        institution['total_balance'] = sum( account['current_balance'] for account in accounts )
        

    total_balance = sum (institution['total_balance'] for institution in institutions)

    return render_template("index.html", 
                            institutions=institutions,
                            user=users[0],
                            total_balance = total_balance,
                            plaid_public_key=PLAID_PUBLIC_KEY)

# Exchange token flow - exchange a link public_token for
# an API access_token
# https://plaid.com/docs/#exchange-token-flow
@app.route('/register_access_token', methods=['POST'])
@login_required
def register_access_token():
    public_token = request.form['public_token']

    exchange_response = client.Item.public_token.exchange(public_token)
    
    # ACCESS TOKEN 
    access_token = exchange_response['access_token']
    session["access_token"] = access_token

    # LOOKUP INSTITUION ID & NAME 

    item_response = client.Item.get(access_token)
    institution_response = client.Institutions.get_by_id(item_response['item']['institution_id'])

    # Put access token and bank information in the financial institution table associated with the user_id
    db.execute("INSERT INTO financial_institution (user_id, access_token, institution_id, institution_name) VALUES (:user_id, :access_token, :institution_id, :institution_name)",
                user_id = session["user_id"],
                access_token = access_token,
                institution_id = item_response['item']['institution_id'],
                institution_name = institution_response['institution']['name'])

    # ACCOUNT DATA             
    accounts_response = client.Accounts.get(access_token)

    # Put account data in the accounts table 
    for account in accounts_response['accounts']: 
        if account['subtype'] in ('checking', 'savings'):
            db.execute("INSERT INTO accounts (user_id, institution_id, account_id, available_balance, current_balance, iso_currency_code, mask, official_name, type) VALUES (:user_id, :institution_id, :account_id, :available_balance, :current_balance, :iso_currency_code, :mask, :official_name, :type)", 
                user_id = session["user_id"],
                institution_id = item_response['item']['institution_id'],
                account_id = account['account_id'],
                available_balance = account['balances']['available'],
                current_balance = account['balances']['current'],
                iso_currency_code = account['balances']['iso_currency_code'],
                mask = account['mask'],
                official_name = account['official_name'],
                type = account['subtype'])


            # Calculate the first day of last month 
            prev_month_firstday = datetime.date.today().replace( day=1 ) - relativedelta(months=1)
            start_date = prev_month_firstday.isoformat()

            # Calculate today's date 
            today = datetime.date.today()
            end_date = today.isoformat()

            # TRANSACTION DATA 
            transactions_response = client.Transactions.get(access_token, start_date, end_date, account_ids=[account['account_id']])

            for transaction in transactions_response['transactions']: 
                db.execute("INSERT INTO transactions (account_id, transaction_id, category, transaction_type, name, amount, iso_currency_code, date) VALUES (:account_id, :transaction_id, :category, :transaction_type, :name, :amount, :iso_currency_code, :date)",
                account_id = transaction['account_id'], 
                transaction_id = transaction['transaction_id'],
                category = transaction['category'][0],
                transaction_type = transaction['transaction_type'],
                name = transaction['name'],
                amount = transaction['amount'],
                iso_currency_code = transaction['iso_currency_code'],
                date = transaction['date'])

    return jsonify({})

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

        # INSERT the new user into users, firstname, lastname, storing a hash of the user’s password with generate_password_hash
        db.execute("INSERT INTO users (username, firstname, lastname, hash) VALUES (:username, :firstname, :lastname, :hash)",
                    username=request.form.get("username"),
                    firstname=request.form.get("firstname"),
                    lastname=request.form.get("lastname"),
                    hash=generate_password_hash(request.form.get("password")))
                 

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")


# def errorhandler(e):
#     """Handle error"""
#     if not isinstance(e, HTTPException):
#         e = InternalServerError()
#     return apology(e.name, e.code)


# # Listen for errors
# for code in default_exceptions:
#     app.errorhandler(code)(errorhandler)


