from flask import Flask, render_template, request, redirect, session, flash, url_for
from flask_mail import Mail, Message
import sqlite3
import bcrypt
import random
import config
import os
from werkzeug.utils import secure_filename
import razorpay
from flask import make_response
import uuid
from datetime import datetime
from utils.pdf_generator import generate_pdf
from flask import jsonify


app = Flask(__name__)
app.secret_key = config.SECRET_KEY

app.config['SESSION_PERMANENT'] = False

razorpay_client = razorpay.Client(
    auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET)
)

# Product images (already exists)
UPLOAD_FOLDER = 'static/uploads/product_images'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ADMIN_UPLOAD_FOLDER = 'static/uploads/admin_profiles'
app.config['ADMIN_UPLOAD_FOLDER'] = ADMIN_UPLOAD_FOLDER

# ---------------- EMAIL CONFIG ----------------
app.config['MAIL_SERVER'] = config.MAIL_SERVER
app.config['MAIL_PORT'] = config.MAIL_PORT
app.config['MAIL_USE_TLS'] = config.MAIL_USE_TLS
app.config['MAIL_USERNAME'] = config.MAIL_USERNAME
app.config['MAIL_PASSWORD'] = config.MAIL_PASSWORD

mail = Mail(app)


# ---------------- DB CONNECTION ----------------

def get_db_connection():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def home():
    if session.get('admin_id'):
        return redirect('/admin-dashboard')

    if session.get('user_id'):
        return redirect('/user-dashboard')

    return render_template("index.html")

# ================= ABOUT PAGE =================
@app.route('/about')
def about():
    return render_template('about.html')


# ================= CONTACT PAGE =================
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        message = request.form['message']

        print(name, email, phone, message)  # you can store later

        flash("Message sent successfully!", "success")
        return redirect('/contact')

    return render_template('contact.html')


# =========================================================
# DAY 2 — ADMIN SIGNUP + OTP
# =========================================================
@app.route('/admin-signup', methods=['GET', 'POST'])
def admin_signup():

    if request.method == "GET":
        return render_template("admin/admin_signup.html")

    name = request.form['name']
    email = request.form['email']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM admin WHERE email=?", (email,))
    existing = cursor.fetchone()

    cursor.close()
    conn.close()

    if existing:
        flash("Email already exists!", "danger")
        return redirect('/admin-signup')

    otp = random.randint(100000, 999999)

    session['admin_name'] = name
    session['admin_email'] = email
    session['admin_otp'] = otp

    msg = Message(
        subject="SmartCart Admin OTP",
        sender=config.MAIL_USERNAME,
        recipients=[email]
    )
    msg.body = f"Your OTP is: {otp}"
    mail.send(msg)

    flash("OTP sent!", "success")
    return redirect('/admin-verify-otp')

# ---------------- OTP PAGE ----------------
@app.route('/verify-otp', methods=['GET'])
def otp_page():
    return render_template("admin/verify_otp.html")


# ---------------- VERIFY OTP ----------------
@app.route('/admin-verify-otp', methods=['GET', 'POST'])
def admin_verify_otp():

    if request.method == 'GET':
        return render_template("admin/admin_verify_otp.html")

    user_otp = request.form['otp']

    if str(session.get('admin_otp')) != str(user_otp):
        flash("Invalid OTP", "danger")
        return redirect('/admin-verify-otp')

    name = session.get('admin_name')
    email = session.get('admin_email')

    if not name or not email:
        flash("Session expired! Please signup again.", "danger")
        return redirect('/admin-signup')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO admin (name,email) VALUES (?,?)",
        (name, email)
    )
    conn.commit()

    cursor.close()
    conn.close()

    # clear ONLY OTP session (IMPORTANT)
    session.pop('admin_otp', None)
    session.pop('admin_name', None)
    session.pop('admin_email', None)

    flash("Admin registered successfully!", "success")
    return redirect('/admin-login')

