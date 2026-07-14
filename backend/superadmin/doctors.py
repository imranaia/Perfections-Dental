import sqlite3
# =========================================
# Perfections Dental Services
# Doctors Management Module - v1.0
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


# Create doctors blueprint
doctors_bp = Blueprint('doctors', __name__,
                       url_prefix='/api/superadmin/doctors')



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
# Get All Doctors
# =========================================

@doctors_bp.route('/', methods=['GET'])
@login_required
@role_required('superadmin')
def get_doctors():
    """Get all doctors with their details including shift and schedule"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        doctors = []

        with db.cursor() as cursor:
            # Get all users with role 'doctor' (includes superadmin if they are also a doctor)
            cursor.execute("""
                SELECT 
                    u.id,
                    u.employee_id,
                    u.first_name,
                    u.last_name,
                    u.email,
                    u.phone,
                    u.password_hash,
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
                WHERE r.name IN ('doctor', 'superadmin')
                ORDER BY u.last_name, u.first_name
            """)

            users = cursor.fetchall()

            for user in users:
                doctor_id = user['id']

                # Get current shift from staff_shifts table
                cursor.execute("""
                    SELECT s.id, s.name, s.display_name, s.start_time, s.end_time
                    FROM staff_shifts ss
                    JOIN shifts s ON ss.shift_id = s.id
                    WHERE ss.staff_id = ? AND ss.is_current = 1
                """, (doctor_id,))
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
                """, (doctor_id,))
                schedule_rows = cursor.fetchall()

                work_days = [row['name'] for row in schedule_rows]

                # Build schedule dictionary
                schedule = {
                    "Monday": "Off",
                    "Tuesday": "Off",
                    "Wednesday": "Off",
                    "Thursday": "Off",
                    "Friday": "Off",
                    "Saturday": "Off",
                    "Sunday": "Off"
                }

                # If no schedule exists, set default based on shift
                if not work_days:
                    if shift_name == 'morning':
                        work_days = ["Monday", "Tuesday",
                                     "Wednesday", "Thursday", "Friday"]
                        schedule["Monday"] = f"{shift_start} - {shift_end}"
                        schedule["Tuesday"] = f"{shift_start} - {shift_end}"
                        schedule["Wednesday"] = f"{shift_start} - {shift_end}"
                        schedule["Thursday"] = f"{shift_start} - {shift_end}"
                        schedule["Friday"] = f"{shift_start} - {shift_end}"
                    elif shift_name == 'afternoon':
                        work_days = ["Monday", "Tuesday",
                                     "Wednesday", "Thursday", "Friday"]
                        schedule["Monday"] = f"{shift_start} - {shift_end}"
                        schedule["Tuesday"] = f"{shift_start} - {shift_end}"
                        schedule["Wednesday"] = f"{shift_start} - {shift_end}"
                        schedule["Thursday"] = f"{shift_start} - {shift_end}"
                        schedule["Friday"] = f"{shift_start} - {shift_end}"
                    else:  # evening
                        work_days = ["Tuesday", "Wednesday",
                                     "Thursday", "Friday", "Saturday"]
                        schedule["Tuesday"] = f"{shift_start} - {shift_end}"
                        schedule["Wednesday"] = f"{shift_start} - {shift_end}"
                        schedule["Thursday"] = f"{shift_start} - {shift_end}"
                        schedule["Friday"] = f"{shift_start} - {shift_end}"
                        schedule["Saturday"] = "10:00 AM - 4:00 PM"
                else:
                    for day in work_days:
                        schedule[day] = f"{shift_start} - {shift_end}"

                # Get today's appointments count
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM appointments
                    WHERE doctor_id = ? AND DATE(appointment_date) = date('now')
                    AND status NOT IN ('cancelled')
                """, (user['id'],))
                today_appointments = cursor.fetchone()['count']

                # Get total patients count
                cursor.execute("""
                    SELECT COUNT(DISTINCT patient_id) as count
                    FROM appointments
                    WHERE doctor_id = ?
                """, (user['id'],))
                total_patients = cursor.fetchone()['count']

                # Get average rating (from reviews table if exists)
                avg_rating = 4.8

                # Get next appointment
                cursor.execute("""
                    SELECT 
                        a.appointment_number,
                        a.start_time,
                        p.first_name as patient_first,
                        p.last_name as patient_last,
                        s.name as service_name
                    FROM appointments a
                    JOIN patients p ON a.patient_id = p.id
                    LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                    LEFT JOIN services s ON ast.service_id = s.id
                    WHERE a.doctor_id = ? 
                    AND a.appointment_date >= date('now')
                    AND a.status NOT IN ('cancelled', 'completed')
                    ORDER BY a.appointment_date, a.start_time
                    LIMIT 1
                """, (user['id'],))
                next_appt = cursor.fetchone()

                next_appointment = "No appointments"
                if next_appt:
                    next_appointment = f"{next_appt['service_name'] or 'Consultation'} - {next_appt['start_time'].strftime('%I:%M %p')}"

                # Get performance metrics for current month
                cursor.execute("""
                    SELECT 
                        COUNT(DISTINCT a.id) as procedures,
                        COUNT(DISTINCT a.patient_id) as patients_mtd,
                        COALESCE(SUM(i.total), 0) as revenue
                    FROM appointments a
                    LEFT JOIN invoices i ON a.id = i.appointment_id
                    WHERE a.doctor_id = ?
                    AND CAST(strftime('%m', a.appointment_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER)
                    AND CAST(strftime('%Y', a.appointment_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
                    AND a.status = 'completed'
                """, (user['id'],))
                performance = cursor.fetchone()

                # Build schedule list for display
                schedule_list = []
                for day, time_slot in schedule.items():
                    if time_slot != "Off":
                        schedule_list.append({'day': day, 'time': time_slot})

                # If no schedule items, add default
                if not schedule_list:
                    schedule_list = [
                        {'day': 'Monday - Friday',
                            'time': f'{shift_start} - {shift_end}'},
                        {'day': 'Saturday', 'time': '10:00 AM - 2:00 PM'}
                    ]

                # Determine role display
                role_display = "Doctor"
                if user['role'] == 'superadmin':
                    role_display = "Doctor (SuperAdmin)"

                doctors.append({
                    'id': user['id'],
                    'employee_id': user['employee_id'],
                    'firstName': user['first_name'],
                    'lastName': user['last_name'],
                    'fullName': f"Dr. {user['first_name']} {user['last_name']}",
                    'initials': f"{user['first_name'][0]}{user['last_name'][0]}",
                    'role': role_display,
                    'specialty': user['specialization'] or 'General Dentistry',
                    'specializations': (user['qualifications'] or 'General Dentistry').split(',') if user['qualifications'] else ['General Dentistry'],
                    'email': user['email'],
                    'phone': user['phone'],
                    'dob': user['date_joined'].strftime('%Y-%m-%d') if user['date_joined'] else '',
                    'gender': 'Male',
                    'license': user['license_number'] or '',
                    'experience': user['experience_years'] or 0,
                    'patients': total_patients,
                    'patientsToday': today_appointments,
                    'yearsExp': user['experience_years'] or 0,
                    'rating': avg_rating,
                    'ratingStars': '★' * int(avg_rating) + '☆' * (5 - int(avg_rating)),
                    'nextAppointment': next_appointment,
                    'room': f"Room {(user['id'] % 4) + 1}",
                    'status': user['status'],
                    'online': user['status'] == 'active',
                    'schedule': schedule_list,
                    'contact': {
                        'emergencyName': user['emergency_contact_name'] or '',
                        'emergencyPhone': user['emergency_contact_phone'] or ''
                    },
                    'performance': {
                        'patientsMTD': performance['patients_mtd'] or 0,
                        'procedures': performance['procedures'] or 0,
                        'revenue': float(performance['revenue'] or 0),
                        'satisfaction': 95,
                        'efficiency': 92
                    }
                })

        db.close()
        return jsonify({'success': True, 'doctors': doctors}), 200

    except Exception as e:
        print(f"Get doctors error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch doctors'}), 500


# =========================================
# Get Single Doctor
# =========================================

@doctors_bp.route('/<int:doctor_id>', methods=['GET'])
@login_required
@role_required('superadmin')
def get_doctor(doctor_id):
    """Get single doctor details"""
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
                    u.avatar,
                    r.name as role
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.id = ? AND r.name IN ('doctor', 'superadmin')
            """, (doctor_id,))

            user = cursor.fetchone()

            if not user:
                return jsonify({'error': 'Doctor not found'}), 404

            # Get current shift
            cursor.execute("""
                SELECT s.name as shift_name
                FROM staff_shifts ss
                JOIN shifts s ON ss.shift_id = s.id
                WHERE ss.staff_id = ? AND ss.is_current = 1
            """, (doctor_id,))
            shift = cursor.fetchone()

            # Get work days
            cursor.execute("""
                SELECT wd.name
                FROM staff_schedule ss
                JOIN work_days wd ON ss.day_id = wd.id
                WHERE ss.staff_id = ? AND ss.is_working = 1
                ORDER BY wd.day_number
            """, (doctor_id,))
            work_days_rows = cursor.fetchall()
            work_days = [row['name'] for row in work_days_rows]

            doctor = {
                'id': user['id'],
                'employee_id': user['employee_id'],
                'firstName': user['first_name'],
                'lastName': user['last_name'],
                'email': user['email'],
                'phone': user['phone'],
                'license': user['license_number'] or '',
                'specialty': user['specialization'] or 'General Dentistry',
                'qualifications': user['qualifications'] or '',
                'experience': user['experience_years'] or 0,
                'date_joined': user['date_joined'].strftime('%Y-%m-%d') if user['date_joined'] else '',
                'status': user['status'],
                'shift': shift['shift_name'] if shift else 'morning',
                'workDays': work_days,
                'emergencyName': user['emergency_contact_name'] or '',
                'emergencyPhone': user['emergency_contact_phone'] or ''
            }

        db.close()
        return jsonify({'success': True, 'doctor': doctor}), 200

    except Exception as e:
        print(f"Get doctor error: {e}")
        return jsonify({'error': 'Failed to fetch doctor'}), 500


# =========================================
# Create Doctor
# =========================================

@doctors_bp.route('/', methods=['POST'])
@login_required
@role_required('superadmin')
def create_doctor():
    """Create a new doctor"""
    try:
        data = request.get_json()

        # Generate employee ID
        import random
        employee_id = f"DOC{random.randint(1000, 9999)}"

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        # Hash password (default password)
        from werkzeug.security import generate_password_hash
        default_password = generate_password_hash("doctor123")

        with db.cursor() as cursor:
            # Get doctor role id
            cursor.execute("SELECT id FROM roles WHERE name = 'doctor'")
            role = cursor.fetchone()

            if not role:
                return jsonify({'error': 'Doctor role not found'}), 500

            # Insert new doctor
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
                data.get('qualifications'),
                data.get('experience'),
                data.get('status', 'active'),
                data.get('emergencyName'),
                data.get('emergencyPhone')
            ))

            doctor_id = cursor.lastrowid

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
                """, (doctor_id, shift['id']))

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
                    """, (doctor_id, day['id']))

            # Log creation
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'CREATE', 'users', ?, ?)
            """, (session['user_id'], doctor_id, json.dumps(data)))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': 'Doctor created successfully',
            'doctor_id': doctor_id
        }), 201

    except Exception as e:
        print(f"Create doctor error: {e}")
        return jsonify({'error': 'Failed to create doctor'}), 500


# =========================================
# Update Doctor
# =========================================

@doctors_bp.route('/<int:doctor_id>', methods=['PUT'])
@login_required
@role_required('superadmin')
def update_doctor(doctor_id):
    """Update doctor details"""
    try:
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if doctor exists
            cursor.execute("""
                SELECT id FROM users WHERE id = ?
            """, (doctor_id,))
            if not cursor.fetchone():
                return jsonify({'error': 'Doctor not found'}), 404

            # Update doctor basic info
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
                data.get('qualifications'),
                data.get('experience'),
                data.get('status', 'active'),
                data.get('emergencyName'),
                data.get('emergencyPhone'),
                doctor_id
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
                """, (doctor_id,))

                # Add new shift
                cursor.execute("""
                    INSERT INTO staff_shifts (staff_id, shift_id, effective_from, is_current)
                    VALUES (?, ?, date('now'), 1)
                """, (doctor_id, shift['id']))

            # Update schedule
            work_days = data.get('workDays', [])

            # First, deactivate all days
            cursor.execute("""
                UPDATE staff_schedule SET is_working = 0
                WHERE staff_id = ?
            """, (doctor_id,))

            # Then activate selected days
            for day_name in work_days:
                cursor.execute(
                    "SELECT id FROM work_days WHERE name = ?", (day_name,))
                day = cursor.fetchone()
                if day:
                    # Check if record exists
                    cursor.execute("""
                        SELECT id FROM staff_schedule WHERE staff_id = ? AND day_id = ?
                    """, (doctor_id, day['id']))
                    existing = cursor.fetchone()

                    if existing:
                        cursor.execute("""
                            UPDATE staff_schedule SET is_working = 1, updated_at = datetime('now')
                            WHERE staff_id = ? AND day_id = ?
                        """, (doctor_id, day['id']))
                    else:
                        cursor.execute("""
                            INSERT INTO staff_schedule (staff_id, day_id, is_working)
                            VALUES (?, ?, 1)
                        """, (doctor_id, day['id']))

            # Log update
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE', 'users', ?, ?)
            """, (session['user_id'], doctor_id, json.dumps(data)))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': 'Doctor updated successfully'
        }), 200

    except Exception as e:
        print(f"Update doctor error: {e}")
        return jsonify({'error': 'Failed to update doctor'}), 500


# =========================================
# Delete Doctor
# =========================================

@doctors_bp.route('/<int:doctor_id>', methods=['DELETE'])
@login_required
@role_required('superadmin')
def delete_doctor(doctor_id):
    """Delete a doctor"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if doctor has appointments
            cursor.execute("""
                SELECT COUNT(*) as count FROM appointments WHERE doctor_id = ?
            """, (doctor_id,))
            appointments = cursor.fetchone()

            if appointments['count'] > 0:
                # Instead of deleting, mark as inactive
                cursor.execute("""
                    UPDATE users SET status = 'inactive', updated_at = datetime('now')
                    WHERE id = ?
                """, (doctor_id,))
                message = "Doctor marked as inactive (had existing appointments)"
            else:
                # Delete doctor and related records
                cursor.execute(
                    "DELETE FROM staff_schedule WHERE staff_id = ?", (doctor_id,))
                cursor.execute(
                    "DELETE FROM staff_shifts WHERE staff_id = ?", (doctor_id,))
                cursor.execute("DELETE FROM users WHERE id = ?", (doctor_id,))
                message = "Doctor deleted successfully"

            # Log deletion
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id)
                VALUES (?, 'DELETE', 'users', ?)
            """, (session['user_id'], doctor_id))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': message
        }), 200

    except Exception as e:
        print(f"Delete doctor error: {e}")
        return jsonify({'error': 'Failed to delete doctor'}), 500


# =========================================
# Get Doctor Schedule for Today
# =========================================

@doctors_bp.route('/schedule/today', methods=['GET'])
@login_required
@role_required('superadmin')
def get_today_schedule():
    """Get today's schedule for all doctors"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        schedule = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    u.id,
                    u.first_name,
                    u.last_name,
                    u.specialization,
                    a.id as appointment_id,
                    a.start_time,
                    a.end_time,
                    a.status,
                    a.room,
                    p.first_name as patient_first,
                    p.last_name as patient_last,
                    COUNT(DISTINCT a.id) as patient_count
                FROM users u
                LEFT JOIN appointments a ON u.id = a.doctor_id 
                    AND DATE(a.appointment_date) = date('now')
                LEFT JOIN patients p ON a.patient_id = p.id
                WHERE u.role_id IN (SELECT id FROM roles WHERE name IN ('doctor', 'superadmin'))
                GROUP BY u.id, a.id, p.id
                ORDER BY u.last_name, a.start_time
            """)

            results = cursor.fetchall()

            # Group by doctor
            doctors_dict = {}
            for row in results:
                doctor_id = row['id']
                if doctor_id not in doctors_dict:
                    doctors_dict[doctor_id] = {
                        'id': doctor_id,
                        'name': f"Dr. {row['first_name']} {row['last_name']}",
                        'specialty': row['specialization'] or 'General Dentistry',
                        'room': row['room'] or 'TBD',
                        'patients': []
                    }

                if row['appointment_id']:
                    time_str = ""
                    if row['start_time']:
                        if isinstance(row['start_time'], (datetime, time)):
                            time_str = row['start_time'].strftime('%I:%M %p')
                        else:
                            time_str = str(row['start_time'])
                    doctors_dict[doctor_id]['patients'].append({
                        'time': time_str,
                        'patient': f"{row['patient_first']} {row['patient_last']}" if row['patient_first'] else '',
                        'status': row['status']
                    })

            # Format for display
            for doctor in doctors_dict.values():
                schedule.append({
                    'id': doctor['id'],
                    'name': doctor['name'],
                    'specialty': doctor['specialty'],
                    'time': doctor['patients'][0]['time'] if doctor['patients'] else 'No appointments',
                    'patients': len(doctor['patients']),
                    'status': 'On Duty',
                    'room': doctor['room']
                })

        db.close()
        return jsonify({'success': True, 'schedule': schedule}), 200

    except Exception as e:
        print(f"Get schedule error: {e}")
        return jsonify({'error': 'Failed to fetch schedule'}), 500


# =========================================
# Get Doctor Performance Metrics
# =========================================

@doctors_bp.route('/performance', methods=['GET'])
@login_required
@role_required('superadmin')
def get_performance_metrics():
    """Get performance metrics for all doctors"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        performance = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    u.id,
                    u.first_name,
                    u.last_name,
                    u.specialization,
                    COUNT(DISTINCT a.id) as procedures,
                    COUNT(DISTINCT a.patient_id) as patients_mtd,
                    COALESCE(SUM(i.total), 0) as revenue,
                    COALESCE(AVG(CASE WHEN a.status = 'completed' THEN 1 ELSE 0 END) * 100, 0) as completion_rate
                FROM users u
                LEFT JOIN appointments a ON u.id = a.doctor_id 
                    AND CAST(strftime('%m', a.appointment_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER)
                    AND CAST(strftime('%Y', a.appointment_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
                LEFT JOIN invoices i ON a.id = i.appointment_id
                WHERE u.role_id IN (SELECT id FROM roles WHERE name IN ('doctor', 'superadmin'))
                GROUP BY u.id
                ORDER BY revenue DESC
            """)

            results = cursor.fetchall()

            for row in results:
                performance.append({
                    'id': row['id'],
                    'name': f"Dr. {row['first_name']} {row['last_name']}",
                    'patientsMTD': row['patients_mtd'] or 0,
                    'procedures': row['procedures'] or 0,
                    'revenue': float(row['revenue'] or 0),
                    'completion_rate': round(row['completion_rate'], 1),
                    'satisfaction': 95,
                    'efficiency': round(row['completion_rate'], 1)
                })

        db.close()
        return jsonify({'success': True, 'performance': performance}), 200

    except Exception as e:
        print(f"Get performance error: {e}")
        return jsonify({'error': 'Failed to fetch performance metrics'}), 500


# =========================================
# Get Dashboard Stats
# =========================================

@doctors_bp.route('/stats', methods=['GET'])
@login_required
@role_required('superadmin')
def get_doctor_stats():
    """Get doctor-related statistics for dashboard"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        stats = {}

        with db.cursor() as cursor:
            # Total doctors (including superadmin if they have doctor role)
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE r.name IN ('doctor', 'superadmin')
            """)
            stats['total_doctors'] = cursor.fetchone()['total']

            # Active doctors
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE r.name IN ('doctor', 'superadmin') AND u.status = 'active'
            """)
            stats['active_doctors'] = cursor.fetchone()['total']

            # On leave doctors
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE r.name IN ('doctor', 'superadmin') AND u.status = 'on-leave'
            """)
            stats['on_leave'] = cursor.fetchone()['total']

            # Suspended doctors
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE r.name IN ('doctor', 'superadmin') AND u.status = 'suspended'
            """)
            stats['suspended'] = cursor.fetchone()['total']

            # Today's appointments
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM appointments a
                WHERE DATE(a.appointment_date) = date('now')
                AND a.doctor_id IS NOT NULL
            """)
            stats['today_appointments'] = cursor.fetchone()['total']

            # Average rating (placeholder)
            stats['avg_rating'] = 4.8

            # Calculate avg appointments per doctor
            if stats['active_doctors'] > 0:
                stats['avg_per_doctor'] = round(
                    stats['today_appointments'] / stats['active_doctors'], 1)
            else:
                stats['avg_per_doctor'] = 0

        db.close()
        return jsonify({'success': True, 'stats': stats}), 200

    except Exception as e:
        print(f"Get stats error: {e}")
        return jsonify({'error': 'Failed to fetch statistics'}), 500
