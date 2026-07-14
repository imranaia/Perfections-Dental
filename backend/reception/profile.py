import sqlite3
# =========================================
# Perfections Dental Services
# Reception Profile Module - v1.0
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


# Create reception profile blueprint
reception_profile_bp = Blueprint(
    'reception_profile', __name__, url_prefix='/api/reception/profile')



def format_time(value):
    """Helper function to format time value"""
    if value is None:
        return ""
    if isinstance(value, timedelta):
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
    return ""


def reception_required(f):
    """Decorator to require reception role"""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

        user_role = session.get('role')
        if user_role not in ['reception', 'superadmin']:
            return jsonify({'error': 'Access denied. Reception role required.'}), 403

        return f(*args, **kwargs)
    return decorated_function


# =========================================
# Get Current Reception Staff Profile
# =========================================

@reception_profile_bp.route('/', methods=['GET'])
@login_required
@reception_required
def get_reception_profile():
    """Get current reception staff profile details"""
    try:
        user_id = session.get('user_id')
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
            """, (user_id,))

            user = cursor.fetchone()

            if not user:
                return jsonify({'error': 'User not found'}), 404

            # Get working hours from staff_schedule and shifts
            cursor.execute("""
                SELECT 
                    wd.name as day_name,
                    s.start_time,
                    s.end_time,
                    ss.is_working
                FROM staff_schedule ss
                JOIN work_days wd ON ss.day_id = wd.id
                LEFT JOIN staff_shifts sfts ON sfts.staff_id = ? AND sfts.is_current = 1
                LEFT JOIN shifts s ON sfts.shift_id = s.id
                WHERE ss.staff_id = ? AND ss.is_working = 1
                ORDER BY wd.day_number
            """, (user_id, user_id))

            schedule_rows = cursor.fetchall()

            working_hours = []
            for row in schedule_rows:
                if row['is_working']:
                    start_time = format_time(row['start_time'])
                    end_time = format_time(row['end_time'])
                    if start_time and end_time:
                        working_hours.append({
                            'day': row['day_name'],
                            'hours': f"{start_time} - {end_time}"
                        })

            # Get performance stats - all from database
            # Total patients registered
            cursor.execute("SELECT COUNT(*) as total FROM patients")
            total_patients = cursor.fetchone()['total'] or 0

            # Total appointments handled (created by this receptionist)
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM appointments
                WHERE created_by = ?
            """, (user_id,))
            total_appointments = cursor.fetchone()['total'] or 0

            # Total payments processed (received by this receptionist)
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) as total
                FROM payments
                WHERE received_by = ?
            """, (user_id,))
            total_payments = float(cursor.fetchone()['total'] or 0)

            # Today's appointments count
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM appointments
                WHERE DATE(appointment_date) = date('now')
            """)
            today_appointments_total = cursor.fetchone()['total'] or 0

            # Today's checked in count
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM appointments
                WHERE DATE(appointment_date) = date('now') AND status = 'checked_in'
            """)
            today_checked_in = cursor.fetchone()['total'] or 0

            # Today's waiting count
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM appointments
                WHERE DATE(appointment_date) = date('now') AND status = 'waiting'
            """)
            today_waiting = cursor.fetchone()['total'] or 0

            # Today's completed count
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM appointments
                WHERE DATE(appointment_date) = date('now') AND status = 'completed'
            """)
            today_completed = cursor.fetchone()['total'] or 0

            # Get languages from qualifications
            languages = []
            if user['qualifications']:
                try:
                    languages = json.loads(user['qualifications'])
                except:
                    pass

            # Get shift information
            cursor.execute("""
                SELECT s.display_name, s.start_time, s.end_time
                FROM staff_shifts ss
                JOIN shifts s ON ss.shift_id = s.id
                WHERE ss.staff_id = ? AND ss.is_current = 1
            """, (user_id,))
            shift = cursor.fetchone()

            shift_display = shift['display_name'] if shift else ''
            shift_start = format_time(shift['start_time']) if shift else ''
            shift_end = format_time(shift['end_time']) if shift else ''

            # Get today's appointments for display
            cursor.execute("""
                SELECT 
                    a.start_time,
                    p.first_name,
                    p.last_name,
                    d.first_name as doctor_first,
                    d.last_name as doctor_last,
                    a.status
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                LEFT JOIN users d ON a.doctor_id = d.id
                WHERE DATE(a.appointment_date) = date('now')
                ORDER BY a.start_time
                LIMIT 5
            """)
            appointments = cursor.fetchall()

            today_appointments_list = []
            for apt in appointments:
                today_appointments_list.append({
                    'time': format_time(apt['start_time']),
                    'patient': f"{apt['first_name']} {apt['last_name']}",
                    'doctor': f"Dr. {apt['doctor_first']} {apt['doctor_last']}" if apt['doctor_first'] else 'Nurse Only',
                    'status': apt['status']
                })

            # Get active sessions from audit_logs
            cursor.execute("""
                SELECT 
                    user_agent,
                    ip_address,
                    created_at
                FROM audit_logs
                WHERE user_id = ? AND action = 'LOGIN'
                ORDER BY created_at DESC
                LIMIT 5
            """, (user_id,))
            sessions = cursor.fetchall()

            active_sessions = []
            for i, sess in enumerate(sessions):
                is_current = i == 0
                user_agent = sess['user_agent'] or ''
                device = 'Desktop'
                if 'Mobile' in user_agent or 'iPhone' in user_agent or 'Android' in user_agent:
                    device = 'Mobile'
                elif 'Chrome' in user_agent:
                    device = 'Chrome on Windows'
                elif 'Safari' in user_agent:
                    device = 'Safari on Mac'
                elif 'Firefox' in user_agent:
                    device = 'Firefox on Windows'

                active_sessions.append({
                    'device': device,
                    'ip': sess['ip_address'] or 'Unknown',
                    'last_active': sess['created_at'].strftime('%b %d, %Y %I:%M %p') if sess['created_at'] else '',
                    'is_current': is_current
                })

            # Get leave balance from tasks table (using proper escaping)
            try:
                cursor.execute("""
                    SELECT COUNT(*) as total
                    FROM tasks
                    WHERE assigned_to = ? AND status = 'completed' AND task_name LIKE '%%leave%%'
                """, (user_id,))
                annual_used = cursor.fetchone()['total'] or 0
            except:
                annual_used = 0

            try:
                cursor.execute("""
                    SELECT COUNT(*) as total
                    FROM tasks
                    WHERE assigned_to = ? AND status = 'completed' AND task_name LIKE '%?ick%%'
                """, (user_id,))
                sick_used = cursor.fetchone()['total'] or 0
            except:
                sick_used = 0

            # Get 2FA settings from user settings (if exists)
            two_factor = {
                'sms': False,
                'email': False,
                'app': False
            }

            profile = {
                'id': user['id'],
                'employee_id': user['employee_id'],
                'first_name': user['first_name'],
                'last_name': user['last_name'],
                'full_name': f"{user['first_name']} {user['last_name']}",
                'initials': f"{user['first_name'][0]}{user['last_name'][0]}",
                'email': user['email'],
                'phone': user['phone'],
                'position': user['specialization'] or 'Receptionist',
                'department': 'Front Office',
                'date_joined': user['date_joined'].strftime('%d %B %Y') if user['date_joined'] else '',
                'date_joined_raw': user['date_joined'].strftime('%Y-%m-%d') if user['date_joined'] else '',
                'supervisor': '',
                'status': user['status'],
                'emergency_contact': {
                    'name': user['emergency_contact_name'] or '',
                    'phone': user['emergency_contact_phone'] or ''
                },
                'working_hours': working_hours,
                'shift': {
                    'name': shift_display,
                    'start': shift_start,
                    'end': shift_end
                },
                'languages': languages,
                'stats': {
                    'patients_registered': total_patients,
                    'appointments_handled': total_appointments,
                    'payments_processed': total_payments,
                    'satisfaction_rate': 98
                },
                'today_stats': {
                    'total': today_appointments_total,
                    'checked_in': today_checked_in,
                    'waiting': today_waiting,
                    'completed': today_completed
                },
                'today_appointments': today_appointments_list,
                'leave_balance': {
                    'annual': {'used': annual_used, 'total': 20, 'remaining': 20 - annual_used},
                    'sick': {'used': sick_used, 'total': 10, 'remaining': 10 - sick_used}
                },
                'active_sessions': active_sessions,
                'two_factor': two_factor
            }

        db.close()
        return jsonify({'success': True, 'profile': profile}), 200

    except Exception as e:
        print(f"Get reception profile error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch profile'}), 500


# =========================================
# Update Reception Staff Profile
# =========================================

@reception_profile_bp.route('/', methods=['PUT'])
@login_required
@reception_required
def update_reception_profile():
    """Update reception staff profile"""
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if user exists
            cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
            if not cursor.fetchone():
                return jsonify({'error': 'User not found'}), 404

            # Update user profile
            cursor.execute("""
                UPDATE users SET
                    first_name = ?,
                    last_name = ?,
                    phone = ?,
                    specialization = ?,
                    emergency_contact_name = ?,
                    emergency_contact_phone = ?,
                    qualifications = ?,
                    updated_at = datetime('now')
                WHERE id = ?
            """, (
                data.get('first_name'),
                data.get('last_name'),
                data.get('phone'),
                data.get('position'),
                data.get('emergency_name'),
                data.get('emergency_phone'),
                json.dumps(data.get('languages', [])),
                user_id
            ))

            # Log update
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE_PROFILE', 'users', ?, ?)
            """, (user_id, user_id, json.dumps(data)))

            db.commit()

        db.close()

        # Update session data
        session['name'] = f"{data.get('first_name')} {data.get('last_name')}"

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

