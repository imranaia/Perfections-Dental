import sqlite3
# =========================================
# Perfections Dental Services
# Access Control Module - v1.0
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


# Create access control blueprint
access_control_bp = Blueprint(
    'access_control', __name__, url_prefix='/api/superadmin/access-control')



# =========================================
# Get All Roles with Permissions
# =========================================


@access_control_bp.route('/roles', methods=['GET'])
@login_required
@role_required('superadmin')
def get_roles():
    """Get all roles with their permissions"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        roles = []

        with db.cursor() as cursor:
            # Get all roles
            cursor.execute("""
                SELECT id, name, description 
                FROM roles 
                ORDER BY id
            """)
            role_rows = cursor.fetchall()

            # Get permissions table (if exists) - create permissions table if needed
            # For now, we'll use default permissions structure
            for role in role_rows:
                role_data = {
                    'id': role['id'],
                    'name': role['name'],
                    'description': role['description'],
                    'user_count': 0,
                    'permissions': {
                        'system': [],
                        'clinical': [],
                        'schedule': [],
                        'front_desk': []
                    }
                }

                # Get user count for this role
                cursor.execute("""
                    SELECT COUNT(*) as count 
                    FROM users 
                    WHERE role_id = ? AND status = 'active'
                """, (role['id'],))
                role_data['user_count'] = cursor.fetchone()['count']

                # Set default permissions based on role
                if role['name'] == 'superadmin':
                    role_data['permissions'] = {
                        'system': [
                            {'name': 'Full System Control', 'has': True},
                            {'name': 'User Management', 'has': True},
                            {'name': 'Financial Oversight', 'has': True},
                            {'name': 'View Audit Logs', 'has': True}
                        ],
                        'clinical': [
                            {'name': 'View All Patients', 'has': True},
                            {'name': 'Prescribe Medications', 'has': True},
                            {'name': 'Access Medical Records', 'has': True},
                            {'name': 'View All Prescriptions', 'has': True}
                        ],
                        'schedule': [
                            {'name': 'View All Schedules', 'has': True},
                            {'name': 'Manage Appointments', 'has': True},
                            {'name': 'Override Schedule', 'has': True}
                        ],
                        'front_desk': [
                            {'name': 'Process Payments', 'has': True},
                            {'name': 'Manage Inventory', 'has': True},
                            {'name': 'Generate Reports', 'has': True}
                        ]
                    }

                elif role['name'] == 'doctor':
                    role_data['permissions'] = {
                        'system': [
                            {'name': 'Full System Control', 'has': False},
                            {'name': 'User Management', 'has': False},
                            {'name': 'Financial Oversight', 'has': False},
                            {'name': 'View Audit Logs', 'has': False}
                        ],
                        'clinical': [
                            {'name': 'View Assigned Patients', 'has': True},
                            {'name': 'Consultation Notes', 'has': True},
                            {'name': 'Prescribe Medications', 'has': True},
                            {'name': 'View Medical History', 'has': True}
                        ],
                        'schedule': [
                            {'name': 'View Own Schedule', 'has': True},
                            {'name': 'View All Schedules', 'has': False},
                            {'name': 'Request Schedule Changes', 'has': True}
                        ],
                        'front_desk': [
                            {'name': 'View Financial Reports', 'has': False},
                            {'name': 'View Inventory', 'has': False},
                            {'name': 'Process Payments', 'has': False}
                        ]
                    }

                elif role['name'] == 'nurse':
                    role_data['permissions'] = {
                        'system': [
                            {'name': 'Full System Control', 'has': False},
                            {'name': 'User Management', 'has': False},
                            {'name': 'Financial Oversight', 'has': False},
                            {'name': 'View Audit Logs', 'has': False}
                        ],
                        'clinical': [
                            {'name': 'View Assigned Patients', 'has': True},
                            {'name': 'Nurse Procedures', 'has': True},
                            {'name': 'Limited Prescriptions', 'has': True},
                            {'name': 'Record Vitals', 'has': True}
                        ],
                        'schedule': [
                            {'name': 'View Assigned Schedule', 'has': True},
                            {'name': 'View All Schedules', 'has': False},
                            {'name': 'Request Schedule Changes', 'has': True}
                        ],
                        'front_desk': [
                            {'name': 'View Inventory', 'has': True},
                            {'name': 'Process Payments', 'has': False},
                            {'name': 'Manage Appointments', 'has': False}
                        ]
                    }

                elif role['name'] == 'reception':
                    role_data['permissions'] = {
                        'system': [
                            {'name': 'Full System Control', 'has': False},
                            {'name': 'User Management', 'has': False},
                            {'name': 'Financial Oversight', 'has': False},
                            {'name': 'View Audit Logs', 'has': False}
                        ],
                        'clinical': [
                            {'name': 'View Patient Basic Info', 'has': True},
                            {'name': 'View Medical Records', 'has': False},
                            {'name': 'Prescribe Medications', 'has': False},
                            {'name': 'Schedule Appointments', 'has': True}
                        ],
                        'schedule': [
                            {'name': 'View All Schedules', 'has': True},
                            {'name': 'Manage Appointments', 'has': True},
                            {'name': 'Cancel Appointments', 'has': True}
                        ],
                        'front_desk': [
                            {'name': 'Process Payments', 'has': True},
                            {'name': 'Manage Inventory', 'has': True},
                            {'name': 'Generate Reports', 'has': True},
                            {'name': 'Register New Patients', 'has': True}
                        ]
                    }

                roles.append(role_data)

        db.close()
        return jsonify({'success': True, 'roles': roles}), 200

    except Exception as e:
        print(f"Get roles error: {e}")
        return jsonify({'error': 'Failed to fetch roles'}), 500

# =========================================
# Update Role Permissions
# =========================================


@access_control_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@login_required
@role_required('superadmin')
def update_role_permissions(role_id):
    """Update permissions for a specific role"""
    try:
        data = request.get_json()
        permissions = data.get('permissions', {})

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        # Create or update permissions in database
        # For now, we'll log the changes to audit_logs
        with db.cursor() as cursor:
            # Get role name
            cursor.execute("SELECT name FROM roles WHERE id = ?", (role_id,))
            role = cursor.fetchone()

            if not role:
                return jsonify({'error': 'Role not found'}), 404

            # Log permission changes
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE_PERMISSIONS', 'roles', ?, ?)
            """, (session['user_id'], role_id, json.dumps(permissions)))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': f'Permissions updated for {role["name"]}'
        }), 200

    except Exception as e:
        print(f"Update permissions error: {e}")
        return jsonify({'error': 'Failed to update permissions'}), 500

