# app.py
import os
from flask import Flask, render_template, redirect, url_for, session, flash, request, jsonify
from models import db, User, Name, favorite_table, passed_name_table # Asegúrate que los modelos estén como en la versión SIN contraseñas
import json
import random
from sqlalchemy.sql.expression import func

# Determinar si estamos en Vercel
IS_VERCEL = os.environ.get('VERCEL') == '1' # Vercel setea VERCEL=1

if IS_VERCEL:
    DATABASE_PATH = "/tmp/babynames_v2.db"
    # Asegurarse que el archivo names_data.json se lea desde la raíz del proyecto
    # ya que /tmp es solo para archivos escribibles, no para tus archivos de código fuente.
    # El open('names_data.json', ...) debería funcionar si names_data.json está en la raíz.
else:
    # Configuración local (puedes seguir usando instance/ o la raíz)
    # Si usas instance/, asegúrate que la carpeta exista.
    INSTANCE_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance')
    if not os.path.exists(INSTANCE_FOLDER):
        os.makedirs(INSTANCE_FOLDER)
    DATABASE_PATH = os.path.join(INSTANCE_FOLDER, 'babynames_v2.db')
    # DATABASE_PATH = 'babynames_v2.db' # O directamente en la raíz para local

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tu_clave_secreta_muy_secreta_revisada'
DATABASE_FILE = 'babynames_v2.db'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DATABASE_FILE}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# --- Funciones de ayuda ---
def infer_gender_from_key_or_category(key_name, category_name):
    key_lower = key_name.lower()
    if "niño" in key_lower or "masculino" in key_lower: return "niño"
    if "niña" in key_lower or "femenino" in key_lower: return "niña"
    category_lower = category_name.lower()
    if "niño" in category_lower or "masculino" in category_lower: return "niño"
    if "niña" in category_lower or "femenino" in category_lower: return "niña"
    return "desconocido"

def initialize_database():
    with app.app_context():
        print("--- Iniciando Inicialización de Base de Datos (Versión Simple Login) ---")
        db.create_all() 
        print("db.create_all() ejecutado.")

        # Crear usuarios Luis y Franyeglys si no existen (sin contraseñas)
        default_usernames = ["luis", "franyeglys"]
        for username_str in default_usernames:
            user = User.query.filter_by(username=username_str).first()
            if not user:
                user = User(username=username_str)
                db.session.add(user)
                print(f"Usuario '{username_str}' creado.")
        try:
            db.session.commit()
            print("Usuarios 'luis' y 'franyeglys' creados/verificados.")
        except Exception as e:
            db.session.rollback()
            print(f"Error al crear/verificar usuarios: {e}")

        # Poblar la tabla Name solo si está vacía
        if Name.query.first() is None:
            print("Tabla 'Name' vacía. Poblando desde names_data.json...")
            try:
                with open('names_data.json', 'r', encoding='utf-8') as f:
                    data_from_json = json.load(f)
            except FileNotFoundError: # ... (manejo de errores) ...
                print("Error: names_data.json no encontrado.")
                return
            except json.JSONDecodeError:
                print("Error: names_data.json no es un JSON válido.")
                return

            names_added_count = 0
            # Procesar categorías de niños
            if 'categorias_ninos' in data_from_json and isinstance(data_from_json['categorias_ninos'], list):
                for category_obj in data_from_json['categorias_ninos']:
                    category_name = category_obj.get("categoria")
                    names_list = category_obj.get("nombres")
                    if not category_name or not isinstance(names_list, list): continue
                    gender = infer_gender_from_key_or_category('categorias_ninos', category_name)
                    if gender == "desconocido": continue
                    for name_data in names_list:
                        name_text = name_data.get("nombre")
                        if name_text:
                            db.session.add(Name(name_text=name_text.capitalize(), gender=gender, category=category_name, ranking=name_data.get("ranking")))
                            names_added_count +=1
            
            # Procesar categorías de niñas
            if 'categorias_ninas' in data_from_json and isinstance(data_from_json['categorias_ninas'], list):
                for category_obj in data_from_json['categorias_ninas']:
                    category_name = category_obj.get("categoria")
                    names_list = category_obj.get("nombres")
                    if not category_name or not isinstance(names_list, list): continue
                    gender = infer_gender_from_key_or_category('categorias_ninas', category_name)
                    if gender == "desconocido": continue
                    for name_data in names_list:
                        name_text = name_data.get("nombre")
                        if name_text:
                             db.session.add(Name(name_text=name_text.capitalize(), gender=gender, category=category_name, ranking=name_data.get("ranking")))
                             names_added_count +=1
            
            if names_added_count > 0:
                try:
                    db.session.commit()
                    print(f"Tabla 'Name' poblada con {names_added_count} nombres.")
                except Exception as e:
                    db.session.rollback()
                    print(f"Error al hacer commit de nombres: {e}")
            else:
                print("No se añadieron nombres desde JSON.")
        else:
            print("La tabla 'Name' ya contiene datos.")
        
        print("--- Finalizada Inicialización de Base de Datos ---")

