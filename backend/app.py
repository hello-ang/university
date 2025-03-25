from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
import json
from datetime import datetime
import os
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
from functools import wraps
from werkzeug.utils import secure_filename
import base64
import re

app = Flask(__name__, static_folder='..', static_url_path='')
app.secret_key = secrets.token_hex(16)

# 修改CORS配置
CORS(app, resources={
    r"/*": {
        "origins": "*",  # 允许所有来源访问
        "supports_credentials": True,
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# 添加session配置
app.config.update(
    SESSION_COOKIE_SECURE=False,  # 如果不是HTTPS，设置为False
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)

# 确保data目录存在

DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, 'users.json')
ARTICLES_FILE = os.path.join(DATA_DIR, 'articles.json')
COMMENTS_FILE = os.path.join(DATA_DIR, 'comments.json')
LIKES_FILE = os.path.join(DATA_DIR, 'likes.json')

# 修改文件上传配置
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_json_file(file_path):
    if not os.path.exists(file_path):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=4)

# 初始化所有数据文件
for file_path in [USERS_FILE, ARTICLES_FILE, COMMENTS_FILE, LIKES_FILE]:
    init_json_file(file_path)

def load_data(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# 用户认证装饰器
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': '请先登录'}), 401
        return f(*args, **kwargs)
    return decorated

# 用户注册
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    users = load_data(USERS_FILE)
    
    if any(user['username'] == data['username'] for user in users):
        return jsonify({'error': '用户名已存在'}), 400
    
    new_user = {
        'id': str(len(users) + 1),
        'username': data['username'],
        'password': generate_password_hash(data['password']),
        'created_at': datetime.now().isoformat()
    }
    users.append(new_user)
    save_data(USERS_FILE, users)
    
    return jsonify({'message': '注册成功'}), 201

# 用户登录
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    users = load_data(USERS_FILE)
    
    user = next((user for user in users if user['username'] == data['username']), None)
    if user and check_password_hash(user['password'], data['password']):
        session['user_id'] = user['id']
        return jsonify({
            'message': '登录成功',
            'user': {
                'id': user['id'],
                'username': user['username']
            }
        })
    
    return jsonify({'error': '用户名或密码错误'}), 401

# 发布文章
@app.route('/api/articles', methods=['POST'])
@login_required
def create_article():
    if 'title' not in request.form or 'content' not in request.form:
        return jsonify({'error': '缺少必要的文章信息'}), 400
        
    title = request.form['title']
    content = request.form['content']
    
    # 处理图片数据
    image_data = []
    for key in request.form:
        if key.startswith('image'):
            img_data = request.form[key]
            if img_data.startswith('data:image'):
                image_data.append(img_data)
    
    articles = load_data(ARTICLES_FILE)
    new_article = {
        'id': str(len(articles) + 1),
        'title': title,
        'content': content,
        'images': image_data,  # 直接存储Base64图片数据
        'author_id': session['user_id'],
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat()
    }
    
    articles.append(new_article)
    save_data(ARTICLES_FILE, articles)
    
    return jsonify(new_article), 201

# 获取文章列表
@app.route('/api/articles', methods=['GET'])
def get_articles():
    articles = load_data(ARTICLES_FILE)
    users = load_data(USERS_FILE)
    comments = load_data(COMMENTS_FILE)
    
    for article in articles:
        # 添加作者信息
        author = next((user for user in users if user['id'] == article['author_id']), None)
        article['author'] = author['username'] if author else '未知用户'
        
        # 添加评论信息
        article['comments'] = [
            comment for comment in comments 
            if comment['article_id'] == article['id']
        ]
    
    return jsonify(articles)

# 获取文章详情
@app.route('/api/articles/<article_id>', methods=['GET'])
def get_article(article_id):
    articles = load_data(ARTICLES_FILE)
    article = next((a for a in articles if a['id'] == article_id), None)
    
    if not article:
        return jsonify({'error': '文章不存在'}), 404
    
    comments = load_data(COMMENTS_FILE)
    article_comments = [c for c in comments if c['article_id'] == article_id]
    
    likes = load_data(LIKES_FILE)
    like_count = len([l for l in likes if l['article_id'] == article_id])
    
    return jsonify({
        **article,
        'comments': article_comments,
        'like_count': like_count
    })

# 修改评论结构
@app.route('/api/articles/<article_id>/comments', methods=['POST'])
@login_required
def add_comment(article_id):
    data = request.json
    comments = load_data(COMMENTS_FILE)
    users = load_data(USERS_FILE)
    
    user = next((user for user in users if user['id'] == session['user_id']), None)
    
    new_comment = {
        'id': str(len(comments) + 1),
        'article_id': article_id,
        'user_id': session['user_id'],
        'author': user['username'],
        'content': data['content'],
        'created_at': datetime.now().isoformat(),
        'parent_id': data.get('parent_id', None),  # 添加父评论ID
        'replies': []  # 添加回复数组
    }
    
    comments.append(new_comment)
    save_data(COMMENTS_FILE, comments)
    
    return jsonify(new_comment), 201

# 添加回复评论的路由
@app.route('/api/comments/<comment_id>/replies', methods=['POST'])
@login_required
def add_reply(comment_id):
    data = request.json
    comments = load_data(COMMENTS_FILE)
    users = load_data(USERS_FILE)
    
    parent_comment = next((c for c in comments if c['id'] == comment_id), None)
    if not parent_comment:
        return jsonify({'error': '评论不存在'}), 404
    
    user = next((user for user in users if user['id'] == session['user_id']), None)
    
    new_reply = {
        'id': str(len(comments) + 1),
        'article_id': parent_comment['article_id'],
        'user_id': session['user_id'],
        'author': user['username'],
        'content': data['content'],
        'created_at': datetime.now().isoformat(),
        'parent_id': comment_id
    }
    
    comments.append(new_reply)
    save_data(COMMENTS_FILE, comments)
    
    return jsonify(new_reply), 201

# 点赞功能
@app.route('/api/articles/<article_id>/like', methods=['POST'])
@login_required
def like_article(article_id):
    try:
        likes = load_data(LIKES_FILE)
        user_id = session['user_id']
        
        # 检查是否已经点赞
        existing_like = any(l['article_id'] == article_id and l['user_id'] == user_id for l in likes)
        if existing_like:
            return jsonify({'error': '已经点赞过了'}), 400
        
        # 添加新的点赞记录
        new_like = {
            'id': str(len(likes) + 1),
            'article_id': article_id,
            'user_id': user_id,
            'created_at': datetime.now().isoformat()
        }
        likes.append(new_like)
        save_data(LIKES_FILE, likes)
        
        # 计算最新点赞数
        like_count = len([l for l in likes if l['article_id'] == article_id])
        
        return jsonify({
            'message': '点赞成功',
            'like_count': like_count
        })
    except Exception as e:
        print(f"点赞失败: {str(e)}")
        return jsonify({'error': '点赞失败'}), 500

# 添加前端路由
@app.route('/')
def index():
    return send_from_directory('..', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('..', filename)

# 添加错误处理
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': '请求的资源不存在'}), 404

# 添加登出功能
@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': '登出成功'})

# 添加检查登录状态的接口
@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    if 'user_id' in session:
        users = load_data(USERS_FILE)
        user = next((user for user in users if user['id'] == session['user_id']), None)
        if user:
            return jsonify({
                'authenticated': True,
                'user': {
                    'id': user['id'],
                    'username': user['username']
                }
            })
    return jsonify({'authenticated': False}), 401

# 添加静态文件服务路由
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# 添加删除文章的路由
@app.route('/api/articles/<article_id>', methods=['DELETE'])
@login_required
def delete_article(article_id):
    articles = load_data(ARTICLES_FILE)
    comments = load_data(COMMENTS_FILE)
    likes = load_data(LIKES_FILE)
    
    # 检查文章是否存在且是否为作者
    article = next((a for a in articles if a['id'] == article_id), None)
    if not article:
        return jsonify({'error': '文章不存在'}), 404
    if article['author_id'] != session['user_id']:
        return jsonify({'error': '没有权限删除此文章'}), 403
    
    # 删除文章相关的图片
    if 'images' in article and article['images']:
        for image_path in article['images']:
            try:
                full_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', image_path.lstrip('/'))
                if os.path.exists(full_path):
                    os.remove(full_path)
            except Exception as e:
                print(f"删除图片失败: {e}")
    
    # 删除文章相关的评论和点赞
    comments[:] = [c for c in comments if c['article_id'] != article_id]
    likes[:] = [l for l in likes if l['article_id'] != article_id]
    
    # 删除文章
    articles.remove(article)
    
    # 保存更改
    save_data(ARTICLES_FILE, articles)
    save_data(COMMENTS_FILE, comments)
    save_data(LIKES_FILE, likes)
    
    return jsonify({'message': '文章删除成功'})

# 添加删除评论的路由
@app.route('/api/comments/<comment_id>', methods=['DELETE'])
@login_required
def delete_comment(comment_id):
    comments = load_data(COMMENTS_FILE)
    
    # 检查评论是否存在且是否为评论作者
    comment = next((c for c in comments if c['id'] == comment_id), None)
    if not comment:
        return jsonify({'error': '评论不存在'}), 404
    if comment['user_id'] != session['user_id']:
        return jsonify({'error': '没有权限删除此评论'}), 403
    
    # 删除评论及其所有回复
    comments[:] = [c for c in comments if c['id'] != comment_id and c.get('parent_id') != comment_id]
    
    save_data(COMMENTS_FILE, comments)
    return jsonify({'message': '评论删除成功'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=8000)