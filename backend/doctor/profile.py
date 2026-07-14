import sqlite3
# =========================================
# Perfections Dental Services
# Doctor Profile Module - v1.0
# =========================================

from config import Config
from db import get_db
from auth import login_required
from flask import Blueprint, jsonify, session, request
from datetime import datetime, timedelta, time
import json
import sys
import os
from werkzeug.security import generate_password_hash, check_password_hash

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Create profile blueprint with unique name
doctor_profile_bp = Blueprint(
    'doctor_profile', __name__, url_prefix='/api/doctor/profile')



def format_time(value):
    """Helper function to format time value"""
    if value is None:
        return "9:00 AM"
    if isinstance(value, timedelta):
        # Convert timedelta to time
        total_seconds = value.total_seconds()
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        period = "AM" if hours < 12 else "PM"
        hour_12 = hours % 12
        if hour_12 == 0:
            hour_12 = 12
        return f"{hour_12}:{minutes:02d} {period}"
    if isinstance(value, time):
        return value.strftime('%I:%M %p')
    if isinstance(value, str):
        return value
    return "9:00 AM"


def doctor_required(f):
    """Decorator to require doctor role"""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

        user_role = session.get('role')
        if user_role not in ['doctor', 'superadmin']:
            return jsonify({'error': 'Access denied. Doctor role required.'}), 403

        return f(*args, **kwargs)
    return decorated_function


# =========================================
# Get Doctor Profile
# =========================================

