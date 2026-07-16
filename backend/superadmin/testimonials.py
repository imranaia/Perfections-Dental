import sqlite3
# =========================================
# Perfections Dental Services
# Testimonials Moderation Module - v1.0
# SuperAdmin Only — edit/remove patient-submitted reviews after the fact.
# Patients create these themselves (backend/patient/testimonials.py,
# publishes immediately); there's no superadmin "create" here on purpose.
# =========================================

from config import Config
from db import get_db
from auth import login_required, role_required
from flask import Blueprint, jsonify, session, request
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

testimonials_bp = Blueprint(
    'testimonials', __name__, url_prefix='/api/superadmin/testimonials')


def _row_to_testimonial(row):
    return {
        'id': row['id'],
        'patient_id': row['patient_id'],
        'author_name': row['author_name'],
        'author_role': row['author_role'],
        'quote': row['quote'],
        'rating': row['rating'],
        'display_order': row['display_order'],
        'is_active': row['is_active'],
    }


@testimonials_bp.route('/', methods=['GET'])
@login_required
@role_required('superadmin')
def get_testimonials():
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM testimonials ORDER BY display_order, id")
            rows = [_row_to_testimonial(r) for r in cursor.fetchall()]

        db.close()
        return jsonify({'success': True, 'testimonials': rows}), 200
    except Exception as e:
        print(f"Get testimonials error: {e}")
        return jsonify({'error': 'Failed to fetch testimonials'}), 500


@testimonials_bp.route('/<int:testimonial_id>', methods=['PUT'])
@login_required
@role_required('superadmin')
def update_testimonial(testimonial_id):
    try:
        data = request.get_json() or {}
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                UPDATE testimonials SET
                    author_name = ?,
                    author_role = ?,
                    quote = ?,
                    rating = ?,
                    display_order = ?,
                    is_active = ?
                WHERE id = ?
            """, (
                data.get('author_name'),
                data.get('author_role', ''),
                data.get('quote'),
                data.get('rating', 5),
                data.get('display_order', 0),
                data.get('is_active', True),
                testimonial_id,
            ))
            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Testimonial updated'}), 200
    except Exception as e:
        print(f"Update testimonial error: {e}")
        return jsonify({'error': 'Failed to update testimonial'}), 500


@testimonials_bp.route('/<int:testimonial_id>', methods=['DELETE'])
@login_required
@role_required('superadmin')
def delete_testimonial(testimonial_id):
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute(
                "DELETE FROM testimonials WHERE id = ?", (testimonial_id,))
            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Testimonial deleted'}), 200
    except Exception as e:
        print(f"Delete testimonial error: {e}")
        return jsonify({'error': 'Failed to delete testimonial'}), 500
