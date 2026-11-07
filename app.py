from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import uuid

app = Flask(__name__)
app.secret_key = "retailplus_secret_key_123"

# Configure SQLite Database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///retailplus.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- DATABASE MODELS ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False) # 'admin' or 'user'

class InventoryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    purchase_price = db.Column(db.Float, nullable=False)
    selling_price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)

class Customer(db.Model):
    __tablename__ = 'customer'
    id = db.Column(db.String(20), primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    cashier = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Float, nullable=False)
    purchase_cost = db.Column(db.Float, nullable=False)
    date = db.Column(db.String(30), nullable=False)
    
    # Relationship to itemized rows
    items = db.relationship('SaleItem', backref='customer', cascade="all, delete-orphan", lazy=True)

class SaleItem(db.Model):
    __tablename__ = 'sale_item'
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.String(20), db.ForeignKey('customer.id'), nullable=False)
    product_name = db.Column(db.String(150), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)

class SupportTicket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    date = db.Column(db.String(30), nullable=False)


# --- INITIALIZE DATABASE & DEFAULT DATA ---
with app.app_context():
    db.create_all()
    if not User.query.first():
        admin = User(name="Admin User", username="admin", password="adminpassword", role="admin")
        cashier = User(name="Cashier One", username="cashier1", password="cashierpassword", role="user")
        db.session.add(admin)
        db.session.add(cashier)
        
        default_items = [
            {"name": "Classmate Notebook (200 Pages)", "purchase_price": 40.0, "selling_price": 60.0, "stock": 50},
            {"name": "Pilot Gel Pen", "purchase_price": 25.0, "selling_price": 40.0, "stock": 3},
            {"name": "Geometry Box", "purchase_price": 80.0, "selling_price": 120.0, "stock": 15},
            {"name": "Color Pencil Set", "purchase_price": 100.0, "selling_price": 150.0, "stock": 2},
            {"name": "Sticky Notes Pack", "purchase_price": 20.0, "selling_price": 35.0, "stock": 30}
        ]
        for item_data in default_items:
            item = InventoryItem(**item_data)
            db.session.add(item)
        db.session.commit()


