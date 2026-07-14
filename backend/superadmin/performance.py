import sqlite3
# =========================================
# Perfections Dental Services
# Staff Performance Module - v1.0
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Create performance blueprint
performance_bp = Blueprint('performance', __name__,
                           url_prefix='/api/superadmin/performance')



def calculate_trend(current, previous):
    """Calculate percentage change between current and previous values"""
    # Convert to float to handle Decimal types
    try:
        current = float(current) if current is not None else 0
        previous = float(previous) if previous is not None else 0
    except (TypeError, ValueError):
        current = 0
        previous = 0

    if previous == 0:
        return 100 if current > 0 else 0
    return round(((current - previous) / previous) * 100, 1)


# =========================================
# Get KPI Overview
# =========================================

@performance_bp.route('/kpi', methods=['GET'])
@login_required
@role_required('superadmin')
def get_kpi_overview():
    """Get KPI overview for all staff"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        kpi = {}

        with db.cursor() as cursor:
            # Attendance Rate (based on user status)
            cursor.execute("""
                SELECT 
                    COUNT(CASE WHEN status = 'active' THEN 1 END) as active,
                    COUNT(*) as total
                FROM users
                WHERE role_id != (SELECT id FROM roles WHERE name = 'superadmin')
            """)
            attendance = cursor.fetchone()
            total_staff = attendance['total'] if attendance['total'] else 1
            kpi['attendance_rate'] = round(
                (attendance['active'] / total_staff * 100), 1) if total_staff > 0 else 0
            kpi['attendance_trend'] = calculate_trend(
                kpi['attendance_rate'], 96)

            # Average Rating (placeholder)
            kpi['avg_rating'] = 4.8
            kpi['rating_trend'] = 0.2

            # Average procedures per staff
            cursor.execute("""
                SELECT 
                    COUNT(DISTINCT a.id) as total_procedures,
                    COUNT(DISTINCT u.id) as total_staff
                FROM users u
                LEFT JOIN appointments a ON u.id = a.doctor_id 
                    AND CAST(strftime('%m', a.appointment_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER)
                    AND CAST(strftime('%Y', a.appointment_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
                WHERE u.role_id IN (SELECT id FROM roles WHERE name IN ('doctor', 'superadmin'))
            """)
            proc_data = cursor.fetchone()
            total_procedures = float(
                proc_data['total_procedures']) if proc_data['total_procedures'] else 0
            total_doctors = float(
                proc_data['total_staff']) if proc_data['total_staff'] else 1
            kpi['avg_procedures'] = round(
                total_procedures / total_doctors, 1) if total_doctors > 0 else 0
            kpi['procedures_trend'] = 12

            # Average revenue per staff
            cursor.execute("""
                SELECT 
                    COALESCE(SUM(i.total), 0) as total_revenue,
                    COUNT(DISTINCT u.id) as total_staff
                FROM users u
                LEFT JOIN invoices i ON u.id = i.created_by 
                    AND CAST(strftime('%m', i.invoice_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER)
                    AND CAST(strftime('%Y', i.invoice_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
                WHERE u.role_id IN (SELECT id FROM roles WHERE name IN ('reception', 'doctor'))
            """)
            rev_data = cursor.fetchone()
            total_revenue = float(
                rev_data['total_revenue']) if rev_data['total_revenue'] else 0
            total_staff_count = float(
                rev_data['total_staff']) if rev_data['total_staff'] else 1
            kpi['avg_revenue'] = total_revenue / \
                total_staff_count if total_staff_count > 0 else 0
            kpi['revenue_trend'] = 8

        db.close()
        return jsonify({'success': True, 'kpi': kpi}), 200

    except Exception as e:
        print(f"Get KPI error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch KPI data'}), 500


# =========================================
# Get Doctors Performance
# =========================================

@performance_bp.route('/doctors', methods=['GET'])
@login_required
@role_required('superadmin')
def get_doctors_performance():
    """Get performance metrics for doctors"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        doctors = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    u.id,
                    u.first_name,
                    u.last_name,
                    u.specialization,
                    u.experience_years,
                    (SELECT COUNT(DISTINCT patient_id) FROM appointments WHERE doctor_id = u.id) as total_patients,
                    (SELECT COALESCE(SUM(i.total), 0) FROM appointments a 
                     LEFT JOIN invoices i ON a.id = i.appointment_id 
                     WHERE a.doctor_id = u.id) as total_revenue,
                    (SELECT COUNT(DISTINCT a.id) FROM appointments a WHERE a.doctor_id = u.id) as total_procedures,
                    (SELECT COUNT(CASE WHEN a.status = 'completed' THEN 1 END) FROM appointments a WHERE a.doctor_id = u.id) as completed_appointments,
                    (SELECT COUNT(CASE WHEN a.status = 'completed' THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) FROM appointments a WHERE a.doctor_id = u.id) as completion_rate
                FROM users u
                WHERE u.role_id IN (SELECT id FROM roles WHERE name IN ('doctor', 'superadmin'))
                ORDER BY total_revenue DESC
            """)

            results = cursor.fetchall()

            for idx, row in enumerate(results):
                # Convert to float to handle Decimal types
                completion = float(row['completion_rate']
                                   ) if row['completion_rate'] else 0
                rating = 4.0 + (completion / 100) * 1
                rating = min(round(rating, 1), 5.0)

                # Get previous month revenue for trend
                cursor.execute("""
                    SELECT COALESCE(SUM(i.total), 0) as revenue
                    FROM appointments a
                    LEFT JOIN invoices i ON a.id = i.appointment_id
                    WHERE a.doctor_id = ?
                    AND CAST(strftime('%m', a.appointment_date) AS INTEGER) = CAST(strftime('%m', date(date('now'), '-1 months')) AS INTEGER)
                    AND CAST(strftime('%Y', a.appointment_date) AS INTEGER) = CAST(strftime('%Y', date(date('now'), '-1 months')) AS INTEGER)
                """, (row['id'],))
                prev_revenue = cursor.fetchone()
                prev_revenue_value = float(
                    prev_revenue['revenue']) if prev_revenue['revenue'] else 0

                total_revenue = float(
                    row['total_revenue']) if row['total_revenue'] else 0
                trend = calculate_trend(total_revenue, prev_revenue_value)

                doctors.append({
                    'id': row['id'],
                    'name': f"Dr. {row['first_name']} {row['last_name']}",
                    'role': 'Doctor',
                    'specialty': row['specialization'] or 'General Dentistry',
                    'patients': int(row['total_patients']) if row['total_patients'] else 0,
                    'revenue': total_revenue,
                    'procedures': int(row['total_procedures']) if row['total_procedures'] else 0,
                    'rating': rating,
                    'ratingStars': '★' * int(rating) + '☆' * (5 - int(rating)),
                    'trend': abs(trend),
                    'trend_up': trend >= 0,
                    'rank': idx + 1
                })

        db.close()
        return jsonify({'success': True, 'doctors': doctors}), 200

    except Exception as e:
        print(f"Get doctors performance error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch doctors performance'}), 500


# =========================================
# Get Nurses Performance
# =========================================

@performance_bp.route('/nurses', methods=['GET'])
@login_required
@role_required('superadmin')
def get_nurses_performance():
    """Get performance metrics for nurses"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        nurses = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    u.id,
                    u.first_name,
                    u.last_name,
                    u.specialization,
                    u.experience_years,
                    (SELECT COUNT(DISTINCT ass.id) FROM assists ass WHERE ass.nurse_id = u.id) as total_assists,
                    (SELECT COUNT(DISTINCT t.id) FROM tasks t WHERE t.assigned_to = u.id) as total_tasks,
                    (SELECT COUNT(CASE WHEN t.status = 'completed' THEN 1 END) FROM tasks t WHERE t.assigned_to = u.id) as completed_tasks
                FROM users u
                WHERE u.role_id = (SELECT id FROM roles WHERE name = 'nurse')
                ORDER BY total_assists DESC
            """)

            results = cursor.fetchall()

            for idx, row in enumerate(results):
                # Calculate independent tasks count
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM tasks
                    WHERE assigned_to = ? AND status = 'completed'
                    AND task_name NOT LIKE '%%assist%%' AND task_name NOT LIKE '%%Assist%%'
                """, (row['id'],))
                independent = cursor.fetchone()
                independent_count = int(
                    independent['count']) if independent['count'] else 0

                # Calculate task completion rate
                total_tasks = int(row['total_tasks']
                                  ) if row['total_tasks'] else 0
                completed_tasks = int(
                    row['completed_tasks']) if row['completed_tasks'] else 0
                completion_rate = (completed_tasks /
                                   total_tasks * 100) if total_tasks > 0 else 0

                # Calculate rating
                rating = 4.0 + (completion_rate / 100) * 1
                rating = min(round(rating, 1), 5.0)

                # Calculate trend based on experience
                trend = 5 + (int(row['experience_years'])
                             if row['experience_years'] else 0) * 2
                trend = min(trend, 15)

                nurses.append({
                    'id': row['id'],
                    'name': f"{row['first_name']} {row['last_name']}",
                    'role': 'Nurse',
                    'specialty': row['specialization'] or 'General Nurse',
                    'assists': int(row['total_assists']) if row['total_assists'] else 0,
                    'independent': independent_count,
                    'task_rate': round(completion_rate, 1),
                    'rating': rating,
                    'ratingStars': '★' * int(rating) + '☆' * (5 - int(rating)),
                    'trend': trend,
                    'trend_up': trend >= 0,
                    'rank': idx + 1
                })

        db.close()
        return jsonify({'success': True, 'nurses': nurses}), 200

    except Exception as e:
        print(f"Get nurses performance error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch nurses performance'}), 500


# =========================================
# Get Reception Performance
# =========================================

@performance_bp.route('/reception', methods=['GET'])
@login_required
@role_required('superadmin')
def get_reception_performance():
    """Get performance metrics for reception staff"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        reception = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    u.id,
                    u.first_name,
                    u.last_name,
                    u.specialization,
                    (SELECT COUNT(DISTINCT a.id) FROM appointments a WHERE a.created_by = u.id AND DATE(a.created_at) >= date(date('now'), '-30 days')) as total_checkins,
                    (SELECT COUNT(DISTINCT p.id) FROM payments p WHERE p.received_by = u.id) as total_payments,
                    (SELECT COALESCE(SUM(p.amount), 0) FROM payments p WHERE p.received_by = u.id) as total_processed
                FROM users u
                WHERE u.role_id = (SELECT id FROM roles WHERE name = 'reception')
                ORDER BY total_processed DESC
            """)

            results = cursor.fetchall()

            for idx, row in enumerate(results):
                # Convert to float for calculations
                processed = float(row['total_processed']
                                  ) if row['total_processed'] else 0
                rating = 4.5 + (processed / 1000000) * 0.3
                rating = min(round(rating, 1), 5.0)

                # Calculate trend
                checkins = int(row['total_checkins']
                               ) if row['total_checkins'] else 0
                trend = 5 + (checkins / 10) if checkins > 0 else 5
                trend = min(trend, 20)

                reception.append({
                    'id': row['id'],
                    'name': f"{row['first_name']} {row['last_name']}",
                    'role': row['specialization'] or 'Receptionist',
                    'checkins': checkins,
                    'payments': int(row['total_payments']) if row['total_payments'] else 0,
                    'processed': processed,
                    'rating': rating,
                    'ratingStars': '★' * int(rating) + '☆' * (5 - int(rating)),
                    'trend': trend,
                    'trend_up': trend >= 0,
                    'rank': idx + 1
                })

        db.close()
        return jsonify({'success': True, 'reception': reception}), 200

    except Exception as e:
        print(f"Get reception performance error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch reception performance'}), 500


# =========================================
# Get Department Comparison
# =========================================

@performance_bp.route('/comparison', methods=['GET'])
@login_required
@role_required('superadmin')
def get_department_comparison():
    """Get department performance comparison"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        comparison = []

        with db.cursor() as cursor:
            # Doctors average rating (based on completion rate)
            cursor.execute("""
                SELECT 
                    COALESCE(AVG(CASE WHEN a.status = 'completed' THEN 1 ELSE 0 END) * 100, 0) as completion_rate
                FROM appointments a
                WHERE a.doctor_id IS NOT NULL
                AND CAST(strftime('%m', a.appointment_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER)
                AND CAST(strftime('%Y', a.appointment_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
            """)
            doctors_current = cursor.fetchone()
            doctors_current_rating = round((float(
                doctors_current['completion_rate']) / 100) * 5, 1) if doctors_current and doctors_current['completion_rate'] else 4.8

            # Previous month
            cursor.execute("""
                SELECT 
                    COALESCE(AVG(CASE WHEN a.status = 'completed' THEN 1 ELSE 0 END) * 100, 0) as completion_rate
                FROM appointments a
                WHERE a.doctor_id IS NOT NULL
                AND CAST(strftime('%m', a.appointment_date) AS INTEGER) = CAST(strftime('%m', date(date('now'), '-1 months')) AS INTEGER)
                AND CAST(strftime('%Y', a.appointment_date) AS INTEGER) = CAST(strftime('%Y', date(date('now'), '-1 months')) AS INTEGER)
            """)
            doctors_prev = cursor.fetchone()
            doctors_prev_rating = round((float(
                doctors_prev['completion_rate']) / 100) * 5, 1) if doctors_prev and doctors_prev['completion_rate'] else 4.6

            doctors_trend = calculate_trend(
                doctors_current_rating, doctors_prev_rating)

            # Nurses average rating (from task completion)
            cursor.execute("""
                SELECT 
                    COALESCE(AVG(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) * 100, 0) as completion_rate
                FROM tasks t
                WHERE CAST(strftime('%m', t.created_at) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER)
                AND CAST(strftime('%Y', t.created_at) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
            """)
            nurses_current = cursor.fetchone()
            nurses_current_rating = round((float(
                nurses_current['completion_rate']) / 100) * 5, 1) if nurses_current and nurses_current['completion_rate'] else 4.7

            cursor.execute("""
                SELECT 
                    COALESCE(AVG(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) * 100, 0) as completion_rate
                FROM tasks t
                WHERE CAST(strftime('%m', t.created_at) AS INTEGER) = CAST(strftime('%m', date(date('now'), '-1 months')) AS INTEGER)
                AND CAST(strftime('%Y', t.created_at) AS INTEGER) = CAST(strftime('%Y', date(date('now'), '-1 months')) AS INTEGER)
            """)
            nurses_prev = cursor.fetchone()
            nurses_prev_rating = round((float(
                nurses_prev['completion_rate']) / 100) * 5, 1) if nurses_prev and nurses_prev['completion_rate'] else 4.5

            nurses_trend = calculate_trend(
                nurses_current_rating, nurses_prev_rating)

            # Reception average rating (from check-in efficiency)
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_checkins,
                    SUM(CASE WHEN a.status IN ('checked_in', 'completed') THEN 1 ELSE 0 END) as efficient
                FROM appointments a
                WHERE CAST(strftime('%m', a.appointment_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER)
                AND CAST(strftime('%Y', a.appointment_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
            """)
            reception_current = cursor.fetchone()
            total_checkins = int(
                reception_current['total_checkins']) if reception_current['total_checkins'] else 0
            efficient = int(
                reception_current['efficient']) if reception_current['efficient'] else 0
            reception_current_rating = round(
                (efficient / total_checkins * 5), 1) if total_checkins > 0 else 4.8

            cursor.execute("""
                SELECT 
                    COUNT(*) as total_checkins,
                    SUM(CASE WHEN a.status IN ('checked_in', 'completed') THEN 1 ELSE 0 END) as efficient
                FROM appointments a
                WHERE CAST(strftime('%m', a.appointment_date) AS INTEGER) = CAST(strftime('%m', date(date('now'), '-1 months')) AS INTEGER)
                AND CAST(strftime('%Y', a.appointment_date) AS INTEGER) = CAST(strftime('%Y', date(date('now'), '-1 months')) AS INTEGER)
            """)
            reception_prev = cursor.fetchone()
            prev_total = int(
                reception_prev['total_checkins']) if reception_prev['total_checkins'] else 0
            prev_efficient = int(
                reception_prev['efficient']) if reception_prev['efficient'] else 0
            reception_prev_rating = round(
                (prev_efficient / prev_total * 5), 1) if prev_total > 0 else 4.4

            reception_trend = calculate_trend(
                reception_current_rating, reception_prev_rating)

            comparison = [
                {
                    'department': 'Doctors',
                    'current': doctors_current_rating,
                    'previous': doctors_prev_rating,
                    'trend': abs(doctors_trend),
                    'trend_up': doctors_trend >= 0,
                    'percentage': round((doctors_current_rating / 5) * 100, 1)
                },
                {
                    'department': 'Nurses',
                    'current': nurses_current_rating,
                    'previous': nurses_prev_rating,
                    'trend': abs(nurses_trend),
                    'trend_up': nurses_trend >= 0,
                    'percentage': round((nurses_current_rating / 5) * 100, 1)
                },
                {
                    'department': 'Reception',
                    'current': reception_current_rating,
                    'previous': reception_prev_rating,
                    'trend': abs(reception_trend),
                    'trend_up': reception_trend >= 0,
                    'percentage': round((reception_current_rating / 5) * 100, 1)
                }
            ]

        db.close()
        return jsonify({'success': True, 'comparison': comparison}), 200

    except Exception as e:
        print(f"Get comparison error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch comparison'}), 500


# =========================================
# Get All Staff Performance (Combined)
# =========================================

@performance_bp.route('/all', methods=['GET'])
@login_required
@role_required('superadmin')
def get_all_staff_performance():
    """Get combined performance for all staff"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        all_staff = []

        with db.cursor() as cursor:
            # Get all staff with their roles
            cursor.execute("""
                SELECT 
                    u.id,
                    u.first_name,
                    u.last_name,
                    r.name as role,
                    u.specialization,
                    u.experience_years,
                    u.status
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE r.name IN ('doctor', 'nurse', 'reception')
                ORDER BY u.last_name
            """)

            staff_list = cursor.fetchall()

            for staff in staff_list:
                if staff['role'] == 'doctor':
                    # Get doctor metrics
                    cursor.execute("""
                        SELECT 
                            (SELECT COUNT(DISTINCT patient_id) FROM appointments WHERE doctor_id = ?) as patients,
                            (SELECT COALESCE(SUM(i.total), 0) FROM appointments a 
                             LEFT JOIN invoices i ON a.id = i.appointment_id 
                             WHERE a.doctor_id = ?) as revenue,
                            (SELECT COUNT(DISTINCT a.id) FROM appointments a WHERE a.doctor_id = ?) as procedures
                    """, (staff['id'], staff['id'], staff['id']))
                    metrics = cursor.fetchone()

                    rating = 4.8
                    rating_stars = '★★★★★'
                    trend = 12
                    trend_up = True

                elif staff['role'] == 'nurse':
                    # Get nurse metrics
                    cursor.execute("""
                        SELECT 
                            (SELECT COUNT(DISTINCT ass.id) FROM assists ass WHERE ass.nurse_id = ?) as assists,
                            (SELECT COUNT(DISTINCT t.id) FROM tasks t WHERE t.assigned_to = ?) as tasks,
                            (SELECT COUNT(CASE WHEN t.status = 'completed' THEN 1 END) FROM tasks t WHERE t.assigned_to = ?) as completed_tasks
                    """, (staff['id'], staff['id'], staff['id']))
                    metrics = cursor.fetchone()

                    rating = 4.7
                    rating_stars = '★★★★☆'
                    trend = 8
                    trend_up = True

                else:  # reception
                    # Get reception metrics
                    cursor.execute("""
                        SELECT 
                            (SELECT COUNT(DISTINCT a.id) FROM appointments a WHERE a.created_by = ?) as checkins,
                            (SELECT COUNT(DISTINCT p.id) FROM payments p WHERE p.received_by = ?) as payments,
                            (SELECT COALESCE(SUM(p.amount), 0) FROM payments p WHERE p.received_by = ?) as processed
                    """, (staff['id'], staff['id'], staff['id']))
                    metrics = cursor.fetchone()

                    rating = 4.8
                    rating_stars = '★★★★★'
                    trend = 15
                    trend_up = True

                # Convert Decimal values to float/int
                if metrics:
                    for key in metrics:
                        if metrics[key] is not None:
                            if isinstance(metrics[key], (int, float)):
                                pass
                            elif hasattr(metrics[key], 'quantize'):  # Decimal
                                metrics[key] = float(metrics[key])
                            elif isinstance(metrics[key], str) and metrics[key].isdigit():
                                metrics[key] = int(metrics[key])

                all_staff.append({
                    'id': staff['id'],
                    'name': f"{staff['first_name']} {staff['last_name']}",
                    'role': staff['role'].capitalize(),
                    'specialty': staff['specialization'] or 'General',
                    'metrics': metrics,
                    'rating': rating,
                    'ratingStars': rating_stars,
                    'trend': trend,
                    'trend_up': trend_up
                })

        db.close()
        return jsonify({'success': True, 'all_staff': all_staff}), 200

    except Exception as e:
        print(f"Get all staff error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch staff performance'}), 500