@app.route('/admin-resend-otp')
def admin_resend_otp():

    email = session.get('admin_email')
    name = session.get('admin_name')

    if not email or not name:
        flash("Session expired! Please signup again.", "danger")
        return redirect('/admin-signup')

    otp = random.randint(100000, 999999)
    session['admin_otp'] = otp

    msg = Message(
        subject="SmartCart Admin OTP (Resend)",
        sender=config.MAIL_USERNAME,
        recipients=[email]
    )
    msg.body = f"Your OTP is: {otp}"
    mail.send(msg)

    flash("OTP resent successfully!", "success")
    return redirect('/admin-verify-otp')

# =========================================================
# DAY 3 — ADMIN LOGIN + SESSION
# =========================================================
@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():

    if session.get('admin_id'):
        return redirect('/admin-dashboard')

    if request.method == 'GET':
        return render_template("admin/admin_login.html")

    if request.method == 'GET':
        return render_template("admin/admin_login.html")

    email = request.form['email']
    password = request.form['password']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM admin WHERE email=?", (email,))
    admin = cursor.fetchone()

    cursor.close()
    conn.close()

    # ✅ FIX 1: ADMIN NOT FOUND CHECK
    if not admin:
        flash("Admin not found!", "danger")
        return redirect('/admin-login')

    stored_hash = admin['password']

    # ✅ FIX 2: PASSWORD NOT SET CHECK
    if not stored_hash:
        flash("Password not set for this admin!", "danger")
        return redirect('/admin-login')

    # convert safely
    if isinstance(stored_hash, str):
        stored_hash = stored_hash.encode('utf-8')

    # ✅ CHECK PASSWORD SAFELY
    if not bcrypt.checkpw(password.encode('utf-8'), stored_hash):
        flash("Wrong password!", "danger")
        return redirect('/admin-login')

    # SESSION CREATE
    session['admin_id'] = admin['admin_id']
    session['admin_name'] = admin['name']
    session['admin_email'] = admin['email']

    flash("Login Successful!", "success")
    return redirect('/admin-dashboard')

@app.route('/admin/profile', methods=['GET'])
def admin_profile():

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    admin_id = session['admin_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM admin WHERE admin_id=?", (admin_id,))
    admin = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template("admin/admin_profile.html", admin=admin)

#ADMIN PROFILE

@app.route('/admin/profile', methods=['POST'])
def admin_profile_update():

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    admin_id = session['admin_id']

    name = request.form['name']
    email = request.form['email']
    new_password = request.form['password']
    new_image = request.files['profile_image']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM admin WHERE admin_id=?", (admin_id,))
    admin = cursor.fetchone()

    old_image = admin['profile_image']

    # Password
    if new_password:
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
    else:
        hashed_password = admin['password']

    # Image
    if new_image and new_image.filename != "":
        filename = secure_filename(new_image.filename)
        path = os.path.join(app.config['ADMIN_UPLOAD_FOLDER'], filename)
        new_image.save(path)

        if old_image:
            old_path = os.path.join(app.config['ADMIN_UPLOAD_FOLDER'], old_image)
            if os.path.exists(old_path):
                os.remove(old_path)

        final_image = filename
    else:
        final_image = old_image

    # Update DB
    cursor.execute("""
        UPDATE admin
        SET name=?, email=?, password=?, profile_image=?
        WHERE admin_id=?
    """, (name, email, hashed_password, final_image, admin_id))

    conn.commit()
    cursor.close()
    conn.close()

    session['admin_name'] = name
    session['admin_email'] = email
    session['admin_image'] = final_image

    flash("Profile updated successfully!", "success")
    return redirect('/admin/profile')

#ENTER EMAIL + SEND OTP

@app.route('/admin-forgot-password', methods=['GET', 'POST'])
def admin_forgot_password():

    if request.method == 'GET':
        return render_template("admin/admin_forgot_password.html")

    email = request.form['email']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM admin WHERE email=?", (email,))
    admin = cursor.fetchone()

    cursor.close()
    conn.close()

    if not admin:
        flash("Email not found!", "danger")
        return redirect('admin/admin-forgot-password')

    otp = random.randint(100000, 999999)

    session['reset_email'] = email
    session['reset_otp'] = otp

    msg = Message(
        subject="Password Reset OTP",
        sender=config.MAIL_USERNAME,
        recipients=[email]
    )
    msg.body = f"Your OTP is: {otp}"
    mail.send(msg)

    flash("OTP sent to your email!", "success")
    return redirect('/admin-verify-reset-otp')

#VERIFY PASS
@app.route('/admin-verify-reset-otp', methods=['GET', 'POST'])
def admin_verify_reset_otp():

    if request.method == 'GET':
        return render_template("admin/admin_verify_otp.html")

    user_otp = request.form['otp']

    if str(user_otp) != str(session.get('reset_otp')):
        flash("Invalid OTP!", "danger")
        return redirect('/admin-verify-reset-otp')

    return redirect('/admin-reset-password')


#RESET PASS
@app.route('/admin-reset-password', methods=['GET', 'POST'])
def admin_reset_password():

    if request.method == 'GET':
        return render_template("admin/admin_reset_password.html")

    password = request.form['password']
    confirm = request.form['confirm_password']

    if password != confirm:
        flash("Passwords do not match!", "danger")
        return redirect('/admin-reset-password')

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE admin SET password=? WHERE email=?",
        (hashed, session['reset_email'])
    )

    conn.commit()
    cursor.close()
    conn.close()

    session.pop('reset_email', None)
    session.pop('reset_otp', None)

    flash("Password reset successful! Please login.", "success")
    return redirect('/admin-login')

