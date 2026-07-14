import sqlite3
# =========================================
# Perfections Dental Services
# Nurse Profile Module - v1.0
# =========================================

from config import Config
from db import get_db
from auth import login_required
from flask import Blueprint, jsonify, session, request
from datetime import datetime, time, timedelta
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Create nurse profile blueprint
nurse_profile_bp = Blueprint(
    'nurse_profile', __name__, url_prefix='/api/nurse/profile')



def nurse_required(f):
    """Decorator to require nurse role"""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

        user_role = session.get('role')
        if user_role not in ['nurse', 'superadmin']:
            return jsonify({'error': 'Access denied. Nurse role required.'}), 403

        return f(*args, **kwargs)
    return decorated_function


# =========================================
# Get Current Nurse Profile
# =========================================

@nurse_profile_bp.route('/', methods=['GET'])
@login_required
@nurse_required
def get_profile():
    """Get current nurse profile details"""
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

            # Get skills from qualifications
            skills = []
            if user['qualifications']:
                skills = [s.strip() for s in user['qualifications'].split(',')]
            else:
                skills = ["Surgical Assistance",
                          "Sterilization", "Patient Monitoring"]

            # Get shift schedule
            cursor.execute("""
                SELECT s.name, s.display_name, s.start_time, s.end_time,
                       ss.is_current
                FROM staff_shifts ss
                JOIN shifts s ON ss.shift_id = s.id
                WHERE ss.staff_id = ? AND ss.is_current = 1
            """, (user_id,))
            shift = cursor.fetchone()

            # Get work days schedule
            cursor.execute("""
                SELECT wd.name, wd.day_number, ss.is_working,
                       ss.custom_start_time, ss.custom_end_time
                FROM staff_schedule ss
                JOIN work_days wd ON ss.day_id = wd.id
                WHERE ss.staff_id = ?
                ORDER BY wd.day_number
            """, (user_id,))
            schedule_rows = cursor.fetchall()

            # Build schedule dictionary
            schedule = {}
            days_of_week = ['Monday', 'Tuesday', 'Wednesday',
                            'Thursday', 'Friday', 'Saturday', 'Sunday']
            for day in days_of_week:
                schedule[day] = {'working': False, 'time': 'Off'}

            for row in schedule_rows:
                if row['is_working']:
                    if row['custom_start_time'] and row['custom_end_time']:
                        start = format_time(row['custom_start_time'])
                        end = format_time(row['custom_end_time'])
                        schedule[row['name']] = {
                            'working': True, 'time': f"{start} - {end}"}
                    elif shift:
                        start = format_time(shift['start_time'])
                        end = format_time(shift['end_time'])
                        schedule[row['name']] = {
                            'working': True, 'time': f"{start} - {end}"}
                    else:
                        schedule[row['name']] = {
                            'working': True, 'time': '8:00 AM - 4:00 PM'}

            # Get performance stats
            cursor.execute("""
                SELECT COUNT(*) as total_assists
                FROM assists
                WHERE nurse_id = ?
            """, (user_id,))
            total_assists = cursor.fetchone()['total_assists']

            cursor.execute("""
                SELECT COUNT(*) as total_procedures
                FROM appointments
                WHERE nurse_id = ? AND type = 'nurse_only'
            """, (user_id,))
            total_procedures = cursor.fetchone()['total_procedures']

            # Get completed tasks
            cursor.execute("""
                SELECT COUNT(*) as completed_tasks
                FROM tasks
                WHERE assigned_to = ? AND status = 'completed'
                AND DATE(completed_at) >= date(date('now'), '-30 days')
            """, (user_id,))
            completed_tasks = cursor.fetchone()['completed_tasks']

            cursor.execute("""
                SELECT COUNT(*) as total_tasks
                FROM tasks
                WHERE assigned_to = ?
                AND DATE(created_at) >= date(date('now'), '-30 days')
            """, (user_id,))
            total_tasks = cursor.fetchone()['total_tasks']

            # Calculate task completion percentage
            if total_tasks > 0:
                task_completion = round((completed_tasks / total_tasks) * 100)
            else:
                task_completion = 0

            # Get pending tasks
            cursor.execute("""
                SELECT 
                    id,
                    task_name,
                    due_date,
                    priority,
                    status
                FROM tasks
                WHERE assigned_to = ? AND status = 'pending'
                ORDER BY 
                    CASE priority 
                        WHEN 'high' THEN 1 
                        WHEN 'medium' THEN 2 
                        WHEN 'low' THEN 3 
                    END,
                    due_date ASC
                LIMIT 3
            """, (user_id,))
            pending_tasks = cursor.fetchall()

            # Get average rating (placeholder)
            avg_rating = 4.8

            # Calculate leave balances (placeholder - would come from leave table)
            leave_balance = {
                'annual': {'total': 20, 'used': 8, 'remaining': 12, 'percentage': 60},
                'sick': {'total': 12, 'used': 2, 'remaining': 10, 'percentage': 20}
            }

            # Format tasks
            formatted_tasks = []
            for task in pending_tasks:
                due_time = format_datetime(
                    task['due_date']) if task['due_date'] else 'No deadline'
                formatted_tasks.append({
                    'id': task['id'],
                    'name': task['task_name'],
                    'due_time': due_time,
                    'priority': task['priority']
                })

            # Get recent activities
            cursor.execute("""
                SELECT 
                    action,
                    table_name,
                    created_at
                FROM audit_logs
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 5
            """, (user_id,))
            activities = cursor.fetchall()

            result = {
                'id': user['id'],
                'employee_id': user['employee_id'],
                'first_name': user['first_name'],
                'last_name': user['last_name'],
                'full_name': f"{user['first_name']} {user['last_name']}",
                'initials': f"{user['first_name'][0]}{user['last_name'][0]}",
                'email': user['email'],
                'phone': user['phone'],
                'license_number': user['license_number'] or 'N/A',
                'position': user['specialization'] or 'Dental Nurse',
                'experience_years': user['experience_years'] or 0,
                'date_joined': user['date_joined'].strftime('%d %B %Y') if user['date_joined'] else '',
                'date_joined_raw': user['date_joined'].strftime('%Y-%m-%d') if user['date_joined'] else '',
                'status': user['status'],
                'emergency_contact': {
                    'name': user['emergency_contact_name'] or '',
                    'phone': user['emergency_contact_phone'] or ''
                },
                'skills': skills,
                'shift': {
                    'name': shift['name'] if shift else 'morning',
                    'display_name': shift['display_name'] if shift else 'Morning Shift',
                    'start_time': format_time(shift['start_time']) if shift else '8:00 AM',
                    'end_time': format_time(shift['end_time']) if shift else '4:00 PM'
                },
                'schedule': schedule,
                'stats': {
                    'assists': total_assists,
                    'procedures': total_procedures,
                    'satisfaction': avg_rating,
                    'experience': user['experience_years'] or 0,
                    'task_completion': task_completion,
                    'completed_tasks': completed_tasks,
                    'total_tasks': total_tasks
                },
                'pending_tasks': formatted_tasks,
                'leave_balance': leave_balance,
                'recent_activities': [
                    {
                        'action': a['action'],
                        'table': a['table_name'],
                        'time_ago': get_time_ago(a['created_at']) if a['created_at'] else ''
                    } for a in activities
                ]
            }

        db.close()
        return jsonify({'success': True, 'profile': result}), 200

    except Exception as e:
        print(f"Get profile error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch profile'}), 500


# =========================================
# Update Profile
# =========================================

@nurse_profile_bp.route('/', methods=['PUT'])
@login_required
@nurse_required
def update_profile():
    """Update nurse profile"""
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

            # Update profile
            cursor.execute("""
                UPDATE users SET
                    first_name = ?,
                    last_name = ?,
                    phone = ?,
                    license_number = ?,
                    specialization = ?,
                    qualifications = ?,
                    experience_years = ?,
                    emergency_contact_name = ?,
                    emergency_contact_phone = ?,
                    updated_at = datetime('now')
                WHERE id = ?
            """, (
                data.get('first_name'),
                data.get('last_name'),
                data.get('phone'),
                data.get('license_number'),
                data.get('position'),
                ', '.join(data.get('skills') or []) or None,
                data.get('experience_years'),
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

        # Update session name
        session['name'] = f"{data.get('first_name')} {data.get('last_name')}"

        return jsonify({
            'success': True,
            'message': 'Profile updated successfully'
        }), 200

    except Exception as e:
        print(f"Update profile error: {e}")
        return jsonify({'error': 'Failed to update profile'}), 500


# =========================================
# Update Skills
# =========================================

@nurse_profile_bp.route('/skills', methods=['PUT'])
@login_required
@nurse_required
def update_skills():
    """Update nurse skills"""
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        skills = data.get('skills', [])

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Update qualifications field with comma-separated skills
            skills_str = ', '.join(skills)
            cursor.execute("""
                UPDATE users 
                SET qualifications = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (skills_str, user_id))

            # Log update
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE_SKILLS', 'users', ?, ?)
            """, (user_id, user_id, json.dumps({'skills': skills})))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': 'Skills updated successfully'
        }), 200

    except Exception as e:
        print(f"Update skills error: {e}")
        return jsonify({'error': 'Failed to update skills'}), 500


# =========================================
# Update Shift Schedule
# =========================================

@nurse_profile_bp.route('/schedule', methods=['PUT'])
@login_required
@nurse_required
def update_schedule():
    """Update nurse's work schedule for a specific day"""
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        day = data.get('day')
        is_working = data.get('is_working', True)
        start_time = data.get('start_time')
        end_time = data.get('end_time')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Get day_id
            cursor.execute("SELECT id FROM work_days WHERE name = ?", (day,))
            day_row = cursor.fetchone()
            if not day_row:
                return jsonify({'error': 'Invalid day'}), 400

            # Check if schedule exists
            cursor.execute("""
                SELECT id FROM staff_schedule 
                WHERE staff_id = ? AND day_id = ?
            """, (user_id, day_row['id']))
            existing = cursor.fetchone()

            if existing:
                # Update existing schedule
                cursor.execute("""
                    UPDATE staff_schedule 
                    SET is_working = ?, 
                        custom_start_time = ?,
                        custom_end_time = ?,
                        updated_at = datetime('now')
                    WHERE staff_id = ? AND day_id = ?
                """, (is_working, start_time, end_time, user_id, day_row['id']))
            else:
                # Insert new schedule
                cursor.execute("""
                    INSERT INTO staff_schedule (staff_id, day_id, is_working, custom_start_time, custom_end_time)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, day_row['id'], is_working, start_time, end_time))

            # Log update
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE_SCHEDULE', 'staff_schedule', ?, ?)
            """, (user_id, user_id, json.dumps({'day': day, 'is_working': is_working})))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': f'Schedule updated for {day}'
        }), 200

    except Exception as e:
        print(f"Update schedule error: {e}")
        return jsonify({'error': 'Failed to update schedule'}), 500


