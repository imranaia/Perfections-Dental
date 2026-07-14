import sqlite3
# =========================================
# Perfections Dental Services
# Doctor Schedule Module - v1.0
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


# Create schedule blueprint
schedule_bp = Blueprint('doctor_schedule', __name__,
                        url_prefix='/api/doctor/schedule')



def format_time(value):
    """Helper function to format time value to string"""
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


def convert_to_time(obj):
    """Convert timedelta or time to time object"""
    if obj is None:
        return None
    if isinstance(obj, timedelta):
        total_seconds = obj.total_seconds()
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        return time(hours, minutes, seconds)
    if isinstance(obj, time):
        return obj
    if isinstance(obj, str):
        try:
            return datetime.strptime(obj, '%H:%M:%S').time()
        except:
            return None
    return None


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
# Parse Time String to Time Object
# =========================================

def parse_time_str(time_str):
    """Parse time string like '8:00 AM' to time object"""
    try:
        return datetime.strptime(time_str.strip(), '%I:%M %p').time()
    except:
        try:
            return datetime.strptime(time_str.strip(), '%I:%M%p').time()
        except:
            return None


# =========================================
# Get Business Hours from Settings
# =========================================

def get_business_hours():
    """Get business hours from clinic_settings"""
    try:
        db = get_db()
        if not db:
            return None, None

        business_hours = {}
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT setting_key, setting_value FROM clinic_settings WHERE setting_key LIKE 'business_hours_%'")
            settings = cursor.fetchall()
            for setting in settings:
                business_hours[setting['setting_key']
                               ] = setting['setting_value']

        db.close()
        return business_hours, None
    except Exception as e:
        print(f"Error getting business hours: {e}")
        return None, str(e)


# =========================================
# Get Time Slots for a Day
# =========================================

def get_time_slots_for_day(day_name):
    """Get list of time slots for a given day (for reference only)"""
    business_hours, error = get_business_hours()

    if day_name == 'Sunday':
        hours_str = business_hours.get(
            'business_hours_sun', 'Closed') if business_hours else 'Closed'
    elif day_name == 'Saturday':
        hours_str = business_hours.get(
            'business_hours_sat', '9:00 AM - 3:00 PM') if business_hours else '9:00 AM - 3:00 PM'
    else:
        hours_str = business_hours.get(
            'business_hours_mon_fri', '8:00 AM - 6:00 PM') if business_hours else '8:00 AM - 6:00 PM'

    if hours_str == 'Closed':
        return []

    parts = hours_str.split(' - ')
    if len(parts) != 2:
        return []

    start_time = parse_time_str(parts[0])
    end_time = parse_time_str(parts[1])

    if not start_time or not end_time:
        return []

    # Generate 30-minute slots for reference
    slots = []
    current = datetime.combine(datetime.today(), start_time)
    end = datetime.combine(datetime.today(), end_time)

    while current < end:
        slot_end = current + timedelta(minutes=30)
        if slot_end <= end:
            slots.append({
                'start': current.strftime('%I:%M %p'),
                'end': slot_end.strftime('%I:%M %p'),
                'start_time': current.strftime('%I:%M %p'),
                'end_time': slot_end.strftime('%I:%M %p')
            })
        current = slot_end

    return slots


# =========================================
# Get Schedule for a Date
# =========================================