# =========================================
# Get Page Access Configuration
# =========================================


@access_control_bp.route('/page-access', methods=['GET'])
@login_required
@role_required('superadmin')
def get_page_access():
    """Get page access configuration for all roles"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        page_access = {}

        with db.cursor() as cursor:
            # Get all roles
            cursor.execute("SELECT id, name FROM roles")
            roles = cursor.fetchall()

            # Define all available pages
            all_pages = [
                {'id': 'dashboard', 'name': 'Dashboard',
                    'path': '/dashboard', 'icon': 'fas fa-chart-line'},
                {'id': 'user-mgmt', 'name': 'User Management',
                    'path': '/user-mgmt', 'icon': 'fas fa-users'},
                {'id': 'access-control', 'name': 'Access Control',
                    'path': '/access-control', 'icon': 'fas fa-lock'},
                {'id': 'financial', 'name': 'Financial',
                    'path': '/financial', 'icon': 'fas fa-coins'},
                {'id': 'analytics', 'name': 'Analytics',
                    'path': '/analytics', 'icon': 'fas fa-chart-pie'},
                {'id': 'inventory', 'name': 'Inventory',
                    'path': '/inventory', 'icon': 'fas fa-pills'},
                {'id': 'appointments', 'name': 'Appointments',
                    'path': '/appointments', 'icon': 'fas fa-calendar-check'},
                {'id': 'consult', 'name': 'Consultation',
                    'path': '/consult', 'icon': 'fas fa-notes-medical'},
                {'id': 'prescribe', 'name': 'Prescribe',
                    'path': '/prescribe', 'icon': 'fas fa-prescription'},
                {'id': 'records', 'name': 'Records',
                    'path': '/records', 'icon': 'fas fa-x-ray'},
                {'id': 'my-patients', 'name': 'My Patients',
                    'path': '/my-patients', 'icon': 'fas fa-user-injured'},
                {'id': 'schedule', 'name': 'Schedule',
                    'path': '/schedule', 'icon': 'fas fa-calendar-alt'},
                {'id': 'my-reports', 'name': 'My Reports',
                    'path': '/my-reports', 'icon': 'fas fa-chart-simple'},
                {'id': 'my-assists', 'name': 'My Assists',
                    'path': '/my-assists', 'icon': 'fas fa-hand-holding-medical'},
                {'id': 'my-tasks', 'name': 'My Tasks',
                    'path': '/my-tasks', 'icon': 'fas fa-tasks'},
                {'id': 'notes', 'name': 'Notes',
                    'path': '/notes', 'icon': 'fas fa-pen'},
                {'id': 'patients', 'name': 'Patients',
                    'path': '/patients', 'icon': 'fas fa-users'},
                {'id': 'payments', 'name': 'Payments',
                    'path': '/payments', 'icon': 'fas fa-credit-card'},
                {'id': 'reports', 'name': 'Reports',
                    'path': '/reports', 'icon': 'fas fa-chart-bar'},
                {'id': 'invoices', 'name': 'Invoices',
                    'path': '/invoices', 'icon': 'fas fa-file-invoice'},
                {'id': 'services', 'name': 'Services',
                    'path': '/services', 'icon': 'fas fa-teeth-open'},
                {'id': 'profile', 'name': 'Profile',
                    'path': '/profile', 'icon': 'fas fa-id-card'},
                {'id': 'settings', 'name': 'Settings',
                    'path': '/settings', 'icon': 'fas fa-cog'},
                {'id': 'performance', 'name': 'Performance',
                    'path': '/performance', 'icon': 'fas fa-chart-bar'},
                {'id': 'doctors', 'name': 'Doctors',
                    'path': '/doctors', 'icon': 'fas fa-user-md'},
                {'id': 'nurses', 'name': 'Nurses',
                    'path': '/nurses', 'icon': 'fas fa-user-nurse'},
                {'id': 'reception', 'name': 'Reception',
                    'path': '/reception', 'icon': 'fas fa-user-tie'}
            ]

            # Define default page access for each role
            default_access = {
                'superadmin': [p['id'] for p in all_pages],  # All pages
                'doctor': ['dashboard', 'my-patients', 'schedule', 'consult', 'prescribe', 'records', 'my-reports', 'profile'],
                'nurse': ['dashboard', 'my-assists', 'procedures', 'notes', 'prescribe', 'records', 'my-tasks', 'profile'],
                'reception': ['dashboard', 'appointments', 'patients', 'services', 'payments', 'reports', 'inventory', 'invoices', 'profile']
            }

            # Build page access for each role
            for role in roles:
                role_name = role['name']
                access_pages = default_access.get(
                    role_name, ['dashboard', 'profile'])

                page_access[role_name] = {
                    'role_id': role['id'],
                    'role_name': role_name,
                    'pages': [p for p in all_pages if p['id'] in access_pages],
                    'available_pages': all_pages
                }

        db.close()

        return jsonify({
            'success': True,
            'page_access': page_access,
            'all_pages': all_pages
        }), 200

    except Exception as e:
        print(f"Get page access error: {e}")
        return jsonify({'error': 'Failed to fetch page access'}), 500

# =========================================
# Update Page Access
# =========================================


@access_control_bp.route('/page-access', methods=['POST'])
@login_required
@role_required('superadmin')
def update_page_access():
    """Update page access for a role"""
    try:
        data = request.get_json()
        role_name = data.get('role')
        pages = data.get('pages', [])

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Get role id
            cursor.execute(
                "SELECT id FROM roles WHERE name = ?", (role_name,))
            role = cursor.fetchone()

            if not role:
                return jsonify({'error': 'Role not found'}), 404

            # Log page access changes
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE_PAGE_ACCESS', 'roles', ?, ?)
            """, (session['user_id'], role['id'], json.dumps({'pages': pages})))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': f'Page access updated for {role_name}'
        }), 200

    except Exception as e:
        print(f"Update page access error: {e}")
        return jsonify({'error': 'Failed to update page access'}), 500

