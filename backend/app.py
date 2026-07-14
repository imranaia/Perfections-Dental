# =========================================
# Perfections Dental Services
# backend/app.py
# Main Application - v1.1 (LAN Session Fix)
# =========================================

from reception.profile import reception_profile_bp
from reception.prescriptions import reception_prescriptions_bp
from reception.invoices import reception_invoices_bp
from reception.inventory import reception_inventory_bp
from reception.reports import reports_bp
from reception.payments import payments_bp
from reception.services import reception_services_bp
from reception.patients import patients_bp
from reception.appointments import appointments_bp
from reception.dashboard import reception_staff_bp
from nurse.profile import nurse_profile_bp
from nurse.my_tasks import my_tasks_bp
from nurse.records import nurse_records_bp
from nurse.prescribe import nurse_prescribe_bp
from nurse.notes import notes_bp
from nurse.procedures import procedures_bp
from nurse.my_assists import my_assists_bp
from nurse.dashboard import nurse_bp
from doctor.profile import doctor_profile_bp
from doctor import records_bp
from doctor.prescribe import prescribe_bp
from doctor.consult import consult_bp
from doctor.schedule import schedule_bp
from doctor.my_patients import my_patients_bp
from doctor.dashboard import doctor_bp
from superadmin.profile import profile_bp
from superadmin.settings import settings_bp
from superadmin.performance import performance_bp
from superadmin.inventory import inventory_bp
from superadmin.services import services_bp
from superadmin.reception import reception_bp
from superadmin.nurses import nurses_bp
from superadmin.doctors import doctors_bp
from superadmin.analytics import analytics_bp
from superadmin.financial import financial_bp
from superadmin.access_control import access_control_bp
from superadmin.dashboard import superadmin_bp
from patient import patient_bp, patient_records_bp, patient_appointments_bp
from auth import auth_bp, login_required, role_required
from config import config
from db import get_db
from flask_cors import CORS
from flask.json.provider import DefaultJSONProvider
from flask import Flask, send_from_directory, jsonify, session
from datetime import datetime, timedelta
import datetime as dt_module
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# =========================================
# Create Flask App
# =========================================