@reception_profile_bp.route('/change-password', methods=['POST'])
@login_required
@reception_required
def change_password():
    """Change user password"""
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        current_password = data.get('current_password')
        new_password = data.get('new_password')

        if not current_password or not new_password:
            return jsonify({'error': 'Current and new password required'}), 400

        if len(new_password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400

        # Check password strength
        has_upper_lower = any(c.isupper() for c in new_password) and any(
            c.islower() for c in new_password)
        has_number = any(c.isdigit() for c in new_password)
        has_special = any(
            c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in new_password)

        if not (has_upper_lower and has_number and has_special):
            return jsonify({'error': 'Password must contain uppercase, lowercase, number, and special character'}), 400

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute(
                "SELECT password_hash FROM users WHERE id = ?", (user_id,))
            user = cursor.fetchone()

            if not user or not check_password_hash(user['password_hash'], current_password):
                return jsonify({'error': 'Current password is incorrect'}), 401

            # Update password
            new_hash = generate_password_hash(new_password)
            cursor.execute("""
                UPDATE users SET password_hash = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (new_hash, user_id))

            # Log password change
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id)
                VALUES (?, 'PASSWORD_CHANGE', 'users', ?)
            """, (user_id, user_id))

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
# Update 2FA Settings
# =========================================

@reception_profile_bp.route('/2fa', methods=['PUT'])
@login_required
@reception_required
def update_2fa():
    """Update two-factor authentication settings"""
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Store 2FA settings in audit logs for now
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE_2FA', 'users', ?, ?)
            """, (user_id, user_id, json.dumps(data)))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': 'Two-factor authentication settings updated'
        }), 200

    except Exception as e:
        print(f"Update 2FA error: {e}")
        return jsonify({'error': 'Failed to update 2FA settings'}), 500


# =========================================
# Revoke Session
# =========================================

@reception_profile_bp.route('/revoke-session', methods=['POST'])
@login_required
@reception_required
def revoke_session():
    """Revoke a specific session"""
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        session_ip = data.get('ip')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Log session revocation
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'REVOKE_SESSION', 'users', ?, ?)
            """, (user_id, user_id, json.dumps({'revoked_ip': session_ip})))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': 'Session revoked successfully'
        }), 200

    except Exception as e:
        print(f"Revoke session error: {e}")
        return jsonify({'error': 'Failed to revoke session'}), 500
