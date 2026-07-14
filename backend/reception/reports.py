import sqlite3
# =========================================
# Perfections Dental Services
# Reception Reports Module - v1.0
# =========================================

from time import time

from config import Config
from db import get_db
from auth import login_required
from flask import Blueprint, jsonify, session, request, send_file
from datetime import datetime, timedelta
import json
import sys
import os
import csv
from io import StringIO, BytesIO
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Create reports blueprint
reports_bp = Blueprint('reception_reports', __name__,
                       url_prefix='/api/reception/reports')



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


def reception_required(f):
    """Decorator to require reception role"""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

        user_role = session.get('role')
        if user_role not in ['reception', 'superadmin']:
            return jsonify({'error': 'Access denied. Reception role required.'}), 403

        return f(*args, **kwargs)
    return decorated_function


# =========================================
# Get Daily Summary
# =========================================

@reports_bp.route('/daily-summary', methods=['GET'])
@login_required
@reception_required
def get_daily_summary():
    """Get daily summary for a specific date"""
    try:
        date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        summary = {}

        with db.cursor() as cursor:
            # Total appointments
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM appointments
                WHERE DATE(appointment_date) = ?
                AND status NOT IN ('cancelled')
            """, (date,))
            summary['total_appointments'] = cursor.fetchone()['total']

            # Completed appointments
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM appointments
                WHERE DATE(appointment_date) = ?
                AND status = 'completed'
            """, (date,))
            summary['completed_appointments'] = cursor.fetchone()['total']

            # Checked in
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM appointments
                WHERE DATE(appointment_date) = ?
                AND status = 'checked_in'
            """, (date,))
            summary['checked_in'] = cursor.fetchone()['total']

            # Waiting
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM appointments
                WHERE DATE(appointment_date) = ?
                AND status = 'waiting'
            """, (date,))
            summary['waiting'] = cursor.fetchone()['total']

            # No-shows
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM appointments
                WHERE DATE(appointment_date) = ?
                AND status = 'no_show'
            """, (date,))
            summary['no_shows'] = cursor.fetchone()['total']

            # Cancelled
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM appointments
                WHERE DATE(appointment_date) = ?
                AND status = 'cancelled'
            """, (date,))
            summary['cancelled'] = cursor.fetchone()['total']

            # Total revenue
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) as total
                FROM payments
                WHERE DATE(payment_date) = ?
            """, (date,))
            summary['total_revenue'] = float(cursor.fetchone()['total'])

            # Total transactions
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM payments
                WHERE DATE(payment_date) = ?
            """, (date,))
            summary['total_transactions'] = cursor.fetchone()['total']

            # Free services
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM payments
                WHERE DATE(payment_date) = ?
                AND payment_method = 'free'
            """, (date,))
            summary['free_services'] = cursor.fetchone()['total']

            # Payment methods breakdown
            cursor.execute("""
                SELECT 
                    payment_method,
                    COUNT(*) as count,
                    COALESCE(SUM(amount), 0) as total
                FROM payments
                WHERE DATE(payment_date) = ?
                GROUP BY payment_method
            """, (date,))
            summary['payment_methods'] = cursor.fetchall()

            # New patients
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM patients
                WHERE DATE(registration_date) = ?
            """, (date,))
            summary['new_patients'] = cursor.fetchone()['total']

        db.close()
        return jsonify({'success': True, 'summary': summary, 'date': date}), 200

    except Exception as e:
        print(f"Daily summary error: {e}")
        return jsonify({'error': 'Failed to fetch daily summary'}), 500


# =========================================
# Get Transaction Details
# =========================================

