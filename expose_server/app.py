from flask import Flask, request, jsonify, render_template_string, redirect,session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import requests
import uuid
from datetime import datetime
import os
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)
CORS(app)

# Database configuration
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'exposed_instances.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# HTML Templates
BASE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>{{ title }} - {{ username }}'s Atom Instance</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body class="bg-gray-100">
    <nav class="bg-white shadow-lg">
        <div class="max-w-6xl mx-auto px-4">
            <div class="flex justify-between">
                <div class="flex space-x-7">
                    <div class="flex items-center py-4">
                        <span class="font-semibold text-gray-500 text-lg">{{ username }}'s Atom</span>
                    </div>
                    <div class="hidden md:flex items-center space-x-1">
                        <a href="/{{ username }}/home" class="py-4 px-2 text-gray-500 hover:text-gray-900">Home</a>
                        <a href="/{{ username }}/files" class="py-4 px-2 text-gray-500 hover:text-gray-900">Files</a>
                        <a href="/{{ username }}/behaviors" class="py-4 px-2 text-gray-500 hover:text-gray-900">Behaviors</a>
                    </div>
                </div>
            </div>
        </div>
    </nav>
    
    <div class="container mx-auto px-4 py-8">
        <h1 class="text-2xl font-bold mb-6">{{ title }}</h1>
        <div class="bg-white shadow-md rounded px-8 pt-6 pb-8 mb-4">
            {{ content | safe }}
        </div>
        
        {% if instance_status %}
        <div class="mt-4 p-4 rounded {% if instance_status == 'online' %}bg-green-100{% else %}bg-yellow-100{% endif %}">
            <p class="text-sm">
                Instance Status: 
                <span class="font-semibold">
                    {% if instance_status == 'online' %}
                        Online
                    {% else %}
                        Offline (showing cached data)
                    {% endif %}
                </span>
            </p>
        </div>
        {% endif %}
    </div>
</body>
</html>
"""

INDEX_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Atom Exposure Server</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body class="bg-gray-100">
    <div class="container mx-auto px-4 py-8">
        <h1 class="text-3xl font-bold mb-6">Active Atom Instances</h1>
        
        {% if instances %}
            <div class="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                {% for instance in instances %}
                    <div class="bg-white rounded-lg shadow p-6">
                        <h2 class="text-xl font-semibold mb-2">{{ instance.username }}</h2>
                        <div class="space-y-2">
                            <a href="/{{ instance.username }}/home" 
                               class="block w-full text-center bg-blue-500 hover:bg-blue-600 text-white font-semibold py-2 px-4 rounded">
                                View Instance
                            </a>
                        </div>
                    </div>
                {% endfor %}
            </div>
        {% else %}
            <div class="bg-white rounded-lg shadow p-6">
                <p class="text-gray-500">No active instances available.</p>
            </div>
        {% endif %}
    </div>
</body>
</html>
"""

# Database Model
class ExposedInstance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    username = db.Column(db.String(100), nullable=False, unique=True)
    local_url = db.Column(db.String(200), nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False)
    last_heartbeat = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Cached data
    home_data = db.Column(db.JSON, nullable=True)
    files_data = db.Column(db.JSON, nullable=True)
    behaviors_data = db.Column(db.JSON, nullable=True)
    last_data_sync = db.Column(db.DateTime, nullable=True)
    
    def to_dict(self):
        return {
            'user_id': self.user_id,
            'username': self.username,
            'local_url': self.local_url,
            'token': self.token,
            'last_heartbeat': self.last_heartbeat.isoformat()
        }
    
    def is_online(self):
        return (datetime.utcnow() - self.last_heartbeat).total_seconds() <= 300

def create_tables():
    with app.app_context():
        db.create_all()

def render_page(username, title, content, instance_status=None):
    return render_template_string(
        BASE_TEMPLATE, 
        username=username,
        title=title,
        content=content,
        instance_status=instance_status
    )

def fetch_local_data(instance, endpoint):
    """Fetch data from local instance with timeout"""
    try:
        response = requests.get(
            f"{instance.local_url}/api/{endpoint}",
            timeout=5
        )
        if response.ok:
            return response.json(), True
    except:
        pass
    return None, False
    
def check_access(instance, request):
    """Check if current user has access to the instance"""
    # Get email from query params
    user_email = request.args.get('email')
    
    # Try to fetch allowed_users from local instance
    try:
        response = requests.get(f"{instance.local_url}/api/allowed_users", timeout=3)
        if response.ok:
            allowed_users = response.json().get('allowed_users', [])
            # If no allowed users set, allow all access
            if not allowed_users:
                return True
            # Check if user email is in allowed users
            return user_email in allowed_users
    except Exception as e:
        print(f"Error checking access: {e}")
    
    # If we can't get the allowed users list, default to allowing access
    # You might want to change this based on your security requirements
    return True


