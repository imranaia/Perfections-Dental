import sqlite3
# =========================================
# Perfections Dental Services
# Reception Staff Management Module - v1.0
# SuperAdmin Only
# =========================================

from config import Config
from db import get_db
from auth import login_required, role_required
from flask import Blueprint, jsonify, session, request
from datetime import datetime, timedelta, time
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Create reception blueprint
reception_bp = Blueprint('reception', __name__,
                         url_prefix='/api/superadmin/reception')



def format_time(value):
    """Helper function to format time value"""
    if value is None:
        return "8:00 AM"
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
    return "8:00 AM"


# =========================================
# Get All Reception Staff
# =========================================

@reception_bp.route('/', methods=['GET'])
@login_required
@role_required('superadmin')
def get_reception_staff():
    """Get all reception staff with their details including shift and schedule"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        staff_list = []

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
                    u.experience_years,
                    u.date_joined,
                    u.status,
                    u.emergency_contact_name,
                    u.emergency_contact_phone,
                    u.avatar
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE r.name = 'reception'
                ORDER BY u.last_name, u.first_name
            """)

            users = cursor.fetchall()

            for user in users:
                staff_id = user['id']

                # Get current shift from staff_shifts table
                cursor.execute("""
                    SELECT s.id, s.name, s.display_name, s.start_time, s.end_time
                    FROM staff_shifts ss
                    JOIN shifts s ON ss.shift_id = s.id
                    WHERE ss.staff_id = ? AND ss.is_current = 1
                """, (staff_id,))
                shift_data = cursor.fetchone()

                shift_name = 'morning'
                shift_display = 'Morning Shift'
                shift_start = '8:00 AM'
                shift_end = '4:00 PM'

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
                """, (staff_id,))
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

                # Build schedule dictionary for display
                schedule = {
                    "Monday": "Off",
                    "Tuesday": "Off",
                    "Wednesday": "Off",
                    "Thursday": "Off",
                    "Friday": "Off",
                    "Saturday": "Off",
                    "Sunday": "Off"
                }

                for day in work_days:
                    if shift_name == 'morning':
                        schedule[day] = f"{shift_start} - {shift_end}"
                    elif shift_name == 'afternoon':
                        schedule[day] = f"{shift_start} - {shift_end}"
                    else:  # evening
                        if day in ["Tuesday", "Wednesday", "Thursday", "Friday"]:
                            schedule[day] = f"{shift_start} - {shift_end}"
                        elif day == "Saturday":
                            schedule[day] = "10:00 AM - 4:00 PM"

                # Build shift time description
                work_days_str = ", ".join(work_days)
                shift_time = f"{work_days_str}, {shift_start} - {shift_end}"

                # Get today's check-ins count
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM appointments
                    WHERE DATE(appointment_date) = date('now')
                    AND status IN ('checked_in', 'waiting', 'in_progress')
                """)
                today_checkins = cursor.fetchone()['count']

                # Get today's payments processed
                cursor.execute("""
                    SELECT COALESCE(SUM(amount), 0) as total
                    FROM payments
                    WHERE DATE(payment_date) = date('now')
                """)
                today_payments = float(cursor.fetchone()['total'])

                # Get average rating (placeholder - would come from reviews)
                avg_rating = 4.8

                # Get performance metrics
                performance = 85 + (user['experience_years'] or 0) * 2
                performance = min(performance, 98)

                staff_list.append({
                    'id': user['id'],
                    'employee_id': user['employee_id'],
                    'firstName': user['first_name'],
                    'lastName': user['last_name'],
                    'fullName': f"{user['first_name']} {user['last_name']}",
                    'initials': f"{user['first_name'][0]}{user['last_name'][0]}",
                    'role': user['specialization'] or 'Receptionist',
                    'shift': shift_name,
                    'shiftDisplay': shift_display,
                    'shiftTime': shift_time,
                    'email': user['email'],
                    'phone': user['phone'],
                    'dob': user['date_joined'].strftime('%Y-%m-%d') if user['date_joined'] else '',
                    'gender': 'Female',
                    'checkins': today_checkins,
                    'payments': today_payments,
                    'rating': avg_rating,
                    'performance': performance,
                    'status': user['status'],
                    'trainer': None,
                    'emergencyName': user['emergency_contact_name'] or '',
                    'emergencyPhone': user['emergency_contact_phone'] or '',
                    'workDays': work_days,
                    'schedule': schedule
                })

        db.close()
        return jsonify({'success': True, 'staff': staff_list}), 200

    except Exception as e:
        print(f"Get reception staff error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch reception staff'}), 500


# =========================================
# Get Single Reception Staff
# =========================================

@reception_bp.route('/<int:staff_id>', methods=['GET'])
@login_required
@role_required('superadmin')
def get_reception_staff_by_id(staff_id):
    """Get single reception staff details"""
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
                    u.specialization,
                    u.experience_years,
                    u.date_joined,
                    u.status,
                    u.emergency_contact_name,
                    u.emergency_contact_phone,
                    u.avatar
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.id = ? AND r.name = 'reception'
            """, (staff_id,))

            user = cursor.fetchone()

            if not user:
                return jsonify({'error': 'Staff not found'}), 404

            # Get current shift
            cursor.execute("""
                SELECT s.name as shift_name
                FROM staff_shifts ss
                JOIN shifts s ON ss.shift_id = s.id
                WHERE ss.staff_id = ? AND ss.is_current = 1
            """, (staff_id,))
            shift = cursor.fetchone()

            # Get work days
            cursor.execute("""
                SELECT wd.name
                FROM staff_schedule ss
                JOIN work_days wd ON ss.day_id = wd.id
                WHERE ss.staff_id = ? AND ss.is_working = 1
                ORDER BY wd.day_number
            """, (staff_id,))
            work_days_rows = cursor.fetchall()
            work_days = [row['name'] for row in work_days_rows]

            staff = {
                'id': user['id'],
                'employee_id': user['employee_id'],
                'firstName': user['first_name'],
                'lastName': user['last_name'],
                'email': user['email'],
                'phone': user['phone'],
                'role': user['specialization'] or 'Receptionist',
                'shift': shift['shift_name'] if shift else 'morning',
                'workDays': work_days,
                'experience': user['experience_years'] or 0,
                'date_joined': user['date_joined'].strftime('%Y-%m-%d') if user['date_joined'] else '',
                'status': user['status'],
                'emergencyName': user['emergency_contact_name'] or '',
                'emergencyPhone': user['emergency_contact_phone'] or ''
            }

        db.close()
        return jsonify({'success': True, 'staff': staff}), 200

    except Exception as e:
        print(f"Get reception staff error: {e}")
        return jsonify({'error': 'Failed to fetch staff'}), 500


# =========================================
# Create Reception Staff
# =========================================

@reception_bp.route('/', methods=['POST'])
@login_required
@role_required('superadmin')
def create_reception_staff():
    """Create a new reception staff member"""
    try:
        data = request.get_json()

        # Generate employee ID
        import random
        employee_id = f"REC{random.randint(1000, 9999)}"

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        # Hash password (default password)
        from werkzeug.security import generate_password_hash
        default_password = generate_password_hash("reception123")

        with db.cursor() as cursor:
            # Get reception role id
            cursor.execute("SELECT id FROM roles WHERE name = 'reception'")
            role = cursor.fetchone()

            if not role:
                return jsonify({'error': 'Reception role not found'}), 500

            # Insert new reception staff
            cursor.execute("""
                INSERT INTO users (
                    role_id, employee_id, first_name, last_name, email, phone,
                    password_hash, specialization, experience_years, date_joined, status,
                    emergency_contact_name, emergency_contact_phone
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, date('now'), ?, ?, ?
                )
            """, (
                role['id'],
                employee_id,
                data.get('firstName'),
                data.get('lastName'),
                data.get('email'),
                data.get('phone'),
                default_password,
                data.get('role'),
                data.get('experience', 0),
                data.get('status', 'active'),
                data.get('emergencyName'),
                data.get('emergencyPhone')
            ))

            staff_id = cursor.lastrowid

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
                """, (staff_id, shift['id']))

            # Get work days and assign schedule
            work_days = data.get('workDays', [])

            for day_name in work_days:
                cursor.execute(
                    "SELECT id FROM work_days WHERE name = ?", (day_name,))
                day = cursor.fetchone()
                if day:
                    cursor.execute("""
                        INSERT INTO staff_schedule (staff_id, day_id, is_working)
                        VALUES (?, ?, 1)
                    """, (staff_id, day['id']))

            # Log creation
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'CREATE', 'users', ?, ?)
            """, (session['user_id'], staff_id, json.dumps(data)))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': 'Reception staff created successfully',
            'staff_id': staff_id
        }), 201

    except Exception as e:
        print(f"Create reception staff error: {e}")
        return jsonify({'error': 'Failed to create reception staff'}), 500


# =========================================
# Update Reception Staff
# =========================================

@reception_bp.route('/<int:staff_id>', methods=['PUT'])
@login_required
@role_required('superadmin')
def update_reception_staff(staff_id):
    """Update reception staff details"""
    try:
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if staff exists
            cursor.execute("SELECT id FROM users WHERE id = ?", (staff_id,))
            if not cursor.fetchone():
                return jsonify({'error': 'Staff not found'}), 404

            # Update user basic info
            cursor.execute("""
                UPDATE users SET
                    first_name = ?,
                    last_name = ?,
                    email = ?,
                    phone = ?,
                    specialization = ?,
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
                data.get('role'),
                data.get('experience', 0),
                data.get('status', 'active'),
                data.get('emergencyName'),
                data.get('emergencyPhone'),
                staff_id
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
                """, (staff_id,))

                # Add new shift
                cursor.execute("""
                    INSERT INTO staff_shifts (staff_id, shift_id, effective_from, is_current)
                    VALUES (?, ?, date('now'), 1)
                """, (staff_id, shift['id']))

            # Update schedule
            work_days = data.get('workDays', [])

            # First, deactivate all days
            cursor.execute("""
                UPDATE staff_schedule SET is_working = 0
                WHERE staff_id = ?
            """, (staff_id,))

            # Then activate selected days
            for day_name in work_days:
                cursor.execute(
                    "SELECT id FROM work_days WHERE name = ?", (day_name,))
                day = cursor.fetchone()
                if day:
                    # Check if record exists
                    cursor.execute("""
                        SELECT id FROM staff_schedule WHERE staff_id = ? AND day_id = ?
                    """, (staff_id, day['id']))
                    existing = cursor.fetchone()

                    if existing:
                        cursor.execute("""
                            UPDATE staff_schedule SET is_working = 1, updated_at = datetime('now')
                            WHERE staff_id = ? AND day_id = ?
                        """, (staff_id, day['id']))
                    else:
                        cursor.execute("""
                            INSERT INTO staff_schedule (staff_id, day_id, is_working)
                            VALUES (?, ?, 1)
                        """, (staff_id, day['id']))

            # Log update
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE', 'users', ?, ?)
            """, (session['user_id'], staff_id, json.dumps(data)))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': 'Reception staff updated successfully'
        }), 200

    except Exception as e:
        print(f"Update reception staff error: {e}")
        return jsonify({'error': 'Failed to update reception staff'}), 500


