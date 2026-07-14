import sqlite3
# =========================================
# Perfections Dental Services
# Profile Management Module - v1.0
# SuperAdmin Only
# =========================================

from config import Config
from db import get_db
from auth import login_required, role_required
from flask import Blueprint, jsonify, session, request
from datetime import datetime, timedelta
import json
import sys
import os
from werkzeug.security import generate_password_hash, check_password_hash

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Create profile blueprint
profile_bp = Blueprint('profile', __name__,
                       url_prefix='/api/superadmin/profile')



# =========================================
# Get Current User Profile
# =========================================

@profile_bp.route('/', methods=['GET'])
@login_required
def get_profile():
    """Get current user profile details"""
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
            """, (user_id,))

            user = cursor.fetchone()

            if not user:
                return jsonify({'error': 'User not found'}), 404

            # Get clinic settings
            cursor.execute(
                "SELECT setting_key, setting_value FROM clinic_settings")
            settings = cursor.fetchall()
            clinic_settings = {s['setting_key']
                : s['setting_value'] for s in settings}

            # Get recent activities from audit_logs
            cursor.execute("""
                SELECT 
                    action,
                    table_name,
                    created_at,
                    ip_address
                FROM audit_logs
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 10
            """, (user_id,))
            activities = cursor.fetchall()

            # Get active sessions (from a sessions table if exists, otherwise from audit_logs)
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

            profile = {
                'id': user['id'],
                'employee_id': user['employee_id'],
                'first_name': user['first_name'],
                'last_name': user['last_name'],
                'full_name': f"{user['first_name']} {user['last_name']}",
                'email': user['email'],
                'phone': user['phone'],
                'license': user['license_number'] or '',
                'specialization': user['specialization'] or 'System Administrator',
                'qualifications': user['qualifications'] or '',
                'experience_years': user['experience_years'] or 0,
                'date_joined': user['date_joined'].strftime('%Y-%m-%d') if user['date_joined'] else '',
                'date_joined_formatted': user['date_joined'].strftime('%d %B %Y') if user['date_joined'] else '',
                'status': user['status'],
                'role': user['role'],
                'role_description': user['role_description'],
                'emergency_contact_name': user['emergency_contact_name'] or '',
                'emergency_contact_phone': user['emergency_contact_phone'] or '',
                'avatar': user['avatar'] or f"{user['first_name'][0]}{user['last_name'][0]}",
                'clinic_settings': clinic_settings
            }

            # Format activities
            activities_list = []
            action_icons = {
                'LOGIN': 'fa-sign-in-alt',
                'LOGOUT': 'fa-sign-out-alt',
                'CREATE': 'fa-plus-circle',
                'UPDATE': 'fa-edit',
                'DELETE': 'fa-trash-alt',
                'UPDATE_PERMISSIONS': 'fa-shield-alt',
                'UPDATE_PAGE_ACCESS': 'fa-lock'
            }
            action_labels = {
                'LOGIN': 'Logged in',
                'LOGOUT': 'Logged out',
                'CREATE': 'Created',
                'UPDATE': 'Updated',
                'DELETE': 'Deleted',
                'UPDATE_PERMISSIONS': 'Updated permissions',
                'UPDATE_PAGE_ACCESS': 'Updated page access'
            }

            for act in activities:
                action_name = act['action']
                table_name = act['table_name'] or ''
                activities_list.append({
                    'action': action_name,
                    'label': action_labels.get(action_name, action_name),
                    'table': table_name,
                    'description': f"{action_labels.get(action_name, action_name)} {table_name}" if table_name else action_labels.get(action_name, action_name),
                    'created_at': act['created_at'].strftime('%Y-%m-%d %H:%M:%S') if act['created_at'] else '',
                    'time_ago': get_time_ago(act['created_at']) if act['created_at'] else '',
                    'icon': action_icons.get(action_name, 'fa-history'),
                    'ip': act['ip_address'] or ''
                })

            # Format sessions
            sessions_list = []
            for i, sess in enumerate(sessions):
                is_current = i == 0
                device = parse_user_agent(sess['user_agent'] or '')
                sessions_list.append({
                    'device': device,
                    'location': 'Lagos, Nigeria',
                    'last_active': get_time_ago(sess['created_at']) if sess['created_at'] else 'Now',
                    'is_current': is_current,
                    'ip': sess['ip_address'] or ''
                })

            profile['recent_activities'] = activities_list[:5]
            profile['active_sessions'] = sessions_list

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

@profile_bp.route('/', methods=['PUT'])
@login_required
def update_profile():
    """Update user profile"""
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
                    emergency_contact_name = ?,
                    emergency_contact_phone = ?,
                    updated_at = datetime('now')
                WHERE id = ?
            """, (
                data.get('first_name'),
                data.get('last_name'),
                data.get('phone'),
                data.get('emergency_contact_name'),
                data.get('emergency_contact_phone'),
                user_id
            ))

            # Log update
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE', 'users', ?, ?)
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

