import sqlite3
# =========================================
# Perfections Dental Services
# Nurses Management Module - v1.0
# SuperAdmin Only
# =========================================

from config import Config
from db import get_db
from auth import login_required, role_required
from flask import Blueprint, jsonify, session, request
from datetime import datetime, time, timedelta
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Create nurses blueprint
nurses_bp = Blueprint('nurses', __name__, url_prefix='/api/superadmin/nurses')



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


# =========================================
# Get All Nurses
# =========================================

@nurses_bp.route('/', methods=['GET'])
@login_required
@role_required('superadmin')
def get_nurses():
    """Get all nurses with their details including shift"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        nurses = []

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
                    r.id as role_id
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE r.name = 'nurse'
                ORDER BY u.last_name, u.first_name
            """)

            users = cursor.fetchall()

            for user in users:
                nurse_id = user['id']

                # Get current shift from staff_shifts table
                cursor.execute("""
                    SELECT s.id, s.name, s.display_name, s.start_time, s.end_time
                    FROM staff_shifts ss
                    JOIN shifts s ON ss.shift_id = s.id
                    WHERE ss.staff_id = ? AND ss.is_current = 1
                """, (nurse_id,))
                shift_data = cursor.fetchone()

                shift_name = 'morning'
                shift_display = 'Morning Shift'
                shift_start = '9:00 AM'
                shift_end = '5:00 PM'

                if shift_data:
                    shift_name = shift_data['name']
                    shift_display = shift_data['display_name']
                    shift_start = format_time(shift_data['start_time'])
                    shift_end = format_time(shift_data['end_time'])

                # Get work days from staff_schedule table
                cursor.execute("""
                    SELECT wd.name, wd.day_number
                    FROM staff_schedule ss
                    JOIN work_days wd ON ss.day_id = wd.id
                    WHERE ss.staff_id = ? AND ss.is_working = 1
                    ORDER BY wd.day_number
                """, (nurse_id,))
                schedule_rows = cursor.fetchall()

                work_days = [row['name'] for row in schedule_rows]

                # If no schedule exists, set default based on shift
                if not work_days:
                    if shift_name == 'morning':
                        work_days = ["Monday", "Tuesday",
                                     "Wednesday", "Thursday", "Friday"]
                    elif shift_name == 'afternoon':
                        work_days = ["Monday", "Tuesday",
                                     "Wednesday", "Thursday", "Friday"]
                    else:  # evening
                        work_days = ["Tuesday", "Wednesday",
                                     "Thursday", "Friday", "Saturday"]

                # Build schedule list for display
                schedule_list = []
                for day in work_days:
                    schedule_list.append({
                        'day': day,
                        'time': f"{shift_start} - {shift_end}"
                    })

                # Add weekend info
                if 'Saturday' not in work_days and shift_name != 'evening':
                    schedule_list.append(
                        {'day': 'Saturday', 'time': '10:00 AM - 2:00 PM'})
                if 'Sunday' not in work_days:
                    schedule_list.append({'day': 'Sunday', 'time': 'Off'})

                # Build shift time description
                work_days_str = ", ".join(work_days)
                shift_time = f"{work_days_str}, {shift_start} - {shift_end}"

                # Get today's assists count
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM assists a
                    JOIN appointments app ON a.appointment_id = app.id
                    WHERE a.nurse_id = ? AND DATE(app.appointment_date) = date('now')
                """, (nurse_id,))
                today_assists = cursor.fetchone()['count']

                # Get independent tasks count
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM tasks
                    WHERE assigned_to = ? AND status != 'completed'
                """, (nurse_id,))
                independent_tasks = cursor.fetchone()['count']

                # Get skills from qualifications
                skills = []
                if user['qualifications']:
                    skills = [s.strip()
                              for s in user['qualifications'].split(',')]
                else:
                    skills = ["Patient Care", "Sterilization", "Assisting"]

                # Independent skills - from license or specialization
                independent_skills = []
                if user['license_number']:
                    independent_skills = [user['specialization']] if user['specialization'] else [
                        "Basic Procedures"]

                # Get current assignments from tasks
                assignments = []
                cursor.execute("""
                    SELECT 
                        task_name,
                        due_date,
                        status
                    FROM tasks
                    WHERE assigned_to = ? AND status != 'completed'
                    ORDER BY due_date ASC
                    LIMIT 3
                """, (nurse_id,))
                tasks = cursor.fetchall()

                for task in tasks:
                    time_str = ""
                    if task['due_date']:
                        if isinstance(task['due_date'], datetime):
                            time_str = task['due_date'].strftime('%I:%M %p')
                    assignments.append({
                        'task': task['task_name'],
                        'time': time_str
                    })

                # Get assists for today
                cursor.execute("""
                    SELECT 
                        d.first_name as doctor_first,
                        d.last_name as doctor_last,
                        app.start_time,
                        app.room
                    FROM assists a
                    JOIN appointments app ON a.appointment_id = app.id
                    JOIN users d ON app.doctor_id = d.id
                    WHERE a.nurse_id = ? AND DATE(app.appointment_date) = date('now')
                    ORDER BY app.start_time
                    LIMIT 3
                """, (nurse_id,))
                assists = cursor.fetchall()

                for assist in assists:
                    time_str = ""
                    if assist['start_time']:
                        if isinstance(assist['start_time'], (datetime, time)):
                            time_str = assist['start_time'].strftime(
                                '%I:%M %p')
                    assignments.append({
                        'doctor': f"Dr. {assist['doctor_first']} {assist['doctor_last']}",
                        'task': f"Assisting - {assist['room'] or 'Room TBD'}",
                        'time': time_str or 'Now'
                    })

                if len(assignments) == 0:
                    assignments = [
                        {'task': 'No current assignments', 'time': ''}]

                # Get total assists (all time)
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM assists
                    WHERE nurse_id = ?
                """, (nurse_id,))
                total_assists = cursor.fetchone()['count']

                # Calculate average rating (placeholder - from a reviews table if exists)
                avg_rating = 4.7

                nurses.append({
                    'id': user['id'],
                    'employee_id': user['employee_id'],
                    'firstName': user['first_name'],
                    'lastName': user['last_name'],
                    'fullName': f"{user['first_name']} {user['last_name']}",
                    'initials': f"{user['first_name'][0]}{user['last_name'][0]}",
                    'role': 'Nurse',
                    'shift': shift_name,
                    'shiftDisplay': shift_display,
                    'shiftTime': shift_time,
                    'experience': user['experience_years'] or 0,
                    'assists': today_assists,
                    'independent': independent_tasks,
                    'rating': avg_rating,
                    'email': user['email'],
                    'phone': user['phone'],
                    'dob': user['date_joined'].strftime('%Y-%m-%d') if user['date_joined'] else '',
                    'gender': 'Female',
                    'skills': skills,
                    'independentSkills': independent_skills,
                    'schedule': schedule_list,
                    'active': user['status'] == 'active',
                    'assignments': assignments,
                    'contact': {
                        'emergencyName': user['emergency_contact_name'] or '',
                        'emergencyPhone': user['emergency_contact_phone'] or ''
                    }
                })

        db.close()
        return jsonify({'success': True, 'nurses': nurses}), 200

    except Exception as e:
        print(f"Get nurses error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch nurses'}), 500


# =========================================
# Get Single Nurse
# =========================================

@nurses_bp.route('/<int:nurse_id>', methods=['GET'])
@login_required
@role_required('superadmin')
def get_nurse(nurse_id):
    """Get single nurse details with shift info"""
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
                    u.phone,
                    u.license_number,
                    u.specialization,
                    u.qualifications,
                    u.experience_years,
                    u.date_joined,
                    u.status,
                    u.emergency_contact_name,
                    u.emergency_contact_phone,
                    u.avatar
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.id = ? AND r.name = 'nurse'
            """, (nurse_id,))

            user = cursor.fetchone()

            if not user:
                return jsonify({'error': 'Nurse not found'}), 404

            # Get current shift
            cursor.execute("""
                SELECT s.name as shift_name, s.display_name
                FROM staff_shifts ss
                JOIN shifts s ON ss.shift_id = s.id
                WHERE ss.staff_id = ? AND ss.is_current = 1
            """, (nurse_id,))
            shift = cursor.fetchone()

            # Get work days
            cursor.execute("""
                SELECT wd.name
                FROM staff_schedule ss
                JOIN work_days wd ON ss.day_id = wd.id
                WHERE ss.staff_id = ? AND ss.is_working = 1
                ORDER BY wd.day_number
            """, (nurse_id,))
            work_days_rows = cursor.fetchall()
            work_days = [row['name'] for row in work_days_rows]

            nurse = {
                'id': user['id'],
                'employee_id': user['employee_id'],
                'firstName': user['first_name'],
                'lastName': user['last_name'],
                'email': user['email'],
                'phone': user['phone'],
                'license': user['license_number'] or '',
                'specialty': user['specialization'] or 'General Nursing',
                'skills': user['qualifications'] or '',
                'shift': shift['shift_name'] if shift else 'morning',
                'shiftDisplay': shift['display_name'] if shift else 'Morning Shift',
                'workDays': work_days,
                'experience': user['experience_years'] or 0,
                'date_joined': user['date_joined'].strftime('%Y-%m-%d') if user['date_joined'] else '',
                'status': user['status'],
                'emergencyName': user['emergency_contact_name'] or '',
                'emergencyPhone': user['emergency_contact_phone'] or ''
            }

        db.close()
        return jsonify({'success': True, 'nurse': nurse}), 200

    except Exception as e:
        print(f"Get nurse error: {e}")
        return jsonify({'error': 'Failed to fetch nurse'}), 500