def get_user_by_username_helper(username_str): # Renombrado para evitar confusión con get_current_user
    return User.query.filter_by(username=username_str).first()

def get_current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

# --- LÓGICA DE LOGROS ---
def calculate_achievements(current_user_obj):
    achievements_status = []
    if not current_user_obj:
        return achievements_status

    # Datos para el usuario actual
    num_own_favorites = len(current_user_obj.favorites)
    num_own_boy_favs = len([n for n in current_user_obj.favorites if n.gender == 'niño'])
    num_own_girl_favs = len([n for n in current_user_obj.favorites if n.gender == 'niña'])
    
    custom_category_prefix = f"Agregados por {current_user_obj.username.capitalize()}"
    num_own_custom_names_added = Name.query.filter_by(category=custom_category_prefix).count()

    liked_texts = {n.name_text for n in current_user_obj.favorites}
    passed_texts = {n.name_text for n in current_user_obj.passed_names_rel}
    total_texts_interacted = len(liked_texts.union(passed_texts))
    
    subquery_total_unique = Name.query.with_entities(Name.name_text).distinct().subquery()
    total_unique_name_texts_in_db = db.session.query(func.count(subquery_total_unique.c.name_text)).scalar() or 0

    # Logros Individuales
    achievements_status.append({'id': 'first_steps', 'name': 'Primeros Pasos', 'desc': 'Marca tu primer favorito.', 'icon': '🌟', 'achieved': num_own_favorites > 0})
    achievements_status.append({'id': 'custom_adder', 'name': 'Aspirante a Escritor', 'desc': 'Añade tu primer nombre.', 'icon': '✏️', 'achieved': num_own_custom_names_added > 0})
    achievements_status.append({'id': 'ten_favs', 'name': 'Corazón Decidido', 'desc': 'Marca 10 favoritos.', 'icon': '❤️', 'achieved': num_own_favorites >= 10})
    achievements_status.append({'id': 'ten_boy_favs', 'name': 'Equipo Azul', 'desc': 'Marca 10 nombres de niño.', 'icon': '💙', 'achieved': num_own_boy_favs >= 10})
    achievements_status.append({'id': 'ten_girl_favs', 'name': 'Equipo Rosa', 'desc': 'Marca 10 nombres de niña.', 'icon': '💖', 'achieved': num_own_girl_favs >= 10})
    achievements_status.append({'id': 'prolific_author', 'name': 'Autor Prolífico', 'desc': 'Añade 5 nombres personalizados.', 'icon': '✍️', 'achieved': num_own_custom_names_added >= 5})
    achievements_status.append({'id': 'name_explorer_50', 'name': 'Explorador', 'desc': 'Evalúa 50 nombres.', 'icon': '🌍', 'achieved': total_texts_interacted >= 50})
    achievements_status.append({'id': 'name_explorer_100', 'name': 'Gran Explorador', 'desc': 'Evalúa 100 nombres.', 'icon': '🗺️', 'achieved': total_texts_interacted >= 100})
    achievements_status.append({'id': 'king_of_list', 'name': 'Conquistador de Nombres', 'desc': '¡Has evaluado todos los nombres!', 'icon': '👑', 'achieved': total_texts_interacted >= total_unique_name_texts_in_db and total_unique_name_texts_in_db > 0})

    # Logros de Pareja
    user_luis = get_user_by_username_helper('luis')
    user_franyeglys = get_user_by_username_helper('franyeglys')

    if user_luis and user_franyeglys:
        # Hito Original (Dúo Dinámico)
        # Contar IDs únicos de nombres de niño likeados por CUALQUIERA de los dos
        luis_boy_fav_ids = {n.id for n in user_luis.favorites if n.gender == 'niño'}
        fran_boy_fav_ids = {n.id for n in user_franyeglys.favorites if n.gender == 'niño'}
        total_distinct_boy_likes_both = len(luis_boy_fav_ids.union(fran_boy_fav_ids))

        luis_girl_fav_ids = {n.id for n in user_luis.favorites if n.gender == 'niña'}
        fran_girl_fav_ids = {n.id for n in user_franyeglys.favorites if n.gender == 'niña'}
        total_distinct_girl_likes_both = len(luis_girl_fav_ids.union(fran_girl_fav_ids))

        achievements_status.append({'id': 'dynamic_duo', 'name': 'Dúo Dinámico', 'desc': '10 nombres de niño y 10 de niña únicos en total (combinados).', 'icon': '💞', 'achieved': total_distinct_boy_likes_both >= 10 and total_distinct_girl_likes_both >= 10})

        # Matches (por texto de nombre)
        luis_fav_texts = {name.name_text for name in user_luis.favorites}
        franyeglys_fav_texts = {name.name_text for name in user_franyeglys.favorites}
        common_matches_texts = luis_fav_texts.intersection(franyeglys_fav_texts)
        num_matches = len(common_matches_texts)

        achievements_status.append({'id': 'first_match', 'name': '¡Es un Match!', 'desc': 'Primer match de nombre con tu pareja.', 'icon': '💘', 'achieved': num_matches > 0})
        achievements_status.append({'id': 'five_matches', 'name': 'Conexión Fuerte', 'desc': '5 matches de nombres.', 'icon': '🎯', 'achieved': num_matches >= 5})
        achievements_status.append({'id': 'ten_matches', 'name': 'Almas Gemelas de Nombres', 'desc': '10 matches de nombres.', 'icon': '🥰', 'achieved': num_matches >= 10})
        
        luis_custom_added = Name.query.filter(Name.category.startswith(f"Agregados por {user_luis.username.capitalize()}")).count() > 0
        frany_custom_added = Name.query.filter(Name.category.startswith(f"Agregados por {user_franyeglys.username.capitalize()}")).count() > 0
        achievements_status.append({'id': 'creative_collab', 'name': 'Colaboradores Creativos', 'desc': 'Ambos han añadido nombres.', 'icon': '🖋️🖋️', 'achieved': luis_custom_added and frany_custom_added})
        
        total_custom_names = Name.query.filter(Name.category.like("Agregados por %")).count()
        achievements_status.append({'id': 'baby_shower_ideas', 'name': '¡Baby Shower de Ideas!', 'desc': '10 nombres personalizados añadidos en total.', 'icon': '🎉', 'achieved': total_custom_names >=10 })


    # Logro de "El Indeciso" (necesita seguimiento en sesión)
    undo_count = session.get('undo_actions_count', 0)
    achievements_status.append({'id': 'indecisive_one', 'name': 'El Indeciso', 'desc': 'Usa "Deshacer" 5 veces.', 'icon': '🔄', 'achieved': undo_count >= 5})

    return achievements_status