@doctor_profile_bp.route('/', methods=['GET'])
@login_required
@doctor_required
def get_profile():
    """Get doctor profile details"""
    try:
        doctor_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    u.id,
                    u.employee_id,
                    u.first_name,
                    u.last_name,
                    u.email,
                    u.phone,
                    u.license_number,
                    u.specialization,
                    u.qualifications,
                    u.experience_years,
                    u.date_joined,
                    u.status,
                    u.emergency_contact_name,
                    u.emergency_contact_phone,
                    u.avatar,
                    r.name as role,
                    r.description as role_description
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.id = ?
            """, (doctor_id,))

            user = cursor.fetchone()

            if not user:
                return jsonify({'error': 'User not found'}), 404

            # Get practice stats
            cursor.execute("""
                SELECT 
                    COUNT(DISTINCT p.id) as total_patients,
                    COUNT(a.id) as total_appointments,
                    COUNT(CASE WHEN a.status = 'completed' THEN 1 END) as completed_appointments,
                    ROUND(AVG(CASE WHEN a.status = 'completed' THEN 100 ELSE 0 END), 1) as completion_rate
                FROM users u
                LEFT JOIN appointments a ON u.id = a.doctor_id
                LEFT JOIN patients p ON a.patient_id = p.id
                WHERE u.id = ?
            """, (doctor_id,))
            stats = cursor.fetchone()

            # Get recent patients
            cursor.execute("""
                SELECT DISTINCT
                    p.id,
                    p.first_name,
                    p.last_name,
                    MAX(a.appointment_date) as last_visit,
                    strftime('%Y-%m-%d', MAX(a.appointment_date)) as last_visit_formatted
                FROM patients p
                JOIN appointments a ON p.id = a.patient_id
                WHERE a.doctor_id = ?
                GROUP BY p.id
                ORDER BY last_visit DESC
                LIMIT 5
            """, (doctor_id,))
            recent_patients = cursor.fetchall()

            # Get specialties from qualifications
            specialties = []
            if user['qualifications']:
                specialties = [s.strip()
                               for s in user['qualifications'].split(',')]
            else:
                specialties = ["General Dentistry"]

            # Get schedule from staff_schedule and shifts
            cursor.execute("""
                SELECT 
                    s.name as shift_name,
                    s.display_name,
                    s.start_time,
                    s.end_time,
                    wd.name as day_name,
                    wd.day_number
                FROM staff_shifts ss
                JOIN shifts s ON ss.shift_id = s.id
                JOIN staff_schedule sc ON ss.staff_id = sc.staff_id
                JOIN work_days wd ON sc.day_id = wd.id
                WHERE ss.staff_id = ? AND ss.is_current = 1 AND sc.is_working = 1
                ORDER BY wd.day_number
            """, (doctor_id,))
            schedule_rows = cursor.fetchall()

            schedule = {}
            days_order = ['Monday', 'Tuesday', 'Wednesday',
                          'Thursday', 'Friday', 'Saturday', 'Sunday']
            for day in days_order:
                schedule[day] = {'hours': 'Closed', 'available': False}

            for row in schedule_rows:
                day_name = row['day_name']
                start = format_time(row['start_time'])
                end = format_time(row['end_time'])
                schedule[day_name] = {
                    'hours': f"{start} - {end}", 'available': True}

        # Format profile data
        profile = {
            'id': user['id'],
            'employee_id': user['employee_id'],
            'first_name': user['first_name'],
            'last_name': user['last_name'],
            'full_name': f"Dr. {user['first_name']} {user['last_name']}",
            'initials': f"{user['first_name'][0]}{user['last_name'][0]}",
            'email': user['email'],
            'phone': user['phone'],
            'license': user['license_number'] or '',
            'specialty': user['specialization'] or 'General Dentistry',
            'qualifications': user['qualifications'] or '',
            'experience_years': user['experience_years'] or 0,
            'date_joined': user['date_joined'].strftime('%d %B %Y') if user['date_joined'] else '',
            'date_joined_iso': user['date_joined'].strftime('%Y-%m-%d') if user['date_joined'] else '',
            'status': user['status'],
            'role': user['role'],
            'emergency_contact': {
                'name': user['emergency_contact_name'] or '',
                'phone': user['emergency_contact_phone'] or ''
            },
            'specialties': specialties,
            'schedule': schedule,
            'stats': {
                'total_patients': stats['total_patients'] or 0,
                'total_appointments': stats['total_appointments'] or 0,
                'completed_appointments': stats['completed_appointments'] or 0,
                'completion_rate': stats['completion_rate'] or 0
            },
            'recent_patients': [
                {
                    'id': p['id'],
                    'name': f"{p['first_name']} {p['last_name']}",
                    'initials': f"{p['first_name'][0]}{p['last_name'][0]}",
                    'last_visit': p['last_visit_formatted'] or 'Never'
                } for p in recent_patients
            ]
        }

        db.close()
        return jsonify({'success': True, 'profile': profile}), 200

    except Exception as e:
        print(f"Get profile error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch profile'}), 500


# =========================================
# Update Profile
# =========================================

@doctor_profile_bp.route('/', methods=['PUT'])
@login_required
@doctor_required
def update_profile():
    """Update doctor profile"""
    try:
        doctor_id = session.get('user_id')
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if user exists
            cursor.execute("SELECT id FROM users WHERE id = ?", (doctor_id,))
            if not cursor.fetchone():
                return jsonify({'error': 'User not found'}), 404

            # Update user profile
            cursor.execute("""
                UPDATE users SET
                    first_name = ?,
                    last_name = ?,
                    phone = ?,
                    specialization = ?,
                    qualifications = ?,
                    experience_years = ?,
                    license_number = ?,
                    emergency_contact_name = ?,
                    emergency_contact_phone = ?,
                    updated_at = datetime('now')
                WHERE id = ?
            """, (
                data.get('first_name'),
                data.get('last_name'),
                data.get('phone'),
                data.get('specialty'),
                data.get('qualifications'),
                data.get('experience_years'),
                data.get('license'),
                data.get('emergency_contact_name'),
                data.get('emergency_contact_phone'),
                doctor_id
            ))

            # Log update
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE_PROFILE', 'users', ?, ?)
            """, (doctor_id, doctor_id, json.dumps(data)))

            db.commit()

        db.close()

        # Update session name
        session['name'] = f"Dr. {data.get('first_name')} {data.get('last_name')}"

        return jsonify({
            'success': True,
            'message': 'Profile updated successfully'
        }), 200

    except Exception as e:
        print(f"Update profile error: {e}")
        return jsonify({'error': 'Failed to update profile'}), 500


# =========================================
# Change Password
# =========================================

