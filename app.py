import sqlite3
import os
from flask import Flask, request, render_template, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import barcode

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY') or os.urandom(24)

BARCODE_LOOKUP_API_KEY = "0scxj47cz3cw68uxy3nobp7dlni9re"  

def get_db():
    db = sqlite3.connect("users.db")
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)')
    db.close()

@app.route('/')
def home():
    if 'username' in session:
        return render_template('home.html')

    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if user:
            flash('Username already exists')
        else:
            db.execute('INSERT INTO users (username, password) VALUES (?, ?)',
                       (username, generate_password_hash(password)))
            db.commit()
            flash('Account created successfully')
            return redirect(url_for('login'))
        
        db.close()
    
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if user and check_password_hash(user['password'], password):
            session['username'] = username
            db.close()
            return redirect(url_for('home'))
        
        flash('Invalid username or password')
        db.close()
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('home'))

@app.route('/barcode', methods=['GET', 'POST'])
def barcode():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('barcode.html')

@app.route('/character', methods=['GET', 'POST'])
def character():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        number = request.form.get('number')
        if number:
            info = get_barcode_info(number)
            print()
            print(info)
        else:
            flash('Please enter a valid number.')
            return redirect(url_for('barcode'))
    
    return render_template('character.html')

def get_barcode_info(barcode_number):
    url = f"https://api.barcodelookup.com/v3/products?barcode={barcode_number}&formatted=y&key={BARCODE_LOOKUP_API_KEY}"
    print(f"Debug: Sending request to Barcode Lookup API")
    response = requests.get(url)
    
    print(f"Debug: Received response with status code {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        if 'products' in data and len(data['products']) > 0:
            product = data['products'][0]
            print("Debug: Product found")
            return {
                'name': product.get('title', 'Unknown'),
                'size': product.get('size', 'Unknown size'),
                'description': product.get('description', 'No description available')
            }
    
    print("Debug: Product not found or error occurred")
    return {}

init_db()
if __name__ == '__main__':
    init_db()
    app.run(debug=True)