# --- ROUTES ---

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            session["username"] = user.username
            session["role"] = user.role
            return redirect(url_for("index"))
        else:
            return render_template("login.html", error="Invalid username or password.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def index():
    if "username" not in session:
        return redirect(url_for("login"))

    sales = Customer.query.all()
    total_revenue = sum(s.total for s in sales)
    total_items_sold = sum(s.quantity for s in sales)
    total_purchase_cost = sum(s.purchase_cost for s in sales)
    net_profit = total_revenue - total_purchase_cost

    daily_sales, weekly_sales, monthly_sales = {}, {}, {}
    for sale in sales:
        dt = datetime.strptime(sale.date, "%Y-%m-%d %H:%M")
        day_key = dt.strftime("%Y-%m-%d")
        week_key = dt.strftime("%Y-W%U")
        month_key = dt.strftime("%B %Y")

        daily_sales[day_key] = daily_sales.get(day_key, 0) + sale.total
        weekly_sales[week_key] = weekly_sales.get(week_key, 0) + sale.total
        monthly_sales[month_key] = monthly_sales.get(month_key, 0) + sale.total

    daily_labels = list(daily_sales.keys())
    daily_values = list(daily_sales.values())
    weekly_labels = list(weekly_sales.keys())
    weekly_values = list(weekly_sales.values())
    monthly_labels = list(monthly_sales.keys())
    monthly_values = list(monthly_sales.values())

    # Query to get top selling products by total quantity sold
    top_products = db.session.query(
        SaleItem.product_name, 
        db.func.sum(SaleItem.quantity).label('total_qty')
    ).group_by(SaleItem.product_name)\
     .order_by(db.func.sum(SaleItem.quantity).desc())\
     .limit(5).all()

    return render_template("index.html", 
                           total=total_revenue, 
                           items_sold=total_items_sold,
                           purchase_cost=total_purchase_cost,
                           profit=net_profit,
                           role=session.get('role'),
                           daily_labels=daily_labels,
                           daily_values=daily_values,
                           weekly_labels=weekly_labels,
                           weekly_values=weekly_values,
                           monthly_labels=monthly_labels,
                           monthly_values=monthly_values,
                           top_products=top_products)


@app.route('/add_sales', methods=['GET', 'POST'])
def add_sales():
    if "username" not in session:
        return redirect(url_for("login"))
        
    if session.get("role") == "admin":
        return redirect(url_for("index"))
        
    if request.method == 'POST':
        customer_name = request.form.get('customer_name') or "Walk-in Customer"
        product_names = request.form.getlist('product_name[]')
        quantities = request.form.getlist('quantity[]')
        
        total_amount = 0
        total_purchase_cost = 0
        valid_items_data = []
        
        for p_name, qty in zip(product_names, quantities):
            if not p_name or not qty:
                continue
            
            qty_int = int(qty)
            item = InventoryItem.query.filter_by(name=p_name).first()
            
            if not item:
                inventory_items = InventoryItem.query.all()
                return render_template('add_sales.html', inventory=inventory_items, role=session.get('role'), error=f"Selected product '{p_name}' not found!")
                
            if item.stock < qty_int:
                inventory_items = InventoryItem.query.all()
                return render_template('add_sales.html', inventory=inventory_items, role=session.get('role'), error=f"Not enough stock for '{p_name}'! Available: {item.stock}")
            
            total_amount += item.selling_price * qty_int
            total_purchase_cost += item.purchase_price * qty_int
            
            valid_items_data.append({
                "name": p_name,
                "qty": qty_int,
                "price": item.selling_price
            })
            
            item.stock -= qty_int

        if not valid_items_data:
            inventory_items = InventoryItem.query.all()
            return render_template('add_sales.html', inventory=inventory_items, role=session.get('role'), error="Please select at least one valid product.")

        sale_id = "SALE-" + uuid.uuid4().hex[:6].upper()
        
        new_customer_sale = Customer(
            id=sale_id,
            customer_name=customer_name,
            cashier=session.get("username"),
            quantity=sum(item["qty"] for item in valid_items_data),
            total=total_amount,
            purchase_cost=total_purchase_cost,
            date=datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        db.session.add(new_customer_sale)
        
        for item_info in valid_items_data:
            sale_item = SaleItem(
                sale_id=sale_id,
                product_name=item_info["name"],
                quantity=item_info["qty"],
                price=item_info["price"]
            )
            db.session.add(sale_item)
            
        db.session.commit()
        
        return redirect(url_for('view_bill', sale_id=sale_id))
        
    inventory_items = InventoryItem.query.all()
    return render_template('add_sales.html', inventory=inventory_items, role=session.get('role'))


@app.route('/bill/<string:sale_id>')
def view_bill(sale_id):
    if "username" not in session:
        return redirect(url_for("login"))
        
    sale = Customer.query.get_or_404(sale_id)
    return render_template("bill.html", sale=sale, role=session.get('role'))


@app.route("/Inventory")
def inventory():
    if "username" not in session:
        return redirect(url_for("login"))
    inventory_items = InventoryItem.query.all()
    return render_template("Inventory.html", inventory=inventory_items, role=session.get('role'))


@app.route("/inventory/add", methods=["POST"])
def add_inventory_item():
    if "username" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))

    name = request.form.get("name")
    try:
        purchase_price = float(request.form.get("purchase_price"))
        selling_price = float(request.form.get("selling_price"))
        stock = int(request.form.get("stock"))
    except (TypeError, ValueError):
        purchase_price, selling_price, stock = 0.0, 0.0, 0

    if name:
        new_item = InventoryItem(name=name, purchase_price=purchase_price, selling_price=selling_price, stock=stock)
        db.session.add(new_item)
        db.session.commit()

    return redirect(url_for("inventory"))


@app.route("/inventory/update_price/<int:item_id>", methods=["POST"])
def update_price(item_id):
    if "username" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))

    item = InventoryItem.query.get_or_404(item_id)
    try:
        new_price = float(request.form.get("selling_price"))
        if new_price >= 0:
            item.selling_price = new_price
            db.session.commit()
    except (TypeError, ValueError):
        pass

    return redirect(url_for("inventory"))


@app.route("/inventory/delete/<int:item_id>")
def delete_inventory_item(item_id):
    if "username" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))

    item = InventoryItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for("inventory"))


@app.route("/restock/<int:item_id>", methods=["POST"])
def restock(item_id):
    if "username" not in session:
        return redirect(url_for("login"))

    item = InventoryItem.query.get(item_id)
    if item:
        try:
            add_qty = int(request.form.get("add_qty", 10))
            if add_qty > 0:
                item.stock += add_qty
                db.session.commit()
        except ValueError:
            pass
    return redirect(url_for("inventory"))


