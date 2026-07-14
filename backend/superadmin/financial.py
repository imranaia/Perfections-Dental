import sqlite3
# =========================================
# Perfections Dental Services
# Financial Overview Module - v1.0
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


# Create financial blueprint
financial_bp = Blueprint('financial', __name__,
                         url_prefix='/api/superadmin/financial')



# =========================================
# Get Financial Summary
# =========================================


@financial_bp.route('/summary', methods=['GET'])
@login_required
@role_required('superadmin')
def get_financial_summary():
    """Get financial summary for a date range"""
    try:
        # today, week, month, quarter
        period = request.args.get('period', 'today')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        summary = {}

        with db.cursor() as cursor:
            # Get date range based on period
            today = datetime.now().date()
            if period == 'today':
                start_date = today
                end_date = today
                compare_start = today - timedelta(days=1)
                compare_end = today - timedelta(days=1)
            elif period == 'week':
                start_date = today - timedelta(days=today.weekday())
                end_date = today
                compare_start = start_date - timedelta(days=7)
                compare_end = end_date - timedelta(days=7)
            elif period == 'month':
                start_date = today.replace(day=1)
                end_date = today
                compare_start = (start_date - timedelta(days=1)).replace(day=1)
                compare_end = start_date - timedelta(days=1)
            elif period == 'quarter':
                quarter_month = ((today.month - 1) // 3) * 3 + 1
                start_date = today.replace(month=quarter_month, day=1)
                end_date = today
                compare_start = (start_date - timedelta(days=1)).replace(day=1)
                compare_start = compare_start.replace(
                    month=((compare_start.month - 1) // 3) * 3 + 1)
                compare_end = start_date - timedelta(days=1)
            else:
                start_date = today
                end_date = today
                compare_start = today - timedelta(days=1)
                compare_end = today - timedelta(days=1)

            # Total revenue
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) as total
                FROM payments p
                JOIN invoices i ON p.invoice_id = i.id
                WHERE DATE(p.payment_date) BETWEEN ? AND ?
            """, (start_date, end_date))
            summary['total_revenue'] = float(cursor.fetchone()['total'])

            # Previous period revenue for comparison
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) as total
                FROM payments p
                JOIN invoices i ON p.invoice_id = i.id
                WHERE DATE(p.payment_date) BETWEEN ? AND ?
            """, (compare_start, compare_end))
            previous_revenue = float(cursor.fetchone()['total'])

            # Calculate change percentage
            if previous_revenue > 0:
                summary['revenue_change'] = round(
                    ((summary['total_revenue'] - previous_revenue) / previous_revenue) * 100, 1)
            else:
                summary['revenue_change'] = 100 if summary['total_revenue'] > 0 else 0

            # Payment methods breakdown
            cursor.execute("""
                SELECT 
                    p.payment_method,
                    COUNT(*) as count,
                    COALESCE(SUM(p.amount), 0) as total
                FROM payments p
                JOIN invoices i ON p.invoice_id = i.id
                WHERE DATE(p.payment_date) BETWEEN ? AND ?
                GROUP BY p.payment_method
            """, (start_date, end_date))

            payment_methods = cursor.fetchall()
            summary['payment_methods'] = {}
            method_icons = {
                'cash': 'fas fa-money-bill-wave',
                'pos': 'fas fa-credit-card',
                'transfer': 'fas fa-university',
                'cheque': 'fas fa-file-invoice',
                'free': 'fas fa-heart'
            }

            for method in payment_methods:
                method_name = method['payment_method']
                summary['payment_methods'][method_name] = {
                    'total': float(method['total']),
                    'count': method['count'],
                    'icon': method_icons.get(method_name, 'fas fa-credit-card')
                }

            # Total transactions count
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM payments p
                JOIN invoices i ON p.invoice_id = i.id
                WHERE DATE(p.payment_date) BETWEEN ? AND ?
            """, (start_date, end_date))
            summary['total_transactions'] = cursor.fetchone()['total']

            # Paid count
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM payments p
                JOIN invoices i ON p.invoice_id = i.id
                WHERE DATE(p.payment_date) BETWEEN ? AND ?
                AND i.status = 'paid'
            """, (start_date, end_date))
            summary['paid_count'] = cursor.fetchone()['total']

            # Free services count
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM payments p
                JOIN invoices i ON p.invoice_id = i.id
                WHERE DATE(p.payment_date) BETWEEN ? AND ?
                AND p.payment_method = 'free'
            """, (start_date, end_date))
            summary['free_services'] = cursor.fetchone()['total']

            # Average ticket
            if summary['total_transactions'] > 0:
                summary['average_ticket'] = summary['total_revenue'] / \
                    summary['total_transactions']
            else:
                summary['average_ticket'] = 0

            # Top service today/period
            cursor.execute("""
                SELECT 
                    s.name as service_name,
                    COUNT(*) as count,
                    COALESCE(SUM(as_total.unit_price * as_total.quantity), 0) as total_revenue
                FROM appointment_services as_total
                JOIN services s ON as_total.service_id = s.id
                JOIN appointments a ON as_total.appointment_id = a.id
                WHERE DATE(a.appointment_date) BETWEEN ? AND ?
                GROUP BY s.id, s.name
                ORDER BY total_revenue DESC
                LIMIT 1
            """, (start_date, end_date))
            top_service = cursor.fetchone()

            if top_service:
                summary['top_service'] = {
                    'name': top_service['service_name'],
                    'count': top_service['count'],
                    'revenue': float(top_service['total_revenue'])
                }
            else:
                summary['top_service'] = None

            # Get period label
            if period == 'today':
                summary['period_label'] = today.strftime('%B %d, %Y')
            elif period == 'week':
                summary['period_label'] = f"Week of {start_date.strftime('%B %d')}"
            elif period == 'month':
                summary['period_label'] = start_date.strftime('%B %Y')
            else:
                summary['period_label'] = f"Q{((today.month - 1) // 3) + 1} {today.year}"

        db.close()
        return jsonify({'success': True, 'summary': summary}), 200

    except Exception as e:
        print(f"Financial summary error: {e}")
        return jsonify({'error': 'Failed to fetch financial summary'}), 500

# =========================================
# Get Profit Margins by Service
# =========================================


@financial_bp.route('/profit-margins', methods=['GET'])
@login_required
@role_required('superadmin')
def get_profit_margins():
    """Get profit margins for services"""
    try:
        period = request.args.get('period', 'month')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        # Get date range
        today = datetime.now().date()
        if period == 'today':
            start_date = today
            end_date = today
        elif period == 'week':
            start_date = today - timedelta(days=today.weekday())
            end_date = today
        elif period == 'month':
            start_date = today.replace(day=1)
            end_date = today
        else:
            start_date = today.replace(day=1)
            end_date = today

        profit_margins = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    s.id,
                    s.name,
                    s.price as service_price,
                    COUNT(as_total.id) as service_count,
                    COALESCE(SUM(as_total.unit_price * as_total.quantity), 0) as total_revenue,
                    COALESCE(SUM(as_total.unit_price * as_total.quantity * 0.3), 0) as estimated_cost
                FROM services s
                LEFT JOIN appointment_services as_total ON s.id = as_total.service_id
                LEFT JOIN appointments a ON as_total.appointment_id = a.id
                WHERE s.is_active = 1
                AND (a.appointment_date BETWEEN ? AND ? OR a.appointment_date IS NULL)
                GROUP BY s.id, s.name, s.price
                HAVING service_count > 0 OR total_revenue > 0
                ORDER BY total_revenue DESC
                LIMIT 10
            """, (start_date, end_date))

            services = cursor.fetchall()

            for service in services:
                revenue = float(service['total_revenue'])
                cost = float(service['estimated_cost'])
                profit = revenue - cost
                margin = (profit / revenue * 100) if revenue > 0 else 0

                profit_margins.append({
                    'name': service['name'],
                    'revenue': revenue,
                    'cost': cost,
                    'profit': profit,
                    'margin': round(margin, 1),
                    'count': service['service_count']
                })

        db.close()
        return jsonify({'success': True, 'profit_margins': profit_margins}), 200

    except Exception as e:
        print(f"Profit margins error: {e}")
        return jsonify({'error': 'Failed to fetch profit margins'}), 500

