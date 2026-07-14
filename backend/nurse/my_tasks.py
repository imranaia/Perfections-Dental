import sqlite3
# =========================================
# Perfections Dental Services
# Nurse My Tasks Module - v1.0
# =========================================

from config import Config
from db import get_db
from auth import login_required
from flask import Blueprint, jsonify, session, request
from datetime import datetime, timedelta, time
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Create my tasks blueprint
my_tasks_bp = Blueprint('my_tasks', __name__, url_prefix='/api/nurse/tasks')



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
# Get All Tasks for Nurse
# =========================================

@my_tasks_bp.route('/', methods=['GET'])
@login_required
@nurse_required
def get_my_tasks():
    """Get all tasks assigned to the nurse with filtering"""
    try:
        nurse_id = session.get('user_id')
        # all, pending, in_progress, completed, overdue, today
        filter_type = request.args.get('filter', 'all')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        tasks = []

        with db.cursor() as cursor:
            query = """
                SELECT 
                    id,
                    task_name,
                    description,
                    due_date,
                    priority,
                    status,
                    notes,
                    created_at,
                    completed_at,
                    created_by
                FROM tasks
                WHERE assigned_to = ?
            """
            params = [nurse_id]

            # Add filters
            if filter_type == 'pending':
                query += " AND status = 'pending'"
            elif filter_type == 'in_progress':
                query += " AND status = 'in_progress'"
            elif filter_type == 'completed':
                query += " AND status = 'completed'"
            elif filter_type == 'overdue':
                query += " AND status != 'completed' AND due_date < datetime('now')"
            elif filter_type == 'today':
                query += " AND DATE(due_date) = date('now') AND status != 'completed'"

            query += """ ORDER BY
                CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END,
                due_date ASC"""

            cursor.execute(query, tuple(params))
            results = cursor.fetchall()

            # Get creator names for tasks
            creator_names = {}
            for row in results:
                if row['created_by'] not in creator_names:
                    cursor.execute(
                        "SELECT first_name, last_name FROM users WHERE id = ?", (row['created_by'],))
                    creator = cursor.fetchone()
                    creator_names[row['created_by']
                                  ] = f"{creator['first_name']} {creator['last_name']}" if creator else 'System'

            for row in results:
                due_date_str = ""
                is_overdue = False
                if row['due_date']:
                    due_date_str = format_time(row['due_date'])
                    if row['status'] != 'completed' and row['due_date'] < datetime.now():
                        is_overdue = True
                        due_date_str = f"Overdue: {due_date_str}"

                tasks.append({
                    'id': row['id'],
                    'name': row['task_name'],
                    'description': row['description'] or '',
                    'due_date': row['due_date'].strftime('%Y-%m-%d %H:%M') if row['due_date'] else None,
                    'due_time': due_date_str,
                    'priority': row['priority'],
                    'status': row['status'],
                    'notes': row['notes'] or '',
                    'created_by': creator_names.get(row['created_by'], 'System'),
                    'is_overdue': is_overdue,
                    'completed_at': row['completed_at'].strftime('%Y-%m-%d %H:%M') if row['completed_at'] else None
                })

        db.close()
        return jsonify({'success': True, 'tasks': tasks}), 200

    except Exception as e:
        print(f"Get my tasks error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch tasks'}), 500


# =========================================
# Get Task Details
# =========================================

@my_tasks_bp.route('/<int:task_id>', methods=['GET'])
@login_required
@nurse_required
def get_task_details(task_id):
    """Get detailed information for a specific task"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id,
                    task_name,
                    description,
                    due_date,
                    priority,
                    status,
                    notes,
                    created_at,
                    completed_at,
                    created_by
                FROM tasks
                WHERE id = ? AND assigned_to = ?
            """, (task_id, nurse_id))

            task = cursor.fetchone()

            if not task:
                return jsonify({'error': 'Task not found'}), 404

            # Get creator name
            cursor.execute(
                "SELECT first_name, last_name FROM users WHERE id = ?", (task['created_by'],))
            creator = cursor.fetchone()
            created_by_name = f"{creator['first_name']} {creator['last_name']}" if creator else 'System'

            # Get subtasks if any (from task_subtasks table if exists, otherwise return sample)
            subtasks = [
                {'name': 'Prepare materials',
                    'completed': task['status'] == 'completed'},
                {'name': 'Follow safety protocols',
                    'completed': task['status'] == 'completed'},
                {'name': 'Document completion',
                    'completed': task['status'] == 'completed'}
            ]

            result = {
                'id': task['id'],
                'name': task['task_name'],
                'description': task['description'] or '',
                'due_date': task['due_date'].strftime('%Y-%m-%d %H:%M') if task['due_date'] else None,
                'priority': task['priority'],
                'status': task['status'],
                'notes': task['notes'] or '',
                'created_by': created_by_name,
                'created_at': task['created_at'].strftime('%b %d, %Y %I:%M %p') if task['created_at'] else '',
                'completed_at': task['completed_at'].strftime('%b %d, %Y %I:%M %p') if task['completed_at'] else None,
                'subtasks': subtasks
            }

        db.close()
        return jsonify({'success': True, 'task': result}), 200

    except Exception as e:
        print(f"Get task details error: {e}")
        return jsonify({'error': 'Failed to fetch task details'}), 500