# ----------------ADMIN DASHBOARD ----------------
@app.route('/admin-dashboard')
def admin_dashboard():

    if 'admin_id' not in session:
        flash("Login required!", "danger")
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    # ADMIN INFO
    cursor.execute(
        "SELECT name, profile_image FROM admin WHERE admin_id=?",
        (session['admin_id'],)
    )
    admin = cursor.fetchone()

    # TOTAL PRODUCTS
    cursor.execute("SELECT COUNT(*) FROM products")
    total_products = cursor.fetchone()[0]

    # TOTAL USERS
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    # TOTAL ORDERS
    cursor.execute("SELECT COUNT(*) FROM orders")
    total_orders = cursor.fetchone()[0]

    # RECENT ORDERS (ONLY LAST 5)
    cursor.execute("""
        SELECT o.order_id, o.amount, o.order_status,
               u.name AS username
        FROM orders o
        LEFT JOIN users u ON o.user_id = u.user_id
        ORDER BY o.created_at DESC
        LIMIT 5
    """)
    recent_orders = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "admin/dashboard.html",
        admin_name=admin['name'] if admin else "Admin",
        admin_image=admin['profile_image'] if admin else None,
        total_products=total_products,
        total_users=total_users,
        total_orders=total_orders,
        recent_orders=recent_orders
    )
# ---------------- IMAGE UPLOAD CONFIG ----------------
UPLOAD_FOLDER = 'static/uploads/product_images'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# ================= SHOW ADD PRODUCT PAGE =================
@app.route('/admin/add-item', methods=['GET'])
def add_item_page():

    if 'admin_id' not in session:
        flash("Please login first!")
        return redirect('/admin-login')

    return render_template("admin/add_item.html")

# ================= HANDLE ADD PRODUCT =================
@app.route('/admin/add-item', methods=['POST'])
def add_item():

    if 'admin_id' not in session:
        flash("Please login first!")
        return redirect('/admin-login')

    name = request.form['name']
    description = request.form['description']
    category = request.form['category']
    price = request.form['price']
    image_file = request.files['image']

    if image_file.filename == "":
        flash("Please upload image!")
        return redirect('/admin/add-item')

    filename = secure_filename(image_file.filename)
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    image_file.save(image_path)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO products (name, description, category, price, image, admin_id) VALUES (?,?,?,?,?,?)",
        (name, description, category, price, filename, session['admin_id'])
    )

    conn.commit()
    cursor.close()
    conn.close()

    flash("Product added successfully!")
    return redirect('/admin/item-list')

# ================= VIEW ADMIN PRODUCTS =================
@app.route('/admin/item-list')
def item_list():

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    search = request.args.get('search', '')
    category_filter = request.args.get('category', '')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT category FROM products WHERE admin_id=?", (session['admin_id'],))
    categories = cursor.fetchall()

    query = "SELECT * FROM products WHERE admin_id=?"
    params = [session['admin_id']]

    if search:
        query += " AND name LIKE ?"
        params.append("%" + search + "%")

    if category_filter:
        query += " AND category=?"
        params.append(category_filter)

    cursor.execute(query, params)
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("admin/item_list.html", products=products, categories=categories)