# =========================================
# Get Revenue Forecast
# =========================================


@financial_bp.route('/forecast', methods=['GET'])
@login_required
@role_required('superadmin')
def get_revenue_forecast():
    """Get revenue forecast for next 7 days"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        forecast = []
        total_forecast = 0

        with db.cursor() as cursor:
            for i in range(7):
                forecast_date = datetime.now().date() + timedelta(days=i)
                day_name = forecast_date.strftime('%A')

                # Get average revenue for this day from past 4 weeks
                cursor.execute("""
                    SELECT 
                        COALESCE(AVG(daily_total), 0) as avg_revenue
                    FROM (
                        SELECT 
                            DATE(payment_date) as day,
                            SUM(amount) as daily_total
                        FROM payments p
                        JOIN invoices i ON p.invoice_id = i.id
                        WHERE strftime('%w', payment_date) = strftime('%w', ?)
                        AND payment_date >= date(?, '-28 days')
                        GROUP BY DATE(payment_date)
                    ) as weekly_data
                """, (forecast_date, forecast_date))

                result = cursor.fetchone()
                forecast_amount = float(result['avg_revenue']) if result else 0

                # Adjust for weekend/holiday patterns
                if day_name in ['Saturday', 'Sunday']:
                    forecast_amount = forecast_amount * 0.7
                elif day_name == 'Monday':
                    forecast_amount = forecast_amount * 0.9

                total_forecast += forecast_amount

                forecast.append({
                    'day': day_name,
                    'amount': forecast_amount,
                    'percentage': 0  # Will be calculated later
                })

            # Calculate percentages
            for f in forecast:
                f['percentage'] = (
                    f['amount'] / total_forecast * 100) if total_forecast > 0 else 0

        db.close()
        return jsonify({
            'success': True,
            'forecast': forecast,
            'total_forecast': total_forecast,
            'confidence': 85  # Placeholder confidence score
        }), 200

    except Exception as e:
        print(f"Forecast error: {e}")
        return jsonify({'error': 'Failed to fetch forecast'}), 500

# =========================================
# Get Discount Approval Queue
# =========================================


@financial_bp.route('/discounts/pending', methods=['GET'])
@login_required
@role_required('superadmin')
def get_pending_discounts():
    """Get pending discount approvals"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        pending_discounts = []

        with db.cursor() as cursor:
            # For now, we'll return sample structure
            # In production, you'd have a discounts table
            cursor.execute("""
                SELECT 
                    a.id as appointment_id,
                    a.appointment_number,
                    p.id as patient_id,
                    p.first_name,
                    p.last_name,
                    i.total as invoice_total,
                    i.discount as discount_amount,
                    i.discount_reason,
                    u.first_name as requested_by_first,
                    u.last_name as requested_by_last,
                    i.created_at as requested_at
                FROM invoices i
                JOIN patients p ON i.patient_id = p.id
                JOIN users u ON i.created_by = u.id
                JOIN appointments a ON i.appointment_id = a.id
                WHERE i.discount > 0 
                AND i.discount_status = 'pending'
                AND i.status != 'cancelled'
                ORDER BY i.created_at DESC
                LIMIT 20
            """)

            discounts = cursor.fetchall()
            for d in discounts:
                discount_percent = (float(
                    d['discount_amount']) / float(d['invoice_total']) * 100) if d['invoice_total'] > 0 else 0
                pending_discounts.append({
                    'id': d['appointment_id'],
                    'patient_name': f"{d['first_name']} {d['last_name']}",
                    'discount_percent': round(discount_percent, 1),
                    'discount_amount': float(d['discount_amount']),
                    'invoice_total': float(d['invoice_total']),
                    'reason': d.get('discount_reason', 'Staff/Patient request'),
                    'requested_by': f"{d['requested_by_first']} {d['requested_by_last']}",
                    'requested_at': d['requested_at'].strftime('%Y-%m-%d %H:%M') if d['requested_at'] else '',
                    'appointment_number': d['appointment_number']
                })

        db.close()
        return jsonify({'success': True, 'discounts': pending_discounts, 'count': len(pending_discounts)}), 200

    except Exception as e:
        print(f"Pending discounts error: {e}")
        # Return empty array if table doesn't exist yet
        return jsonify({'success': True, 'discounts': [], 'count': 0}), 200

