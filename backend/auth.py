# =========================================
# Perfections Dental Services
# Authentication Module - v1.0
# Session-based Authentication
# =========================================

from config import Config
from db import get_db
import json
import re
import sys
import os
import sqlite3
from functools import wraps
from flask import Blueprint, request, jsonify, session, g
from werkzeug.security import check_password_hash, generate_password_hash

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# Create auth blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


# =========================================
# Login Required Decorator
# =========================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required', 'redirect': '/login.html'}), 401
        return f(*args, **kwargs)
    return decorated_function


# =========================================
# Role Required Decorator
# =========================================
def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'error': 'Authentication required', 'redirect': '/login.html'}), 401

            user_role = session.get('role')
            active_role = session.get('active_role', user_role)

            # Superadmin can access everything regardless of active_role
            if user_role == 'superadmin':
                return f(*args, **kwargs)

            # Regular role check for non-superadmin users
            if active_role not in roles:
                return jsonify({'error': 'Access forbidden'}), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator


# =========================================
# Validate Email Format
# =========================================
def is_valid_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


# =========================================
# Login Endpoint
# =========================================
@auth_bp.route('/login', methods=['POST'])
def login():
    """Authenticate user and create session"""
    try:
        data = request.get_json()

        # Validate input
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        email = data.get('email', '').strip().lower()
        password = data.get('password', '')

        # Basic validation
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400

        if not is_valid_email(email):
            return jsonify({'error': 'Invalid email format'}), 400

        # Get database connection
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        try:
            with db.cursor() as cursor:
                # Get user with role information
                sql = """
                    SELECT 
                        u.id,
                        u.employee_id,
                        u.first_name,
                        u.last_name,
                        u.email,
                        u.password_hash,
                        u.license_number,
                        u.specialization,
                        u.qualifications,
                        u.experience_years,
                        u.status,
                        u.avatar,
                        r.id as role_id,
                        r.name as role
                    FROM users u
                    INNER JOIN roles r ON u.role_id = r.id
                    WHERE u.email = ? AND u.status = 'active'
                """
                cursor.execute(sql, (email,))
                user = cursor.fetchone()

                if not user or not check_password_hash(user['password_hash'], password):
                    return jsonify({'error': 'Invalid email or password'}), 401

                # Remove password hash from session data
                user_data = {
                    'id': user['id'],
                    'employee_id': user['employee_id'],
                    'first_name': user['first_name'],
                    'last_name': user['last_name'],
                    'name': f"{user['first_name']} {user['last_name']}",
                    'email': user['email'],
                    'role': user['role'],
                    'role_id': user['role_id'],
                    'license_number': user['license_number'],
                    'specialization': user['specialization'],
                    'avatar': user['avatar'] or f"{user['first_name'][0]}{user['last_name'][0]}",
                    'can_switch_to_doctor': user['role'] == 'superadmin'
                }

                # Set session data
                session.clear()
                session['user_id'] = user['id']
                session['user'] = user_data
                session['role'] = user['role']
                session['active_role'] = user['role']
                session.permanent = True

                # Log login in audit_logs
                audit_sql = """
                    INSERT INTO audit_logs (user_id, action, table_name, ip_address, user_agent)
                    VALUES (?, 'LOGIN', 'users', ?, ?)
                """
                cursor.execute(audit_sql, (
                    user['id'],
                    request.remote_addr,
                    request.headers.get('User-Agent')
                ))
                db.commit()

                # Determine redirect URL
                redirect_url = f'/pages/{user["role"]}/dashboard.html'
                if user['role'] == 'superadmin' and session.get('active_role') == 'doctor':
                    redirect_url = '/pages/doctor/dashboard.html'

                return jsonify({
                    'success': True,
                    'message': 'Login successful',
                    'user': user_data,
                    'redirect': redirect_url
                }), 200

        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return jsonify({'error': 'Database error occurred'}), 500
        finally:
            db.close()

    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'error': 'An unexpected error occurred'}), 500


# =========================================
# Logout Endpoint
# =========================================
@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Clear user session"""
    try:
        # Log logout if user was logged in
        if 'user_id' in session:
            db = get_db()
            if db:
                try:
                    with db.cursor() as cursor:
                        audit_sql = """
                            INSERT INTO audit_logs (user_id, action, table_name, ip_address, user_agent)
                            VALUES (?, 'LOGOUT', 'users', ?, ?)
                        """
                        cursor.execute(audit_sql, (
                            session['user_id'],
                            request.remote_addr,
                            request.headers.get('User-Agent')
                        ))
                        db.commit()
                except:
                    pass
                finally:
                    db.close()

        session.clear()
        return jsonify({'success': True, 'message': 'Logout successful', 'redirect': '/login.html'}), 200

    except Exception as e:
        print(f"Logout error: {e}")
        session.clear()
        return jsonify({'success': True, 'message': 'Logout successful', 'redirect': '/login.html'}), 200


# =========================================
# Check Session Endpoint
# =========================================
@auth_bp.route('/session', methods=['GET'])
def check_session():
    """Check if user is logged in"""
    if 'user_id' in session:
        return jsonify({
            'authenticated': True,
            'user': session.get('user'),
            'role': session.get('role'),
            'active_role': session.get('active_role')
        }), 200

    return jsonify({'authenticated': False}), 200


# =========================================
# Switch Role (for Superadmin)
# =========================================
@auth_bp.route('/switch-role', methods=['POST'])
@login_required
def switch_role():
    """Allow superadmin to switch between superadmin and doctor roles"""
    try:
        data = request.get_json()
        new_role = data.get('role')

        # Check if user is superadmin
        if session.get('role') != 'superadmin':
            return jsonify({'error': 'Access forbidden'}), 403

        # Only allow switching to doctor or back to superadmin
        if new_role not in ['superadmin', 'doctor']:
            return jsonify({'error': 'Invalid role'}), 400

        # Update active role in session
        session['active_role'] = new_role

        # Log the role switch
        db = get_db()
        if db:
            try:
                with db.cursor() as cursor:
                    audit_sql = """
                        INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                        VALUES (?, 'SWITCH_ROLE', 'users', ?, ?)
                    """
                    cursor.execute(audit_sql, (
                        session['user_id'],
                        session['user_id'],
                        json.dumps({'new_role': new_role})
                    ))
                    db.commit()
            except:
                pass
            finally:
                db.close()

        return jsonify({
            'success': True,
            'message': f'Switched to {new_role} role',
            'active_role': new_role,
            'redirect': f'/pages/{new_role}/dashboard.html' if new_role in ['doctor', 'superadmin'] else None
        }), 200

    except Exception as e:
        print(f"Role switch error: {e}")
        return jsonify({'error': 'An unexpected error occurred'}), 500


# =========================================
# Get Current User Endpoint
# =========================================
@auth_bp.route('/me', methods=['GET'])
@login_required
def get_current_user():
    """Get current logged in user details"""
    return jsonify({
        'user': session.get('user'),
        'role': session.get('role'),
        'active_role': session.get('active_role')
    }), 200
