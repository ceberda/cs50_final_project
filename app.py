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
from retry import retry

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
DB = None 

def get_db():
    ''' Get the DB connection the first time we need it. '''
    global DB
    if not DB:
        DB = SQL("sqlite:///finance_mgmt.db")
    return DB

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
    users = get_db().execute("SELECT firstname FROM users WHERE id = :user_id", user_id = session["user_id"])

    # institutions:
    #     [ { 
    #         institution_name: <>, 
    #         institution_id: <>, 
    #         total_balance: <>, 
    #         accounts: [ { official_name: <>, ... } ] 
    #      } ]
    institutions = get_db().execute("SELECT institution_name, institution_id, timestamp FROM financial_institution WHERE user_id = :user_id ORDER BY institution_name", user_id = session["user_id"] )

    for institution in institutions:
        accounts = get_db().execute("SELECT official_name, mask, type, current_balance FROM accounts WHERE user_id = :user_id AND institution_id = :institution_id", 
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

@retry(plaid.errors.ItemError, tries=10, delay=5)
def _retrying_get_transactions(access_token, start_date, end_date, account_id):
    ''' The test accounts in Plaid sometimes 'aren't ready' so we wait a bit and try again. '''
    return client.Transactions.get(access_token, start_date, end_date, account_ids=[account_id])
    

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
    get_db().execute("INSERT INTO financial_institution (user_id, access_token, institution_id, institution_name) VALUES (:user_id, :access_token, :institution_id, :institution_name)",
                user_id = session["user_id"],
                access_token = access_token,
                institution_id = item_response['item']['institution_id'],
                institution_name = institution_response['institution']['name'])

    # ACCOUNT DATA             
    accounts_response = client.Accounts.get(access_token)

    # Put account data in the accounts table 
    for account in accounts_response['accounts']: 
        if account['subtype'] in ('checking', 'savings'):
            get_db().execute("INSERT INTO accounts (user_id, institution_id, account_id, available_balance, current_balance, iso_currency_code, mask, official_name, type) VALUES (:user_id, :institution_id, :account_id, :available_balance, :current_balance, :iso_currency_code, :mask, :official_name, :type)", 
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
            transactions_response = _retrying_get_transactions(access_token, start_date, end_date, account['account_id'])

            for transaction in transactions_response['transactions']: 
                get_db().execute("INSERT INTO transactions (account_id, transaction_id, category, transaction_type, name, amount, iso_currency_code, date) VALUES (:account_id, :transaction_id, :category, :transaction_type, :name, :amount, :iso_currency_code, :date)",
                account_id = transaction['account_id'], 
                transaction_id = transaction['transaction_id'],
                category = transaction['category'][0],
                transaction_type = transaction['transaction_type'],
                name = transaction['name'],
                amount = transaction['amount'] * -1, # Amount returned from Plaid is settled dollar value.  Positive values when money moves out of the account; negative values when money moves in.  For Jesse the data should be represented the opposite way, so * -1
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
        rows = get_db().execute("SELECT * FROM users WHERE username = :username",
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


@app.route("/transactions", methods=["GET"])
@login_required
def transactions():
    transactions = get_db().execute("""
        SELECT financial_institution.institution_name, accounts.official_name, accounts.mask, 
                transactions.amount, transactions.name, transactions.date 
        FROM transactions 
        JOIN accounts on accounts.account_id = transactions.account_id 
        JOIN financial_institution on financial_institution.institution_id = accounts.institution_id 
        WHERE financial_institution.user_id = :user_id 
        ORDER BY transactions.date DESC
    """, user_id = session["user_id"] )
        
    return render_template("transactions.html", transactions=transactions )

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
        elif len( get_db().execute("SELECT * FROM users WHERE username = :username",
                        username=request.form.get("username")) ) > 0:
            return apology("username already exist", 400)

        # Passwords do not match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords do not match", 400)

        # INSERT the new user into users, firstname, lastname, storing a hash of the user’s password with generate_password_hash
        get_db().execute("INSERT INTO users (username, firstname, lastname, hash) VALUES (:username, :firstname, :lastname, :hash)",
                    username=request.form.get("username"),
                    firstname=request.form.get("firstname"),
                    lastname=request.form.get("lastname"),
                    hash=generate_password_hash(request.form.get("password")))
        

        # Query database for username
        rows = get_db().execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # GET list of categories from Plaid
        categories = client.Categories.get()                 
        top_level_categories = list( set( sorted( category['hierarchy'][0] for category in categories['categories'] ) ) )

        # when user regristers for the first time, update budget table with categories 
        for category_name in top_level_categories:
            get_db().execute("INSERT INTO budget (user_id, category) VALUES (:user_id, :category)",
                        user_id = session["user_id"],
                        category = category_name )

        # Redirect user to home page
        return redirect("/")


@app.route("/budget", methods=["GET", "POST"])
@login_required
def budget():
    if request.method == "GET":

        # Calculate the first day of last month 
        prev_month_firstday = datetime.date.today().replace( day=1 ) - relativedelta(months=1)
        
        # Calculate the last day of the month 
        prev_month_lastday = datetime.date.today().replace( day=1 ) - relativedelta(days=1)
        
        budgets = get_db().execute("""
            SELECT budget.category, 
                   budget_summary.month_total * -1 as month_total, 
                   budget.amount as budget_amount
            FROM budget
            LEFT OUTER JOIN ( 
                SELECT category, sum(amount) as month_total
                FROM transactions
                JOIN accounts on accounts.account_id = transactions.account_id 
                WHERE 
                    accounts.user_id = :user_id AND
                    transactions.date >= :prev_month_firstday  AND
                    transactions.date <= :prev_month_lastday 
                GROUP BY transactions.category ) as budget_summary
            ON budget_summary.category = budget.category
            WHERE budget.user_id = :user_id
            ORDER BY budget.category
        """, 
        user_id = session["user_id"], 
        prev_month_firstday=prev_month_firstday.isoformat(),
        prev_month_lastday=prev_month_lastday.isoformat())

        active_accounts = get_db().execute( """
            SELECT account_id 
            FROM accounts 
            WHERE user_id = :user_id
        """, user_id=session["user_id"])

        return render_template("budget.html", 
                                active_accounts=active_accounts,
                                prev_month_firstday=prev_month_firstday,
                                budgets=budgets)

    if request.method == "POST":
        
        for category, budget_amount in request.form.items():
            if budget_amount:
                budget_amount = float(budget_amount)
            else: 
                budget_amount = None

            get_db().execute( """
                UPDATE budget 
                SET amount =:budget_amount 
                WHERE user_id = :user_id AND category = :category
            """, category=category, user_id=session["user_id"], budget_amount=budget_amount )

        return redirect("/budget")

# def errorhandler(e):
#     """Handle error"""
#     if not isinstance(e, HTTPException):
#         e = InternalServerError()
#     return apology(e.name, e.code)


# # Listen for errors
# for code in default_exceptions:
#     app.errorhandler(code)(errorhandler)

if __name__ == "__main__":
    app.run(threaded=False)