def get_name_dict(name_obj):
    if not name_obj: return None
    return {"id": name_obj.id, "name_text": name_obj.name_text, "gender": name_obj.gender, "category": name_obj.category, "ranking": name_obj.ranking}

# --- Rutas ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if get_current_user():
        return redirect(url_for('index'))
    
    users = User.query.order_by(User.username).all() # Para el selector
    if not users: # Debería ser raro si initialize_database funciona
        flash("Error: No hay usuarios en el sistema. Intenta reiniciar.", "error")
        return render_template('login.html', users=[])

    if request.method == 'POST':
        user_id_selected = request.form.get('user_id')
        if not user_id_selected:
            flash('Por favor, selecciona un usuario.', 'warning')
            return redirect(url_for('login'))
        
        user = User.query.get(user_id_selected)
        if user:
            session['user_id'] = user.id
            session['username'] = user.username
            session['undo_actions_count'] = 0 # Resetear contador de undo al iniciar sesión
            flash(f'¡Bienvenido/a, {user.username.capitalize()}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Usuario no válido seleccionado.', 'error')
            
    return render_template('login.html', users=users) # login.html necesita un select para usuarios

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('last_action', None)
    session.pop('undo_actions_count', None) # Limpiar contador de undo
    flash('Has cerrado sesión.', 'info')
    return redirect(url_for('login'))