@reports_bp.route('/transactions', methods=['GET'])
@login_required
@reception_required
def get_transactions():
    """Get transaction details for a date range"""
    try:
        start_date = request.args.get(
            'start_date', datetime.now().strftime('%Y-%m-%d'))
        end_date = request.args.get(
            'end_date', datetime.now().strftime('%Y-%m-%d'))
        # daily, weekly, monthly, quarterly, yearly
        report_type = request.args.get('type', 'daily')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        transactions = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    p.id,
                    p.payment_date,
                    p.amount,
                    p.payment_method,
                    p.reference,
                    p.notes,
                    pt.id as patient_id,
                    pt.first_name as patient_first,
                    pt.last_name as patient_last,
                    pt.patient_number,
                    i.invoice_number,
                    i.status as invoice_status,
                    i.discount as invoice_discount,
                    u.first_name as received_by_first,
                    u.last_name as received_by_last
                FROM payments p
                JOIN invoices i ON p.invoice_id = i.id
                JOIN patients pt ON i.patient_id = pt.id
                JOIN users u ON p.received_by = u.id
                WHERE DATE(p.payment_date) BETWEEN ? AND ?
                ORDER BY p.payment_date DESC, p.id DESC
            """, (start_date, end_date))

            results = cursor.fetchall()

            subtotal = 0
            discounts = 0

            for row in results:
                discount = float(row['invoice_discount']
                                 ) if row['invoice_discount'] else 0
                discounts += discount

                amount = float(row['amount'])
                subtotal += amount + discount

                transactions.append({
                    'id': row['id'],
                    'payment_date': row['payment_date'].strftime('%I:%M %p') if row['payment_date'] else '',
                    'payment_date_full': row['payment_date'].strftime('%Y-%m-%d %H:%M:%S') if row['payment_date'] else '',
                    'patient_name': f"{row['patient_first']} {row['patient_last']}",
                    'patient_initials': f"{row['patient_first'][0]}{row['patient_last'][0]}",
                    'patient_id': row['patient_id'],
                    'patient_number': row['patient_number'],
                    'invoice_number': row['invoice_number'],
                    'amount': amount,
                    'discount': discount,
                    'payment_method': row['payment_method'].upper(),
                    'reference': row['reference'] or '-',
                    'status': row['invoice_status'],
                    'received_by': f"{row['received_by_first']} {row['received_by_last']}" if row['received_by_first'] else 'System'
                })

            total = sum(t['amount'] for t in transactions)

        db.close()

        return jsonify({
            'success': True,
            'transactions': transactions,
            'summary': {
                'subtotal': subtotal,
                'discounts': discounts,
                'total': total,
                'count': len(transactions)
            },
            'date_range': {
                'start': start_date,
                'end': end_date
            }
        }), 200

    except Exception as e:
        print(f"Get transactions error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch transactions'}), 500


# =========================================
# Get Financial Report
# =========================================

@reports_bp.route('/financial', methods=['GET'])
@login_required
@reception_required
def get_financial_report():
    """Get financial report for a date range"""
    try:
        # daily, weekly, monthly, quarterly, yearly
        period = request.args.get('period', 'daily')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        # Determine date range based on period
        today = datetime.now().date()
        if period == 'daily':
            start_date = today
            end_date = today
        elif period == 'weekly':
            start_date = today - timedelta(days=today.weekday())
            end_date = today
        elif period == 'monthly':
            start_date = today.replace(day=1)
            end_date = today
        elif period == 'quarterly':
            quarter_month = ((today.month - 1) // 3) * 3 + 1
            start_date = today.replace(month=quarter_month, day=1)
            end_date = today
        elif period == 'yearly':
            start_date = today.replace(month=1, day=1)
            end_date = today
        else:
            start_date = today
            end_date = today

        report = {}

        with db.cursor() as cursor:
            # Daily breakdown
            cursor.execute("""
                SELECT 
                    DATE(payment_date) as date,
                    COALESCE(SUM(amount), 0) as daily_total,
                    COUNT(*) as daily_count
                FROM payments
                WHERE DATE(payment_date) BETWEEN ? AND ?
                GROUP BY DATE(payment_date)
                ORDER BY date
            """, (start_date, end_date))

            daily_breakdown = cursor.fetchall()
            report['daily_breakdown'] = daily_breakdown

            # Payment methods summary
            cursor.execute("""
                SELECT 
                    payment_method,
                    COUNT(*) as count,
                    COALESCE(SUM(amount), 0) as total
                FROM payments
                WHERE DATE(payment_date) BETWEEN ? AND ?
                GROUP BY payment_method
            """, (start_date, end_date))

            report['payment_methods'] = cursor.fetchall()

            # Total revenue
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) as total,
                       COUNT(*) as count
                FROM payments
                WHERE DATE(payment_date) BETWEEN ? AND ?
            """, (start_date, end_date))
            totals = cursor.fetchone()
            report['total_revenue'] = float(totals['total'])
            report['total_transactions'] = totals['count']

            # Average transaction value
            if totals['count'] > 0:
                report['avg_transaction'] = report['total_revenue'] / \
                    totals['count']
            else:
                report['avg_transaction'] = 0

            # Free services count
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM payments
                WHERE DATE(payment_date) BETWEEN ? AND ?
                AND payment_method = 'free'
            """, (start_date, end_date))
            report['free_services'] = cursor.fetchone()['count']

            # Discounts total
            cursor.execute("""
                SELECT COALESCE(SUM(discount), 0) as total
                FROM invoices
                WHERE DATE(invoice_date) BETWEEN ? AND ?
                AND discount > 0
            """, (start_date, end_date))
            report['total_discounts'] = float(cursor.fetchone()['total'])

            # Top performing days
            cursor.execute("""
                SELECT 
                    DATE(payment_date) as date,
                    COALESCE(SUM(amount), 0) as total
                FROM payments
                WHERE DATE(payment_date) BETWEEN ? AND ?
                GROUP BY DATE(payment_date)
                ORDER BY total DESC
                LIMIT 5
            """, (start_date, end_date))
            report['top_days'] = cursor.fetchall()

        db.close()

        return jsonify({
            'success': True,
            'report': report,
            'period': period,
            'date_range': {
                'start': start_date.strftime('%Y-%m-%d'),
                'end': end_date.strftime('%Y-%m-%d')
            }
        }), 200

    except Exception as e:
        print(f"Financial report error: {e}")
        return jsonify({'error': 'Failed to fetch financial report'}), 500


# =========================================
# Get Appointment Summary Report
# =========================================

@reports_bp.route('/appointment-summary', methods=['GET'])
@login_required
@reception_required
def get_appointment_summary():
    """Get appointment summary report"""
    try:
        period = request.args.get('period', 'daily')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        # Determine date range
        today = datetime.now().date()
        if period == 'daily':
            start_date = today
            end_date = today
        elif period == 'weekly':
            start_date = today - timedelta(days=today.weekday())
            end_date = today
        elif period == 'monthly':
            start_date = today.replace(day=1)
            end_date = today
        elif period == 'quarterly':
            quarter_month = ((today.month - 1) // 3) * 3 + 1
            start_date = today.replace(month=quarter_month, day=1)
            end_date = today
        elif period == 'yearly':
            start_date = today.replace(month=1, day=1)
            end_date = today
        else:
            start_date = today
            end_date = today

        summary = {}

        with db.cursor() as cursor:
            # Status breakdown
            cursor.execute("""
                SELECT 
                    status,
                    COUNT(*) as count
                FROM appointments
                WHERE DATE(appointment_date) BETWEEN ? AND ?
                GROUP BY status
            """, (start_date, end_date))

            status_breakdown = cursor.fetchall()
            summary['status_breakdown'] = status_breakdown

            # Type breakdown (regular, emergency, nurse_only)
            cursor.execute("""
                SELECT 
                    type,
                    COUNT(*) as count
                FROM appointments
                WHERE DATE(appointment_date) BETWEEN ? AND ?
                GROUP BY type
            """, (start_date, end_date))

            type_breakdown = cursor.fetchall()
            summary['type_breakdown'] = type_breakdown

            # Peak hours
            cursor.execute("""
                SELECT 
                    CAST(strftime('%H', start_time) AS INTEGER) as hour,
                    COUNT(*) as count
                FROM appointments
                WHERE DATE(appointment_date) BETWEEN ? AND ?
                GROUP BY CAST(strftime('%H', start_time) AS INTEGER)
                ORDER BY hour
            """, (start_date, end_date))

            peak_hours = cursor.fetchall()
            summary['peak_hours'] = peak_hours

            # Total appointments
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM appointments
                WHERE DATE(appointment_date) BETWEEN ? AND ?
                AND status NOT IN ('cancelled')
            """, (start_date, end_date))
            summary['total'] = cursor.fetchone()['total']

            # Completed appointments
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM appointments
                WHERE DATE(appointment_date) BETWEEN ? AND ?
                AND status = 'completed'
            """, (start_date, end_date))
            summary['completed'] = cursor.fetchone()['total']

            # Cancelled appointments
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM appointments
                WHERE DATE(appointment_date) BETWEEN ? AND ?
                AND status = 'cancelled'
            """, (start_date, end_date))
            summary['cancelled'] = cursor.fetchone()['total']

            # No-shows
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM appointments
                WHERE DATE(appointment_date) BETWEEN ? AND ?
                AND status = 'no_show'
            """, (start_date, end_date))
            summary['no_shows'] = cursor.fetchone()['total']

            # Emergencies
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM appointments
                WHERE DATE(appointment_date) BETWEEN ? AND ?
                AND type = 'emergency'
            """, (start_date, end_date))
            summary['emergencies'] = cursor.fetchone()['total']

            # Nurse-only appointments
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM appointments
                WHERE DATE(appointment_date) BETWEEN ? AND ?
                AND type = 'nurse_only'
            """, (start_date, end_date))
            summary['nurse_only'] = cursor.fetchone()['total']

        db.close()

        return jsonify({
            'success': True,
            'summary': summary,
            'period': period,
            'date_range': {
                'start': start_date.strftime('%Y-%m-%d'),
                'end': end_date.strftime('%Y-%m-%d')
            }
        }), 200

    except Exception as e:
        print(f"Appointment summary error: {e}")
        return jsonify({'error': 'Failed to fetch appointment summary'}), 500


# =========================================
# Get Patient Demographics Report
# =========================================

@reports_bp.route('/patient-demographics', methods=['GET'])
@login_required
@reception_required
def get_patient_demographics():
    """Get patient demographics report"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        demographics = {}

        with db.cursor() as cursor:
            # Age groups
            cursor.execute("""
                SELECT 
                    CASE 
                        WHEN ((julianday(date('now')) - julianday(dob)) / 365.25) BETWEEN 0 AND 12 THEN '0-12 years'
                        WHEN ((julianday(date('now')) - julianday(dob)) / 365.25) BETWEEN 13 AND 25 THEN '13-25 years'
                        WHEN ((julianday(date('now')) - julianday(dob)) / 365.25) BETWEEN 26 AND 40 THEN '26-40 years'
                        WHEN ((julianday(date('now')) - julianday(dob)) / 365.25) BETWEEN 41 AND 60 THEN '41-60 years'
                        ELSE '60+ years'
                    END as age_group,
                    COUNT(*) as count
                FROM patients
                WHERE status = 'active'
                GROUP BY age_group
                ORDER BY 
                    CASE age_group
                        WHEN '0-12 years' THEN 1
                        WHEN '13-25 years' THEN 2
                        WHEN '26-40 years' THEN 3
                        WHEN '41-60 years' THEN 4
                        ELSE 5
                    END
            """)

            demographics['age_groups'] = cursor.fetchall()

            # Gender distribution
            cursor.execute("""
                SELECT 
                    gender,
                    COUNT(*) as count
                FROM patients
                WHERE status = 'active'
                GROUP BY gender
            """)

            demographics['gender'] = cursor.fetchall()

            # New vs returning patients (last 30 days)
            cursor.execute("""
                SELECT 
                    SUM(CASE WHEN registration_date >= date(date('now'), '-30 days') THEN 1 ELSE 0 END) as new_patients,
                    SUM(CASE WHEN registration_date < date(date('now'), '-30 days') THEN 1 ELSE 0 END) as returning_patients
                FROM patients
                WHERE status = 'active'
            """)

            patient_types = cursor.fetchone()
            demographics['patient_types'] = {
                'new': patient_types['new_patients'],
                'returning': patient_types['returning_patients']
            }

            # Total patients
            cursor.execute(
                "SELECT COUNT(*) as total FROM patients WHERE status = 'active'")
            demographics['total_patients'] = cursor.fetchone()['total']

        db.close()

        return jsonify({'success': True, 'demographics': demographics}), 200

    except Exception as e:
        print(f"Patient demographics error: {e}")
        return jsonify({'error': 'Failed to fetch patient demographics'}), 500