@app.route("/staff", methods=["GET", "POST"])
def staff():
    if "username" not in session or session.get("role") != "admin":
        return redirect(url_for("index"))

    if request.method == "POST":
        name = request.form.get("name")
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            staff_users = User.query.all()
            return render_template("staff.html", staff=staff_users, role=session.get('role'), error="Username already exists!")

        new_user = User(name=name, username=username, password=password, role=role)
        db.session.add(new_user)
        db.session.commit()

    staff_users = User.query.all()
    return render_template("staff.html", staff=staff_users, role=session.get('role'))


@app.route("/staff/delete/<username>")
def delete_staff(username):
    if "username" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))

    if username != session.get("username"):
        user_to_delete = User.query.filter_by(username=username).first()
        if user_to_delete:
            db.session.delete(user_to_delete)
            db.session.commit()

    return redirect(url_for("staff"))


@app.route("/sales_history")
def history():
    if "username" not in session:
        return redirect(url_for("login"))
    
    role = session.get("role")
    current_user = session.get("username")
    cashier_filter = request.args.get("cashier")
    date_filter = request.args.get("filter", "all")
    
    query = Customer.query
    
    # Role-based restriction
    if role != "admin":
        query = query.filter_by(cashier=current_user)
    elif cashier_filter:
        query = query.filter_by(cashier=cashier_filter)
        
    # Date Filtering Logic
    now = datetime.now()
    if date_filter == "today":
        today_str = now.strftime("%Y-%m-%d")
        query = query.filter(Customer.date.startswith(today_str))
    elif date_filter == "week":
        start_week = now - timedelta(days=7)
        sales_all = query.all()
        sales = [s for s in sales_all if datetime.strptime(s.date, "%Y-%m-%d %H:%M") >= start_week]
    elif date_filter == "month":
        month_str = now.strftime("%Y-%m")
        query = query.filter(Customer.date.startswith(month_str))
        
    if date_filter != "week":
        sales = query.order_by(Customer.date.desc()).all()
        
    cashiers = [u.username for u in User.query.filter_by(role="user").all()]

    return render_template("sales_history.html", 
                           sales=sales, 
                           cashiers=cashiers, 
                           selected_cashier=cashier_filter, 
                           current_filter=date_filter,
                           role=role)

@app.route("/sales_history/print")
def print_history():
    if "username" not in session:
        return redirect(url_for("login"))
    
    role = session.get("role")
    current_user = session.get("username")
    cashier_filter = request.args.get("cashier")
    date_filter = request.args.get("filter", "all")
    
    query = Customer.query
    
    if role != "admin":
        query = query.filter_by(cashier=current_user)
    elif cashier_filter:
        query = query.filter_by(cashier=cashier_filter)
        
    now = datetime.now()
    if date_filter == "today":
        today_str = now.strftime("%Y-%m-%d")
        query = query.filter(Customer.date.startswith(today_str))
    elif date_filter == "week":
        start_week = now - timedelta(days=7)
        sales_all = query.all()
        sales = [s for s in sales_all if datetime.strptime(s.date, "%Y-%m-%d %H:%M") >= start_week]
    elif date_filter == "month":
        month_str = now.strftime("%Y-%m")
        query = query.filter(Customer.date.startswith(month_str))
        
    if date_filter != "week":
        sales = query.order_by(Customer.date.desc()).all()
        
    cashiers = [u.username for u in User.query.filter_by(role="user").all()]

    return render_template("sales_history.html", 
                           sales=sales, 
                           cashiers=cashiers, 
                           selected_cashier=cashier_filter, 
                           current_filter=date_filter,
                           role=role,
                           is_print_mode=True) # <-- This tells the page to trigger printing

@app.route("/support", methods=["GET", "POST"])
def support():
    if "username" not in session:
        return redirect(url_for("login"))

    success = None
    if request.method == "POST":
        subject = request.form.get("subject")
        message = request.form.get("message")
        
        if subject and message:
            ticket = SupportTicket(
                username=session.get("username"),
                subject=subject,
                message=message,
                date=datetime.now().strftime("%Y-%m-%d %H:%M")
            )
            db.session.add(ticket)
            db.session.commit()
            success = "Your support ticket has been successfully submitted!"
            
    return render_template("support.html", success=success, role=session.get('role'))


if __name__ == "__main__":
    app.run(debug=True)