@app.route('/')
def index():
    current_user = get_current_user()
    if not current_user:
        return redirect(url_for('login'))
    
    achievements = calculate_achievements(current_user)
    milestone_dynamic_duo = next((ach for ach in achievements if ach['id'] == 'dynamic_duo'), {}).get('achieved', False)

    return render_template('index.html',
                           current_user=current_user,
                           suggested_name=None, 
                           milestone_reached=milestone_dynamic_duo, # Para la notificación de hito en index
                           can_undo=bool(session.get('last_action'))
                           )

@app.route('/get_next_name', methods=['GET'])
def get_next_name():
    current_user = get_current_user()
    if not current_user:
        return jsonify({"status": "error", "message": "Not authenticated"}), 401

    liked_name_texts = {name.name_text for name in current_user.favorites}
    passed_name_texts = {name.name_text for name in current_user.passed_names_rel}
    interacted_name_texts = liked_name_texts.union(passed_name_texts)
    
    query = Name.query.filter(~Name.name_text.in_(interacted_name_texts))
    
    subquery = query.with_entities(Name.name_text).distinct().subquery()
    count_remaining_unique_texts = db.session.query(func.count(subquery.c.name_text)).scalar() or 0

    suggested_name_obj = query.order_by(func.random()).first()

    return jsonify({
        "name": get_name_dict(suggested_name_obj),
        "milestone_reached": next((ach['achieved'] for ach in calculate_achievements(current_user) if ach['id'] == 'dynamic_duo'), False),
        "can_undo": bool(session.get('last_action')),
        "remaining_count": count_remaining_unique_texts
    })

@app.route('/like_from_other/<int:name_id>/<string:other_username>', methods=['POST'])
def like_name_from_other_favs(name_id, other_username):
    current_user = get_current_user()
    if not current_user:
        flash("Debes iniciar sesión para marcar favoritos.", "warning")
        # Idealmente, guardar la intención y redirigir a login, luego de vuelta.
        # Por ahora, redirigimos a la página de donde vino.
        return redirect(url_for('view_other_favorites', username_to_view=other_username))

    name_to_like = Name.query.get(name_id)
    if not name_to_like:
        flash("Nombre no encontrado.", "error")
        return redirect(url_for('view_other_favorites', username_to_view=other_username))

    if name_to_like not in current_user.favorites:
        # Quitar de pasados si estaba allí (lógica de la ruta /like original)
        if name_to_like in current_user.passed_names_rel:
            current_user.passed_names_rel.remove(name_to_like)
        
        current_user.favorites.append(name_to_like)
        db.session.commit()
        flash(f"'{name_to_like.name_text}' añadido a tus favoritos.", "success")
        # Actualizar last_action si es necesario para 'undo' (copiado de /like)
        session['last_action'] = {'type': 'like', 'name_id': name_id, 'user_id': current_user.id}
        session.modified = True
    else:
        flash(f"'{name_to_like.name_text}' ya estaba en tus favoritos.", "info")
    
    # Redirigir de vuelta a la página de favoritos del otro usuario
    return redirect(url_for('view_other_favorites', username_to_view=other_username))