# =========================================
# Delete Reception Staff
# =========================================

@reception_bp.route('/<int:staff_id>', methods=['DELETE'])
@login_required
@role_required('superadmin')
def delete_reception_staff(staff_id):
    """Delete reception staff"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if staff has any appointments created
            cursor.execute(
                "SELECT COUNT(*) as count FROM appointments WHERE created_by = ?", (staff_id,))
            appointments = cursor.fetchone()

            if appointments['count'] > 0:
                # Instead of deleting, mark as inactive
                cursor.execute("""
                    UPDATE users SET status = 'inactive', updated_at = datetime('now')
                    WHERE id = ?
                """, (staff_id,))
                message = "Staff marked as inactive (had existing appointments)"
            else:
                # Delete staff and related records
                cursor.execute(
                    "DELETE FROM staff_schedule WHERE staff_id = ?", (staff_id,))
                cursor.execute(
                    "DELETE FROM staff_shifts WHERE staff_id = ?", (staff_id,))
                cursor.execute("DELETE FROM users WHERE id = ?", (staff_id,))
                message = "Reception staff deleted successfully"

            # Log deletion
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id)
                VALUES (?, 'DELETE', 'users', ?)
            """, (session['user_id'], staff_id))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': message
        }), 200

    except Exception as e:
        print(f"Delete reception staff error: {e}")
        return jsonify({'error': 'Failed to delete staff'}), 500