# =========================================
# Get Staff List for Access Management
# =========================================


@access_control_bp.route('/staff', methods=['GET'])
@login_required
@role_required('superadmin')
def get_staff_for_access():
    """Get staff members for individual access control"""
    try:
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
                    r.name as role,
                    u.status,
                    u.specialization
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.role_id != (SELECT id FROM roles WHERE name = 'superadmin')
                ORDER BY r.name, u.last_name
            """)
            staff = cursor.fetchall()

            # Format dates
            for member in staff:
                member['name'] = f"{member['first_name']} {member['last_name']}"

        db.close()

        return jsonify({'success': True, 'staff': staff}), 200

    except Exception as e:
        print(f"Get staff error: {e}")
        return jsonify({'error': 'Failed to fetch staff'}), 500

# =========================================
# Update Staff Role
# =========================================


@access_control_bp.route('/staff/<int:staff_id>/role', methods=['PUT'])
@login_required
@role_required('superadmin')
def update_staff_role(staff_id):
    """Update staff member's role"""
    try:
        data = request.get_json()
        new_role_id = data.get('role_id')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Get old role for audit
            cursor.execute("""
                SELECT u.role_id, r.name as old_role
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.id = ?
            """, (staff_id,))
            old_data = cursor.fetchone()

            if not old_data:
                return jsonify({'error': 'Staff not found'}), 404

            # Update role
            cursor.execute("""
                UPDATE users 
                SET role_id = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (new_role_id, staff_id))

            # Get new role name
            cursor.execute(
                "SELECT name FROM roles WHERE id = ?", (new_role_id,))
            new_role = cursor.fetchone()

            # Log the change
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, old_data, new_data)
                VALUES (?, 'UPDATE_ROLE', 'users', ?, ?, ?)
            """, (
                session['user_id'], staff_id,
                json.dumps({'role': old_data['old_role']}),
                json.dumps({'role': new_role['name']})
            ))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': 'Staff role updated successfully'
        }), 200

    except Exception as e:
        print(f"Update staff role error: {e}")
        return jsonify({'error': 'Failed to update staff role'}), 500

