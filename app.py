import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.getenv( 'SECRET-KEY')

# MongoDB Atlas URI placeholder - set MONGO_URI in your .env to connect to Atlas
MONGO_URI = os.getenv('MONGO_URI', 'mongodb+srv://menesescelangelcbtis272_db_user:admin123@mejoradat.lcgxclk.mongodb.net/').strip() 

USE_FAKE_DB = False
db = None
users_col = None
products_col = None
categories_col = None

if MONGO_URI:
    try:
        from pymongo import MongoClient
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=4000)
        client.admin.command('ping')
        db = client.get_default_database()
        users_col = db.users
        products_col = db.products
        categories_col = db.categories
        print('Connected to MongoDB Atlas.')
    except Exception as e:
        print('Could not connect to MongoDB Atlas:', e)
        USE_FAKE_DB = True
else:
    USE_FAKE_DB = True

# Simple in-memory fallback for development / offline use
if USE_FAKE_DB:
    import uuid
    class FakeCollection:
        def __init__(self):
            self.rows = []
        def find(self, *args, **kwargs):
            return list(self.rows)
        def find_one(self, q):
            for r in self.rows:
                ok = True
                for k,v in (q.items() if isinstance(q, dict) else []):
                    if str(r.get(k)) != str(v):
                        ok = False; break
                if ok: return r
            return None
        def insert_one(self, doc):
            doc = dict(doc)
            if '_id' not in doc:
                doc['_id'] = str(uuid.uuid4())
            self.rows.append(doc)
            return type('R',(),{'inserted_id':doc['_id']})()
        def delete_one(self,q):
            r = self.find_one(q)
            if r: self.rows.remove(r)
        def update_one(self,q,upd):
            r = self.find_one(q)
            if not r: return
            if '$set' in upd:
                for k,v in upd['$set'].items():
                    r[k]=v
        def update_many(self,q,upd):
            for r in list(self.rows):
                match=True
                for k,v in (q.items() if isinstance(q, dict) else []):
                    if str(r.get(k))!=str(v): match=False; break
                if match and '$set' in upd:
                    for k,v in upd['$set'].items(): r[k]=v
        def count_documents(self,q=None):
            if not q: return len(self.rows)
            cnt=0
            for r in self.rows:
                ok=True
                for k,v in q.items():
                    if isinstance(v, dict) and '$lte' in v:
                        if not (r.get(k,0) <= v['$lte']): ok=False; break
                    else:
                        if str(r.get(k))!=str(v): ok=False; break
                if ok: cnt+=1
            return cnt

    users_col = FakeCollection()
    products_col = FakeCollection()
    categories_col = FakeCollection()

    # sample data
    categories_col.insert_one({'_id':'cat1','name':'Ropa','subcategory':'Moda'})
    categories_col.insert_one({'_id':'cat2','name':'Calzado','subcategory':'Deportivos'})
    products_col.insert_one({'name':'Camiseta','quantity':15,'price':299.99,'description':'Camiseta de algodón','category_id':'cat1','image':None})
    products_col.insert_one({'name':'Tenis','quantity':4,'price':1299.50,'description':'Tenis running','category_id':'cat2','image':None})
    users_col.insert_one({'_id':'u1','username':'admin','password': generate_password_hash('admin123'), 'role':'admin'})
else:
    print('Using Atlas collections.')

# Login manager
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXT = {'png','jpg','jpeg','gif'}

class User(UserMixin):
    def __init__(self, user_doc):
        self.id = str(user_doc['_id'])
        self.username = user_doc['username']
        self.role = user_doc.get('role','user')

@login_manager.user_loader
def load_user(user_id):
    try:
        doc = users_col.find_one({'_id': ObjectId(user_id)})
        if doc: return User(doc)
    except Exception:
        pass
    doc = users_col.find_one({'_id': user_id})
    if doc: return User(doc)
    return None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXT

def admin_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or getattr(current_user,'role','user')!='admin':
            flash('Acceso denegado: administradores solamente','danger')
            return redirect(url_for('dashboard'))
        return func(*args, **kwargs)
    return wrapper

@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        username = request.form['username'].strip()
        password = request.form['password']
        role = request.form.get('role','user')
        if users_col.find_one({'username':username}):
            flash('Usuario ya existe','danger'); return redirect(url_for('register'))
        hashed = generate_password_hash(password)
        users_col.insert_one({'username':username,'password':hashed,'role':role})
        flash('Usuario creado','success'); return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        username = request.form['username']; password = request.form['password']
        user_doc = users_col.find_one({'username':username})
        if user_doc and check_password_hash(user_doc['password'], password):
            login_user(User(user_doc))
            return redirect(url_for('dashboard'))
        flash('Usuario o contraseña incorrectos','danger'); return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user(); flash('Has cerrado sesión','info'); return redirect(url_for('login'))

