import sqlite3
# =========================================
# Perfections Dental Services
# Gallery Module - v1.0
# SuperAdmin Only — powers the landing page's "A World-Class Environment"
# gallery section (frontend/index.html) via /api/public/site-content for
# reads. Mirrors backend/superadmin/team.py's shape.
# =========================================

from config import Config
from db import get_db
from auth import login_required, role_required
from flask import Blueprint, jsonify, session, request
from datetime import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

gallery_bp = Blueprint('gallery', __name__, url_prefix='/api/superadmin/gallery')


def _row_to_image(row):
    return {
        'id': row['id'],
        'image_url': row['image_url'],
        'caption': row['caption'],
        'display_order': row['display_order'],
        'is_active': row['is_active'],
    }


@gallery_bp.route('/', methods=['GET'])
@login_required
@role_required('superadmin')
def get_gallery_images():
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM gallery_images ORDER BY display_order, id")
            images = [_row_to_image(r) for r in cursor.fetchall()]

        db.close()
        return jsonify({'success': True, 'gallery': images}), 200
    except Exception as e:
        print(f"Get gallery images error: {e}")
        return jsonify({'error': 'Failed to fetch gallery images'}), 500


@gallery_bp.route('/', methods=['POST'])
@login_required
@role_required('superadmin')
def create_gallery_image():
    try:
        data = request.get_json() or {}
        if not data.get('image_url'):
            return jsonify({'error': 'image_url is required'}), 400

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                INSERT INTO gallery_images (image_url, caption, display_order, is_active)
                VALUES (?, ?, ?, ?)
            """, (
                data.get('image_url'),
                data.get('caption', ''),
                data.get('display_order', 0),
                data.get('is_active', True),
            ))
            image_id = cursor.lastrowid
            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Gallery image created', 'image_id': image_id}), 201
    except Exception as e:
        print(f"Create gallery image error: {e}")
        return jsonify({'error': 'Failed to create gallery image'}), 500


@gallery_bp.route('/<int:image_id>', methods=['PUT'])
@login_required
@role_required('superadmin')
def update_gallery_image(image_id):
    try:
        data = request.get_json() or {}
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                UPDATE gallery_images SET
                    image_url = ?,
                    caption = ?,
                    display_order = ?,
                    is_active = ?
                WHERE id = ?
            """, (
                data.get('image_url'),
                data.get('caption', ''),
                data.get('display_order', 0),
                data.get('is_active', True),
                image_id,
            ))
            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Gallery image updated'}), 200
    except Exception as e:
        print(f"Update gallery image error: {e}")
        return jsonify({'error': 'Failed to update gallery image'}), 500


@gallery_bp.route('/<int:image_id>', methods=['DELETE'])
@login_required
@role_required('superadmin')
def delete_gallery_image(image_id):
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute(
                "DELETE FROM gallery_images WHERE id = ?", (image_id,))
            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Gallery image deleted'}), 200
    except Exception as e:
        print(f"Delete gallery image error: {e}")
        return jsonify({'error': 'Failed to delete gallery image'}), 500