# =========================================
# Create Nurse
# =========================================

@nurses_bp.route('/', methods=['POST'])
@login_required
@role_required('superadmin')
def create_nurse():
    """Create a new nurse with shift assignment"""
    try:
        data = request.get_json()

        # Generate employee ID
        import random
        employee_id = f"NUR{random.randint(1000, 9999)}"

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        # Hash password (default password)
        from werkzeug.security import generate_password_hash
        default_password = generate_password_hash("nurse123")

        with db.cursor() as cursor:
            # Get nurse role id
            cursor.execute("SELECT id FROM roles WHERE name = 'nurse'")
            role = cursor.fetchone()

            if not role:
                return jsonify({'error': 'Nurse role not found'}), 500

            # Insert new nurse
            cursor.execute("""
                INSERT INTO users (
                    role_id, employee_id, first_name, last_name, email, phone,
                    password_hash, license_number, specialization, qualifications,
                    experience_years, date_joined, status, emergency_contact_name,
                    emergency_contact_phone
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, date('now'), ?, ?, ?
                )
            """, (
                role['id'],
                employee_id,
                data.get('firstName'),
                data.get('lastName'),
                data.get('email'),
                data.get('phone'),
                default_password,
                data.get('license'),
                data.get('specialty'),
                data.get('skills'),
                data.get('experience', 0),
                data.get('status', 'active'),
                data.get('emergencyName'),
                data.get('emergencyPhone')
            ))

            nurse_id = cursor.lastrowid

            # Get shift id
            shift_name = data.get('shift', 'morning')
            cursor.execute(
                "SELECT id FROM shifts WHERE name = ?", (shift_name,))
            shift = cursor.fetchone()

            if shift:
                # Assign shift
                cursor.execute("""
                    INSERT INTO staff_shifts (staff_id, shift_id, effective_from, is_current)
                    VALUES (?, ?, date('now'), 1)
                """, (nurse_id, shift['id']))

            # Get work days and assign schedule
            work_days = data.get('workDays', [])
            if not work_days:
                # Default work days based on shift
                if shift_name == 'morning' or shift_name == 'afternoon':
                    work_days = ["Monday", "Tuesday",
                                 "Wednesday", "Thursday", "Friday"]
                else:
                    work_days = ["Tuesday", "Wednesday",
                                 "Thursday", "Friday", "Saturday"]

            for day_name in work_days:
                cursor.execute(
                    "SELECT id FROM work_days WHERE name = ?", (day_name,))
                day = cursor.fetchone()
                if day:
                    cursor.execute("""
                        INSERT INTO staff_schedule (staff_id, day_id, is_working)
                        VALUES (?, ?, 1)
                    """, (nurse_id, day['id']))

            # Log creation
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'CREATE', 'users', ?, ?)
            """, (session['user_id'], nurse_id, json.dumps(data)))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': 'Nurse created successfully',
            'nurse_id': nurse_id
        }), 201

    except Exception as e:
        print(f"Create nurse error: {e}")
        return jsonify({'error': 'Failed to create nurse'}), 500


# =========================================
# Update Nurse
# =========================================

@nurses_bp.route('/<int:nurse_id>', methods=['PUT'])
@login_required
@role_required('superadmin')
def update_nurse(nurse_id):
    """Update nurse details including shift"""
    try:
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if nurse exists
            cursor.execute("SELECT id FROM users WHERE id = ?", (nurse_id,))
            if not cursor.fetchone():
                return jsonify({'error': 'Nurse not found'}), 404

            # Update nurse basic info
            cursor.execute("""
                UPDATE users SET
                    first_name = ?,
                    last_name = ?,
                    email = ?,
                    phone = ?,
                    license_number = ?,
                    specialization = ?,
                    qualifications = ?,
                    experience_years = ?,
                    status = ?,
                    emergency_contact_name = ?,
                    emergency_contact_phone = ?,
                    updated_at = datetime('now')
                WHERE id = ?
            """, (
                data.get('firstName'),
                data.get('lastName'),
                data.get('email'),
                data.get('phone'),
                data.get('license'),
                data.get('specialty'),
                data.get('skills'),
                data.get('experience', 0),
                data.get('status', 'active'),
                data.get('emergencyName'),
                data.get('emergencyPhone'),
                nurse_id
            ))

            # Update shift
            shift_name = data.get('shift', 'morning')
            cursor.execute(
                "SELECT id FROM shifts WHERE name = ?", (shift_name,))
            shift = cursor.fetchone()

            if shift:
                # Deactivate old shifts
                cursor.execute("""
                    UPDATE staff_shifts SET is_current = 0
                    WHERE staff_id = ?
                """, (nurse_id,))

                # Add new shift
                cursor.execute("""
                    INSERT INTO staff_shifts (staff_id, shift_id, effective_from, is_current)
                    VALUES (?, ?, date('now'), 1)
                """, (nurse_id, shift['id']))

            # Update schedule
            work_days = data.get('workDays', [])

            # First, deactivate all days
            cursor.execute("""
                UPDATE staff_schedule SET is_working = 0
                WHERE staff_id = ?
            """, (nurse_id,))

            # Then activate selected days
            for day_name in work_days:
                cursor.execute(
                    "SELECT id FROM work_days WHERE name = ?", (day_name,))
                day = cursor.fetchone()
                if day:
                    # Check if record exists
                    cursor.execute("""
                        SELECT id FROM staff_schedule WHERE staff_id = ? AND day_id = ?
                    """, (nurse_id, day['id']))
                    existing = cursor.fetchone()

                    if existing:
                        cursor.execute("""
                            UPDATE staff_schedule SET is_working = 1, updated_at = datetime('now')
                            WHERE staff_id = ? AND day_id = ?
                        """, (nurse_id, day['id']))
                    else:
                        cursor.execute("""
                            INSERT INTO staff_schedule (staff_id, day_id, is_working)
                            VALUES (?, ?, 1)
                        """, (nurse_id, day['id']))

            # Log update
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE', 'users', ?, ?)
            """, (session['user_id'], nurse_id, json.dumps(data)))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': 'Nurse updated successfully'
        }), 200

    except Exception as e:
        print(f"Update nurse error: {e}")
        return jsonify({'error': 'Failed to update nurse'}), 500