@app.route('/like/<int:name_id>', methods=['POST'])
def like_name(name_id):
    current_user = get_current_user()
    if not current_user: return jsonify({"status": "error", "message": "Not authenticated"}), 401

    name_to_like = Name.query.get(name_id)
    if not name_to_like: return jsonify({"status": "error", "message": "Name not found"}), 404

    action_occurred = False
    message = ""
    if name_to_like not in current_user.favorites:
        if name_to_like in current_user.passed_names_rel:
            current_user.passed_names_rel.remove(name_to_like)
        current_user.favorites.append(name_to_like)
        db.session.commit()
        session['last_action'] = {'type': 'like', 'name_id': name_id, 'user_id': current_user.id}
        session.modified = True
        action_occurred = True
        message = f"'{name_to_like.name_text}' añadido a favoritos."
    else:
        message = f"'{name_to_like.name_text}' ya estaba en favoritos."

    # Recalcular remaining_count y milestone para la respuesta
    achievements = calculate_achievements(current_user)
    milestone_dynamic_duo = next((ach['achieved'] for ach in achievements if ach['id'] == 'dynamic_duo'), False)
    
    liked_name_texts = {name.name_text for name in current_user.favorites}
    passed_name_texts = {name.name_text for name in current_user.passed_names_rel}
    interacted_name_texts = liked_name_texts.union(passed_name_texts)
    query = Name.query.filter(~Name.name_text.in_(interacted_name_texts))
    subquery = query.with_entities(Name.name_text).distinct().subquery()
    count_remaining_after_action = db.session.query(func.count(subquery.c.name_text)).scalar() or 0
    next_name_obj = query.order_by(func.random()).first()

    return jsonify({
        "status": "success", "message": message, "next_name": get_name_dict(next_name_obj),
        "milestone_reached": milestone_dynamic_duo, "can_undo": action_occurred,
        "remaining_count": count_remaining_after_action
    })

@app.route('/pass', methods=['POST'])
def pass_name():
    current_user = get_current_user()
    if not current_user: return jsonify({"status": "error", "message": "Not authenticated"}), 401

    name_id_passed_str = request.form.get('name_id')
    can_undo_pass = False
    message = "No se recibió ID de nombre para pasar."

    if name_id_passed_str:
        try:
            name_id_passed = int(name_id_passed_str)
            name_obj_passed = Name.query.get(name_id_passed)
            if name_obj_passed:
                is_already_passed = name_obj_passed in current_user.passed_names_rel
                is_favorite = name_obj_passed in current_user.favorites
                if not is_already_passed and not is_favorite:
                    current_user.passed_names_rel.append(name_obj_passed)
                    db.session.commit()
                    session['last_action'] = {'type': 'pass', 'name_id': name_id_passed, 'user_id': current_user.id}
                    session.modified = True
                    can_undo_pass = True
                    message = f"'{name_obj_passed.name_text}' marcado como pasado."
                elif is_already_passed: message = f"'{name_obj_passed.name_text}' ya había sido pasado."
                elif is_favorite: message = f"'{name_obj_passed.name_text}' está en favoritos."
            else: message = f"Nombre con ID {name_id_passed_str} no encontrado."
        except ValueError: message = f"ID de nombre '{name_id_passed_str}' no válido."
    
    achievements = calculate_achievements(current_user)
    milestone_dynamic_duo = next((ach['achieved'] for ach in achievements if ach['id'] == 'dynamic_duo'), False)
    
    liked_name_texts = {name.name_text for name in current_user.favorites}
    passed_name_texts = {name.name_text for name in current_user.passed_names_rel}
    interacted_name_texts = liked_name_texts.union(passed_name_texts)
    query = Name.query.filter(~Name.name_text.in_(interacted_name_texts))
    subquery = query.with_entities(Name.name_text).distinct().subquery()
    count_remaining_after_action = db.session.query(func.count(subquery.c.name_text)).scalar() or 0
    next_name_obj = query.order_by(func.random()).first()

    return jsonify({
        "status": "success", "message": message, "next_name": get_name_dict(next_name_obj),
        "milestone_reached": milestone_dynamic_duo, "can_undo": can_undo_pass,
        "remaining_count": count_remaining_after_action
    })

