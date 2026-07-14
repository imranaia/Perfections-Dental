import sqlite3
# =========================================
# Perfections Dental Services
# SuperAdmin Dashboard Module - v1.0
# =========================================

from config import Config
from db import get_db
from auth import login_required, role_required
from flask import Blueprint, jsonify, session, request
from datetime import datetime, timedelta
import json
import os

# Import from parent directory using absolute import
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Create superadmin blueprint
superadmin_bp = Blueprint('superadmin', __name__, url_prefix='/api/superadmin')



# =========================================
# Dashboard Statistics
# =========================================


@superadmin_bp.route('/dashboard/stats', methods=['GET'])
@login_required
@role_required('superadmin')
def get_dashboard_stats():
    """Get comprehensive dashboard statistics for superadmin"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        stats = {}

        with db.cursor() as cursor:
            # Total staff (excluding superadmin)
            cursor.execute("""
                SELECT COUNT(*) as total 
                FROM users 
                WHERE role_id != (SELECT id FROM roles WHERE name = 'superadmin')
                AND status = 'active'
            """)
            stats['total_staff'] = cursor.fetchone()['total']

            # Total patients
            cursor.execute(
                "SELECT COUNT(*) as total FROM patients WHERE status = 'active'")
            stats['total_patients'] = cursor.fetchone()['total']

            # Today's appointments
            cursor.execute("""
                SELECT COUNT(*) as total 
                FROM appointments 
                WHERE DATE(appointment_date) = date('now')
                AND status NOT IN ('cancelled')
            """)
            stats['today_appointments'] = cursor.fetchone()['total']

            # Monthly revenue
            cursor.execute("""
                SELECT COALESCE(SUM(total), 0) as total 
                FROM invoices 
                WHERE CAST(strftime('%m', invoice_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER)
                AND CAST(strftime('%Y', invoice_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
                AND status = 'paid'
            """)
            stats['monthly_revenue'] = float(cursor.fetchone()['total'])

            # Low stock alerts
            cursor.execute("""
                SELECT COUNT(*) as total 
                FROM inventory_items 
                WHERE current_stock <= min_threshold 
                AND is_active = 1
            """)
            stats['low_stock_alerts'] = cursor.fetchone()['total']

            # Staff change this month
            cursor.execute("""
                SELECT COUNT(*) as total 
                FROM users 
                WHERE role_id != (SELECT id FROM roles WHERE name = 'superadmin')
                AND CAST(strftime('%m', created_at) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER)
                AND CAST(strftime('%Y', created_at) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
            """)
            stats['staff_change'] = cursor.fetchone()['total']

            # Appointments change vs yesterday
            cursor.execute("""
                SELECT 
                    COUNT(CASE WHEN DATE(appointment_date) = date('now') THEN 1 END) as today,
                    COUNT(CASE WHEN DATE(appointment_date) = date(date('now'), '-1 days') THEN 1 END) as yesterday
                FROM appointments
                WHERE status NOT IN ('cancelled')
            """)
            appt_counts = cursor.fetchone()
            if appt_counts['yesterday'] > 0:
                stats['appointments_change'] = round(
                    ((appt_counts['today'] - appt_counts['yesterday']) / appt_counts['yesterday']) * 100, 1)
            else:
                stats['appointments_change'] = 100 if appt_counts['today'] > 0 else 0

            # Revenue change vs last month
            cursor.execute("""
                SELECT 
                    COALESCE(SUM(CASE WHEN CAST(strftime('%m', invoice_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER) THEN total END), 0) as this_month,
                    COALESCE(SUM(CASE WHEN CAST(strftime('%m', invoice_date) AS INTEGER) = CAST(strftime('%m', date(date('now'), '-1 months')) AS INTEGER) THEN total END), 0) as last_month
                FROM invoices 
                WHERE CAST(strftime('%Y', invoice_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
                AND status = 'paid'
            """)
            revenue_counts = cursor.fetchone()
            if revenue_counts['last_month'] > 0:
                stats['revenue_change'] = round(
                    ((revenue_counts['this_month'] - revenue_counts['last_month']) / revenue_counts['last_month']) * 100, 1)
            else:
                stats['revenue_change'] = 100 if revenue_counts['this_month'] > 0 else 0

            # Pending approvals (new staff registrations)
            cursor.execute("""
                SELECT COUNT(*) as total 
                FROM users 
                WHERE status = 'pending' 
                AND role_id != (SELECT id FROM roles WHERE name = 'superadmin')
            """)
            stats['pending_approvals'] = cursor.fetchone()['total']

            # Today's check-ins
            cursor.execute("""
                SELECT COUNT(*) as total 
                FROM appointments 
                WHERE DATE(appointment_date) = date('now') 
                AND status IN ('checked_in', 'waiting', 'in_progress')
            """)
            stats['today_checkins'] = cursor.fetchone()['total']

            # Completed appointments this month
            cursor.execute("""
                SELECT COUNT(*) as total 
                FROM appointments 
                WHERE status = 'completed'
                AND CAST(strftime('%m', appointment_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER)
                AND CAST(strftime('%Y', appointment_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
            """)
            stats['completed_appointments'] = cursor.fetchone()['total']

            # Total services
            cursor.execute(
                "SELECT COUNT(*) as total FROM services WHERE is_active = TRUE")
            stats['total_services'] = cursor.fetchone()['total']

        db.close()
        return jsonify({'success': True, 'stats': stats}), 200

    except Exception as e:
        print(f"Dashboard stats error: {e}")
        return jsonify({'error': 'Failed to fetch dashboard stats'}), 500

# =========================================
# Recent Activities
# =========================================


@superadmin_bp.route('/dashboard/activities', methods=['GET'])
@login_required
@role_required('superadmin')
def get_recent_activities():
    """Get recent activities across the system"""
    try:
        limit = request.args.get('limit', 10, type=int)
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        activities = []

        with db.cursor() as cursor:
            # Get recent patient registrations
            cursor.execute("""
                SELECT 
                    'patient_registration' as type,
                    ('New patient registered: ' || first_name || ' ' || last_name) as title,
                    created_at,
                    'fas fa-user-plus' as icon,
                    'success' as badge_type,
                    'New Patient' as badge_text,
                    created_at as activity_date
                FROM patients
                ORDER BY created_at DESC
                LIMIT 3
            """)
            activities.extend(cursor.fetchall())

            # Get recent payments
            cursor.execute("""
                SELECT 
                    'payment' as type,
                    ('Payment of ₦' || printf('%.0f', p.amount) || ' received from ' || pt.first_name || ' ' || pt.last_name) as title,
                    p.created_at,
                    'fas fa-credit-card' as icon,
                    'success' as badge_type,
                    'Payment' as badge_text,
                    p.created_at as activity_date
                FROM payments p
                JOIN invoices i ON p.invoice_id = i.id
                JOIN patients pt ON i.patient_id = pt.id
                ORDER BY p.created_at DESC
                LIMIT 3
            """)
            activities.extend(cursor.fetchall())

            # Get low stock alerts
            cursor.execute("""
                SELECT 
                    'low_stock' as type,
                    ('Low stock alert: ' || name || ' (Only ' || current_stock || ' left)') as title,
                    updated_at as created_at,
                    'fas fa-exclamation-triangle' as icon,
                    'warning' as badge_type,
                    'Low Stock' as badge_text,
                    updated_at as activity_date
                FROM inventory_items
                WHERE current_stock <= min_threshold 
                AND is_active = 1
                ORDER BY updated_at DESC
                LIMIT 2
            """)
            activities.extend(cursor.fetchall())

            # Get new staff registrations
            cursor.execute("""
                SELECT 
                    'staff_registration' as type,
                    ('New staff: ' || u.first_name || ' ' || u.last_name || ' (' || r.name || ')') as title,
                    u.created_at,
                    'fas fa-user-check' as icon,
                    'info' as badge_type,
                    'New Staff' as badge_text,
                    u.created_at as activity_date
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.role_id != (SELECT id FROM roles WHERE name = 'superadmin')
                ORDER BY u.created_at DESC
                LIMIT 2
            """)
            activities.extend(cursor.fetchall())

            # Get appointment completions
            cursor.execute("""
                SELECT 
                    'appointment' as type,
                    ('Appointment completed: ' || p.first_name || ' ' || p.last_name || ' with Dr. ' || d.first_name || ' ' || d.last_name) as title,
                    a.updated_at as created_at,
                    'fas fa-calendar-check' as icon,
                    'success' as badge_type,
                    'Completed' as badge_text,
                    a.updated_at as activity_date
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                JOIN users d ON a.doctor_id = d.id
                WHERE a.status = 'completed'
                ORDER BY a.updated_at DESC
                LIMIT 2
            """)
            activities.extend(cursor.fetchall())

            # Get prescription creations
            cursor.execute("""
                SELECT 
                    'prescription' as type,
                    ('New prescription #' || pr.prescription_number || ' for ' || p.first_name || ' ' || p.last_name) as title,
                    pr.created_at,
                    'fas fa-prescription' as icon,
                    'info' as badge_type,
                    'Prescription' as badge_text,
                    pr.created_at as activity_date
                FROM prescriptions pr
                JOIN patients p ON pr.patient_id = p.id
                ORDER BY pr.created_at DESC
                LIMIT 2
            """)
            activities.extend(cursor.fetchall())

        db.close()

        # Sort by date and limit (convert to list if tuple)
        activities_list = list(activities)
        activities_list.sort(key=lambda x: x['activity_date'], reverse=True)
        activities_list = activities_list[:limit]

        # Format dates for display
        for activity in activities_list:
            if activity.get('created_at'):
                if hasattr(activity['created_at'], 'strftime'):
                    activity['created_at'] = activity['created_at'].strftime(
                        '%Y-%m-%d %H:%M:%S')

        return jsonify({'success': True, 'activities': activities_list}), 200

    except Exception as e:
        print(f"Recent activities error: {e}")
        return jsonify({'error': 'Failed to fetch recent activities'}), 500

# =========================================
# Chart Data
# =========================================


@superadmin_bp.route('/dashboard/charts', methods=['GET'])
@login_required
@role_required('superadmin')
def get_chart_data():
    """Get chart data for visualizations"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        revenue_data = {'labels': [], 'values': []}
        appointment_data = {'labels': [], 'values': [], 'colors': []}

        with db.cursor() as cursor:
            # Get last 30 days revenue from paid invoices
            for i in range(29, -1, -1):
                date = datetime.now() - timedelta(days=i)
                date_str = date.strftime('%Y-%m-%d')
                display_date = date.strftime('%a')
                revenue_data['labels'].append(display_date)

                # Get total for this date from paid invoices
                cursor.execute("""
                    SELECT COALESCE(SUM(total), 0) as daily_total
                    FROM invoices
                    WHERE DATE(invoice_date) = ? 
                    AND status IN ('paid', 'partial')
                """, (date_str,))
                daily_total = cursor.fetchone()['daily_total']
                revenue_data['values'].append(float(daily_total))

                # Debug print
                print(f"Date: {date_str}, Revenue: {float(daily_total)}")

            # Get appointment distribution by status for current month
            cursor.execute("""
                SELECT 
                    status,
                    COUNT(*) as count
                FROM appointments
                WHERE CAST(strftime('%m', appointment_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER)
                AND CAST(strftime('%Y', appointment_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
                GROUP BY status
                ORDER BY count DESC
            """)

            status_colors = {
                'scheduled': '#0066cc',
                'checked_in': '#34c759',
                'waiting': '#ff9500',
                'in_progress': '#5856d6',
                'completed': '#34c759',
                'cancelled': '#ff3b30',
                'no_show': '#ff3b30'
            }

            results = cursor.fetchall()
            if results:
                for row in results:
                    status_display = row['status'].replace('_', ' ').title()
                    appointment_data['labels'].append(status_display)
                    appointment_data['values'].append(row['count'])
                    appointment_data['colors'].append(
                        status_colors.get(row['status'], '#6c757d'))
            else:
                # If no data, show placeholder
                appointment_data['labels'].append('No Data')
                appointment_data['values'].append(1)
                appointment_data['colors'].append('#e9ecef')

        db.close()

        return jsonify({
            'success': True,
            'revenue_data': revenue_data,
            'appointment_data': appointment_data
        }), 200

    except Exception as e:
        print(f"Chart data error: {e}")
        return jsonify({'error': 'Failed to fetch chart data'}), 500