# =========================================
# Get Inventory Status Report
# =========================================

@reports_bp.route('/inventory-status', methods=['GET'])
@login_required
@reception_required
def get_inventory_status():
    """Get inventory status report"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        inventory = {}

        with db.cursor() as cursor:
            # Low stock items
            cursor.execute("""
                SELECT 
                    id,
                    name,
                    category,
                    current_stock,
                    min_threshold
                FROM inventory_items
                WHERE current_stock <= min_threshold
                AND is_active = 1
                ORDER BY (current_stock / min_threshold) ASC
            """)

            inventory['low_stock'] = cursor.fetchall()

            # Expiring soon items
            cursor.execute("""
                SELECT 
                    id,
                    name,
                    category,
                    expiry_date,
                    CAST(julianday(expiry_date) - julianday(date('now')) AS INTEGER) as days_left
                FROM inventory_items
                WHERE expiry_date BETWEEN date('now') AND date(date('now'), '+30 days')
                AND is_active = 1
                ORDER BY expiry_date ASC
            """)

            inventory['expiring_soon'] = cursor.fetchall()

            # Category breakdown
            cursor.execute("""
                SELECT 
                    category,
                    COUNT(*) as count,
                    SUM(current_stock) as total_stock
                FROM inventory_items
                WHERE is_active = 1
                GROUP BY category
            """)

            inventory['category_breakdown'] = cursor.fetchall()

            # Total items
            cursor.execute(
                "SELECT COUNT(*) as total FROM inventory_items WHERE is_active = TRUE")
            inventory['total_items'] = cursor.fetchone()['total']

            # Total stock value
            cursor.execute("""
                SELECT COALESCE(SUM(current_stock * price), 0) as total_value
                FROM inventory_items
                WHERE is_active = 1 AND price IS NOT NULL
            """)
            inventory['total_value'] = float(cursor.fetchone()['total_value'])

        db.close()

        return jsonify({'success': True, 'inventory': inventory}), 200

    except Exception as e:
        print(f"Inventory status error: {e}")
        return jsonify({'error': 'Failed to fetch inventory status'}), 500


# =========================================
# Get Staff Performance Report
# =========================================

@reports_bp.route('/staff-performance', methods=['GET'])
@login_required
@reception_required
def get_staff_performance():
    """Get staff performance report"""
    try:
        period = request.args.get('period', 'monthly')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        # Determine date range
        today = datetime.now().date()
        if period == 'daily':
            start_date = today
            end_date = today
        elif period == 'weekly':
            start_date = today - timedelta(days=today.weekday())
            end_date = today
        elif period == 'monthly':
            start_date = today.replace(day=1)
            end_date = today
        else:
            start_date = today.replace(day=1)
            end_date = today

        performance = {}

        with db.cursor() as cursor:
            # Doctor performance
            cursor.execute("""
                SELECT 
                    u.id,
                    u.first_name,
                    u.last_name,
                    u.specialization,
                    COUNT(DISTINCT a.id) as total_appointments,
                    COUNT(DISTINCT CASE WHEN a.status = 'completed' THEN a.id END) as completed,
                    COUNT(DISTINCT CASE WHEN a.type = 'emergency' THEN a.id END) as emergencies,
                    COALESCE(AVG(((julianday(a.end_time) - julianday(a.start_time)) * 24 * 60)), 0) as avg_duration
                FROM users u
                LEFT JOIN appointments a ON u.id = a.doctor_id
                    AND DATE(a.appointment_date) BETWEEN ? AND ?
                WHERE u.role_id IN (SELECT id FROM roles WHERE name IN ('doctor', 'superadmin'))
                GROUP BY u.id
                ORDER BY total_appointments DESC
            """, (start_date, end_date))

            performance['doctors'] = cursor.fetchall()

            # Nurse performance
            cursor.execute("""
                SELECT 
                    u.id,
                    u.first_name,
                    u.last_name,
                    COUNT(DISTINCT ass.id) as assists,
                    COUNT(DISTINCT a.id) as appointments_handled
                FROM users u
                LEFT JOIN assists ass ON u.id = ass.nurse_id
                LEFT JOIN appointments a ON ass.appointment_id = a.id
                    AND DATE(a.appointment_date) BETWEEN ? AND ?
                WHERE u.role_id = (SELECT id FROM roles WHERE name = 'nurse')
                GROUP BY u.id
                ORDER BY assists DESC
            """, (start_date, end_date))

            performance['nurses'] = cursor.fetchall()

            # Reception performance
            cursor.execute("""
                SELECT 
                    u.id,
                    u.first_name,
                    u.last_name,
                    COUNT(DISTINCT p.id) as payments_processed,
                    COALESCE(SUM(p.amount), 0) as total_amount,
                    COUNT(DISTINCT a.id) as appointments_created
                FROM users u
                LEFT JOIN payments p ON u.id = p.received_by
                    AND DATE(p.payment_date) BETWEEN ? AND ?
                LEFT JOIN appointments a ON u.id = a.created_by
                    AND DATE(a.created_at) BETWEEN ? AND ?
                WHERE u.role_id = (SELECT id FROM roles WHERE name = 'reception')
                GROUP BY u.id
                ORDER BY payments_processed DESC
            """, (start_date, end_date, start_date, end_date))

            performance['reception'] = cursor.fetchall()

        db.close()

        return jsonify({
            'success': True,
            'performance': performance,
            'period': period,
            'date_range': {
                'start': start_date.strftime('%Y-%m-%d'),
                'end': end_date.strftime('%Y-%m-%d')
            }
        }), 200

    except Exception as e:
        print(f"Staff performance error: {e}")
        return jsonify({'error': 'Failed to fetch staff performance'}), 500


# =========================================
# Export Report to CSV
# =========================================

@reports_bp.route('/export-csv', methods=['GET'])
@login_required
@reception_required
def export_report_csv():
    """Export report data to CSV"""
    try:
        report_type = request.args.get('type', 'transactions')
        start_date = request.args.get(
            'start_date', datetime.now().strftime('%Y-%m-%d'))
        end_date = request.args.get(
            'end_date', datetime.now().strftime('%Y-%m-%d'))

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        output = StringIO()
        writer = csv.writer(output)

        if report_type == 'transactions':
            # Write headers
            writer.writerow(['Date', 'Time', 'Patient Name', 'Patient ID', 'Invoice #',
                            'Amount', 'Method', 'Reference', 'Status', 'Received By'])

            with db.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        p.payment_date,
                        p.amount,
                        p.payment_method,
                        p.reference,
                        pt.first_name,
                        pt.last_name,
                        pt.patient_number,
                        i.invoice_number,
                        i.status,
                        u.first_name as received_by_first,
                        u.last_name as received_by_last
                    FROM payments p
                    JOIN invoices i ON p.invoice_id = i.id
                    JOIN patients pt ON i.patient_id = pt.id
                    JOIN users u ON p.received_by = u.id
                    WHERE DATE(p.payment_date) BETWEEN ? AND ?
                    ORDER BY p.payment_date DESC
                """, (start_date, end_date))

                results = cursor.fetchall()

                for row in results:
                    writer.writerow([
                        row['payment_date'].strftime(
                            '%Y-%m-%d') if row['payment_date'] else '',
                        row['payment_date'].strftime(
                            '%I:%M %p') if row['payment_date'] else '',
                        f"{row['first_name']} {row['last_name']}",
                        row['patient_number'],
                        row['invoice_number'],
                        row['amount'],
                        row['payment_method'].upper(),
                        row['reference'] or '-',
                        row['status'],
                        f"{row['received_by_first']} {row['received_by_last']}"
                    ])

        elif report_type == 'appointments':
            writer.writerow(['Date', 'Time', 'Patient', 'Doctor',
                            'Nurse', 'Status', 'Type', 'Room', 'Notes'])

            with db.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        a.appointment_date,
                        a.start_time,
                        a.end_time,
                        p.first_name,
                        p.last_name,
                        d.first_name as doctor_first,
                        d.last_name as doctor_last,
                        n.first_name as nurse_first,
                        n.last_name as nurse_last,
                        a.status,
                        a.type,
                        a.room,
                        a.notes
                    FROM appointments a
                    JOIN patients p ON a.patient_id = p.id
                    LEFT JOIN users d ON a.doctor_id = d.id
                    LEFT JOIN users n ON a.nurse_id = n.id
                    WHERE DATE(a.appointment_date) BETWEEN ? AND ?
                    ORDER BY a.appointment_date DESC, a.start_time
                """, (start_date, end_date))

                results = cursor.fetchall()

                for row in results:
                    writer.writerow([
                        row['appointment_date'].strftime(
                            '%Y-%m-%d') if row['appointment_date'] else '',
                        row['start_time'].strftime(
                            '%I:%M %p') if row['start_time'] else '',
                        f"{row['first_name']} {row['last_name']}",
                        f"Dr. {row['doctor_first']} {row['doctor_last']}" if row['doctor_first'] else 'N/A',
                        f"Nurse {row['nurse_first']} {row['nurse_last']}" if row['nurse_first'] else 'N/A',
                        row['status'],
                        row['type'],
                        row['room'] or 'TBD',
                        row['notes'] or ''
                    ])

        output.seek(0)
        filename = f"{report_type}_report_{start_date}_to_{end_date}.csv"

        return send_file(
            BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        print(f"Export CSV error: {e}")
        return jsonify({'error': 'Failed to export report'}), 500


# =========================================
# Get Cash Reconciliation
# =========================================

@reports_bp.route('/cash-reconciliation', methods=['GET'])
@login_required
@reception_required
def get_cash_reconciliation():
    """Get end-of-day cash reconciliation report"""
    try:
        date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        reconciliation = {}

        with db.cursor() as cursor:
            # Cash payments
            cursor.execute("""
                SELECT 
                    COALESCE(SUM(amount), 0) as total,
                    COUNT(*) as count
                FROM payments
                WHERE DATE(payment_date) = ?
                AND payment_method = 'cash'
            """, (date,))
            cash = cursor.fetchone()
            reconciliation['cash'] = {
                'total': float(cash['total']),
                'count': cash['count']
            }

            # POS payments
            cursor.execute("""
                SELECT 
                    COALESCE(SUM(amount), 0) as total,
                    COUNT(*) as count
                FROM payments
                WHERE DATE(payment_date) = ?
                AND payment_method = 'pos'
            """, (date,))
            pos = cursor.fetchone()
            reconciliation['pos'] = {
                'total': float(pos['total']),
                'count': pos['count']
            }

            # Transfer payments
            cursor.execute("""
                SELECT 
                    COALESCE(SUM(amount), 0) as total,
                    COUNT(*) as count
                FROM payments
                WHERE DATE(payment_date) = ?
                AND payment_method = 'transfer'
            """, (date,))
            transfer = cursor.fetchone()
            reconciliation['transfer'] = {
                'total': float(transfer['total']),
                'count': transfer['count']
            }

            # Free services
            cursor.execute("""
                SELECT 
                    COALESCE(SUM(amount), 0) as total,
                    COUNT(*) as count
                FROM payments
                WHERE DATE(payment_date) = ?
                AND payment_method = 'free'
            """, (date,))
            free = cursor.fetchone()
            reconciliation['free'] = {
                'total': float(free['total']),
                'count': free['count']
            }

            # Total
            reconciliation['total'] = {
                'total': reconciliation['cash']['total'] + reconciliation['pos']['total'] + reconciliation['transfer']['total'],
                'count': reconciliation['cash']['count'] + reconciliation['pos']['count'] + reconciliation['transfer']['count']
            }

            # Get last 5 payments for verification
            cursor.execute("""
                SELECT 
                    p.amount,
                    p.payment_method,
                    p.reference,
                    pt.first_name,
                    pt.last_name,
                    p.payment_date
                FROM payments p
                JOIN invoices i ON p.invoice_id = i.id
                JOIN patients pt ON i.patient_id = pt.id
                WHERE DATE(p.payment_date) = ?
                ORDER BY p.payment_date DESC
                LIMIT 5
            """, (date,))

            recent_payments = cursor.fetchall()
            reconciliation['recent_payments'] = []
            for payment in recent_payments:
                reconciliation['recent_payments'].append({
                    'amount': float(payment['amount']),
                    'payment_method': payment['payment_method'],
                    'reference': payment['reference'] or '-',
                    'patient_name': f"{payment['first_name']} {payment['last_name']}",
                    'payment_date': payment['payment_date'].strftime('%I:%M %p') if payment['payment_date'] else ''
                })

        db.close()

        return jsonify({
            'success': True,
            'reconciliation': reconciliation,
            'date': date
        }), 200

    except Exception as e:
        print(f"Cash reconciliation error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch cash reconciliation'}), 500
