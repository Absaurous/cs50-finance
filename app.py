import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # From users, select cash balance. Note: db.exec returns a list(array) of dicts(key, pair values)
    user_data = db.execute("SELECT cash, username FROM users WHERE id == (?)",
                           session["user_id"])[0]
    total = user_data["cash"]

    # From holdings, select symbol, quantity
    if db.execute("SELECT COUNT(*) as count FROM holdings WHERE person_id == (?)", session["user_id"])[0]['count'] == 0:
        return render_template("homepage.html", user_data=user_data, total=total)
    updated = db.execute("SELECT * FROM holdings WHERE person_id == (?)", session["user_id"])

    # Through lookup, get current price/share
    unit_price = (lookup(updated[0]['symbol']))

    for row in updated:
        total += row["price"] * row["quantity"]

    return render_template("homepage.html", values=updated, user_data=user_data, price=unit_price, total=total)


# CONSIDER WHETHER I NEED CERTAIN COLUMNS IN HOLDINGS


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))
        quantity = request.form.get("shares")

        # if stock doesnt exist or blank symbol
        if stock is None or not stock:
            return apology("invalid stock", 400)

        # if quantity contains letters
        if not quantity.isnumeric():
            return apology("invalid quantity", 400)
        # if quantity is a decimal
        elif not float(quantity).is_integer():
            return apology("invalid quantity", 400)
        # if quantity is 0 or negative
        elif int(quantity) < 1:
            return apology("invalid quantity", 400)

        total_cost = stock["price"] * float(quantity)
        balance = int(db.execute("SELECT cash FROM users WHERE id == (?)",
                      session["user_id"])[0]["cash"])

        # if balance is insufficient, error
        if total_cost > balance:
            return apology("Insufficient funds")

        # Deduct price of stocks bought from cash balance
        db.execute("UPDATE users SET cash = (?) WHERE id = (?)",
                   balance - total_cost, session["user_id"])

        # If user is already holding similar type of stocks, update the qty instead of inserting, LIKE?
        if db.execute("SELECT * FROM holdings WHERE symbol == (?) AND person_id == (?)", stock["symbol"], session["user_id"]):
            db.execute("UPDATE holdings SET quantity = quantity + (?) WHERE symbol == (?)",
                       quantity, stock["symbol"])
        # If user does not hold this stock, insert to make a new row
        else:
            db.execute("INSERT INTO holdings(person_id, symbol, price, quantity, total_value) VALUES(?, ?, ?, ?, ?)",
                       session["user_id"], stock["symbol"], stock["price"], quantity, total_cost)

        # Update purchase history of website
        now = datetime.now()
        db.execute("INSERT INTO history(person_id, symbol, price, quantity, total_value, status, date_time) VALUES(?, ?, ?, ?, ?, ?, ?)",
                   session["user_id"], stock["symbol"], stock["price"], quantity, total_cost, "BUY", now.strftime('%a %d %b %Y, %I:%M%p'))

        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_data = db.execute("SELECT cash, username FROM users WHERE id == (?)",
                           session["user_id"])[0]

    # From holdings, select symbol, quantity
    if db.execute("SELECT COUNT(*) as count FROM history WHERE person_id == (?)", session["user_id"])[0]['count'] == 0:
        return render_template("history.html", user_data=user_data)

    # bought or sold, symbol, price, the number of shares bought or sold, and the date and time at which the transaction occurred.
    records = db.execute("SELECT * FROM history WHERE person_id == (?)", session["user_id"])

    return render_template("history.html", values=records, user_data=user_data)


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
        rows = db.execute(
            "SELECT * FROM users WHERE username = (?)", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
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


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        results = lookup(request.form.get("symbol"))

        # in case of misspelling or blank search
        if not results:
            return apology("invalid search result", 400)

        # embedding results from lookup into html
        return render_template("quoted.html", results=results)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # if wrongly keyed in confirmation OR blank password
        if password != confirmation or not password:
            return apology("passwords do not match", 400)
        # if username blank
        elif not username:
            return apology("username is blank", 400)
        else:
            # if username is already taken
            if db.execute("SELECT * FROM users WHERE username == (?)", username):
                return apology("username taken", 400)
            else:
                hash = generate_password_hash(password)
                db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, hash)
                return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        stock = request.form.get('symbol')
        quantity = int(request.form.get("shares"))

        # returns a list of dicts with key of symbol and different values
        dict = db.execute("SELECT symbol FROM holdings WHERE person_id == (?)", session["user_id"])

        # extracts values from the list of dicts into a list
        stocks = [row['symbol'] for row in dict]

        # Invalid stock selected not present in holdings
        if stock in stocks:
            # Invalid quantity requested
            if quantity <= db.execute("SELECT quantity FROM holdings WHERE person_id == (?)AND symbol == (?)", session["user_id"], stock)[0]["quantity"]:

                total_value = lookup(stock)['price'] * quantity

                # Update qty in holdings
                db.execute("UPDATE holdings SET quantity = quantity - (?)WHERE person_id = (?)AND symbol == (?)",
                           quantity, session["user_id"], stock)

                # Update history
                now = datetime.now()
                db.execute("INSERT INTO history(person_id, symbol, price, quantity, total_value, status, date_time) VALUES(?, ?, ?, ?, ?, ?, ?)",
                           session["user_id"], stock, lookup(stock)["price"], quantity, total_value, "SELL", now.strftime('%a %d %b %Y, %I:%M%p'))

                # Update cash in users
                db.execute("UPDATE users SET cash = cash + (?) WHERE id = (?)",
                           total_value, session["user_id"])

                # If after being sold, qty reaches 0, delete from table
                if db.execute("SELECT quantity FROM holdings WHERE person_id == (?) AND symbol == (?)", session["user_id"], stock)[0]["quantity"] <= 0:
                    db.execute(
                        "DELETE FROM holdings WHERE quantity == 0 AND person_id == (?)", session["user_id"])
                return redirect("/")
            else:
                return apology("Invalid Quantity Requested")
        else:
            return apology("Invalid Stock")
        # set a limit on the amount reques TODOOOOOOOOOOOOOOOOOOOOO

    else:
        assets = db.execute(
            "SELECT symbol FROM holdings WHERE person_id == (?)", session["user_id"])
        return render_template("sell.html", assets=assets)


@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    """Deposit money into account"""
    if request.method == "POST":
        deposit = request.form.get('deposit')

        # if deposit is blank, contains letters, negatives/0, exceeds maximum
        if not deposit or not deposit.isnumeric() or int(deposit) <= 0 or int(deposit) > 10000:
            return apology("invalid deposit")

        # update cash in users
        db.execute("UPDATE users SET cash = cash + (?) WHERE id = (?)",
                   float(deposit), session["user_id"])

        return redirect("/")
    else:
        # show current cash in account, from users
        user_data = db.execute("SELECT cash FROM users WHERE id == (?)", session["user_id"])[0]
        balance = user_data["cash"]

        return render_template("deposit.html", balance=balance)

# person_id (foreign key), symbol, qty, price per stock, total -- holdings
# person_id (foreign key), symbol, bought/sold, qty, price per stock, total, date time -- history
# each person has 1 table for personal holdings and there is a universal history table
# holdings will be used for any calculations and history is purely for logs