# =========================================
# Get Dashboard Stats
# =========================================

@reception_bp.route('/stats', methods=['GET'])
@login_required
@role_required('superadmin')
def get_reception_stats():
    """Get reception-related statistics"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        stats = {}

        with db.cursor() as cursor:
            # Total reception staff
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE r.name = 'reception'
            """)
            stats['total_staff'] = cursor.fetchone()['total']

            # Active staff
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE r.name = 'reception' AND u.status = 'active'
            """)
            stats['active_staff'] = cursor.fetchone()['total']

            # Today's check-ins
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM appointments
                WHERE DATE(appointment_date) = date('now')
                AND status IN ('checked_in', 'waiting', 'in_progress')
            """)
            stats['today_checkins'] = cursor.fetchone()['total']

            # Today's payments
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) as total
                FROM payments
                WHERE DATE(payment_date) = date('now')
            """)
            stats['today_payments'] = float(cursor.fetchone()['total'])

            # Average efficiency
            stats['avg_efficiency'] = 92

            # Average rating
            stats['avg_rating'] = 4.8

        db.close()
        return jsonify({'success': True, 'stats': stats}), 200

    except Exception as e:
        print(f"Get stats error: {e}")
        return jsonify({'error': 'Failed to fetch statistics'}), 500


# =========================================
# Get Queue Status
# =========================================

@reception_bp.route('/queue', methods=['GET'])
@login_required
@role_required('superadmin')
def get_queue_status():
    """Get current queue status"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        queue = []

        with db.cursor() as cursor:
            # Check-in counter queue
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM appointments
                WHERE DATE(appointment_date) = date('now')
                AND status = 'scheduled'
                AND start_time <= TIME(datetime('now'))
            """)
            checkin_waiting = cursor.fetchone()['count']

            # Payment counter queue
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM invoices
                WHERE status = 'unpaid'
                AND DATE(created_at) = date('now')
            """)
            payment_pending = cursor.fetchone()['count']

            # Appointment desk queue
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM appointments
                WHERE DATE(appointment_date) = date('now')
                AND status = 'waiting'
            """)
            waiting_appointments = cursor.fetchone()['count']

            queue = [
                {'counter': 'Check-in Counter', 'patients': checkin_waiting, 'waitTime': '2 min' if checkin_waiting >
                    0 else 'Immediate', 'status': 'warning' if checkin_waiting > 2 else 'success'},
                {'counter': 'Payment Counter', 'patients': payment_pending, 'waitTime': 'Immediate' if payment_pending ==
                    0 else '5 min', 'status': 'success' if payment_pending == 0 else 'warning'},
                {'counter': 'Appointment Desk', 'patients': waiting_appointments, 'waitTime': '5 min' if waiting_appointments >
                    0 else 'None', 'status': 'warning' if waiting_appointments > 0 else 'success'},
                {'counter': 'Insurance Verification', 'patients': 0,
                    'waitTime': 'None', 'status': 'success'}
            ]

        db.close()
        return jsonify({'success': True, 'queue': queue}), 200

    except Exception as e:
        print(f"Get queue error: {e}")
        return jsonify({'error': 'Failed to fetch queue status'}), 500