# =========================================
# Approve or Reject Discount
# =========================================


@financial_bp.route('/discounts/<int:appointment_id>/approve', methods=['POST'])
@login_required
@role_required('superadmin')
def approve_discount(appointment_id):
    """Approve a discount request"""
    try:
        data = request.get_json()
        approved = data.get('approved', True)

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            if approved:
                cursor.execute("""
                    UPDATE invoices i
                    SET discount_status = 'approved',
                        discount_approved_by = ?,
                        discount_approved_at = datetime('now')
                    WHERE appointment_id = ?
                """, (session['user_id'], appointment_id))

                # Log the approval
                cursor.execute("""
                    INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                    VALUES (?, 'APPROVE_DISCOUNT', 'invoices', 
                            (SELECT id FROM invoices WHERE appointment_id = ?), ?)
                """, (session['user_id'], appointment_id, json.dumps({'status': 'approved'})))
            else:
                cursor.execute("""
                    UPDATE invoices i
                    SET discount_status = 'rejected',
                        discount_rejected_by = ?,
                        discount_rejected_at = datetime('now')
                    WHERE appointment_id = ?
                """, (session['user_id'], appointment_id))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': f'Discount {approved and "approved" or "rejected"} successfully'
        }), 200

    except Exception as e:
        print(f"Approve discount error: {e}")
        return jsonify({'error': 'Failed to process discount'}), 500

