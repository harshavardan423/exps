from flask import Flask, request, jsonify, render_template_string, redirect, session
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
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css" rel="stylesheet">
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

# File explorer template
FILE_EXPLORER_TEMPLATE = """
<div class="mb-4">
    <div class="flex items-center space-x-2 mb-4">
        <div class="bg-gray-200 text-gray-700 px-3 py-1 rounded-md text-sm">
            / {{ current_path }}
        </div>
        <div class="flex-grow"></div>
        <button class="bg-blue-500 hover:bg-blue-600 text-white px-3 py-1 rounded text-sm">
            <i class="fas fa-upload mr-1"></i> Upload
        </button>
        <button class="bg-green-500 hover:bg-green-600 text-white px-3 py-1 rounded text-sm">
            <i class="fas fa-folder-plus mr-1"></i> New Folder
        </button>
    </div>
    
    <div class="bg-white border rounded-md">
        <div class="flex items-center justify-between px-4 py-2 bg-gray-50 border-b font-medium text-sm">
            <div class="w-1/2">Name</div>
            <div class="w-1/4 text-center">Size</div>
            <div class="w-1/4 text-center">Modified</div>
        </div>
        
        {% if current_path != "" %}
        <div class="flex items-center px-4 py-2 border-b hover:bg-gray-50">
            <div class="w-1/2 flex items-center">
                <i class="fas fa-arrow-up text-gray-500 mr-2"></i>
                <a href="/{{ username }}/files?path={{ parent_path }}" class="text-blue-500 hover:underline">...</a>
            </div>
            <div class="w-1/4 text-center text-gray-500">-</div>
            <div class="w-1/4 text-center text-gray-500">-</div>
        </div>
        {% endif %}
        
        {% for item in file_data.folders %}
        <div class="flex items-center px-4 py-2 border-b hover:bg-gray-50">
            <div class="w-1/2 flex items-center">
                <i class="fas fa-folder text-yellow-400 mr-2"></i>
                <a href="/{{ username }}/files?path={{ current_path_prefix }}{{ item.name }}" class="hover:underline">{{ item.name }}</a>
            </div>
            <div class="w-1/4 text-center text-gray-500">-</div>
            <div class="w-1/4 text-center text-gray-500">{{ item.modified }}</div>
        </div>
        {% endfor %}
        
        {% for item in file_data.files %}
        <div class="flex items-center px-4 py-2 border-b hover:bg-gray-50">
            <div class="w-1/2 flex items-center">
                <i class="{{ item.icon }} mr-2 text-gray-500"></i>
                <span>{{ item.name }}</span>
            </div>
            <div class="w-1/4 text-center text-gray-500">{{ item.size }}</div>
            <div class="w-1/4 text-center text-gray-500">{{ item.modified }}</div>
        </div>
        {% endfor %}
    </div>
</div>
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

def fetch_local_data(instance, endpoint, params=None):
    """Fetch data from local instance with timeout
    
    Args:
        instance: The ExposedInstance object
        endpoint: API endpoint to call
        params: Optional query parameters
        
    Returns:
        (data, is_fresh) tuple, where data is the API response and is_fresh indicates
        whether the data was successfully retrieved from the instance
    """
    try:
        url = f"{instance.local_url}/api/{endpoint}"
        response = requests.get(
            url,
            params=params,
            timeout=5
        )
        if response.ok:
            return response.json(), True
    except Exception as e:
        print(f"Error fetching data from {endpoint}: {e}")
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

def get_file_icon(filename):
    """Get appropriate Font Awesome icon for file type"""
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    
    icons = {
        'pdf': 'fas fa-file-pdf text-red-500',
        'doc': 'fas fa-file-word text-blue-500',
        'docx': 'fas fa-file-word text-blue-500',
        'xls': 'fas fa-file-excel text-green-500',
        'xlsx': 'fas fa-file-excel text-green-500',
        'ppt': 'fas fa-file-powerpoint text-orange-500',
        'pptx': 'fas fa-file-powerpoint text-orange-500',
        'jpg': 'fas fa-file-image text-purple-500',
        'jpeg': 'fas fa-file-image text-purple-500',
        'png': 'fas fa-file-image text-purple-500',
        'gif': 'fas fa-file-image text-purple-500',
        'txt': 'fas fa-file-alt',
        'md': 'fas fa-file-alt',
        'py': 'fab fa-python text-blue-500',
        'js': 'fab fa-js text-yellow-500',
        'html': 'fab fa-html5 text-orange-500',
        'css': 'fab fa-css3 text-blue-500',
        'json': 'fas fa-file-code',
    }
    
    return icons.get(ext, 'fas fa-file')

def get_dummy_files(path=''):
    """Generate dummy file structure based on path"""
    # Mock file system structure
    root = {
        'documents': {
            'type': 'folder',
            'children': {
                'reports': {
                    'type': 'folder',
                    'children': {
                        'q1_report.pdf': {'type': 'file', 'size': '2.3 MB', 'modified': '2025-02-01'},
                        'q2_report.pdf': {'type': 'file', 'size': '3.1 MB', 'modified': '2025-02-15'},
                    }
                },
                'project_proposal.docx': {'type': 'file', 'size': '546 KB', 'modified': '2025-01-20'},
                'budget.xlsx': {'type': 'file', 'size': '1.2 MB', 'modified': '2025-02-10'},
            }
        },
        'images': {
            'type': 'folder',
            'children': {
                'profile.jpg': {'type': 'file', 'size': '1.5 MB', 'modified': '2025-01-15'},
                'background.png': {'type': 'file', 'size': '2.8 MB', 'modified': '2025-01-22'},
            }
        },
        'code': {
            'type': 'folder',
            'children': {
                'projects': {
                    'type': 'folder',
                    'children': {
                        'atom': {
                            'type': 'folder',
                            'children': {
                                'main.py': {'type': 'file', 'size': '4.2 KB', 'modified': '2025-02-18'},
                                'utils.py': {'type': 'file', 'size': '2.7 KB', 'modified': '2025-02-18'},
                                'config.json': {'type': 'file', 'size': '1.3 KB', 'modified': '2025-02-17'},
                            }
                        }
                    }
                },
                'snippets': {
                    'type': 'folder',
                    'children': {
                        'script.js': {'type': 'file', 'size': '1.8 KB', 'modified': '2025-02-05'},
                        'style.css': {'type': 'file', 'size': '3.4 KB', 'modified': '2025-02-08'},
                    }
                }
            }
        },
        'notes.txt': {'type': 'file', 'size': '12 KB', 'modified': '2025-02-20'},
        'README.md': {'type': 'file', 'size': '5 KB', 'modified': '2025-01-10'},
    }
    
    # Default return value if path is not found
    result = {'folders': [], 'files': []}
    
    # Navigate to the requested path
    if not path:
        current = root
    else:
        parts = path.strip('/').split('/')
        current = root
        try:
            for part in parts:
                if part in current and current[part]['type'] == 'folder':
                    current = current[part]['children']
                else:
                    # Path not found, return empty structure
                    return result
        except (KeyError, TypeError):
            # Handle any navigation errors
            return result
    
    # Convert the current directory structure to the response format
    folders = []
    files = []
    
    for name, item in current.items():
        if item['type'] == 'folder':
            folders.append({
                'name': name,
                'modified': '2025-02-20'  # Default date for folders
            })
        else:
            files.append({
                'name': name,
                'size': item['size'],
                'modified': item['modified'],
                'icon': get_file_icon(name)
            })
    
    result = {
        'folders': sorted(folders, key=lambda x: x['name']),
        'files': sorted(files, key=lambda x: x['name'])
    }
    
    return result

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

    # Create the connections section
    connections_section = '<div class="text-gray-500 italic">No connections configured</div>'
    if data.get('connections_data'):
        connections_section = '<div class="grid grid-cols-2 gap-3">'
        for k in data['connections_data'].keys():
            connections_section += f'<div class="bg-gray-50 p-3 rounded">{k}</div>'
        connections_section += '</div>'

    # Create the apps section
    apps_section = '<div class="text-gray-500 italic">No apps installed</div>'
    if data.get('apps'):
        apps_section = '<div class="grid grid-cols-2 gap-3">'
        for k in data['apps'].keys():
            apps_section += f'<div class="bg-gray-50 p-3 rounded">{k}</div>'
        apps_section += '</div>'

    # Create the sequences section
    sequences_section = '<div class="text-gray-500 italic">No sequences defined</div>'
    if data.get('sequences'):
        sequences_section = ''
        for seq_name, seq_data in data['sequences'].items():
            sequences_section += f'''
                <div class="mb-4 last:mb-0">
                    <div class="font-medium text-lg mb-2">{seq_name}</div>
                    <div class="bg-gray-50 p-4 rounded">
                        <div class="space-y-2">
            '''
            for action in seq_data:
                icon = 'code' if action['type'] == 'actions' else 'cog'
                sequences_section += f'''
                    <div class="flex items-center space-x-2">
                        <span class="text-blue-500">
                            <i class="fas fa-{icon}"></i>
                        </span>
                        <span class="font-medium">{action['name']}</span>
                    </div>
                '''
            sequences_section += '''
                        </div>
                    </div>
                </div>
            '''

    content = f'''
        <div class="space-y-6">
            <div class="flex items-center space-x-4">
                <div class="text-2xl font-bold text-gray-700">{data.get('name', username)}'s Dashboard</div>
            </div>
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div class="bg-white p-6 rounded-lg shadow">
                    <h2 class="text-xl font-semibold mb-4 text-gray-700">
                        <i class="fas fa-plug mr-2"></i>Connections
                    </h2>
                    {connections_section}
                </div>

                <div class="bg-white p-6 rounded-lg shadow">
                    <h2 class="text-xl font-semibold mb-4 text-gray-700">
                        <i class="fas fa-cube mr-2"></i>Apps
                    </h2>
                    {apps_section}
                </div>
            </div>

            <div class="bg-white p-6 rounded-lg shadow">
                <h2 class="text-xl font-semibold mb-4 text-gray-700">
                    <i class="fas fa-code-branch mr-2"></i>Sequences
                </h2>
                {sequences_section}
            </div>
        </div>
    '''
    
    return render_page(username, "Home", content, 
                      instance_status='online' if is_fresh else 'offline')


@app.route('/<username>/files')
def user_files(username):
    instance = ExposedInstance.query.filter_by(username=username).first()
    if not instance:
        return jsonify({'error': 'User not found'}), 404
    
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
        
    path = request.args.get('path', '')
    path_parts = path.strip('/').split('/') if path else []
    parent_path = '/'.join(path_parts[:-1]) if path_parts else ""
    
    # Try to get real file data from local instance or cached data
    data, is_fresh = fetch_local_data(instance, 'files_data', {'path': path})
    
    if data:
        # Update cached data for this path
        if not instance.files_data:
            instance.files_data = {}
        
        instance.files_data = data
        instance.last_data_sync = datetime.utcnow()
        db.session.commit()
        file_data = data.get('structure', {'folders': [], 'files': []})
    elif instance.files_data:
        # Use cached data if available
        file_data = instance.files_data.get('structure', {'folders': [], 'files': []})
    else:
        # Fall back to dummy data if nothing is available
        file_data = get_dummy_files(path)
    
    # Add icons to file data
    for file in file_data.get('files', []):
        if 'icon' not in file:
            file['icon'] = get_file_icon(file['name'])
    
    # Render the file explorer template
    content = render_template_string(
        FILE_EXPLORER_TEMPLATE,
        username=username,
        file_data=file_data,
        current_path=path,
        current_path_prefix=path + '/' if path else '',
        parent_path=parent_path
    )
    
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
        initial_data = data.get('initial_data', {})
        
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
        
        # Store initial data if provided
        if initial_data:
            instance.home_data = initial_data.get('home_data')
            instance.files_data = initial_data.get('files_data')
            instance.behaviors_data = initial_data.get('behaviors_data')
            instance.last_data_sync = datetime.utcnow()
        
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
        
        # Update instance data if provided
        if request.is_json:
            data = request.json
            if data:
                if 'home_data' in data:
                    instance.home_data = data['home_data']
                if 'files_data' in data:
                    instance.files_data = data['files_data']
                if 'behaviors_data' in data:
                    instance.behaviors_data = data['behaviors_data']
                instance.last_data_sync = datetime.utcnow()
        
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
            username = instance.username  # Store username for logging
            db.session.delete(instance)
            db.session.commit()
            print(f"Successfully deregistered instance for user: {username}")
            return jsonify({'status': 'Instance deregistered successfully'}), 200
        return jsonify({'error': 'Instance not found'}), 404
    except Exception as e:
        db.session.rollback()
        print(f"Error during deregistration: {e}")
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
