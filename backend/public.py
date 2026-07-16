# =========================================
# Perfections Dental Services
# Public Content Module - v1.0
# Unauthenticated endpoints that feed the public landing page
# (frontend/index.html) with database-driven content instead of
# hardcoded HTML. Read-only — all writes still go through the existing
# superadmin-only /api/superadmin/settings and /api/superadmin/team APIs.
# =========================================

from db import get_db
from flask import Blueprint, jsonify
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

public_bp = Blueprint('public', __name__, url_prefix='/api/public')


@public_bp.route('/site-content', methods=['GET'])
def get_site_content():
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        settings = {}
        team = []
        gallery = []
        testimonials = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT setting_key, setting_value FROM clinic_settings
                WHERE setting_key LIKE 'site.%'
            """)
            for row in cursor.fetchall():
                settings[row['setting_key']] = row['setting_value']

            cursor.execute("""
                SELECT id, name, role_title, bio, photo_url, tags
                FROM team_members
                WHERE is_active = 1
                ORDER BY display_order, id
            """)
            team = [dict(row) for row in cursor.fetchall()]

            cursor.execute("""
                SELECT id, image_url, caption
                FROM gallery_images
                WHERE is_active = 1
                ORDER BY display_order, id
            """)
            gallery = [dict(row) for row in cursor.fetchall()]

            cursor.execute("""
                SELECT id, author_name, author_role, quote, rating
                FROM testimonials
                WHERE is_active = 1
                ORDER BY display_order, id
            """)
            testimonials = [dict(row) for row in cursor.fetchall()]

        db.close()
        return jsonify({
            'success': True,
            'settings': settings,
            'team': team,
            'gallery': gallery,
            'testimonials': testimonials,
        }), 200
    except Exception as e:
        print(f"Get site content error: {e}")
        return jsonify({'error': 'Failed to fetch site content'}), 500
