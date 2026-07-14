import sqlite3
# =========================================
# Perfections Dental Services
# Doctor Consultation Module - v1.1
# =========================================

from config import Config
from db import get_db
from auth import login_required
from flask import Blueprint, jsonify, session, request
from datetime import datetime, timedelta, time
import json
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

consult_bp = Blueprint('doctor_consult', __name__,
                       url_prefix='/api/doctor/consult')



def format_time(value):
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


def doctor_required(f):
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


def format_teeth_by_quadrant(teeth_list):
    """Format teeth numbers by quadrant (1-8 per quadrant) — unchanged from v1"""
    quadrants = {
        'Upper Right': [1, 2, 3, 4, 5, 6, 7, 8],
        'Upper Left':  [9, 10, 11, 12, 13, 14, 15, 16],
        'Lower Left':  [17, 18, 19, 20, 21, 22, 23, 24],
        'Lower Right': [25, 26, 27, 28, 29, 30, 31, 32]
    }
    result = {}
    for quadrant_name, quadrant_numbers in quadrants.items():
        quadrant_selected = [t for t in teeth_list if t in quadrant_numbers]
        display_numbers = []
        for t in quadrant_selected:
            idx = quadrant_numbers.index(t)
            display_numbers.append(idx + 1)
        result[quadrant_name] = display_numbers
    return result


def format_teeth_display(teeth_dict, category_name):
    """Format teeth findings for display in medical notes — unchanged from v1"""
    lines = []
    lines.append(f" {category_name}: ")
    quadrants = ['Upper Right', 'Upper Left', 'Lower Left', 'Lower Right']
    for quadrant in quadrants:
        teeth = teeth_dict.get(quadrant, [])
        if teeth:
            teeth_str = ', '.join(map(str, sorted(teeth)))
            lines.append(f" {quadrant}: {teeth_str}")
        else:
            lines.append(f" {quadrant}: nothing was selected")
    return '\n'.join(lines)


def parse_notes_content(content):
    """Parse existing notes content to extract data — unchanged from v1"""
    parsed = {
        'presenting_complain': '',
        'history': '',
        'eoe': '',
        'ioe': '',
        'others': '',
        'diagnosis': '',
        'treatment_plan': '',
        'treatment': '',
        'treatment_done': '',
        'review_date': '',
        'review_notes': '',
        'teeth_findings': {}
    }

    teeth_section = re.search(
        r'=== TEETH FINDINGS ===(.*?)=== OTHER FINDINGS ===', content, re.DOTALL)
    if teeth_section:
        teeth_content = teeth_section.group(1)
        for cat_name in ['Teeth Present', 'Missing Teeth', 'Mobile Teeth', 'Carious Teeth',
                         'Fractured Teeth', 'Impacted Teeth', 'Periodontal Pocket']:
            cat_match = re.search(
                f'{cat_name}: (.*?)(?=\n |$)', teeth_content, re.DOTALL)
            if cat_match:
                cat_text = cat_match.group(1)
                tooth_numbers = []
                quadrant_pattern = r'([A-Za-z ]+): (.*?)(?=\n |$)'
                for quad_match in re.finditer(quadrant_pattern, cat_text, re.DOTALL):
                    quad_content = quad_match.group(2)
                    if quad_content and 'nothing was selected' not in quad_content:
                        numbers = re.findall(r'\d+', quad_content)
                        tooth_numbers.extend([int(n) for n in numbers])
                cat_key = {
                    'Teeth Present': 'present',
                    'Missing Teeth': 'missing',
                    'Mobile Teeth':  'mobile',
                    'Carious Teeth': 'carious',
                    'Fractured Teeth': 'fractured',
                    'Impacted Teeth':  'impacted',
                    'Periodontal Pocket': 'periodontal'
                }.get(cat_name)
                if cat_key and tooth_numbers:
                    parsed['teeth_findings'][cat_key] = tooth_numbers

    sections = {
        'PRESENTING COMPLAINT': 'presenting_complain',
        'HISTORY':               'history',
        'EXTRAORAL EXAMINATION': 'eoe',
        'INTRAORAL EXAMINATION': 'ioe',
        'OTHER FINDINGS':        'others',
        'DIAGNOSIS':             'diagnosis',
        'TREATMENT PLAN':        'treatment_plan',
        'TREATMENT PERFORMED':   'treatment',
        'TREATMENT DONE':        'treatment_done',
        'REVIEW':                'review'
    }

    current_section = None
    current_content = []

    for line in content.split('\n'):
        line = line.strip()
        matched = False
        for section, key in sections.items():
            if line.startswith(f'=== {section} =='):
                if current_section and current_content:
                    if current_section == 'review':
                        review_text = '\n'.join(current_content)
                        date_match = re.search(
                            r'Review Date: (.*?)(?:\n|$)', review_text)
                        notes_match = re.search(
                            r'Review Notes: (.*?)(?:\n|$)', review_text)
                        if date_match:
                            parsed['review_date'] = date_match.group(1).strip()
                        if notes_match:
                            parsed['review_notes'] = notes_match.group(
                                1).strip()
                    else:
                        parsed[current_section] = '\n'.join(
                            current_content).strip()
                current_section = sections.get(section, section)
                current_content = []
                matched = True
                break
        if not matched and current_section:
            current_content.append(line)

    return parsed