# ================= DELETE PRODUCT (SECURE) =================
@app.route('/admin/delete-item/<int:item_id>')
def delete_item(item_id):

    if 'admin_id' not in session:
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM products WHERE product_id=? AND admin_id=?",
                   (item_id, session['admin_id']))
    product = cursor.fetchone()

    if not product:
        flash("Not authorized!", "danger")
        return redirect('/admin/item-list')

    image_path = os.path.join(app.config['UPLOAD_FOLDER'], product['image'])

    if os.path.exists(image_path):
        os.remove(image_path)

    cursor.execute("DELETE FROM products WHERE product_id=?", (item_id,))
    conn.commit()

    cursor.close()
    conn.close()

    flash("Deleted successfully!", "success")
    return redirect('/admin/item-list')


# ================= VIEW PRODUCT (SECURE) =================
@app.route('/admin/view-item/<int:item_id>')
def view_item(item_id):

    if 'admin_id' not in session:
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM products WHERE product_id=? AND admin_id=?",
                   (item_id, session['admin_id']))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Not authorized!", "danger")
        return redirect('/admin/item-list')

    return render_template("admin/view_item.html", product=product)

# ================= SHOW UPDATE FORM =================
@app.route('/admin/update-item/<int:item_id>', methods=['GET'])
def update_item_page(item_id):

    if 'admin_id' not in session:
        flash("Login required")
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM products WHERE product_id=?", (item_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found")
        return redirect('/admin/item-list')

    return render_template("admin/update_item.html", product=product)


# ================= UPDATE PRODUCT =================
@app.route('/admin/update-item/<int:item_id>', methods=['POST'])
def update_item(item_id):

    if 'admin_id' not in session:
        return redirect('/admin-login')

    name = request.form['name']
    description = request.form['description']
    category = request.form['category']
    price = request.form['price']
    new_image = request.files['image']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM products WHERE product_id=? AND admin_id=?",
                   (item_id, session['admin_id']))
    product = cursor.fetchone()

    if not product:
        flash("Not authorized!", "danger")
        return redirect('/admin/item-list')

    old_image = product['image']

    if new_image and new_image.filename != "":
        filename = secure_filename(new_image.filename)
        new_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        new_image.save(new_path)

        old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_image)
        if os.path.exists(old_path):
            os.remove(old_path)

        final_image = filename
    else:
        final_image = old_image

    cursor.execute("""
        UPDATE products
        SET name=?, description=?, category=?, price=?, image=?
        WHERE product_id=? AND admin_id=?
    """, (name, description, category, price, final_image, item_id, session['admin_id']))

    conn.commit()
    cursor.close()
    conn.close()

    flash("Updated successfully!", "success")
    return redirect('/admin/item-list')


# ADMIN: VIEW ALL ORDERS

