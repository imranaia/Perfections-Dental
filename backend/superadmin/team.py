import sqlite3
# =========================================
# Perfections Dental Services
# Team Members Module - v1.0
# SuperAdmin Only — powers the landing page's "Meet Your Smile Architects"
# section (frontend/index.html) via /api/public/site-content for reads.
# =========================================

from config import Config
from db import get_db
from auth import login_required, role_required
from flask import Blueprint, jsonify, session, request
from werkzeug.utils import secure_filename
from datetime import datetime
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

team_bp = Blueprint('team', __name__, url_prefix='/api/superadmin/team')
uploads_bp = Blueprint('uploads', __name__, url_prefix='/api/superadmin')

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), '..', 'frontend', 'assets', 'uploads')


def _row_to_member(row):
    return {
        'id': row['id'],
        'name': row['name'],
        'role_title': row['role_title'],
        'bio': row['bio'],
        'photo_url': row['photo_url'],
        'tags': row['tags'],
        'display_order': row['display_order'],
        'is_active': row['is_active'],
    }


# =========================================
# Get All Team Members (incl. inactive)
# =========================================
@team_bp.route('/', methods=['GET'])
@login_required
@role_required('superadmin')
def get_team_members():
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM team_members ORDER BY display_order, id")
            members = [_row_to_member(r) for r in cursor.fetchall()]

        db.close()
        return jsonify({'success': True, 'team': members}), 200
    except Exception as e:
        print(f"Get team members error: {e}")
        return jsonify({'error': 'Failed to fetch team members'}), 500


# =========================================
# Create Team Member
# =========================================
@team_bp.route('/', methods=['POST'])
@login_required
@role_required('superadmin')
def create_team_member():
    try:
        data = request.get_json() or {}
        if not data.get('name') or not data.get('role_title'):
            return jsonify({'error': 'Name and role are required'}), 400

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                INSERT INTO team_members
                    (name, role_title, bio, photo_url, tags, display_order, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get('name'),
                data.get('role_title'),
                data.get('bio', ''),
                data.get('photo_url'),
                data.get('tags', ''),
                data.get('display_order', 0),
                data.get('is_active', True),
            ))
            member_id = cursor.lastrowid
            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Team member created', 'member_id': member_id}), 201
    except Exception as e:
        print(f"Create team member error: {e}")
        return jsonify({'error': 'Failed to create team member'}), 500


# =========================================
# Update Team Member
# =========================================
@team_bp.route('/<int:member_id>', methods=['PUT'])
@login_required
@role_required('superadmin')
def update_team_member(member_id):
    try:
        data = request.get_json() or {}
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                UPDATE team_members SET
                    name = ?,
                    role_title = ?,
                    bio = ?,
                    photo_url = ?,
                    tags = ?,
                    display_order = ?,
                    is_active = ?,
                    updated_at = datetime('now')
                WHERE id = ?
            """, (
                data.get('name'),
                data.get('role_title'),
                data.get('bio', ''),
                data.get('photo_url'),
                data.get('tags', ''),
                data.get('display_order', 0),
                data.get('is_active', True),
                member_id,
            ))
            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Team member updated'}), 200
    except Exception as e:
        print(f"Update team member error: {e}")
        return jsonify({'error': 'Failed to update team member'}), 500


# =========================================
# Delete Team Member
# =========================================
@team_bp.route('/<int:member_id>', methods=['DELETE'])
@login_required
@role_required('superadmin')
def delete_team_member(member_id):
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute(
                "DELETE FROM team_members WHERE id = ?", (member_id,))
            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Team member deleted'}), 200
    except Exception as e:
        print(f"Delete team member error: {e}")
        return jsonify({'error': 'Failed to delete team member'}), 500


# =========================================
# Upload a photo (team member photo, logo replacement, etc.)
# Used by the landing-page "first person" editor.
# =========================================
@uploads_bp.route('/uploads', methods=['POST'])
@login_required
@role_required('superadmin')
def upload_photo():
    try:
        if 'photo' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['photo']
        if not file or not file.filename:
            return jsonify({'error': 'No file selected'}), 400

        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({'error': 'Only jpg, jpeg, png, or webp images are allowed'}), 400

        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)
        if size > MAX_UPLOAD_BYTES:
            return jsonify({'error': 'Image must be smaller than 5MB'}), 400

        os.makedirs(UPLOAD_DIR, exist_ok=True)
        filename = secure_filename(f"{uuid.uuid4().hex}.{ext}")
        file.save(os.path.join(UPLOAD_DIR, filename))

        return jsonify({'success': True, 'url': f'/assets/uploads/{filename}'}), 201
    except Exception as e:
        print(f"Upload photo error: {e}")
        return jsonify({'error': 'Failed to upload photo'}), 500