# =========================================
# Get Recent Transactions
# =========================================


@financial_bp.route('/transactions/recent', methods=['GET'])
@login_required
@role_required('superadmin')
def get_recent_transactions():
    """Get recent transactions"""
    try:
        limit = request.args.get('limit', 10, type=int)
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        transactions = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    p.id,
                    p.amount,
                    p.payment_method,
                    p.payment_date,
                    p.reference,
                    p.created_at,
                    pt.id as patient_id,
                    pt.first_name as patient_first,
                    pt.last_name as patient_last,
                    i.invoice_number,
                    i.status as invoice_status
                FROM payments p
                JOIN invoices i ON p.invoice_id = i.id
                JOIN patients pt ON i.patient_id = pt.id
                ORDER BY p.created_at DESC
                LIMIT ?
            """, (limit,))

            payments = cursor.fetchall()

            for payment in payments:
                method_icons = {
                    'cash': 'fas fa-money-bill-wave',
                    'pos': 'fas fa-credit-card',
                    'transfer': 'fas fa-university',
                    'cheque': 'fas fa-file-invoice',
                    'free': 'fas fa-heart'
                }

                status_badge = 'success' if payment['invoice_status'] == 'paid' else 'warning'
                status_text = 'Paid' if payment['invoice_status'] == 'paid' else 'Pending'

                transactions.append({
                    'id': payment['id'],
                    'patient_name': f"{payment['patient_first']} {payment['patient_last']}",
                    'amount': float(payment['amount']),
                    'method': payment['payment_method'],
                    'method_icon': method_icons.get(payment['payment_method'], 'fas fa-credit-card'),
                    'status': payment['invoice_status'],
                    'status_badge': status_badge,
                    'status_text': status_text,
                    'reference': payment['reference'] or '-',
                    'invoice_number': payment['invoice_number'],
                    'date': payment['payment_date'].strftime('%Y-%m-%d') if payment['payment_date'] else ''
                })

        db.close()
        return jsonify({'success': True, 'transactions': transactions}), 200

    except Exception as e:
        print(f"Recent transactions error: {e}")
        return jsonify({'error': 'Failed to fetch transactions'}), 500

# =========================================
# Get Daily Summary
# =========================================


@financial_bp.route('/daily-summary', methods=['GET'])
@login_required
@role_required('superadmin')
def get_daily_summary():
    """Get daily financial summary"""
    try:
        date = request.args.get(
            'date', datetime.now().date().strftime('%Y-%m-%d'))
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        summary = {}

        with db.cursor() as cursor:
            # Total transactions
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM payments p
                JOIN invoices i ON p.invoice_id = i.id
                WHERE DATE(p.payment_date) = ?
            """, (date,))
            summary['total_transactions'] = cursor.fetchone()['total']

            # Paid count
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM payments p
                JOIN invoices i ON p.invoice_id = i.id
                WHERE DATE(p.payment_date) = ?
                AND i.status = 'paid'
            """, (date,))
            summary['paid_count'] = cursor.fetchone()['total']

            # Free services count
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM payments p
                JOIN invoices i ON p.invoice_id = i.id
                WHERE DATE(p.payment_date) = ?
                AND p.payment_method = 'free'
            """, (date,))
            summary['free_services'] = cursor.fetchone()['total']

            # Average ticket
            cursor.execute("""
                SELECT COALESCE(AVG(amount), 0) as avg_ticket
                FROM payments p
                JOIN invoices i ON p.invoice_id = i.id
                WHERE DATE(p.payment_date) = ?
                AND i.status = 'paid'
            """, (date,))
            summary['average_ticket'] = float(cursor.fetchone()['avg_ticket'])

            # Top service
            cursor.execute("""
                SELECT 
                    s.name as service_name,
                    COUNT(*) as count,
                    COALESCE(SUM(as_total.unit_price * as_total.quantity), 0) as total_revenue
                FROM appointment_services as_total
                JOIN services s ON as_total.service_id = s.id
                JOIN appointments a ON as_total.appointment_id = a.id
                WHERE DATE(a.appointment_date) = ?
                GROUP BY s.id, s.name
                ORDER BY total_revenue DESC
                LIMIT 1
            """, (date,))
            top_service = cursor.fetchone()

            if top_service:
                summary['top_service'] = {
                    'name': top_service['service_name'],
                    'count': top_service['count'],
                    'revenue': float(top_service['total_revenue'])
                }
            else:
                summary['top_service'] = None

            # Get yesterday's comparison
            yesterday = (datetime.strptime(date, '%Y-%m-%d') -
                         timedelta(days=1)).strftime('%Y-%m-%d')
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) as total
                FROM payments p
                JOIN invoices i ON p.invoice_id = i.id
                WHERE DATE(p.payment_date) = ?
            """, (yesterday,))
            yesterday_total = float(cursor.fetchone()['total'])

            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) as total
                FROM payments p
                JOIN invoices i ON p.invoice_id = i.id
                WHERE DATE(p.payment_date) = ?
            """, (date,))
            today_total = float(cursor.fetchone()['total'])

            if yesterday_total > 0:
                summary['daily_change'] = round(
                    ((today_total - yesterday_total) / yesterday_total) * 100, 1)
            else:
                summary['daily_change'] = 100 if today_total > 0 else 0

        db.close()
        return jsonify({'success': True, 'summary': summary}), 200

    except Exception as e:
        print(f"Daily summary error: {e}")
        return jsonify({'error': 'Failed to fetch daily summary'}), 500