# =========================================
# Delete Nurse
# =========================================

@nurses_bp.route('/<int:nurse_id>', methods=['DELETE'])
@login_required
@role_required('superadmin')
def delete_nurse(nurse_id):
    """Delete a nurse"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if nurse has assists
            cursor.execute(
                "SELECT COUNT(*) as count FROM assists WHERE nurse_id = ?", (nurse_id,))
            assists = cursor.fetchone()

            if assists['count'] > 0:
                # Instead of deleting, mark as inactive
                cursor.execute("""
                    UPDATE users SET status = 'inactive', updated_at = datetime('now')
                    WHERE id = ?
                """, (nurse_id,))
                message = "Nurse marked as inactive (had existing assists)"
            else:
                # Delete nurse and related records
                cursor.execute(
                    "DELETE FROM staff_schedule WHERE staff_id = ?", (nurse_id,))
                cursor.execute(
                    "DELETE FROM staff_shifts WHERE staff_id = ?", (nurse_id,))
                cursor.execute("DELETE FROM users WHERE id = ?", (nurse_id,))
                message = "Nurse deleted successfully"

            # Log deletion
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id)
                VALUES (?, 'DELETE', 'users', ?)
            """, (session['user_id'], nurse_id))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': message
        }), 200

    except Exception as e:
        print(f"Delete nurse error: {e}")
        return jsonify({'error': 'Failed to delete nurse'}), 500