# =========================================
# Get Audit Logs for Access Control
# =========================================


@access_control_bp.route('/audit-logs', methods=['GET'])
@login_required
@role_required('superadmin')
def get_access_audit_logs():
    """Get audit logs related to access control"""
    try:
        limit = request.args.get('limit', 50, type=int)

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    al.id,
                    al.action,
                    al.table_name,
                    al.record_id,
                    al.old_data,
                    al.new_data,
                    al.ip_address,
                    al.created_at,
                    u.first_name,
                    u.last_name,
                    u.email
                FROM audit_logs al
                LEFT JOIN users u ON al.user_id = u.id
                WHERE al.action IN ('UPDATE_PERMISSIONS', 'UPDATE_PAGE_ACCESS', 'UPDATE_ROLE', 'LOGIN', 'LOGOUT')
                ORDER BY al.created_at DESC
                LIMIT ?
            """, (limit,))

            logs = cursor.fetchall()

            # Format dates
            for log in logs:
                if log['created_at']:
                    log['created_at'] = log['created_at'].strftime(
                        '%Y-%m-%d %H:%M:%S')
                log['user_name'] = f"{log['first_name']} {log['last_name']}" if log['first_name'] else 'System'

        db.close()

        return jsonify({'success': True, 'logs': logs}), 200

    except Exception as e:
        print(f"Get audit logs error: {e}")
        return jsonify({'error': 'Failed to fetch audit logs'}), 500