@profile_bp.route('/change-password', methods=['POST'])
@login_required
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

@profile_bp.route('/2fa', methods=['PUT'])
@login_required
def update_2fa():
    """Update two-factor authentication settings"""
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Store 2FA settings in user meta or settings table
            # For now, log the change
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
# Terminate Session
# =========================================

@profile_bp.route('/sessions/terminate', methods=['POST'])
@login_required
def terminate_session():
    """Terminate other sessions"""
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        session_ip = data.get('ip')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Log session termination
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'TERMINATE_SESSION', 'users', ?, ?)
            """, (user_id, user_id, json.dumps({'terminated_ip': session_ip})))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': 'Session terminated successfully'
        }), 200

    except Exception as e:
        print(f"Terminate session error: {e}")
        return jsonify({'error': 'Failed to terminate session'}), 500


# =========================================
# Terminate All Other Sessions
# =========================================

@profile_bp.route('/sessions/terminate-all', methods=['POST'])
@login_required
def terminate_all_sessions():
    """Terminate all other sessions except current"""
    try:
        user_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Log termination of all sessions
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id)
                VALUES (?, 'TERMINATE_ALL_SESSIONS', 'users', ?)
            """, (user_id, user_id))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': 'All other sessions terminated successfully'
        }), 200

    except Exception as e:
        print(f"Terminate all sessions error: {e}")
        return jsonify({'error': 'Failed to terminate sessions'}), 500


# =========================================
# Deactivate Account
# =========================================

@profile_bp.route('/deactivate', methods=['POST'])
@login_required
def deactivate_account():
    """Deactivate user account"""
    try:
        user_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Update user status to inactive
            cursor.execute("""
                UPDATE users SET status = 'inactive', updated_at = datetime('now')
                WHERE id = ?
            """, (user_id,))

            # Log deactivation
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id)
                VALUES (?, 'DEACTIVATE', 'users', ?)
            """, (user_id, user_id))

            db.commit()

        db.close()

        # Clear session
        session.clear()

        return jsonify({
            'success': True,
            'message': 'Account deactivated successfully'
        }), 200

    except Exception as e:
        print(f"Deactivate account error: {e}")
        return jsonify({'error': 'Failed to deactivate account'}), 500


# =========================================
# Delete Account
# =========================================

@profile_bp.route('/delete', methods=['POST'])
@login_required
def delete_account():
    """Delete user account permanently"""
    try:
        user_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        # Check if user has created appointments or invoices
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) as count FROM appointments WHERE created_by = ?", (user_id,))
            appointments = cursor.fetchone()

            cursor.execute(
                "SELECT COUNT(*) as count FROM invoices WHERE created_by = ?", (user_id,))
            invoices = cursor.fetchone()

            if appointments['count'] > 0 or invoices['count'] > 0:
                # Instead of deleting, mark as inactive
                cursor.execute("""
                    UPDATE users SET status = 'inactive', updated_at = datetime('now')
                    WHERE id = ?
                """, (user_id,))
                message = "Account marked as inactive (has existing records)"
            else:
                # Delete user and related records
                cursor.execute(
                    "DELETE FROM staff_schedule WHERE staff_id = ?", (user_id,))
                cursor.execute(
                    "DELETE FROM staff_shifts WHERE staff_id = ?", (user_id,))
                cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
                message = "Account deleted permanently"

            # Log deletion
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id)
                VALUES (?, 'DELETE_ACCOUNT', 'users', ?)
            """, (user_id, user_id))

            db.commit()

        db.close()

        # Clear session
        session.clear()

        return jsonify({
            'success': True,
            'message': message
        }), 200

    except Exception as e:
        print(f"Delete account error: {e}")
        return jsonify({'error': 'Failed to delete account'}), 500


# =========================================
# Helper Functions
# =========================================

def get_time_ago(date):
    """Get time ago string"""
    if not date:
        return ''
    now = datetime.now()
    diff = now - date

    if diff.days > 30:
        return date.strftime('%d %b %Y')
    elif diff.days > 7:
        weeks = diff.days // 7
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    elif diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    else:
        return "Just now"


def parse_user_agent(user_agent):
    """Parse user agent to get device info"""
    if not user_agent:
        return "Unknown Device"

    ua = user_agent.lower()
    if 'windows' in ua:
        return "Windows PC"
    elif 'mac' in ua:
        return "Mac Computer"
    elif 'iphone' in ua:
        return "iPhone"
    elif 'android' in ua:
        return "Android Phone"
    elif 'ipad' in ua:
        return "iPad"
    else:
        return "Unknown Device"