def _find_existing_note(cursor, appointment_id):
    """
    THE CORE FIX:
    Always look up by appointment_id directly from DB.
    Returns (note_id, note_content) or (None, None).
    Called before every save or complete — never trust frontend's existing_note_id.
    """
    cursor.execute("""
        SELECT id, content FROM medical_notes
        WHERE appointment_id = ? AND note_type = 'general'
        ORDER BY note_date ASC
        LIMIT 1
    """, (appointment_id,))
    row = cursor.fetchone()
    if row:
        return row['id'], row['content']
    return None, None


# =========================================
# Get Active Consultations
# FIX: includes checked_in + waiting (not just in_progress)
#      uses subquery to get ONE note per appointment
# =========================================

@consult_bp.route('/active', methods=['GET'])
@login_required
@doctor_required
def get_active_consultations():
    try:
        doctor_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        consultations = []
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT
                    a.id as appointment_id,
                    a.appointment_date,
                    a.start_time,
                    a.room,
                    a.status,
                    p.id as patient_id,
                    p.first_name,
                    p.last_name,
                    p.patient_number,
                    p.phone,
                    p.dob,
                    p.gender,
                    (
                        SELECT mn.id FROM medical_notes mn
                        WHERE mn.appointment_id = a.id
                        AND mn.note_type = 'general'
                        ORDER BY mn.note_date ASC
                        LIMIT 1
                    ) AS note_id
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                WHERE a.doctor_id = ?
                AND a.status IN ('checked_in', 'waiting', 'in_progress')
                AND DATE(a.appointment_date) = date('now')
                ORDER BY a.start_time ASC
            """, (doctor_id,))
            results = cursor.fetchall()

            today = datetime.now().date()
            for row in results:
                age = None
                if row['dob']:
                    age = today.year - row['dob'].year - (
                        (today.month, today.day) < (row['dob'].month, row['dob'].day))

                # Auto-promote checked_in/waiting → in_progress
                if row['status'] in ('checked_in', 'waiting'):
                    cursor.execute("""
                        UPDATE appointments
                        SET status = 'in_progress', updated_at = datetime('now')
                        WHERE id = ? AND doctor_id = ?
                    """, (row['appointment_id'], doctor_id))

                consultations.append({
                    'appointment_id':   row['appointment_id'],
                    'patient_id':       row['patient_id'],
                    'patient_name':     f"{row['first_name']} {row['last_name']}",
                    'patient_initials': f"{row['first_name'][0]}{row['last_name'][0]}",
                    'patient_number':   row['patient_number'],
                    'age':              age,
                    'gender':           row['gender'],
                    'phone':            row['phone'],
                    'appointment_time': format_time(row['start_time']),
                    'room':             row['room'] or 'TBD',
                    'has_notes':        row['note_id'] is not None,
                    'note_id':          row['note_id']
                })

            db.commit()  # commit the status updates

        db.close()
        return jsonify({'success': True, 'consultations': consultations}), 200

    except Exception as e:
        print(f"Get active consultations error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch active consultations'}), 500


# =========================================
# Get Patient Data for Consultation — unchanged from v1
# =========================================

@consult_bp.route('/patient/<int:patient_id>', methods=['GET'])
@login_required
@doctor_required
def get_patient_for_consult(patient_id):
    try:
        doctor_id = session.get('user_id')
        appointment_id = request.args.get('appointment_id', type=int)
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT id, patient_number, first_name, last_name, dob, gender,
                       phone, email, address, emergency_contact_name, emergency_contact_phone,
                       allergies, chronic_conditions, current_medications,
                       medical_alerts, registration_date
                FROM patients WHERE id = ? AND status = 'active'
            """, (patient_id,))
            patient = cursor.fetchone()
            if not patient:
                return jsonify({'error': 'Patient not found'}), 404

            age = None
            if patient['dob']:
                today = datetime.now().date()
                age = today.year - patient['dob'].year - (
                    (today.month, today.day) < (patient['dob'].month, patient['dob'].day))

            # Use _find_existing_note — DB is source of truth
            existing_note_id = None
            parsed_data = {}
            if appointment_id:
                existing_note_id, note_content = _find_existing_note(
                    cursor, appointment_id)
                if note_content:
                    parsed_data = parse_notes_content(note_content)

            cursor.execute("""
                SELECT bp_systolic, bp_diastolic, heart_rate,
                       temperature, oxygen_saturation, recorded_at
                FROM vitals WHERE patient_id = ?
                ORDER BY recorded_at DESC LIMIT 1
            """, (patient_id,))
            vitals = cursor.fetchone()

            cursor.execute("""
                SELECT a.appointment_date, s.name as procedure_name, a.notes
                FROM appointments a
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE a.patient_id = ? AND a.doctor_id = ?
                ORDER BY a.appointment_date DESC LIMIT 5
            """, (patient_id, doctor_id))
            recent_procedures = cursor.fetchall()

            cursor.execute(
                "SELECT first_name, last_name, specialization FROM users WHERE id = ?", (doctor_id,))
            doctor = cursor.fetchone()

            cursor.execute("""
                SELECT setting_key, setting_value FROM clinic_settings
                WHERE setting_key IN ('clinic_name', 'clinic_address', 'clinic_phone', 'clinic_email')
            """)
            clinic_settings = {
                row['setting_key']: row['setting_value'] for row in cursor.fetchall()}

        db.close()
        return jsonify({'success': True, 'patient': {
            'id':             patient['id'],
            'patient_number': patient['patient_number'],
            'first_name':     patient['first_name'],
            'last_name':      patient['last_name'],
            'full_name':      f"{patient['first_name']} {patient['last_name']}",
            'age':            age,
            'gender':         patient['gender'],
            'phone':          patient['phone'],
            'email':          patient['email'],
            'address':        patient['address'],
            'dob':            patient['dob'].strftime('%b %d, %Y') if patient['dob'] else '',
            'emergency_contact': {
                'name':  patient['emergency_contact_name'],
                'phone': patient['emergency_contact_phone']
            },
            'medical_history': {
                'allergies':           patient['allergies'],
                'chronic_conditions':  patient['chronic_conditions'],
                'current_medications': patient['current_medications'],
                'medical_alerts':      patient['medical_alerts']
            },
            'vitals': {
                'bp_systolic':       vitals['bp_systolic'] if vitals else None,
                'bp_diastolic':      vitals['bp_diastolic'] if vitals else None,
                'heart_rate':        vitals['heart_rate'] if vitals else None,
                'temperature':       vitals['temperature'] if vitals else None,
                'oxygen_saturation': vitals['oxygen_saturation'] if vitals else None
            },
            'recent_procedures': [{
                'date':      p['appointment_date'].strftime('%b %d, %Y') if p['appointment_date'] else '',
                'procedure': p['procedure_name'] or 'Consultation',
                'notes':     p['notes']
            } for p in recent_procedures],
            'doctor': {
                'name':           f"Dr. {doctor['first_name']} {doctor['last_name']}" if doctor else 'Doctor',
                'specialization': doctor['specialization'] if doctor else 'General Dentistry'
            },
            'clinic': {
                'name':    clinic_settings.get('clinic_name'),
                'address': clinic_settings.get('clinic_address'),
                'phone':   clinic_settings.get('clinic_phone'),
                'email':   clinic_settings.get('clinic_email')
            },
            'existing_note_id': existing_note_id,
            'existing_content': parsed_data
        }}), 200

    except Exception as e:
        print(f"Get patient for consult error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch patient data'}), 500


# =========================================
# Save Consultation Notes
# =========================================

@consult_bp.route('/save', methods=['POST'])
@login_required
@doctor_required
def save_consultation():
    try:
        data = request.get_json()
        doctor_id = session.get('user_id')

        patient_id = data.get('patient_id')
        appointment_id = data.get('appointment_id')
        # frontend sends this but we don't trust it — we look up DB instead
        # existing_note_id = data.get('existing_note_id')  ← intentionally ignored

        presenting_complain = data.get('presenting_complain', '')
        history = data.get('history', '')
        eoe = data.get('eoe', '')
        ioe = data.get('ioe', '')
        others = data.get('others', '')
        diagnosis = data.get('diagnosis', '')
        treatment_plan = data.get('treatment_plan', '')
        treatment = data.get('treatment', '')
        treatment_done = data.get('treatment_done', '')
        review_date = data.get('review_date')
        review_notes = data.get('review_notes', '')
        teeth_findings = data.get('teeth_findings', {})

        # Format teeth by quadrant — same as v1
        present_by_quadrant = format_teeth_by_quadrant(
            teeth_findings.get('present', []))
        missing_by_quadrant = format_teeth_by_quadrant(
            teeth_findings.get('missing', []))
        mobile_by_quadrant = format_teeth_by_quadrant(
            teeth_findings.get('mobile', []))
        carious_by_quadrant = format_teeth_by_quadrant(
            teeth_findings.get('carious', []))
        fractured_by_quadrant = format_teeth_by_quadrant(
            teeth_findings.get('fractured', []))
        impacted_by_quadrant = format_teeth_by_quadrant(
            teeth_findings.get('impacted', []))
        periodontal_by_quadrant = format_teeth_by_quadrant(
            teeth_findings.get('periodontal', []))

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute(
                "SELECT first_name, last_name, specialization FROM users WHERE id = ?", (doctor_id,))
            doctor = cursor.fetchone()

            nurse_name = ""
            if appointment_id:
                cursor.execute("""
                    SELECT u.first_name, u.last_name FROM assists a
                    JOIN users u ON a.nurse_id = u.id
                    WHERE a.appointment_id = ?
                """, (appointment_id,))
                nurse = cursor.fetchone()
                if nurse:
                    nurse_name = f"Nurse {nurse['first_name']} {nurse['last_name']}"

            # Build content in EXACT v1 format
            content = f"""=== CONSULTATION NOTES ===
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

=== PRESENTING COMPLAINT ===
{presenting_complain if presenting_complain else 'none'}

=== HISTORY ===
{history if history else 'none'}

=== EXTRAORAL EXAMINATION ===
{eoe if eoe else 'none'}

=== INTRAORAL EXAMINATION ===
{ioe if ioe else 'none'}

=== TEETH FINDINGS ===
{format_teeth_display(present_by_quadrant, 'Teeth Present')}

{format_teeth_display(missing_by_quadrant, 'Missing Teeth')}

{format_teeth_display(mobile_by_quadrant, 'Mobile Teeth')}

{format_teeth_display(carious_by_quadrant, 'Carious Teeth')}

{format_teeth_display(fractured_by_quadrant, 'Fractured Teeth')}

{format_teeth_display(impacted_by_quadrant, 'Impacted Teeth')}

{format_teeth_display(periodontal_by_quadrant, 'Periodontal Pocket')}

=== OTHER FINDINGS ===
{others if others else 'none'}

=== DIAGNOSIS ===
{diagnosis if diagnosis else 'none'}

=== TREATMENT PLAN ===
{treatment_plan if treatment_plan else 'none'}

=== TREATMENT PERFORMED ===
{treatment if treatment else 'none'}

=== TREATMENT DONE ===
{treatment_done if treatment_done else 'none'}

=== REVIEW ===
Review Date: {review_date if review_date else 'Not scheduled'}
Review Notes: {review_notes if review_notes else 'none'}

=== STAFF ===
Doctor: Dr. {doctor['first_name']} {doctor['last_name']} ({doctor['specialization'] or 'General Dentistry'})
Nurse: {nurse_name if nurse_name else 'None assigned'}"""

            # ── THE FIX: always query DB, never trust frontend ─────────────
            note_id, _ = _find_existing_note(cursor, appointment_id)

            if note_id:
                # Note exists → UPDATE
                cursor.execute("""
                    UPDATE medical_notes
                    SET content = ?, updated_at = datetime('now')
                    WHERE id = ?
                """, (content, note_id))
                message = "Consultation notes updated"
            else:
                # No note yet → INSERT (only ever happens once per appointment)
                cursor.execute("""
                    INSERT INTO medical_notes
                        (patient_id, author_id, appointment_id, note_date, note_type, content)
                    VALUES (?, ?, ?, datetime('now'), 'general', ?)
                """, (patient_id, doctor_id, appointment_id, content))
                note_id = cursor.lastrowid
                message = "Consultation notes saved"
            # ────────────────────────────────────────────────────────────────

            # Keep appointment in_progress (don't overwrite notes field with timestamps)
            if appointment_id:
                cursor.execute("""
                    UPDATE appointments
                    SET status = 'in_progress', updated_at = datetime('now')
                    WHERE id = ? AND doctor_id = ? AND status != 'completed'
                """, (appointment_id, doctor_id))

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': message, 'note_id': note_id}), 200

    except Exception as e:
        print(f"Save consultation error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to save consultation'}), 500


# =========================================
# Complete Consultation
# =========================================

@consult_bp.route('/complete', methods=['POST'])
@login_required
@doctor_required
def complete_consultation():
    try:
        data = request.get_json()
        doctor_id = session.get('user_id')

        patient_id = data.get('patient_id')
        appointment_id = data.get('appointment_id')

        # All fields — identical to save_consultation
        presenting_complain = data.get('presenting_complain', '')
        history = data.get('history', '')
        eoe = data.get('eoe', '')
        ioe = data.get('ioe', '')
        others = data.get('others', '')
        diagnosis = data.get('diagnosis', '')
        treatment_plan = data.get('treatment_plan', '')
        treatment = data.get('treatment', '')
        treatment_done = data.get('treatment_done', '')
        review_date = data.get('review_date')
        review_notes = data.get('review_notes', '')
        teeth_findings = data.get('teeth_findings', {})
        final_notes = data.get('final_notes', '')

        # Merge final notes into review notes if provided
        if final_notes:
            review_notes = (review_notes + f"\n\nFinal Notes: {final_notes}").strip(
            ) if review_notes else f"Final Notes: {final_notes}"

        # Format teeth — same as save_consultation
        present_by_quadrant = format_teeth_by_quadrant(
            teeth_findings.get('present', []))
        missing_by_quadrant = format_teeth_by_quadrant(
            teeth_findings.get('missing', []))
        mobile_by_quadrant = format_teeth_by_quadrant(
            teeth_findings.get('mobile', []))
        carious_by_quadrant = format_teeth_by_quadrant(
            teeth_findings.get('carious', []))
        fractured_by_quadrant = format_teeth_by_quadrant(
            teeth_findings.get('fractured', []))
        impacted_by_quadrant = format_teeth_by_quadrant(
            teeth_findings.get('impacted', []))
        periodontal_by_quadrant = format_teeth_by_quadrant(
            teeth_findings.get('periodontal', []))

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute(
                "SELECT first_name, last_name, specialization FROM users WHERE id = ?",
                (doctor_id,))
            doctor = cursor.fetchone()

            nurse_name = ""
            if appointment_id:
                cursor.execute("""
                    SELECT u.first_name, u.last_name FROM assists a
                    JOIN users u ON a.nurse_id = u.id
                    WHERE a.appointment_id = ?
                """, (appointment_id,))
                nurse = cursor.fetchone()
                if nurse:
                    nurse_name = f"Nurse {nurse['first_name']} {nurse['last_name']}"

            # Build note — IDENTICAL format to save_consultation
            # Only difference: header is "=== CONSULTATION COMPLETED ===" not "=== CONSULTATION NOTES ==="
            content = f"""=== CONSULTATION COMPLETED ===
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
 
=== PRESENTING COMPLAINT ===
{presenting_complain if presenting_complain else 'none'}
 
=== HISTORY ===
{history if history else 'none'}
 
=== EXTRAORAL EXAMINATION ===
{eoe if eoe else 'none'}
 
=== INTRAORAL EXAMINATION ===
{ioe if ioe else 'none'}
 
=== TEETH FINDINGS ===
{format_teeth_display(present_by_quadrant, 'Teeth Present')}
 
{format_teeth_display(missing_by_quadrant, 'Missing Teeth')}
 
{format_teeth_display(mobile_by_quadrant, 'Mobile Teeth')}
 
{format_teeth_display(carious_by_quadrant, 'Carious Teeth')}
 
{format_teeth_display(fractured_by_quadrant, 'Fractured Teeth')}
 
{format_teeth_display(impacted_by_quadrant, 'Impacted Teeth')}
 
{format_teeth_display(periodontal_by_quadrant, 'Periodontal Pocket')}
 
=== OTHER FINDINGS ===
{others if others else 'none'}
 
=== DIAGNOSIS ===
{diagnosis if diagnosis else 'none'}
 
=== TREATMENT PLAN ===
{treatment_plan if treatment_plan else 'none'}
 
=== TREATMENT PERFORMED ===
{treatment if treatment else 'none'}
 
=== TREATMENT DONE ===
{treatment_done if treatment_done else 'none'}
 
=== REVIEW ===
Review Date: {review_date if review_date else 'Not scheduled'}
Review Notes: {review_notes if review_notes else 'none'}
 
=== STAFF ===
Doctor: Dr. {doctor['first_name']} {doctor['last_name']} ({doctor['specialization'] or 'General Dentistry'})
Nurse: {nurse_name if nurse_name else 'None assigned'}"""

            if appointment_id:
                # DB-first lookup — same pattern as save_consultation
                note_id, _ = _find_existing_note(cursor, appointment_id)

                if note_id:
                    # OVERWRITE the existing note — no append, no new row
                    cursor.execute("""
                        UPDATE medical_notes
                        SET content = ?, updated_at = datetime('now')
                        WHERE id = ?
                    """, (content, note_id))
                else:
                    # No note exists yet (doctor skipped Save and went straight to Complete)
                    # Create it now — still just one row
                    cursor.execute("""
                        INSERT INTO medical_notes
                            (patient_id, author_id, appointment_id, note_date, note_type, content)
                        VALUES (?, ?, ?, datetime('now'), 'general', ?)
                    """, (patient_id, doctor_id, appointment_id, content))

                # Mark appointment completed
                cursor.execute("""
                    UPDATE appointments SET status = 'completed', updated_at = datetime('now')
                    WHERE id = ? AND doctor_id = ?
                """, (appointment_id, doctor_id))

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Consultation completed successfully'}), 200

    except Exception as e:
        print(f"Complete consultation error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to complete consultation'}), 500

# =========================================
# Save Vitals — unchanged from v1
# =========================================


@consult_bp.route('/vitals', methods=['POST'])
@login_required
@doctor_required
def save_vitals():
    try:
        data = request.get_json()
        doctor_id = session.get('user_id')

        patient_id = data.get('patient_id')
        bp_systolic = data.get('bp_systolic')
        bp_diastolic = data.get('bp_diastolic')
        heart_rate = data.get('heart_rate')
        temperature = data.get('temperature')
        oxygen_saturation = data.get('oxygen_saturation')
        appointment_id = data.get('appointment_id')

        bp_systolic = int(bp_systolic) if bp_systolic else None
        bp_diastolic = int(bp_diastolic) if bp_diastolic else None
        heart_rate = int(heart_rate) if heart_rate else None
        temperature = float(temperature) if temperature else None
        oxygen_saturation = int(
            oxygen_saturation) if oxygen_saturation else None

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                INSERT INTO vitals
                    (patient_id, appointment_id, recorded_by, recorded_at,
                     bp_systolic, bp_diastolic, heart_rate, temperature, oxygen_saturation)
                VALUES (?, ?, ?, datetime('now'), ?, ?, ?, ?, ?)
            """, (patient_id, appointment_id, doctor_id,
                  bp_systolic, bp_diastolic, heart_rate, temperature, oxygen_saturation))
            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Vitals saved successfully'}), 200

    except Exception as e:
        print(f"Save vitals error: {e}")
        return jsonify({'error': 'Failed to save vitals'}), 500


# =========================================
# Get Medicines — unchanged from v1
# =========================================

@consult_bp.route('/medicines', methods=['GET'])
@login_required
@doctor_required
def get_medicines():
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT id, name, category, unit, price,
                       current_stock as stock, min_threshold, requires_prescription
                FROM inventory_items
                WHERE is_active = 1
                ORDER BY name
            """)
            medicines = cursor.fetchall()

            for med in medicines:
                if med['stock'] <= 0:
                    med['stock_status'] = 'out-of-stock'
                    med['stock_badge'] = {
                        'text': 'Out of Stock', 'class': 'error'}
                elif med['stock'] <= med['min_threshold']:
                    med['stock_status'] = 'low-stock'
                    med['stock_badge'] = {
                        'text': 'Low Stock', 'class': 'warning'}
                else:
                    med['stock_status'] = 'in-stock'
                    med['stock_badge'] = {
                        'text': 'In Stock', 'class': 'success'}

                med['rx_badge'] = (
                    {'text': 'Rx Required', 'class': 'info'}
                    if med['requires_prescription']
                    else {'text': 'OTC', 'class': 'secondary'}
                )

        db.close()
        return jsonify({'success': True, 'medicines': medicines}), 200

    except Exception as e:
        print(f"Get medicines error: {e}")
        return jsonify({'error': 'Failed to fetch medicines'}), 500


# =========================================
# Create Prescription — fixed number collision, otherwise same as v1
# =========================================

@consult_bp.route('/prescription', methods=['POST'])
@login_required
@doctor_required
def create_prescription():
    try:
        data = request.get_json()
        doctor_id = session.get('user_id')

        patient_id = data.get('patient_id')
        items = data.get('items', [])
        notes = data.get('notes', '')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Insert with placeholder, update with id-based number (no collision)
            cursor.execute("""
                INSERT INTO prescriptions
                    (prescription_number, patient_id, prescriber_id, prescription_date, status, notes)
                VALUES ('PENDING', ?, ?, date('now'), 'active', ?)
            """, (patient_id, doctor_id, notes))

            prescription_id = cursor.lastrowid
            prescription_number = f"RX-{datetime.now().strftime('%Y%m%d')}-{prescription_id:04d}"
            cursor.execute(
                "UPDATE prescriptions SET prescription_number = ? WHERE id = ?",
                (prescription_number, prescription_id)
            )

            for item in items:
                cursor.execute("""
                    INSERT INTO prescription_items
                        (prescription_id, inventory_item_id, dosage, frequency, duration, instructions, quantity)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (prescription_id, item['medicine_id'], item['dosage'],
                      item.get('frequency', ''), item.get('duration', ''),
                      item.get('instructions', ''), 1))

            db.commit()

        db.close()
        return jsonify({
            'success':             True,
            'message':             'Prescription created',
            'prescription_number': prescription_number
        }), 200

    except Exception as e:
        print(f"Create prescription error: {e}")
        return jsonify({'error': 'Failed to create prescription'}), 500