@app.route('/undo', methods=['POST'])
def undo_action():
    current_user = get_current_user()
    if not current_user: return jsonify({"status": "error", "message": "Not authenticated"}), 401

    last_action = session.pop('last_action', None)
    session.modified = True
    undone_name_obj = None
    message = "No hay acción para deshacer."
    
    session['undo_actions_count'] = session.get('undo_actions_count', 0) + 1 # Incrementar contador de undo

    if last_action and last_action.get('user_id') == current_user.id:
        # ... (lógica de deshacer como la tenías) ...
        action_type = last_action.get('type')
        name_id = last_action.get('name_id')
        name_obj = Name.query.get(name_id)
        if name_obj:
            undone_name_obj = name_obj
            if action_type == 'like':
                if name_obj in current_user.favorites:
                    current_user.favorites.remove(name_obj)
                    db.session.commit()
                    message = f"Like de '{name_obj.name_text}' deshecho."
                else: message = f"'{name_obj.name_text}' no estaba en favoritos."
            elif action_type == 'pass':
                if name_obj in current_user.passed_names_rel:
                    current_user.passed_names_rel.remove(name_obj)
                    db.session.commit()
                    message = f"Pase de '{name_obj.name_text}' deshecho."
                else: message = f"'{name_obj.name_text}' no estaba en pasados."
            else: message = "Tipo de acción desconocida."; undone_name_obj = None
        else: message = "Nombre de la última acción no encontrado."

    achievements = calculate_achievements(current_user)
    milestone_dynamic_duo = next((ach['achieved'] for ach in achievements if ach['id'] == 'dynamic_duo'), False)
    
    liked_name_texts = {name.name_text for name in current_user.favorites}
    passed_name_texts = {name.name_text for name in current_user.passed_names_rel}
    interacted_name_texts = liked_name_texts.union(passed_name_texts)
    query = Name.query.filter(~Name.name_text.in_(interacted_name_texts))
    subquery = query.with_entities(Name.name_text).distinct().subquery()
    count_remaining_after_action = db.session.query(func.count(subquery.c.name_text)).scalar() or 0

    return jsonify({
        "status": "success", "message": message, "undone_name": get_name_dict(undone_name_obj),
        "milestone_reached": milestone_dynamic_duo, "can_undo": False,
        "remaining_count": count_remaining_after_action
    })

@app.route('/get_undo_status', methods=['GET'])
def get_undo_status():
    current_user = get_current_user()
    if not current_user: return jsonify({"can_undo": False})
    return jsonify({"can_undo": bool(session.get('last_action'))})

@app.route('/unlike/<int:name_id>', methods=['POST']) # <--- CAMBIADO DE VUELTA a name_id
def unlike_name(name_id): # <--- CAMBIADO DE VUELTA a name_id
    current_user = get_current_user()
    if not current_user: return redirect(url_for('login'))

    name_obj_to_unlike = Name.query.get(name_id) # Usar name_id aquí
    if not name_obj_to_unlike:
        flash('Nombre no encontrado.', 'error')
        return redirect(request.referrer or url_for('favorites'))

    text_to_remove = name_obj_to_unlike.name_text # Usar name_obj_to_unlike
    names_removed_count = 0
    favorites_to_check = list(current_user.favorites)
    for fav_name_obj in favorites_to_check:
        if fav_name_obj.name_text == text_to_remove: 
            current_user.favorites.remove(fav_name_obj)
            names_removed_count += 1
    
    if names_removed_count > 0:
        db.session.commit()
        flash(f'Todas las instancias de "{text_to_remove}" eliminadas de tus favoritos.', 'success')
    else:
        flash(f'"{text_to_remove}" no estaba en tus favoritos.', 'info')
    
    return redirect(request.referrer or url_for('favorites'))

@app.route('/view_favorites/<string:username_to_view>')
def view_other_favorites(username_to_view):
    current_user = get_current_user() # El que está viendo la página
    # No es estrictamente necesario estar logueado para ver, pero sí para dar 'like'.
    # Si quieres restringir la vista, añade la comprobación aquí.

    other_user = User.query.filter(func.lower(User.username) == func.lower(username_to_view)).first()

    if not other_user:
        flash(f"Usuario '{username_to_view}' no encontrado.", "error")
        return redirect(url_for('index'))
    
    if current_user and current_user.id == other_user.id:
        # Si el usuario intenta ver sus propios favoritos a través de esta ruta,
        # redirigirlo a su página normal de favoritos.
        return redirect(url_for('favorites'))

    # Favoritos del OTRO usuario (únicos por texto para la visualización)
    other_user_all_favs = other_user.favorites
    unique_other_favs_by_text = {}
    for name_obj in other_user_all_favs:
        if name_obj.name_text not in unique_other_favs_by_text:
            unique_other_favs_by_text[name_obj.name_text] = name_obj
    
    final_other_favs_list = sorted(list(unique_other_favs_by_text.values()), key=lambda x: x.name_text)
    other_user_boy_names = [name for name in final_other_favs_list if name.gender == 'niño']
    other_user_girl_names = [name for name in final_other_favs_list if name.gender == 'niña']

    # IDs de los favoritos del USUARIO ACTUAL (para saber si ya le gustan los del otro)
    current_user_fav_ids = set()
    if current_user:
        current_user_fav_ids = {name.id for name in current_user.favorites}

    return render_template('view_other_favorites.html',
                           current_user=current_user,
                           other_user=other_user,
                           other_user_boy_names=other_user_boy_names,
                           other_user_girl_names=other_user_girl_names,
                           current_user_fav_ids=current_user_fav_ids)