@app.route('/admin/orders')
def admin_orders():

    if 'admin_id' not in session:
        flash("Please login as admin!", "danger")
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT o.order_id, o.user_id, o.amount, 
               o.payment_status, o.order_status, o.created_at,
               u.name AS username
        FROM orders o
        LEFT JOIN users u ON o.user_id = u.user_id
        ORDER BY o.created_at DESC
    """)

    orders = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("admin/order_list.html", orders=orders)

# ADMIN: VIEW ORDER DETAILS

@app.route('/admin/order/<int:order_id>')
def admin_order_details(order_id):

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM orders WHERE order_id=?", (order_id,))
    order = cursor.fetchone()

    cursor.execute("SELECT * FROM order_items WHERE order_id=?", (order_id,))
    items = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("admin/order_details.html", order=order, items=items)


# ADMIN: UPDATE ORDER STATUS

@app.route("/admin/update-order-status/<int:order_id>", methods=['POST'])
def update_order_status(order_id):

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    new_status = request.form.get('status')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE orders SET order_status=? WHERE order_id=?",
                   (new_status, order_id))

    conn.commit()
    cursor.close()
    conn.close()

    flash("Order status updated successfully!", "success")
    return redirect(url_for('admin_order_details', order_id=order_id))

# ---------------- LOGOUT ----------------

@app.route('/admin-logout')
def admin_logout():

    session.clear()

    flash("Logged out successfully!", "success")
    return redirect('/admin-login')

#USER REGISTER

@app.route('/user-register', methods=['GET','POST'])
def user_register():

    if request.method == 'GET':
        return render_template("user/user_register.html")

    name = request.form['name']
    email = request.form['email']
    password = bcrypt.hashpw(request.form['password'].encode(), bcrypt.gensalt())

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("INSERT INTO users(name,email,password) VALUES(?,?,?)",
                   (name,email,password))
    conn.commit()

    cursor.close()
    conn.close()

    flash("Registered Successfully!", "success")
    return redirect('/user-login')

#USER LOGIN

@app.route('/user-login', methods=['GET','POST'])
def user_login():

    if session.get('user_id'):
        return redirect('/user-dashboard')

    if request.method == 'GET':
        return render_template("user/user_login.html")

    if request.method == 'GET':
        return render_template("user/user_login.html")

    email = request.form['email']
    password = request.form['password']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE email=?",(email,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if not user:
        flash("User not found","danger")
        return redirect('/user-login')

    if not bcrypt.checkpw(password.encode(), user['password']):
        flash("Wrong password","danger")
        return redirect('/user-login')

    session['user_id'] = user['user_id']
    session['user_name'] = user['name']
    session['user_image'] = user['profile_image']
    
    flash("Login Successful!", "success")
    return redirect('/user-dashboard')

#USER FORGOT PASS

@app.route('/user-forgot-password', methods=['GET', 'POST'])
def user_forgot_password():

    if request.method == 'GET':
        return render_template("user/user_forgot_password.html")

    email = request.form['email']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE email=?", (email,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if not user:
        flash("Email not found!", "danger")
        return redirect('/user-forgot-password')

    otp = random.randint(100000, 999999)

    session['reset_email'] = email
    session['reset_otp'] = otp

    msg = Message(
        subject="Password Reset OTP",
        sender=config.MAIL_USERNAME,
        recipients=[email]
    )
    msg.body = f"Your OTP is: {otp}"
    mail.send(msg)

    flash("OTP sent!", "success")
    return redirect('/user-verify-reset-otp')

#VERIFY OTP

@app.route('/user-verify-reset-otp', methods=['GET', 'POST'])
def user_verify_reset_otp():

    if request.method == 'GET':
        return render_template("user/user_verify_otp.html")

    if request.form['otp'] != str(session.get('reset_otp')):
        flash("Invalid OTP!", "danger")
        return redirect('/user-verify-reset-otp')

    return redirect('/user-reset-password')

#RESET PASS

@app.route('/user-reset-password', methods=['GET', 'POST'])
def user_reset_password():

    if request.method == 'GET':
        return render_template("user/user_reset_password.html")

    password = request.form['password']
    confirm = request.form['confirm_password']

    if password != confirm:
        flash("Passwords do not match!", "danger")
        return redirect('/user-reset-password')

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE users SET password=? WHERE email=?",
        (hashed, session['reset_email'])
    )

    conn.commit()
    cursor.close()
    conn.close()

    session.pop('reset_email', None)
    session.pop('reset_otp', None)

    flash("Password reset successful!", "success")
    return redirect('/user-login')

#USER DASHBOARD

@app.route('/user-dashboard')
def user_dashboard():

    if 'user_id' not in session:
        return redirect('/user-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    # GET PRODUCTS
    cursor.execute("SELECT * FROM products LIMIT 8")
    products = cursor.fetchall()

    # GET CATEGORIES
    cursor.execute("SELECT DISTINCT category FROM products")
    categories = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "user/user_home.html",
        user_name=session['user_name'],
        products=products,
        categories=categories
    )

#USER PROFILE

@app.route('/user/profile', methods=['GET', 'POST'])
def user_profile():

    if 'user_id' not in session:
        return redirect('/user-login')

    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    # ================= UPDATE =================
    if request.method == 'POST':

        name = request.form['name']
        email = request.form['email']
        new_password = request.form['password']
        new_image = request.files['profile_image']

        # get existing user
        cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        user = cursor.fetchone()

        old_image = user['profile_image']

        # -------- PASSWORD --------
        if new_password:
            hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        else:
            hashed_password = user['password']

        # -------- IMAGE --------
        if new_image and new_image.filename != "":
            filename = secure_filename(new_image.filename)

            path = os.path.join('static/uploads/user_profiles', filename)
            new_image.save(path)

            # delete old image
            if old_image:
                old_path = os.path.join('static/uploads/user_profiles', old_image)
                if os.path.exists(old_path):
                    os.remove(old_path)

            final_image = filename
        else:
            final_image = old_image
        
        session['user_image'] = final_image

        # -------- UPDATE DB --------
        cursor.execute("""
            UPDATE users
            SET name=?, email=?, password=?, profile_image=?
            WHERE user_id=?
        """, (name, email, hashed_password, final_image, user_id))

        conn.commit()

        # update session
        session['user_name'] = name

        flash("Profile updated successfully!", "success")
        return redirect('/user/profile')

    # ================= FETCH =================
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template("user/user_profile.html", user=user)

#USER LOGOUT

@app.route('/user-logout')
def user_logout():
    session.clear()
    return redirect('/user-login')

#SEARCH

@app.route('/user/search')
def user_search():

    if 'user_id' not in session:
        return redirect('/user-login')

    query = request.args.get('q')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM products
        WHERE name LIKE ? OR category LIKE ?
    """, (f"%{query}%", f"%{query}%"))

    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("user/products.html", products=products)

