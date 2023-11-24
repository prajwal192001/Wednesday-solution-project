import os, requests

from flask import Flask, session, render_template, request, redirect, logging, url_for, flash, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from passlib.hash import sha256_crypt

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

#index route
@app.route("/")
def index():
    return render_template("home.html")

#register form
@app.route("/register", methods=['GET', 'POST'])
def register():
    if request.method == "POST":
        fullname = request.form.get("fullname")
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        confirmpass = request.form.get("confirmpass")
        secure_password = sha256_crypt.encrypt(str(password))

        if db.execute("SELECT username FROM users WHERE username = :username",{"username": username }).fetchone() :
            flash("Sorry! this username is already taken", "danger")
            return render_template("register.html")
        
        if password==confirmpass:
            db.execute("INSERT INTO users(fullname, username, email, password) VALUES(:fullname, :username, :email, :password)",{
                "fullname": fullname,
                "username": username,
                "email": email,
                "password": secure_password
            })
            db.commit()
            flash("You are registered, Please login with your username and password to continue","success")
            return redirect(url_for('login'))
        else:
            flash("Passwords does not match", "danger")
            return render_template("register.html")

    return render_template("register.html")

#login form
@app.route("/login", methods = ['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get("username")
        password = request.form.get("password")
        
        usernamedata = db.execute("SELECT id,username,password FROM users WHERE username = :username",{"username": username}).fetchone()
    
        if usernamedata is None:
            flash("No username found, enter correct username or please register if you haven't.", "danger")
            return render_template("loginpage.html")
        else:
            password_data = usernamedata.password
            if sha256_crypt.verify(password,password_data):
                session["log"]=True
                session["user_id"] = usernamedata.id
                session["username"] = usernamedata.username
                flash("Your are now logged in", "success")
                return redirect(url_for('books'))
            else: 
                flash("You entered an incorrect password", "danger")
                return render_template("loginpage.html")
    return render_template("loginpage.html")

#logout route
@app.route("/logout")
def logout():
    session.clear()
    flash("You have successfuly logged out, press on Knowbooks to return home page", "success")
    return render_template("home.html")
                    
#books from database                
@app.route("/books")                    
def books():
    books = db.execute("SELECT isbn,title,author FROM books ORDER BY title ASC ")
    return render_template("books.html", books=books)

#searching books and showing matching results
@app.route("/search", methods = ['POST'])
def search():
    option = request.form.get('options') 
    search = request.form.get("search")   
    if option=="isbn":        
        books_srch = db.execute("SELECT * FROM books WHERE isbn= :isbn", {"isbn": search}).fetchall()        
        if db.execute("SELECT * FROM books WHERE isbn= :isbn", {"isbn": search}).rowcount==0:
            flash("No matches found", 'danger')
            return render_template("books.html")
        return render_template("searchresult.html", books_srch=books_srch)
    
    elif option=="title":        
        books_srch = db.execute("SELECT * FROM books WHERE title ILIKE :title ",{"title": '%' + search + '%'}).fetchall()
        if db.execute("SELECT * FROM books WHERE title ILIKE :title ",{"title": '%' + search + '%'}).rowcount==0:
            flash("No matches found", 'danger')
            return render_template("books.html")
        return render_template("searchresult.html", books_srch=books_srch)

    elif option=="author":
        books_srch = db.execute("SELECT * FROM books WHERE author ILIKE :author ",{"author": '%' + search + '%'}).fetchall()
        if db.execute("SELECT * FROM books WHERE author ILIKE :author ",{"author": '%' + search + '%'}).rowcount==0:
            flash("No matches found", 'danger')
            return render_template("books.html")
        return render_template("searchresult.html", books_srch=books_srch)

    elif option=="year":
        try:
            search = int(search)
        except ValueError:
            flash("Enter only numbers in year field","danger")
            return redirect(url_for('books'))
        books_srch = db.execute("SELECT * FROM books WHERE year=:year ",{"year": search}).fetchall()
        
        if db.execute("SELECT * FROM books WHERE year=:year ",{"year": search}).rowcount==0:
            flash("No matches found", 'danger')
            return render_template("books.html")
        return render_template("searchresult.html", books_srch=books_srch)

    else:
        flash("You need to select an option ", "danger")
        return redirect(url_for('books'))

#book details with goodreads api reviews and user reviews
@app.route("/book/<string:book_isbn>", methods = ['GET','POST'])
def book(book_isbn):
    book = db.execute("SELECT * FROM books WHERE isbn = :isbn",{"isbn":book_isbn}).fetchone()

    reviews_book = db.execute("SELECT fullname,review,rating FROM users JOIN reviews ON reviews.user_id = users.id WHERE book_id = :book_id",{
        "book_id":book.id
    }).fetchall()
    
    if request.method=='POST':
        review = request.form.get("review")
        rating = request.form.get("rating")
        if db.execute("SELECT review,rating FROM reviews WHERE user_id=:user_id AND book_id=:book_id",{"user_id":session["user_id"], "book_id":book.id}).rowcount==0:
            db.execute("INSERT INTO reviews (review,rating,book_id,user_id) VALUES(:review, :rating, :book_id, :user_id)",{
            "review": review,
            "rating": rating,
            "book_id": book.id,
            "user_id": session["user_id"]
                })
            db.commit()
            flash("Review submitted", "success")
            return redirect(url_for('book', book_isbn=book.isbn))
        else:
            flash("You have already reviewed this book","danger")
            return redirect(url_for('book', book_isbn=book.isbn))


    if not os.getenv("GOODREADS_KEY"):
        raise RuntimeError("GOODREADS_KEY is not set")
    key = os.getenv("GOODREADS_KEY")
    res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": key, "isbns": book_isbn})
    data = res.json()
    work_ratings_count = data["books"][0]["work_ratings_count"]
    work_reviews_count = data["books"][0]["work_reviews_count"]
    average_rating = data["books"][0]["average_rating"]
    bookcover = "http://covers.openlibrary.org/b/ISBN/{}-L.jpg".format(book_isbn)    

    return render_template("book.html",book=book,bookcover=bookcover,reviews_book=reviews_book,work_ratings_count=work_ratings_count, work_reviews_count=work_reviews_count, average_rating=average_rating)

#api route
@app.route("/api/<book_isbn>")
def book_api(book_isbn):
    book = db.execute("SELECT * FROM BOOKS WHERE isbn = :isbn",{"isbn": book_isbn}).fetchone()

    #Checking for isbn existance
    if book is None:
        return jsonify({"error": "ISBN not found"}), 404

        
    if not os.getenv("GOODREADS_KEY"):
        raise RuntimeError("GOODREADS_KEY is not set")
    key = os.getenv("Goodreads_key")
    #Getting data from goodreads api
    res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": key, "isbns": book_isbn})
    data = res.json()
    review_count = data["books"][0]["work_reviews_count"]
    average_score = data["books"][0]["average_rating"]

    return jsonify({
        "isbn": book.isbn,
        "titile": book.title,
        "author": book.author,
        "year": book.year,
        "review_count": review_count,
        "average_score": average_score
    })