# Routes
@app.route('/')
def index():
    try:
        instances = ExposedInstance.query.all()
        active_instances = [
            instance for instance in instances
            if (datetime.utcnow() - instance.last_heartbeat).total_seconds() <= 300
        ]
        
        return render_template_string(
            INDEX_TEMPLATE,
            instances=active_instances
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/<username>/home')
def user_home(username):
    instance = ExposedInstance.query.filter_by(username=username).first()
    if not instance:
        return jsonify({'error': 'User not found'}), 404

    # Fixed indentation
    if not check_access(instance, request):
        return render_template_string("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Access Required</title>
                <script src="https://cdn.tailwindcss.com"></script>
            </head>
            <body class="bg-gray-100">
                <div class="container mx-auto px-4 py-8">
                    <div class="bg-white shadow-md rounded px-8 pt-6 pb-8 mb-4">
                        <h1 class="text-2xl font-bold mb-4">Access Required</h1>
                        <p class="mb-4">Please enter your email to access this instance:</p>
                        <form method="GET" class="space-y-4">
                            <input type="email" name="email" placeholder="Enter your email" 
                                   class="w-full px-3 py-2 border rounded" required>
                            <button type="submit" 
                                    class="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600">
                                Submit
                            </button>
                        </form>
                    </div>
                </div>
            </body>
            </html>
        """)
         
    data, is_fresh = fetch_local_data(instance, 'home_data')
    if data:
        instance.home_data = data
        instance.last_data_sync = datetime.utcnow()
        db.session.commit()
    elif instance.home_data:
        data = instance.home_data
    else:
        data = {"message": "No data available"}

    content = f"""
        <div class="space-y-4">
            <div class="text-lg">Welcome to {username}'s Atom Instance</div>
            <div class="text-gray-600">
                Last updated: {instance.last_data_sync.strftime('%Y-%m-%d %H:%M:%S') if instance.last_data_sync else 'Never'}
            </div>
            <pre class="bg-gray-100 p-4 rounded overflow-auto">{str(data)}</pre>
        </div>
    """
    
    return render_page(username, "Home", content, 
                      instance_status='online' if is_fresh else 'offline')

@app.route('/<username>/files')
def user_files(username):
    instance = ExposedInstance.query.filter_by(username=username).first()
    if not instance:
        return jsonify({'error': 'User not found'}), 404

    data, is_fresh = fetch_local_data(instance, 'files_data')
    if data:
        instance.files_data = data
        instance.last_data_sync = datetime.utcnow()
        db.session.commit()
    elif instance.files_data:
        data = instance.files_data
    else:
        data = {"message": "No files data available"}

    content = f"""
        <div class="space-y-4">
            <div class="text-lg">Files View</div>
            <pre class="bg-gray-100 p-4 rounded overflow-auto">{str(data)}</pre>
        </div>
    """
    
    return render_page(username, "Files", content,
                      instance_status='online' if is_fresh else 'offline')

@app.route('/<username>/behaviors')
def user_behaviors(username):
    instance = ExposedInstance.query.filter_by(username=username).first()
    if not instance:
        return jsonify({'error': 'User not found'}), 404

    data, is_fresh = fetch_local_data(instance, 'behaviors_data')
    if data:
        instance.behaviors_data = data
        instance.last_data_sync = datetime.utcnow()
        db.session.commit()
    elif instance.behaviors_data:
        data = instance.behaviors_data
    else:
        data = {"message": "No behaviors data available"}

    content = f"""
        <div class="space-y-4">
            <div class="text-lg">Behaviors</div>
            <pre class="bg-gray-100 p-4 rounded overflow-auto">{str(data)}</pre>
        </div>
    """
    
    return render_page(username, "Behaviors", content,
                      instance_status='online' if is_fresh else 'offline')

@app.route('/register', methods=['POST'])
def register_instance():
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        user_id = data.get('user_id')
        username = data.get('username')
        local_url = data.get('local_url')
        
        if not all([user_id, username, local_url]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Check if instance already exists
        instance = ExposedInstance.query.filter_by(username=username).first()
        if instance:
            instance.local_url = local_url
            instance.last_heartbeat = datetime.utcnow()
        else:
            instance = ExposedInstance(
                user_id=user_id,
                username=username,
                local_url=local_url,
                token=str(uuid.uuid4())
            )
            db.session.add(instance)
        
        db.session.commit()
        return jsonify(instance.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/heartbeat/<token>', methods=['POST'])
def heartbeat(token):
    try:
        instance = ExposedInstance.query.filter_by(token=token).first()
        if not instance:
            return jsonify({'error': 'Instance not found'}), 404
        
        instance.last_heartbeat = datetime.utcnow()
        db.session.commit()
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/deregister/<token>', methods=['DELETE'])
def deregister_instance(token):
    try:
        instance = ExposedInstance.query.filter_by(token=token).first()
        if instance:
            db.session.delete(instance)
            db.session.commit()
            return jsonify({'status': 'Instance deregistered successfully'}), 200
        return jsonify({'error': 'Instance not found'}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    create_tables()
    app.run(host='0.0.0.0', port=5000)