# ================= USER PRODUCTS =================
@app.route('/user/products')
def user_products():

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    search = request.args.get('search', '').strip()
    category = request.args.get('category', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    # 🔹 GET ALL CATEGORIES
    cursor.execute("SELECT DISTINCT category FROM products")
    categories = cursor.fetchall()

    # 🔹 BASE QUERY
    query = "SELECT * FROM products WHERE 1=1"
    params = []

    # 🔍 SEARCH (NAME + CATEGORY)
    if search:
        query += " AND (name LIKE ? OR category LIKE ?)"
        params.append(f"%{search}%")
        params.append(f"%{search}%")

    # CATEGORY FILTER
    if category:
        query += " AND category LIKE ?"
        params.append(f"%{category}%")

    cursor.execute(query, params)
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    # ❗ NO RESULTS MESSAGE
    if not products:
        flash("No products found!", "warning")

    return render_template(
        "user/user_products.html",
        products=products,
        categories=categories
    )


# ================= PRODUCT DETAILS =================

@app.route('/user/product/<int:id>')
def user_product_details(id):

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    # MAIN PRODUCT
    cursor.execute("SELECT * FROM products WHERE product_id=?", (id,))
    product = cursor.fetchone()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/user/products')

    # SIMILAR PRODUCTS (same category, exclude current)
    cursor.execute("""
        SELECT * FROM products 
        WHERE category=? AND product_id!=? 
        LIMIT 4
    """, (product['category'], id))

    similar_products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "user/product_details.html",
        product=product,
        similar_products=similar_products
    )


# ADD TO CART

@app.route('/user/add-to-cart-ajax/<int:product_id>')
def add_to_cart_ajax(product_id):

    if 'user_id' not in session:
        return {"error": "not_logged_in"}, 401

    if 'cart' not in session:
        session['cart'] = {}

    cart = session['cart']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM products WHERE product_id=?", (product_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        return {"error": "Product not found"}, 404

    pid = str(product_id)

    if pid in cart:
        cart[pid]['quantity'] += 1
    else:
        cart[pid] = {
            'product_id': product_id,   # ✅ FIX IMPORTANT
            'name': product['name'],
            'price': float(product['price']),
            'image': product['image'],
            'quantity': 1
        }

    session['cart'] = cart
    session.modified = True

    return {
        "message": "Item added to cart!",
        "cart_count":  len(cart)
    }

@app.context_processor
def cart_count():
    cart = session.get('cart', {})
    return dict(cart_count=len(cart))


