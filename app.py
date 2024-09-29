import sqlite3
import os
from flask import Flask, request, render_template, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import barcode
from openai import OpenAI
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY') or os.urandom(24)

BARCODE_LOOKUP_API_KEY = "0scxj47cz3cw68uxy3nobp7dlni9re"  

client = OpenAI(api_key=OPENAI_API_KEY)

def get_db():
    db = sqlite3.connect("users.db")
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)')
    db.execute('''CREATE TABLE IF NOT EXISTS characters 
                  (id INTEGER PRIMARY KEY AUTOINCREMENT,
                   username TEXT,
                   FOREIGN KEY (username) REFERENCES users(username))''')
    db.commit()
    db.close()
    
    alter_characters_table()

def alter_characters_table():
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("PRAGMA table_info(characters)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'about' not in columns:
        cursor.execute('ALTER TABLE characters ADD COLUMN about TEXT')
    
    if 'file' not in columns:
        cursor.execute('ALTER TABLE characters ADD COLUMN file TEXT')
    
    db.commit()
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
            ecomon = gen_character(number)
            print(ecomon)

            if ecomon == {}:
                return redirect(url_for('error'))
            else:
                file = ecomon.split()[-1]
                print(file)

                db = get_db()
                db.execute('INSERT INTO characters (username, about, file) VALUES (?, ?, ?)',
                            (session['username'], ecomon, file))
                db.commit()
                db.close()
        else:
            flash('Please enter a valid number.')
            return redirect(url_for('barcode'))
    
    return redirect(url_for('inventory'))

@app.route('/error', methods=['GET'])
def error():
    return render_template('error.html')

@app.route('/inventory', methods=['GET'])
def inventory():
    if 'username' not in session:
        flash('Please log in to view your inventory.')
        return redirect(url_for('login'))
    db = get_db()
    characters = db.execute('SELECT * FROM characters WHERE username = ?', (session['username'],)).fetchall()
    db.close()
    return render_template('inventory.html', characters=characters)
    
@app.route('/leaderboard', methods=['GET'])
def leaderboard():
    return render_template('leaderboard.html')

init_db()
if __name__ == '__main__':
    init_db()
    app.run(debug=True)

def get_product_info(barcode_number):
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
                'description': product.get('description', 'No description available')
            }
    
    print("Debug: Product not found or error occurred")
    return None

def process_barcode(barcode_number):
    return get_product_info(barcode_number)

def format_llm_input(product_info):
    current_date = datetime.now().strftime("%B %d, %Y")
    return f"""Generate an EcoMon character based on this product:
Product Name: {product_info['name']}
Product Description: {product_info['description']}

Rules:
1. Type: water->Water, soda->Fire, energy->Air, other->Earth
2. Size: <16oz -> evolution 1, ≥16oz -> evolution 2 (default: evolution 1)
3. Names:
   Water: aquadrop/splashfin (1), aquashade/tidalfin (2)
   Fire: flarepaw/emberkit (1), inferpaw/blazetail (2)
   Earth: mudding/terrafig (1), geobark/terragrowl (2)
   Air: draftwing/whispsky (1), gustdrift/stormgleam (2)
4. You most only use the names provided. Do not make new names.

Generate an EcoMon for the given product in this exact format:
EcoMon: [Name] ([Type], evolution [Level])
About: Hatched on {current_date}. [Name] is a [Type]-type EcoMon known for its abilities: [Ability 1] and [Ability 2]. [One unique detail].
Hatched From: [Product Name]
[Name].jpeg

Ensure you follow the format exactly, including the .jpeg filename at the end. Also make sure you put an empty line between each characteristic. Be sure you only specify the file name as only one singular ecomon name, not two."""

def query_gpt(input_text):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a creative assistant that generates EcoMon characters based on product information."},
                {"role": "user", "content": input_text}
            ],
            max_tokens=300,
            n=1,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error querying GPT-3.5-turbo: {e}")
        return None

def gen_character(barcode_input):
    result = process_barcode(barcode_input)
    print(result)

    if result: 
        llm_input = format_llm_input(result)
        ecomon_character = query_gpt(llm_input)
        
        if ecomon_character:
            print("\nEcoMon Character Generated Successfully:")
            return ecomon_character
        else:
            print("Failed to generate EcoMon character. Please try again.")
    else: 
        print("Product not found or invalid barcode number. Please try again.")
    return {}