@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    total_products = products_col.count_documents({})
    low_stock = products_col.count_documents({'quantity':{'$lte':5}})
    cats = list(categories_col.find())
    labels = [c.get('name','Sin nombre') for c in cats]
    values = [products_col.count_documents({'category_id': str(c.get('_id'))}) for c in cats]
    return render_template('dashboard.html', total_products=total_products, low_stock=low_stock, labels=labels, values=values)

@app.route('/inventory')
@login_required
def inventory():
    products = list(products_col.find())
    for p in products:
        try: p['_id']=str(p['_id'])
        except: pass
    categories = list(categories_col.find())
    for c in categories:
        try: c['_id']=str(c['_id'])
        except: pass
        c['count'] = products_col.count_documents({'category_id': c.get('_id')})
    return render_template('inventory.html', products=products, categories=categories)

@app.route('/product/new', methods=['GET','POST'])
@login_required
def product_new():
    if request.method=='POST':
        name = request.form['name'].strip()
        quantity = int(request.form.get('quantity',0))
        price = float(request.form.get('price',0))
        description = request.form.get('description','').strip()
        category_id = request.form.get('category_id') or None
        image_filename = None
        if 'image' in request.files:
            f = request.files['image']
            if f and allowed_file(f.filename):
                filename = secure_filename(f.filename)
                f.save(os.path.join(UPLOAD_FOLDER, filename))
                image_filename = filename
        products_col.insert_one({'name':name,'quantity':quantity,'price':price,'description':description,'category_id':category_id,'image':image_filename})
        flash('Producto agregado','success'); return redirect(url_for('inventory'))
    categories = list(categories_col.find()); return render_template('product_form.html', action='Crear', categories=categories)

@app.route('/product/edit/<id>', methods=['GET','POST'])
@login_required
def product_edit(id):
    try:
        prod = products_col.find_one({'_id': ObjectId(id)})
    except Exception:
        prod = products_col.find_one({'_id': id})
    if not prod:
        flash('Producto no encontrado','danger'); return redirect(url_for('inventory'))
    if request.method=='POST':
        image_filename = prod.get('image')
        if 'image' in request.files:
            f = request.files['image']
            if f and allowed_file(f.filename):
                filename = secure_filename(f.filename)
                f.save(os.path.join(UPLOAD_FOLDER, filename))
                image_filename = filename
        products_col.update_one({'_id': prod.get('_id')}, {'$set':{
            'name': request.form['name'].strip(),
            'quantity': int(request.form.get('quantity',0)),
            'price': float(request.form.get('price',0)),
            'description': request.form.get('description','').strip(),
            'category_id': request.form.get('category_id') or None,
            'image': image_filename
        }})
        flash('Producto actualizado','success'); return redirect(url_for('inventory'))
    prod['_id'] = str(prod.get('_id')); categories = list(categories_col.find()); return render_template('product_form.html', action='Editar', product=prod, categories=categories)

@app.route('/product/delete/<id>', methods=['POST'])
@login_required
def product_delete(id):
    try:
        products_col.delete_one({'_id': ObjectId(id)})
    except Exception:
        products_col.delete_one({'_id': id})
    flash('Producto eliminado','info'); return redirect(url_for('inventory'))

@app.route('/categories')
@login_required
def categories():
    cats = list(categories_col.find())
    for c in cats:
        c['count'] = products_col.count_documents({'category_id': str(c.get('_id'))})
    return render_template('categories.html', categories=cats)

@app.route('/category/new', methods=['GET','POST'])
@login_required
@admin_required
def category_new():
    if request.method=='POST':
        name = request.form['name'].strip(); sub = request.form.get('subcategory','').strip()
        categories_col.insert_one({'name':name,'subcategory':sub}); flash('Categoría creada','success'); return redirect(url_for('categories'))
    return render_template('category_form.html', action='Crear')

@app.route('/category/edit/<id>', methods=['GET','POST'])
@login_required
@admin_required
def category_edit(id):
    try:
        cat = categories_col.find_one({'_id': ObjectId(id)})
    except Exception:
        cat = categories_col.find_one({'_id': id})
    if request.method=='POST':
        categories_col.update_one({'_id': cat.get('_id')}, {'$set': {'name': request.form['name'].strip(), 'subcategory': request.form.get('subcategory','').strip()}})
        flash('Categoría actualizada','success'); return redirect(url_for('categories'))
    return render_template('category_form.html', action='Editar', category=cat)

if __name__ == '__main__':
    app.run(debug=True)