# VIEW CART

@app.route('/user/cart')
def view_cart():

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    cart = session.get('cart', {})

    updated_cart = []
    grand_total = 0

    for pid, item in cart.items():

        try:
            price = float(item.get('price', 0))
            qty = int(item.get('quantity', 0))

            total = price * qty
            grand_total += total

            updated_cart.append({
                "pid": pid,
                "name": item.get('name', ''),
                "price": price,
                "quantity": qty,
                "image": item.get('image', ''),
                "total": total
            })

        except Exception as e:
            print(f"Cart item error for {pid}: {e}")

    return render_template(
        "user/cart.html",
        cart=updated_cart,
        grand_total=grand_total
    )
#INCREASE

@app.route('/user/cart/increase/<pid>')
def increase_quantity(pid):

    cart = session.get('cart', {})

    if pid in cart:
        cart[pid]['quantity'] += 1

    session['cart'] = cart
    return redirect('/user/cart')

#DECREASE

@app.route('/user/cart/decrease/<pid>')
def decrease_quantity(pid):

    cart = session.get('cart', {})

    if pid in cart:
        cart[pid]['quantity'] -= 1

        if cart[pid]['quantity'] <= 0:
            cart.pop(pid)

    session['cart'] = cart
    return redirect('/user/cart')

#REMOVE

@app.route('/user/cart/remove/<pid>')
def remove_from_cart(pid):

    cart = session.get('cart', {})

    if pid in cart:
        cart.pop(pid)

    session['cart'] = cart

    flash("Item removed!", "success")
    return redirect('/user/cart')

#CHECKOUT

@app.route('/user/checkout')
def checkout():

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    cart = session.get('cart', {})

    items = []
    grand_total = 0

    for pid, item in cart.items():
        total = item['price'] * item['quantity']

        items.append({
            "name": item['name'],
            "price": item['price'],
            "quantity": item['quantity'],
            "image": item['image'],
            "total": total
        })

        grand_total += total

    return render_template(
        "user/checkout.html",
        items=items,
        grand_total=grand_total
    )
# ================= PLACE ORDER =================

@app.route('/user/place-order', methods=['POST'])
def place_order():

    if 'user_id' not in session:
        return redirect('/user-login')

    cart = session.get('cart', {})
    if not cart:
        return redirect('/user/cart')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get user snapshot
    cursor.execute("""
        SELECT name, email, address 
        FROM users 
        WHERE user_id=?
    """, (session['user_id'],))
    user = cursor.fetchone()

    # Create order
    cursor.execute("""
        INSERT INTO orders (user_id, amount, payment_status, address)
        VALUES (?, ?, ?, ?)
    """, (session['user_id'], 0, "Paid", user['address']))

    order_id = cursor.lastrowid

    total = 0

    # Insert order items (FIXED)
    for pid, item in cart.items():

        subtotal = item['price'] * item['quantity']
        total += subtotal

        cursor.execute("""
            INSERT INTO order_items 
            (order_id, product_id, product_name, quantity, price)
            VALUES (?, ?, ?, ?, ?)
        """, (
            order_id,
            item['product_id'],
            item['name'],
            item['quantity'],
            item['price']
        ))

    # Update order total
    cursor.execute("""
        UPDATE orders 
        SET amount=? 
        WHERE order_id=?
    """, (total, order_id))

    conn.commit()
    cursor.close()
    conn.close()

    # Clear cart
    session['cart'] = {}

    return redirect(f"/user/download-invoice/{order_id}")


# PAYMENT PAGE/ RAZORPAY ORDER

@app.route('/user/pay')
def user_pay():

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    cart = session.get('cart', {})

    if not cart:
        flash("Your cart is empty!", "danger")
        return redirect('/user/products')

    # ================= CALCULATE TOTAL =================
    total_amount = 0

    for item in cart.values():
        total_amount += item['price'] * item['quantity']

    amount_paise = int(total_amount * 100)

    # ================= STORE SNAPSHOT (ONLY ONCE) =================
    session['checkout_data'] = {
        'user_id': session['user_id'],
        'cart': cart,
        'amount': total_amount
    }

    # ================= CREATE RAZORPAY ORDER =================
    razorpay_order = razorpay_client.order.create({
        "amount": amount_paise,
        "currency": "INR",
        "payment_capture": 1
    })

    session['razorpay_order_id'] = razorpay_order['id']
    session['payment_amount'] = total_amount

    return render_template(
        "user/payment.html",
        amount=total_amount,
        amount_paise=amount_paise,
        key_id=config.RAZORPAY_KEY_ID,
        order_id=razorpay_order['id']
    )