# =========================================
# Get Today's Nurse Assignments
# =========================================

@nurses_bp.route('/assignments/today', methods=['GET'])
@login_required
@role_required('superadmin')
def get_today_assignments():
    """Get today's nurse assignments"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        assignments = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    ass.id,
                    app.appointment_number,
                    app.start_time,
                    app.room,
                    app.status,
                    u.first_name as nurse_first,
                    u.last_name as nurse_last,
                    d.first_name as doctor_first,
                    d.last_name as doctor_last,
                    s.name as service_name
                FROM assists ass
                JOIN appointments app ON ass.appointment_id = app.id
                JOIN users u ON ass.nurse_id = u.id
                LEFT JOIN users d ON app.doctor_id = d.id
                LEFT JOIN appointment_services ast ON app.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE DATE(app.appointment_date) = date('now')
                ORDER BY app.start_time
            """)

            results = cursor.fetchall()

            for row in results:
                time_str = ""
                if row['start_time']:
                    if isinstance(row['start_time'], (datetime, time)):
                        time_str = row['start_time'].strftime('%I:%M %p')
                    else:
                        time_str = str(row['start_time'])

                doctor_name = "Nurse Only"
                if row['doctor_first']:
                    doctor_name = f"Dr. {row['doctor_first']} {row['doctor_last']}"

                status_text = row['status'].replace(
                    '_', ' ').title() if row['status'] else 'Scheduled'
                status_class = "badge-success" if row['status'] == 'completed' else "badge-info"

                assignments.append({
                    'id': row['id'],
                    'nurse_id': row['nurse_id'],
                    'nurse': f"{row['nurse_first']} {row['nurse_last']}",
                    'doctor': doctor_name,
                    'time': time_str or 'TBD',
                    'procedure': row['service_name'] or 'General Assist',
                    'room': row['room'] or 'TBD',
                    'status': status_text
                })

        db.close()
        return jsonify({'success': True, 'assignments': assignments}), 200

    except Exception as e:
        print(f"Get assignments error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch assignments'}), 500


# =========================================
# Get Dashboard Stats
# =========================================

@nurses_bp.route('/stats', methods=['GET'])
@login_required
@role_required('superadmin')
def get_nurse_stats():
    """Get nurse-related statistics"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        stats = {}

        with db.cursor() as cursor:
            # Total nurses
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE r.name = 'nurse'
            """)
            stats['total_nurses'] = cursor.fetchone()['total']

            # Active nurses
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE r.name = 'nurse' AND u.status = 'active'
            """)
            stats['active_nurses'] = cursor.fetchone()['total']

            # Today's assists
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM assists ass
                JOIN appointments app ON ass.appointment_id = app.id
                WHERE DATE(app.appointment_date) = date('now')
            """)
            stats['today_assists'] = cursor.fetchone()['total']

            # Independent tasks (pending tasks)
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM tasks
                WHERE status = 'pending'
            """)
            stats['independent_tasks'] = cursor.fetchone()['total']

            # Average rating (placeholder)
            stats['avg_rating'] = 4.7

            # Calculate average assists per nurse
            if stats['active_nurses'] > 0:
                stats['avg_assists'] = round(
                    stats['today_assists'] / stats['active_nurses'], 1)
            else:
                stats['avg_assists'] = 0

        db.close()
        return jsonify({'success': True, 'stats': stats}), 200

    except Exception as e:
        print(f"Get stats error: {e}")
        return jsonify({'error': 'Failed to fetch statistics'}), 500