# =========================================
# Change Password
# =========================================

@nurse_profile_bp.route('/change-password', methods=['POST'])
@login_required
@nurse_required
def change_password():
    """Change nurse password"""
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

        from werkzeug.security import check_password_hash, generate_password_hash

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
# Complete Task
# =========================================

@nurse_profile_bp.route('/task/<int:task_id>/complete', methods=['PUT'])
@login_required
@nurse_required
def complete_task(task_id):
    """Mark a task as completed"""
    try:
        user_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                UPDATE tasks 
                SET status = 'completed', 
                    completed_at = datetime('now'),
                    updated_at = datetime('now')
                WHERE id = ? AND assigned_to = ? AND status != 'completed'
            """, (task_id, user_id))

            if cursor.rowcount == 0:
                return jsonify({'error': 'Task not found or already completed'}), 404

            # Log completion
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'COMPLETE_TASK', 'tasks', ?, ?)
            """, (user_id, task_id, json.dumps({'status': 'completed'})))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': 'Task completed successfully'
        }), 200

    except Exception as e:
        print(f"Complete task error: {e}")
        return jsonify({'error': 'Failed to complete task'}), 500


# =========================================
# Helper Functions
# =========================================

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
    if isinstance(value, datetime):
        return value.strftime('%I:%M %p')
    if isinstance(value, time):
        return value.strftime('%I:%M %p')
    if isinstance(value, str):
        return value
    return ""


def format_datetime(value):
    """Format datetime for display"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        now = datetime.now()
        if value.date() == now.date():
            return value.strftime('Today, %I:%M %p')
        elif value.date() == now.date() - timedelta(days=1):
            return value.strftime('Yesterday, %I:%M %p')
        else:
            return value.strftime('%b %d, %I:%M %p')
    return str(value)


def get_time_ago(date):
    """Get time ago string"""
    if not date:
        return ''
    now = datetime.now()
    diff = now - date

    if diff.days > 30:
        return date.strftime('%b %d, %Y')
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