# PAYMENT SUCCESS

@app.route('/payment-success')
def payment_success():

    payment_id = request.args.get('payment_id')
    order_id = request.args.get('order_id')

    if not payment_id:
        flash("Payment failed!", "danger")
        return redirect('/user/cart')

    return render_template(
        "user/payment_success.html",
        payment_id=payment_id,
        order_id=order_id
    )

# ================= VERIFY PAYMENT =================
@app.route('/verify-payment', methods=['POST'])
def verify_payment():

    import hmac
    import hashlib

    razorpay_payment_id = request.form.get('razorpay_payment_id')
    razorpay_order_id = request.form.get('razorpay_order_id')
    razorpay_signature = request.form.get('razorpay_signature')

    data = session.get('checkout_data')

    if not data:
        return "failed"

    # -------- SIGNATURE VERIFY (MANUAL SAFE METHOD) --------
    generated_signature = hmac.new(
        bytes(config.RAZORPAY_KEY_SECRET, 'utf-8'),
        bytes(f"{razorpay_order_id}|{razorpay_payment_id}", 'utf-8'),
        hashlib.sha256
    ).hexdigest()

    if generated_signature != razorpay_signature:
        print("Signature mismatch")
        return "failed"

    # -------- SAVE ORDER --------
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO orders 
        (user_id, razorpay_order_id, razorpay_payment_id, amount, payment_status, order_status, created_at)
        VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)
    """, (
        data['user_id'],
        razorpay_order_id,
        razorpay_payment_id,
        data['amount'],
        "PAID",
        "PLACED"
    ))

    new_order_id = cursor.lastrowid

    for pid, item in data['cart'].items():
        cursor.execute("""
            INSERT INTO order_items 
            (order_id, product_id, product_name, quantity, price)
            VALUES (?,?,?,?,?)
        """, (
            new_order_id,
            pid,
            item['name'],
            item['quantity'],
            item['price']
        ))

    conn.commit()
    cursor.close()
    conn.close()

    session['cart'] = {}
    session.pop('checkout_data', None)

    return str(new_order_id)

#ORDER SUCCESS

@app.route('/user/order-success/<int:order_id>')
def order_success(order_id):

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM orders WHERE order_id=?", (order_id,))
    order = cursor.fetchone()

    cursor.execute("SELECT * FROM order_items WHERE order_id=?", (order_id,))
    items = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("user/order_success.html", order=order, items=items)

#MY ORDERS

@app.route('/user/my-orders')
def my_orders():

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC", (session['user_id'],))
    orders = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("user/my_orders.html", orders=orders)

#INVOICE

@app.route("/user/download-invoice/<int:order_id>")
def download_invoice(order_id):

    if 'user_id' not in session:
        return redirect('/user-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    # ORDER
    cursor.execute("""
        SELECT * FROM orders
        WHERE order_id=? AND user_id=?
    """, (order_id, session['user_id']))
    order = cursor.fetchone()

    # USER (FIX FOR BLANK NAME/EMAIL)
    cursor.execute("""
        SELECT name, email
        FROM users
        WHERE user_id=?
    """, (session['user_id'],))
    user = cursor.fetchone()

    # ITEMS
    cursor.execute("""
        SELECT product_name, quantity, price
        FROM order_items
        WHERE order_id=?
    """, (order_id,))
    items = cursor.fetchall()

    cursor.close()
    conn.close()

    html = render_template("user/invoice.html",
                           order=order,
                           user=user,
                           items=items)

    pdf = generate_pdf(html)

    response = make_response(pdf.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f"attachment; filename=invoice_{order_id}.pdf"

    return response

# ---------------- RUN ---------------
if __name__ == "__main__":
    app.run(debug=True)