def create_app(config_name='default'):
    app = Flask(__name__,
                static_folder='../frontend',
                static_url_path='')

    # Load base configuration from config object
    app.config.from_object(config[config_name])

    # SQLite date/datetime columns now come back as real Python date/datetime
    # objects (see db.py converters). Flask's default JSON provider renders
    # those as RFC-822 strings ("Mon, 13 Jul 2026 ... GMT") — override it so
    # every endpoint serializes them as plain ISO 8601 instead.
    class ISOJSONProvider(DefaultJSONProvider):
        @staticmethod
        def default(o):
            if isinstance(o, (dt_module.date, dt_module.datetime)):
                return o.isoformat()
            return DefaultJSONProvider.default(o)

    app.json = ISOJSONProvider(app)

    # ── SESSION & COOKIE FIX FOR LAN ACCESS ──────────────────────────────────
    # These must be set explicitly here because .env values are not
    # automatically applied to Flask session config by default.
    # Without these, session cookies only work on localhost and fail
    # on every other computer on the network.

    # Use a fixed secret key — never generate it randomly at startup
    # or every server restart will log everyone out
    app.secret_key = os.getenv(
        'SECRET_KEY', 'perfections-dental-secret-key-2024')

    # Critical: False means cookies work over plain HTTP (no HTTPS needed)
    # If this is True, browsers on other computers will silently reject
    # the session cookie and users get stuck on the login page
    app.config['SESSION_COOKIE_SECURE'] = False

    # Lax allows the cookie to be sent on normal same-site navigation
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # None means the cookie works on any IP/hostname — not just localhost
    app.config['SESSION_COOKIE_DOMAIN'] = None

    # Prevents JavaScript from reading the session cookie (security)
    app.config['SESSION_COOKIE_HTTPONLY'] = True

    # How long sessions stay alive — 12 hours (covers a full clinic day)
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)

    # Cookie name — no change needed but explicit is better
    app.config['SESSION_COOKIE_NAME'] = 'perfections_session'
    # ─────────────────────────────────────────────────────────────────────────

    # CORS — allow requests from localhost and the server's LAN IP
    # Change 192.168.8.105 to your actual server IP if different
    server_ip = os.getenv('SERVER_IP', '192.168.8.105')
    CORS(app,
         supports_credentials=True,
         origins=[
             "http://localhost:5000",
             "http://127.0.0.1:5000",
             f"http://{server_ip}:5000",
         ])

    # Register all blueprints — unchanged
    app.register_blueprint(auth_bp)
    app.register_blueprint(superadmin_bp)
    app.register_blueprint(access_control_bp)
    app.register_blueprint(financial_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(doctors_bp)
    app.register_blueprint(nurses_bp)
    app.register_blueprint(reception_bp)
    app.register_blueprint(services_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(performance_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(doctor_bp)
    app.register_blueprint(my_patients_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(consult_bp)
    app.register_blueprint(prescribe_bp)
    app.register_blueprint(records_bp)
    app.register_blueprint(doctor_profile_bp)
    app.register_blueprint(nurse_bp)
    app.register_blueprint(my_assists_bp)
    app.register_blueprint(procedures_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(nurse_prescribe_bp)
    app.register_blueprint(nurse_records_bp)
    app.register_blueprint(my_tasks_bp)
    app.register_blueprint(nurse_profile_bp)
    app.register_blueprint(reception_staff_bp)
    app.register_blueprint(appointments_bp)
    app.register_blueprint(patients_bp)
    app.register_blueprint(reception_services_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(reception_inventory_bp)
    app.register_blueprint(reception_invoices_bp)
    app.register_blueprint(reception_profile_bp)
    app.register_blueprint(reception_prescriptions_bp)
    app.register_blueprint(patient_bp)
    app.register_blueprint(patient_records_bp)
    app.register_blueprint(patient_appointments_bp)

    return app


# Initialize database (creates schema.sql tables if the .db file is new,
# then loads seed.sql demo data the first time only)
def _bootstrap_db():
    from db import init_db, get_db
    is_new = init_db()
    if is_new:
        seed_path = os.path.join(os.path.dirname(
            os.path.abspath(__file__)), 'database', 'seed.sql')
        if os.path.exists(seed_path):
            conn = get_db()
            with open(seed_path, 'r', encoding='utf-8') as f:
                conn.executescript(f.read())
            conn.commit()
            conn.close()
            print('Seeded fresh database with demo data.')


_bootstrap_db()

# Initialize app
app = create_app(os.getenv('FLASK_ENV', 'development'))


# =========================================
# Root route - Serve the public landing page
# =========================================

@app.route('/')
def index():
    return send_from_directory('../pdsl', 'index.html')


# =========================================
# Serve all frontend files
# =========================================

@app.route('/pages/<path:filename>')
def serve_pages(filename):
    return send_from_directory(os.path.join(app.static_folder, 'pages'), filename)


@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(os.path.join(app.static_folder, 'css'), filename)


@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory(os.path.join(app.static_folder, 'js'), filename)


@app.route('/assets/<path:filename>')
def serve_assets(filename):
    return send_from_directory(os.path.join(app.static_folder, 'assets'), filename)


# =========================================
# Test database connection
# =========================================

@app.route('/api/test-db')
def test_db():
    try:
        connection = get_db()
        connection.close()
        return jsonify({'status': 'success', 'message': 'Database connected successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# =========================================
# Dashboard Stats
# =========================================

@app.route('/api/dashboard/stats')
@login_required
def dashboard_stats():
    try:
        user = session.get('user')
        active_role = session.get('active_role') or session.get('role')

        connection = get_db()

        stats = {}

        with connection.cursor() as cursor:
            if active_role == 'superadmin':
                cursor.execute("""
                    SELECT COUNT(*) as total FROM users
                    WHERE role_id != (SELECT id FROM roles WHERE name='superadmin')
                """)
                stats['total_staff'] = cursor.fetchone()['total']

                cursor.execute("SELECT COUNT(*) as total FROM patients")
                stats['total_patients'] = cursor.fetchone()['total']

                cursor.execute("""
                    SELECT COUNT(*) as total FROM appointments
                    WHERE DATE(appointment_date) = date('now')
                """)
                stats['today_appointments'] = cursor.fetchone()['total']

                cursor.execute("""
                    SELECT COALESCE(SUM(total), 0) as total FROM invoices
                    WHERE CAST(strftime('%m', invoice_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER)
                    AND CAST(strftime('%Y', invoice_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
                """)
                stats['monthly_revenue'] = float(cursor.fetchone()['total'])

                cursor.execute("""
                    SELECT COUNT(*) as total FROM inventory_items
                    WHERE current_stock <= min_threshold AND is_active = 1
                """)
                stats['low_stock_alerts'] = cursor.fetchone()['total']

                cursor.execute("""
                    SELECT COUNT(*) as total FROM users
                    WHERE role_id != (SELECT id FROM roles WHERE name='superadmin')
                    AND CAST(strftime('%m', created_at) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER)
                    AND CAST(strftime('%Y', created_at) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
                """)
                stats['staff_change'] = cursor.fetchone()['total']

                cursor.execute("""
                    SELECT
                        COUNT(CASE WHEN DATE(appointment_date) = date('now') THEN 1 END) as today,
                        COUNT(CASE WHEN DATE(appointment_date) = date(date('now'), '-1 days') THEN 1 END) as yesterday
                    FROM appointments
                """)
                appt_counts = cursor.fetchone()
                if appt_counts['yesterday'] > 0:
                    stats['appointments_change'] = round(
                        ((appt_counts['today'] - appt_counts['yesterday']) / appt_counts['yesterday']) * 100, 1)
                else:
                    stats['appointments_change'] = 100 if appt_counts['today'] > 0 else 0

                cursor.execute("""
                    SELECT
                        COALESCE(SUM(CASE WHEN CAST(strftime('%m', invoice_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER) THEN total END), 0) as this_month,
                        COALESCE(SUM(CASE WHEN CAST(strftime('%m', invoice_date) AS INTEGER) = CAST(strftime('%m', date(date('now'), '-1 months')) AS INTEGER) THEN total END), 0) as last_month
                    FROM invoices WHERE CAST(strftime('%Y', invoice_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
                """)
                revenue_counts = cursor.fetchone()
                if revenue_counts['last_month'] > 0:
                    stats['revenue_change'] = round(
                        ((revenue_counts['this_month'] - revenue_counts['last_month']) / revenue_counts['last_month']) * 100, 1)
                else:
                    stats['revenue_change'] = 100 if revenue_counts['this_month'] > 0 else 0

            elif active_role == 'doctor':
                cursor.execute("""
                    SELECT COUNT(*) as total FROM appointments
                    WHERE doctor_id = ? AND DATE(appointment_date) = date('now')
                """, (user['id'],))
                stats['today_appointments'] = cursor.fetchone()['total']

                cursor.execute("""
                    SELECT COUNT(*) as total FROM patients
                    WHERE id IN (SELECT DISTINCT patient_id FROM appointments WHERE doctor_id = ?)
                """, (user['id'],))
                stats['total_patients'] = cursor.fetchone()['total']

                cursor.execute("""
                    SELECT COUNT(*) as total FROM appointments
                    WHERE doctor_id = ? AND status = 'waiting'
                """, (user['id'],))
                stats['waiting_patients'] = cursor.fetchone()['total']

            elif active_role == 'nurse':
                cursor.execute("""
                    SELECT COUNT(*) as total FROM assists
                    WHERE nurse_id = ? AND appointment_id IN
                    (SELECT id FROM appointments WHERE DATE(appointment_date) = date('now'))
                """, (user['id'],))
                stats['today_assists'] = cursor.fetchone()['total']

                cursor.execute("""
                    SELECT COUNT(*) as total FROM tasks
                    WHERE assigned_to = ? AND status = 'pending'
                """, (user['id'],))
                stats['pending_tasks'] = cursor.fetchone()['total']

            elif active_role == 'reception':
                cursor.execute(
                    "SELECT COUNT(*) as total FROM appointments WHERE DATE(appointment_date) = date('now')")
                stats['today_appointments'] = cursor.fetchone()['total']

                cursor.execute(
                    "SELECT COUNT(*) as total FROM patients WHERE DATE(registration_date) = date('now')")
                stats['new_patients'] = cursor.fetchone()['total']

                cursor.execute(
                    "SELECT COALESCE(SUM(amount), 0) as total FROM payments WHERE DATE(payment_date) = date('now')")
                stats['today_collections'] = float(cursor.fetchone()['total'])

        connection.close()
        return jsonify({'success': True, 'stats': stats}), 200

    except Exception as e:
        print(f"Dashboard stats error: {e}")
        return jsonify({'error': 'Failed to fetch dashboard stats'}), 500


# =========================================
# Recent Activities
# =========================================

@app.route('/api/dashboard/recent-activities', methods=['GET'])
@login_required
def recent_activities():
    try:
        user = session.get('user')
        active_role = session.get('active_role') or session.get('role')

        connection = get_db()

        activities = []

        with connection.cursor() as cursor:
            if active_role == 'superadmin':
                cursor.execute("""
                    SELECT 'patient_registration' as type,
                        ('New patient registered: ' || first_name || ' ' || last_name) as title,
                        created_at,
                        'fas fa-user-plus' as icon,
                        'success' as badge_type, 'New' as badge_text
                    FROM patients ORDER BY created_at DESC LIMIT 2
                """)
                activities.extend(cursor.fetchall())

                cursor.execute("""
                    SELECT 'payment' as type,
                        ('Payment of ₦' || printf('%.0f', p.amount) || ' received') as title,
                        p.created_at,
                        'fas fa-credit-card' as icon,
                        'success' as badge_type, 'Paid' as badge_text
                    FROM payments p ORDER BY p.created_at DESC LIMIT 2
                """)
                activities.extend(cursor.fetchall())

                cursor.execute("""
                    SELECT 'low_stock' as type,
                        ('Low stock alert: ' || name) as title,
                        updated_at as created_at,
                        'fas fa-exclamation-circle' as icon,
                        'warning' as badge_type, 'Alert' as badge_text
                    FROM inventory_items
                    WHERE current_stock <= min_threshold AND is_active = 1
                    ORDER BY updated_at DESC LIMIT 1
                """)
                activities.extend(cursor.fetchall())

            elif active_role == 'doctor':
                cursor.execute("""
                    SELECT 'appointment' as type,
                        ('Appointment with ' || p.first_name || ' ' || p.last_name) as title,
                        a.created_at,
                        'fas fa-calendar-check' as icon,
                        'info' as badge_type, a.status as badge_text
                    FROM appointments a
                    JOIN patients p ON a.patient_id = p.id
                    WHERE a.doctor_id = ?
                    ORDER BY a.created_at DESC LIMIT 5
                """, (user['id'],))
                activities = cursor.fetchall()

            elif active_role == 'nurse':
                cursor.execute("""
                    SELECT 'assist' as type,
                        ('Assisted with Dr. ' || d.first_name || ' ' || d.last_name) as title,
                        a.created_at,
                        'fas fa-hand-holding-medical' as icon,
                        'info' as badge_type, 'Assist' as badge_text
                    FROM assists ass
                    JOIN appointments a ON ass.appointment_id = a.id
                    JOIN users d ON a.doctor_id = d.id
                    WHERE ass.nurse_id = ?
                    ORDER BY a.created_at DESC LIMIT 5
                """, (user['id'],))
                activities = cursor.fetchall()

            elif active_role == 'reception':
                cursor.execute("""
                    SELECT 'appointment' as type,
                        ('Appointment scheduled for ' || p.first_name || ' ' || p.last_name) as title,
                        a.created_at,
                        'fas fa-calendar-check' as icon,
                        'info' as badge_type, a.status as badge_text
                    FROM appointments a
                    JOIN patients p ON a.patient_id = p.id
                    ORDER BY a.created_at DESC LIMIT 5
                """)
                activities = cursor.fetchall()

        connection.close()
        activities.sort(key=lambda x: x['created_at'], reverse=True)
        return jsonify({'success': True, 'activities': activities[:5]}), 200

    except Exception as e:
        print(f"Recent activities error: {e}")
        return jsonify({'error': 'Failed to fetch recent activities'}), 500


# =========================================
# Chart Data
# =========================================

@app.route('/api/dashboard/chart-data', methods=['GET'])
@login_required
def chart_data():
    try:
        user = session.get('user')
        active_role = session.get('active_role') or session.get('role')

        connection = get_db()

        revenue_data = {'labels': [], 'values': []}
        appointment_data = {'labels': [], 'values': []}

        with connection.cursor() as cursor:
            for i in range(6, -1, -1):
                date = datetime.now() - timedelta(days=i)
                date_str = date.strftime('%Y-%m-%d')
                display_date = date.strftime('%a')
                revenue_data['labels'].append(display_date)
                cursor.execute("""
                    SELECT COALESCE(SUM(total), 0) as daily_total
                    FROM invoices WHERE DATE(invoice_date) = ?
                """, (date_str,))
                revenue_data['values'].append(
                    float(cursor.fetchone()['daily_total']))

            if active_role in ('superadmin', 'reception'):
                cursor.execute("""
                    SELECT status, COUNT(*) as count FROM appointments
                    WHERE CAST(strftime('%m', appointment_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER)
                    AND CAST(strftime('%Y', appointment_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
                    GROUP BY status ORDER BY count DESC
                """)
            elif active_role == 'doctor':
                cursor.execute("""
                    SELECT status, COUNT(*) as count FROM appointments
                    WHERE doctor_id = ?
                    AND CAST(strftime('%m', appointment_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER)
                    AND CAST(strftime('%Y', appointment_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
                    GROUP BY status ORDER BY count DESC
                """, (user['id'],))
            else:
                appointment_data = {'labels': ['No data'], 'values': [1]}

            results = cursor.fetchall()
            for row in results:
                appointment_data['labels'].append(
                    row['status'].replace('_', ' ').title())
                appointment_data['values'].append(row['count'])

            if not appointment_data['values']:
                appointment_data = {'labels': [
                    'No Appointments'], 'values': [1]}

        connection.close()
        return jsonify({
            'success':          True,
            'revenue_data':     revenue_data,
            'appointment_data': appointment_data
        }), 200

    except Exception as e:
        print(f"Chart data error: {e}")
        return jsonify({'error': 'Failed to fetch chart data'}), 500


# =========================================
# Error Handlers
# =========================================

@app.errorhandler(404)
def not_found(error):
    return send_from_directory('../frontend', '404.html') \
        if os.path.exists('../frontend/404.html') \
        else ('Page not found', 404)


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500


# =========================================
# Run the application
# =========================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
