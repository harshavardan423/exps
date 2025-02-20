from flask import Flask, request, jsonify, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import requests
import uuid
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Configure SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///exposed_instances.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class ExposedInstance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    username = db.Column(db.String(100), nullable=False)
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

with app.app_context():
    db.create_all()

@app.route('/register', methods=['POST'])
def register_instance():
    data = request.json
    user_id = data.get('user_id')
    username = data.get('username')
    local_url = data.get('local_url')
    
    if not all([user_id, username, local_url]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Check if instance already exists
    instance = ExposedInstance.query.filter_by(user_id=user_id).first()
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

@app.route('/heartbeat/<token>', methods=['POST'])
def heartbeat(token):
    instance = ExposedInstance.query.filter_by(token=token).first()
    if not instance:
        return jsonify({'error': 'Instance not found'}), 404
    
    instance.last_heartbeat = datetime.utcnow()
    db.session.commit()
    return jsonify({'status': 'ok'}), 200

@app.route('/<username>/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy_request(username, subpath):
    instance = ExposedInstance.query.filter_by(username=username).first()
    if not instance:
        return jsonify({'error': 'Instance not found'}), 404
    
    # Check if instance is still alive (within last 5 minutes)
    if (datetime.utcnow() - instance.last_heartbeat).total_seconds() > 300:
        return jsonify({'error': 'Instance not responding'}), 503
    
    # Forward the request to the local instance
    target_url = f"{instance.local_url}/{subpath}"
    response = requests.request(
        method=request.method,
        url=target_url,
        headers={key: value for key, value in request.headers if key != 'Host'},
        data=request.get_data(),
        cookies=request.cookies,
        allow_redirects=False
    )
    
    return response.content, response.status_code, response.headers.items()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)