# =========================================
# Update Task Status
# =========================================

@my_tasks_bp.route('/<int:task_id>/status', methods=['PUT'])
@login_required
@nurse_required
def update_task_status(task_id):
    """Update task status (start, complete, etc.)"""
    try:
        data = request.get_json()
        new_status = data.get('status')
        notes = data.get('notes', '')

        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if task exists and belongs to nurse
            cursor.execute("""
                SELECT id, status, notes FROM tasks 
                WHERE id = ? AND assigned_to = ?
            """, (task_id, nurse_id))

            task = cursor.fetchone()
            if not task:
                return jsonify({'error': 'Task not found'}), 404

            # Update status
            if new_status == 'in_progress' and task['status'] == 'pending':
                cursor.execute("""
                    UPDATE tasks 
                    SET status = 'in_progress', notes = (IFNULL(notes, '') || '\n' || ?), updated_at = datetime('now')
                    WHERE id = ?
                """, (f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M')}: {notes}", task_id))
            elif new_status == 'completed':
                cursor.execute("""
                    UPDATE tasks 
                    SET status = 'completed', completed_at = datetime('now'), 
                        notes = (IFNULL(notes, '') || '\n' || ?), updated_at = datetime('now')
                    WHERE id = ?
                """, (f"Completed at {datetime.now().strftime('%Y-%m-%d %H:%M')}: {notes}", task_id))
            else:
                cursor.execute("""
                    UPDATE tasks 
                    SET status = ?, updated_at = datetime('now')
                    WHERE id = ?
                """, (new_status, task_id))

            # Log action
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE_TASK_STATUS', 'tasks', ?, ?)
            """, (nurse_id, task_id, json.dumps({'status': new_status})))

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': f'Task marked as {new_status}'}), 200

    except Exception as e:
        print(f"Update task status error: {e}")
        return jsonify({'error': 'Failed to update task status'}), 500


# =========================================
# Get Task Statistics
# =========================================

@my_tasks_bp.route('/stats', methods=['GET'])
@login_required
@nurse_required
def get_task_stats():
    """Get task statistics for the nurse"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        stats = {}

        with db.cursor() as cursor:
            # Total tasks
            cursor.execute(
                "SELECT COUNT(*) as total FROM tasks WHERE assigned_to = ?", (nurse_id,))
            stats['total'] = cursor.fetchone()['total']

            # Pending tasks
            cursor.execute(
                "SELECT COUNT(*) as total FROM tasks WHERE assigned_to = ? AND status = 'pending'", (nurse_id,))
            stats['pending'] = cursor.fetchone()['total']

            # In progress tasks
            cursor.execute(
                "SELECT COUNT(*) as total FROM tasks WHERE assigned_to = ? AND status = 'in_progress'", (nurse_id,))
            stats['in_progress'] = cursor.fetchone()['total']

            # Completed tasks
            cursor.execute(
                "SELECT COUNT(*) as total FROM tasks WHERE assigned_to = ? AND status = 'completed'", (nurse_id,))
            stats['completed'] = cursor.fetchone()['total']

            # Overdue tasks
            cursor.execute("""
                SELECT COUNT(*) as total 
                FROM tasks 
                WHERE assigned_to = ? 
                AND status != 'completed' 
                AND due_date < datetime('now')
            """, (nurse_id,))
            stats['overdue'] = cursor.fetchone()['total']

            # Today's tasks
            cursor.execute("""
                SELECT COUNT(*) as total 
                FROM tasks 
                WHERE assigned_to = ? 
                AND DATE(due_date) = date('now') 
                AND status != 'completed'
            """, (nurse_id,))
            stats['today'] = cursor.fetchone()['total']

            # Urgent tasks (high priority pending)
            cursor.execute("""
                SELECT COUNT(*) as total 
                FROM tasks 
                WHERE assigned_to = ? 
                AND priority = 'high' 
                AND status != 'completed'
            """, (nurse_id,))
            stats['urgent'] = cursor.fetchone()['total']

            # Completion rate
            if stats['total'] > 0:
                stats['completion_rate'] = round(
                    (stats['completed'] / stats['total']) * 100, 1)
            else:
                stats['completion_rate'] = 0

        db.close()
        return jsonify({'success': True, 'stats': stats}), 200

    except Exception as e:
        print(f"Get task stats error: {e}")
        return jsonify({'error': 'Failed to fetch task stats'}), 500


# =========================================
# Add Note to Task
# =========================================

@my_tasks_bp.route('/<int:task_id>/note', methods=['POST'])
@login_required
@nurse_required
def add_task_note(task_id):
    """Add a note to a task"""
    try:
        data = request.get_json()
        note = data.get('note', '')
        nurse_id = session.get('user_id')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                UPDATE tasks 
                SET notes = (IFNULL(notes, '') || '\n' || ?), updated_at = datetime('now')
                WHERE id = ? AND assigned_to = ?
            """, (f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {note}", task_id, nurse_id))

            if cursor.rowcount == 0:
                return jsonify({'error': 'Task not found'}), 404

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Note added successfully'}), 200

    except Exception as e:
        print(f"Add task note error: {e}")
        return jsonify({'error': 'Failed to add note'}), 500