@schedule_bp.route('/', methods=['GET'])
@login_required
@doctor_required
def get_schedule():
    """Get doctor's schedule for a specific date"""
    try:
        doctor_id = session.get('user_id')
        date_str = request.args.get(
            'date', datetime.now().strftime('%Y-%m-%d'))
        view = request.args.get('view', 'day')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        appointments = []
        summary = {}
        business_hours, _ = get_business_hours()

        with db.cursor() as cursor:
            if view == 'day':
                # Get appointments for specific day
                cursor.execute("""
                    SELECT
                        a.id,
                        a.appointment_number,
                        a.start_time,
                        a.end_time,
                        a.status,
                        a.room,
                        a.type,
                        a.emergency_priority,
                        a.notes,
                        p.id as patient_id,
                        p.first_name,
                        p.last_name,
                        p.patient_number,
                        p.phone,
                        p.dob,
                        p.gender,
                        p.allergies,
                        p.medical_alerts,
                        p.chronic_conditions
                    FROM appointments a
                    JOIN patients p ON a.patient_id = p.id
                    WHERE a.doctor_id = ?
                    AND DATE(a.appointment_date) = ?
                    ORDER BY a.start_time
                """, (doctor_id, date_str))

                results = cursor.fetchall()

                # Get services separately for each appointment
                appointments_list = []
                for row in results:
                    # Get services for this appointment
                    cursor.execute("""
                        SELECT s.name
                        FROM appointment_services ast
                        JOIN services s ON ast.service_id = s.id
                        WHERE ast.appointment_id = ?
                    """, (row['id'],))
                    services_rows = cursor.fetchall()
                    services = [s['name'] for s in services_rows] if services_rows else [
                        'Consultation']

                    # Calculate age
                    age = None
                    if row['dob']:
                        today = datetime.now().date()
                        age = today.year - \
                            row['dob'].year - ((today.month, today.day)
                                               < (row['dob'].month, row['dob'].day))

                    # Convert times to formatted strings
                    start_time_str = format_time(row['start_time'])
                    end_time_str = format_time(row['end_time'])

                    appointments_list.append({
                        'id': row['id'],
                        'appointment_number': row['appointment_number'],
                        'start_time': start_time_str,
                        'end_time': end_time_str,
                        'status': row['status'],
                        'room': row['room'] or 'TBD',
                        'type': row['type'],
                        'is_emergency': row['type'] == 'emergency' or row['emergency_priority'] is not None,
                        'notes': row['notes'],
                        'patient': {
                            'id': row['patient_id'],
                            'name': f"{row['first_name']} {row['last_name']}",
                            'first_name': row['first_name'],
                            'last_name': row['last_name'],
                            'initials': f"{row['first_name'][0]}{row['last_name'][0]}",
                            'patient_number': row['patient_number'],
                            'age': age,
                            'gender': row['gender'],
                            'phone': row['phone'],
                            'allergies': row['allergies'],
                            'medical_alerts': row['medical_alerts'],
                            'chronic_conditions': row['chronic_conditions']
                        },
                        'services': services
                    })

                # Build appointments list - each appointment as its own block
                appointments = appointments_list

                # Get summary statistics
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                        SUM(CASE WHEN status IN ('checked_in', 'in_progress') THEN 1 ELSE 0 END) as in_progress,
                        SUM(CASE WHEN status = 'waiting' THEN 1 ELSE 0 END) as waiting,
                        SUM(CASE WHEN type = 'emergency' THEN 1 ELSE 0 END) as emergencies
                    FROM appointments
                    WHERE doctor_id = ? AND DATE(appointment_date) = ?
                """, (doctor_id, date_str))
                summary_row = cursor.fetchone()

                summary = {
                    'total': summary_row['total'] or 0,
                    'completed': summary_row['completed'] or 0,
                    'in_progress': summary_row['in_progress'] or 0,
                    'waiting': summary_row['waiting'] or 0,
                    'emergencies': summary_row['emergencies'] or 0
                }

            elif view == 'week':
                # Get appointments for the week
                start_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                start_date = start_date - timedelta(days=start_date.weekday())
                end_date = start_date + timedelta(days=6)

                cursor.execute("""
                    SELECT 
                        a.id,
                        a.appointment_date,
                        a.start_time,
                        a.end_time,
                        a.status,
                        a.room,
                        p.first_name,
                        p.last_name,
                        p.patient_number
                    FROM appointments a
                    JOIN patients p ON a.patient_id = p.id
                    WHERE a.doctor_id = ? 
                    AND DATE(a.appointment_date) BETWEEN ? AND ?
                    ORDER BY a.appointment_date, a.start_time
                """, (doctor_id, start_date, end_date))

                results = cursor.fetchall()

                week_days = ['Monday', 'Tuesday', 'Wednesday',
                             'Thursday', 'Friday', 'Saturday', 'Sunday']
                appointments = {day: [] for day in week_days}

                # Get business hours for each day
                day_hours = {}
                for day in week_days:
                    slots = get_time_slots_for_day(day)
                    day_hours[day] = f"{slots[0]['start']} - {slots[-1]['end']}" if slots else 'Closed'

                for row in results:
                    day_name = row['appointment_date'].strftime('%A')
                    appointments[day_name].append({
                        'id': row['id'],
                        'start_time': format_time(row['start_time']),
                        'end_time': format_time(row['end_time']),
                        'status': row['status'],
                        'room': row['room'] or 'TBD',
                        'patient_name': f"{row['first_name']} {row['last_name']}",
                        'patient_initials': f"{row['first_name'][0]}{row['last_name'][0]}",
                        'procedure': 'Consultation'
                    })

                # Get weekly summary
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                        SUM(CASE WHEN type = 'emergency' THEN 1 ELSE 0 END) as emergencies
                    FROM appointments
                    WHERE doctor_id = ? 
                    AND DATE(appointment_date) BETWEEN ? AND ?
                """, (doctor_id, start_date, end_date))
                summary_row = cursor.fetchone()

                summary = {
                    'total': summary_row['total'] or 0,
                    'completed': summary_row['completed'] or 0,
                    'emergencies': summary_row['emergencies'] or 0,
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d'),
                    'day_hours': day_hours
                }

            else:  # month view
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                start_date = date_obj.replace(day=1)
                if date_obj.month == 12:
                    end_date = date_obj.replace(
                        year=date_obj.year + 1, month=1, day=1) - timedelta(days=1)
                else:
                    end_date = date_obj.replace(
                        month=date_obj.month + 1, day=1) - timedelta(days=1)

                cursor.execute("""
                    SELECT 
                        DATE(a.appointment_date) as appointment_date,
                        COUNT(*) as count,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
                    FROM appointments a
                    WHERE a.doctor_id = ? 
                    AND DATE(a.appointment_date) BETWEEN ? AND ?
                    GROUP BY DATE(a.appointment_date)
                    ORDER BY appointment_date
                """, (doctor_id, start_date, end_date))

                results = cursor.fetchall()

                appointments = {}
                for row in results:
                    appointments[row['appointment_date'].strftime('%Y-%m-%d')] = {
                        'count': row['count'],
                        'completed': row['completed']
                    }

                cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                        SUM(CASE WHEN type = 'emergency' THEN 1 ELSE 0 END) as emergencies
                    FROM appointments
                    WHERE doctor_id = ? 
                    AND DATE(appointment_date) BETWEEN ? AND ?
                """, (doctor_id, start_date, end_date))
                summary_row = cursor.fetchone()

                summary = {
                    'total': summary_row['total'] or 0,
                    'completed': summary_row['completed'] or 0,
                    'emergencies': summary_row['emergencies'] or 0,
                    'month': date_obj.strftime('%B %Y'),
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d')
                }

        db.close()

        return jsonify({
            'success': True,
            'view': view,
            'date': date_str,
            'appointments': appointments,
            'summary': summary,
            'business_hours': business_hours
        }), 200

    except Exception as e:
        print(f"Get schedule error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch schedule'}), 500


# =========================================
# Update Appointment Status
# =========================================

@schedule_bp.route('/appointment/<int:appointment_id>/status', methods=['PUT'])
@login_required
@doctor_required
def update_appointment_status(appointment_id):
    """Update appointment status"""
    try:
        doctor_id = session.get('user_id')
        data = request.get_json()
        new_status = data.get('status')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Verify appointment belongs to doctor
            cursor.execute("""
                SELECT id FROM appointments 
                WHERE id = ? AND doctor_id = ?
            """, (appointment_id, doctor_id))

            if not cursor.fetchone():
                return jsonify({'error': 'Appointment not found'}), 404

            # Update status
            cursor.execute("""
                UPDATE appointments 
                SET status = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (new_status, appointment_id))

            # Log action
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE_APPOINTMENT_STATUS', 'appointments', ?, ?)
            """, (doctor_id, appointment_id, json.dumps({'status': new_status})))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': 'Appointment status updated'
        }), 200

    except Exception as e:
        print(f"Update appointment status error: {e}")
        return jsonify({'error': 'Failed to update status'}), 500


# =========================================
# Get Break/Lunch Schedule from Settings
# =========================================

@schedule_bp.route('/breaks', methods=['GET'])
@login_required
@doctor_required
def get_breaks():
    """Get break schedule (from clinic_settings)"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        breaks = [
            {'time': '11:30 AM', 'duration': 30,
                'name': 'Morning Break', 'type': 'break'},
            {'time': '1:00 PM', 'duration': 60,
                'name': 'Lunch Break', 'type': 'lunch'},
            {'time': '3:30 PM', 'duration': 15,
                'name': 'Afternoon Break', 'type': 'break'}
        ]

        db.close()
        return jsonify({'success': True, 'breaks': breaks}), 200

    except Exception as e:
        print(f"Get breaks error: {e}")
        return jsonify({'error': 'Failed to fetch breaks'}), 500