# =========================================
# Export Financial Report
# =========================================


@financial_bp.route('/export', methods=['GET'])
@login_required
@role_required('superadmin')
def export_financial_report():
    """Export financial report as CSV"""
    try:
        period = request.args.get('period', 'month')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        # Get date range
        today = datetime.now().date()
        if period == 'today':
            start_date = today
            end_date = today
        elif period == 'week':
            start_date = today - timedelta(days=today.weekday())
            end_date = today
        elif period == 'month':
            start_date = today.replace(day=1)
            end_date = today
        else:
            start_date = today.replace(day=1)
            end_date = today

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    p.payment_date,
                    p.amount,
                    p.payment_method,
                    p.reference,
                    pt.first_name as patient_first,
                    pt.last_name as patient_last,
                    i.invoice_number,
                    i.status as invoice_status,
                    s.name as service_name
                FROM payments p
                JOIN invoices i ON p.invoice_id = i.id
                JOIN patients pt ON i.patient_id = pt.id
                LEFT JOIN appointment_services ast ON i.appointment_id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE DATE(p.payment_date) BETWEEN ? AND ?
                ORDER BY p.payment_date DESC
            """, (start_date, end_date))

            transactions = cursor.fetchall()

        db.close()

        # Generate CSV
        import csv
        from io import StringIO

        output = StringIO()
        writer = csv.writer(output)

        # Write headers
        writer.writerow(['Date', 'Patient', 'Service', 'Amount',
                        'Method', 'Reference', 'Invoice #', 'Status'])

        # Write data
        for t in transactions:
            writer.writerow([
                t['payment_date'].strftime(
                    '%Y-%m-%d') if t['payment_date'] else '',
                f"{t['patient_first']} {t['patient_last']}",
                t['service_name'] or 'Various',
                t['amount'],
                t['payment_method'],
                t['reference'] or '',
                t['invoice_number'],
                t['invoice_status']
            ])

        return jsonify({
            'success': True,
            'csv_data': output.getvalue(),
            'filename': f'financial_report_{period}_{today.strftime("%Y%m%d")}.csv'
        }), 200

    except Exception as e:
        print(f"Export error: {e}")
        return jsonify({'error': 'Failed to export report'}), 500
