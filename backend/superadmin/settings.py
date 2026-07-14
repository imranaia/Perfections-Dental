import sqlite3
# =========================================
# Perfections Dental Services
# System Settings Module - v1.0
# SuperAdmin Only
# =========================================

from config import Config
from db import get_db
from auth import login_required, role_required
from flask import Blueprint, jsonify, session, request
from datetime import datetime
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Create settings blueprint
settings_bp = Blueprint('settings', __name__,
                        url_prefix='/api/superadmin/settings')



# =========================================
# Get All Settings
# =========================================


@settings_bp.route('/', methods=['GET'])
@login_required
@role_required('superadmin')
def get_settings():
    """Get all system settings from clinic_settings table"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        settings = {}

        with db.cursor() as cursor:
            cursor.execute(
                "SELECT setting_key, setting_value FROM clinic_settings")
            results = cursor.fetchall()

            for row in results:
                settings[row['setting_key']] = row['setting_value']

        db.close()
        return jsonify({'success': True, 'settings': settings}), 200

    except Exception as e:
        print(f"Get settings error: {e}")
        return jsonify({'error': 'Failed to fetch settings'}), 500

# =========================================
# Update Settings
# =========================================


@settings_bp.route('/', methods=['POST'])
@login_required
@role_required('superadmin')
def update_settings():
    """Update system settings"""
    try:
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            for key, value in data.items():
                cursor.execute("""
                    INSERT INTO clinic_settings (setting_key, setting_value)
                    VALUES (?, ?)
                    ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value
                """, (key, value))

            # Log update
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, new_data)
                VALUES (?, 'UPDATE_SETTINGS', 'clinic_settings', ?)
            """, (session['user_id'], json.dumps(data)))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': 'Settings updated successfully'
        }), 200

    except Exception as e:
        print(f"Update settings error: {e}")
        return jsonify({'error': 'Failed to update settings'}), 500