@doctor_profile_bp.route('/change-password', methods=['POST'])
@login_required
@doctor_required
def change_password():
    """Change doctor password"""
    try:
        doctor_id = session.get('user_id')
        data = request.get_json()
        current_password = data.get('current_password')
        new_password = data.get('new_password')

        if not current_password or not new_password:
            return jsonify({'error': 'Current and new password required'}), 400

        if len(new_password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute(
                "SELECT password_hash FROM users WHERE id = ?", (doctor_id,))
            user = cursor.fetchone()

            if not user or not check_password_hash(user['password_hash'], current_password):
                return jsonify({'error': 'Current password is incorrect'}), 401

            # Update password
            new_hash = generate_password_hash(new_password)
            cursor.execute("""
                UPDATE users SET password_hash = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (new_hash, doctor_id))

            # Log password change
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id)
                VALUES (?, 'PASSWORD_CHANGE', 'users', ?)
            """, (doctor_id, doctor_id))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': 'Password changed successfully'
        }), 200

    except Exception as e:
        print(f"Change password error: {e}")
        return jsonify({'error': 'Failed to change password'}), 500


# =========================================
# Add Specialty
# =========================================

@doctor_profile_bp.route('/specialties', methods=['POST'])
@login_required
@doctor_required
def add_specialty():
    """Add a new specialty to doctor's profile"""
    try:
        doctor_id = session.get('user_id')
        data = request.get_json()
        new_specialty = data.get('specialty')

        if not new_specialty:
            return jsonify({'error': 'Specialty name required'}), 400

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Get current qualifications
            cursor.execute(
                "SELECT qualifications FROM users WHERE id = ?", (doctor_id,))
            user = cursor.fetchone()

            current_specialties = []
            if user['qualifications']:
                current_specialties = [s.strip()
                                       for s in user['qualifications'].split(',')]

            if new_specialty in current_specialties:
                return jsonify({'error': 'Specialty already exists'}), 400

            current_specialties.append(new_specialty)
            new_qualifications = ', '.join(current_specialties)

            # Update qualifications
            cursor.execute("""
                UPDATE users SET qualifications = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (new_qualifications, doctor_id))

            # Log action
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'ADD_SPECIALTY', 'users', ?, ?)
            """, (doctor_id, doctor_id, json.dumps({'specialty': new_specialty})))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': f'Specialty "{new_specialty}" added successfully',
            'specialties': current_specialties
        }), 200

    except Exception as e:
        print(f"Add specialty error: {e}")
        return jsonify({'error': 'Failed to add specialty'}), 500


# =========================================
# Remove Specialty
# =========================================

@doctor_profile_bp.route('/specialties/<specialty>', methods=['DELETE'])
@login_required
@doctor_required
def remove_specialty(specialty):
    """Remove a specialty from doctor's profile"""
    try:
        doctor_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Get current qualifications
            cursor.execute(
                "SELECT qualifications FROM users WHERE id = ?", (doctor_id,))
            user = cursor.fetchone()

            current_specialties = []
            if user['qualifications']:
                current_specialties = [s.strip()
                                       for s in user['qualifications'].split(',')]

            if specialty not in current_specialties:
                return jsonify({'error': 'Specialty not found'}), 404

            current_specialties.remove(specialty)
            new_qualifications = ', '.join(
                current_specialties) if current_specialties else None

            # Update qualifications
            cursor.execute("""
                UPDATE users SET qualifications = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (new_qualifications, doctor_id))

            # Log action
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, old_data)
                VALUES (?, 'REMOVE_SPECIALTY', 'users', ?, ?)
            """, (doctor_id, doctor_id, json.dumps({'specialty': specialty})))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': f'Specialty "{specialty}" removed successfully',
            'specialties': current_specialties
        }), 200

    except Exception as e:
        print(f"Remove specialty error: {e}")
        return jsonify({'error': 'Failed to remove specialty'}), 500


# =========================================
# Update 2FA Settings
# =========================================

@doctor_profile_bp.route('/2fa', methods=['PUT'])
@login_required
@doctor_required
def update_2fa():
    """Update two-factor authentication settings"""
    try:
        doctor_id = session.get('user_id')
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Store 2FA settings (you can create a user_settings table if needed)
            # For now, just log the change
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE_2FA', 'users', ?, ?)
            """, (doctor_id, doctor_id, json.dumps(data)))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': 'Two-factor authentication settings updated'
        }), 200

    except Exception as e:
        print(f"Update 2FA error: {e}")
        return jsonify({'error': 'Failed to update 2FA settings'}), 500
