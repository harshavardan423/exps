from flask import Flask, request, jsonify, redirect
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

# Configure SQLAlchemy
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'exposed_instances.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class ExposedInstance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    username = db.Column(db.String(100), nullable=False, unique=True)
    local_url = db.Column(db.String(200), nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False)
    last_heartbeat = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'user_id': self.user_id,
            'username': self.username,
            'local_url': self.local_url,
            'token': self.token,
            'last_heartbeat': self.last_heartbeat.isoformat()
        }

def create_tables():
    with app.app_context():
        db.create_all()

@app.route('/')
def index():
    try:
        # Fetch all instances
        instances = ExposedInstance.query.all()

        # Filter active instances (heartbeat within the last 5 minutes)
        active_instances = [
            {
                'username': instance.username,
                'local_url': instance.local_url
            }
            for instance in instances
            if (datetime.utcnow() - instance.last_heartbeat).total_seconds() <= 300
        ]

        return jsonify({
            'status': 'running',
            'message': 'Expose Server is running',
            'active_instance_count': len(active_instances),
            'active_instances': active_instances
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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

@app.route('/<username>', methods=['GET', 'POST', 'PUT', 'DELETE'])
@app.route('/<username>/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy_request(username, subpath=""):
    try:
        instance = ExposedInstance.query.filter_by(username=username).first()
        if not instance:
            return jsonify({'error': 'Instance not found'}), 404
        
        # Check if instance is still alive (within last 5 minutes)
        if (datetime.utcnow() - instance.last_heartbeat).total_seconds() > 300:
            return jsonify({'error': 'Instance not responding'}), 503
        
        # Forward the request to the local instance
        target_url = f"{instance.local_url.rstrip('/')}/{subpath}"
        
        # Filter out problematic headers
        headers = {
            key: value for key, value in request.headers.items()
            if key.lower() not in ['host', 'content-length']
        }
        
        try:
            response = requests.request(
                method=request.method,
                url=target_url,
                headers=headers,
                data=request.get_data(),
                cookies=request.cookies,
                allow_redirects=False,
                timeout=30  # Add timeout to prevent hanging
            )
            
            # Filter response headers
            response_headers = {
                key: value for key, value in response.headers.items()
                if key.lower() not in ['content-encoding', 'transfer-encoding']
            }
            
            return response.content, response.status_code, response_headers
        except requests.RequestException as e:
            return jsonify({'error': f'Failed to forward request: {str(e)}'}), 502
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Internal server error'}), 500

def main():
    create_tables()
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    main()