@app.route('/add_name', methods=['GET', 'POST'])
def add_custom_name():
    current_user = get_current_user()
    if not current_user:
        flash('Debes iniciar sesión para añadir nombres.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        names_input_str = request.form.get('names_input', '').strip()
        gender_input = request.form.get('gender')
        add_to_favs_checked = request.form.get('add_to_favorites') == 'yes'

        if not names_input_str:
            flash('El campo de nombres no puede estar vacío.', 'error')
            return redirect(url_for('add_custom_name'))
        
        if gender_input not in ['niño', 'niña']:
            flash('Por favor, selecciona un género válido.', 'error')
            return redirect(url_for('add_custom_name'))

        # Procesar la cadena de nombres
        name_texts_to_add = [name.strip().capitalize() for name in names_input_str.split(',') if name.strip()]
        
        if not name_texts_to_add: # Si después de limpiar no queda nada
            flash('No se ingresaron nombres válidos.', 'error')
            return redirect(url_for('add_custom_name'))

        added_count = 0
        favorited_count = 0
        already_exist_messages = []
        
        category_name = f"Agregados por {current_user.username.capitalize()}"

        for name_text in name_texts_to_add:
            if not name_text: continue # Saltar si algún nombre queda vacío después de limpiar

            # Comprobar duplicados: mismo texto de nombre y mismo género
            existing_name = Name.query.filter(
                func.lower(Name.name_text) == func.lower(name_text),
                Name.gender == gender_input
            ).first()

            name_object_to_process = None

            if existing_name:
                already_exist_messages.append(f'El nombre "{name_text}" ({gender_input}) ya existe (categoría "{existing_name.category}").')
                name_object_to_process = existing_name # Usar el existente para añadir a favoritos si se marca
            else:
                new_name = Name(
                    name_text=name_text,
                    gender=gender_input,
                    category=category_name,
                    ranking=None
                )
                db.session.add(new_name)
                # Necesitamos el ID para 'last_action' si se añade a favoritos,
                # así que hacemos un flush para obtener el ID antes del commit final.
                # O hacemos commit por cada nombre, lo cual es menos eficiente.
                # Por ahora, vamos a hacer flush para obtener ID y luego un solo commit.
                # db.session.flush() # Para obtener new_name.id si es necesario para last_action aquí
                name_object_to_process = new_name
                added_count += 1
        
        # Hacer commit de todos los nombres nuevos añadidos en el bucle
        if added_count > 0:
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                flash(f"Error al guardar nombres nuevos: {e}", "error")
                return redirect(url_for('add_custom_name'))
        
        # Ahora procesar la adición a favoritos si está marcado
        # Esto se hace DESPUÉS de que los nombres nuevos tengan ID (después del commit o flush)
        if add_to_favs_checked:
            for name_text in name_texts_to_add: # Iterar de nuevo para obtener los objetos (nuevos o existentes)
                if not name_text: continue
                
                # Re-consultar para asegurar que tenemos el objeto con ID (especialmente para los nuevos)
                name_obj = Name.query.filter(
                    func.lower(Name.name_text) == func.lower(name_text),
                    Name.gender == gender_input).first()

                if name_obj and name_obj not in current_user.favorites:
                    current_user.favorites.append(name_obj)
                    favorited_count += 1
                    # Actualizar last_action para el último nombre añadido a favoritos
                    session['last_action'] = {'type': 'like', 'name_id': name_obj.id, 'user_id': current_user.id}
                    session.modified = True # Asegurar que se guarde la sesión
        
        if favorited_count > 0:
            try:
                db.session.commit() # Commit de los cambios en favoritos
            except Exception as e:
                db.session.rollback()
                flash(f"Error al guardar nombres en favoritos: {e}", "error")
                return redirect(url_for('add_custom_name'))

        # Mensajes Flash
        if added_count > 0:
            flash(f'¡{added_count} nombre(s) nuevo(s) añadido(s) con éxito!', 'success')
        if favorited_count > 0:
            flash(f'¡{favorited_count} nombre(s) añadido(s) a tus favoritos!', 'success')
        for msg in already_exist_messages:
            flash(msg, 'info')
        if not already_exist_messages and added_count == 0 and favorited_count == 0:
             flash('No se realizaron cambios. Los nombres podrían ya existir y/o estar en favoritos.', 'info')


        return redirect(url_for('index')) # O a donde prefieras
            
    return render_template('add_name.html')

@app.route('/favorites')
def favorites():
    current_user = get_current_user()
    if not current_user: return redirect(url_for('login'))
    unique_favorite_names_by_text = {}
    for name_obj in current_user.favorites:
        if name_obj.name_text not in unique_favorite_names_by_text:
            unique_favorite_names_by_text[name_obj.name_text] = name_obj
    final_unique_favorites_list = sorted(list(unique_favorite_names_by_text.values()), key=lambda x: x.name_text)
    liked_boy_names = [name for name in final_unique_favorites_list if name.gender == 'niño'] # Renombrado para claridad
    liked_girl_names = [name for name in final_unique_favorites_list if name.gender == 'niña'] # Renombrado
    
    achievements = calculate_achievements(current_user)
    milestone_dynamic_duo = next((ach['achieved'] for ach in achievements if ach['id'] == 'dynamic_duo'), False)

    return render_template('favorites.html',
                           current_user=current_user,
                           liked_boy_names=liked_boy_names,
                           liked_girl_names=liked_girl_names,
                           milestone_reached=milestone_dynamic_duo)

@app.route('/matches')
def matches_page():
    current_user = get_current_user()
    user_luis = get_user_by_username_helper('luis') # Usar helper
    user_franyeglys = get_user_by_username_helper('franyeglys') # Usar helper
    if not user_luis or not user_franyeglys:
        flash("Usuarios 'luis' o 'franyeglys' no encontrados.", "error"); return redirect(url_for('index'))
    luis_fav_texts = {name.name_text for name in user_luis.favorites}
    franyeglys_fav_texts = {name.name_text for name in user_franyeglys.favorites}
    common_name_texts = luis_fav_texts.intersection(franyeglys_fav_texts)
    matched_boy_names, matched_girl_names = [], []
    if common_name_texts:
        displayed_names = {}
        all_relevant_favs = list(user_luis.favorites) + list(user_franyeglys.favorites)
        for name_obj in all_relevant_favs:
            if name_obj.name_text in common_name_texts and name_obj.name_text not in displayed_names:
                displayed_names[name_obj.name_text] = name_obj
        final_common_name_objects = sorted(list(displayed_names.values()), key=lambda x: x.name_text)
        matched_boy_names = [name for name in final_common_name_objects if name.gender == 'niño']
        matched_girl_names = [name for name in final_common_name_objects if name.gender == 'niña']
    return render_template('matches.html',
                           current_user=current_user,
                           matched_boy_names=matched_boy_names, matched_girl_names=matched_girl_names,
                           user_luis=user_luis, user_franyeglys=user_franyeglys)

# NUEVA RUTA PARA LA PÁGINA DE LOGROS
@app.route('/achievements')
def achievements_page_route(): # Renombrado para evitar conflicto con la variable 'achievements'
    current_user = get_current_user()
    if not current_user:
        flash("Debes iniciar sesión para ver tus logros.", "warning")
        return redirect(url_for('login'))

    achievements_list_data = calculate_achievements(current_user)
    return render_template('achievements_page.html', 
                           achievements_list=achievements_list_data, 
                           current_user=current_user)

# --- Punto de Entrada ---
if __name__ == '__main__':
    # MUY IMPORTANTE: Si cambiaste el modelo User para quitar contraseñas, etc.,
    # DEBES ELIMINAR el archivo babynames_v2.db ANTES de ejecutar esto la primera vez
    # para que se cree con el esquema correcto.
    if not os.path.exists(DATABASE_FILE):
        print(f"Archivo de base de datos {DATABASE_FILE} no encontrado. Se creará uno nuevo.")
        # No es necesario borrarlo explícitamente si no existe.
        # Si existe y quieres un reinicio completo por cambio de esquema, bórralo manualmente.

    with app.app_context():
        initialize_database()
    app.run(debug=True, host='0.0.0.0', port=5001)