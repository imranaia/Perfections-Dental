-- =========================================
-- Perfections Dental Services
-- SQLite Schema — v2.0 (post MySQL -> SQLite migration)
-- =========================================

PRAGMA foreign_keys = ON;

-- =========================================
-- Roles & Staff Users
-- =========================================
CREATE TABLE IF NOT EXISTS roles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,  -- superadmin | doctor | nurse | reception
    description TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id             TEXT UNIQUE,
    role_id                 INTEGER NOT NULL REFERENCES roles(id),
    first_name              TEXT NOT NULL,
    last_name               TEXT NOT NULL,
    email                   TEXT NOT NULL UNIQUE,
    password_hash           TEXT NOT NULL,
    phone                   TEXT,
    license_number          TEXT,
    specialization          TEXT,
    qualifications          TEXT,
    experience_years        INTEGER,
    gender                  TEXT,
    avatar                  TEXT,
    status                  TEXT NOT NULL DEFAULT 'active',   -- active | inactive | suspended
    emergency_contact_name  TEXT,
    emergency_contact_phone TEXT,
    date_joined             DATETIME DEFAULT (datetime('now')),
    created_at              DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at              DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_shifts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day_of_week INTEGER NOT NULL,          -- 0=Sunday .. 6=Saturday
    shift_name  TEXT NOT NULL,             -- morning | afternoon | evening
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL
);

-- Staff scheduling (shift + working-day matrix), used by staff profile pages
CREATE TABLE IF NOT EXISTS shifts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL UNIQUE,      -- morning | afternoon | evening
    display_name TEXT,
    start_time   TEXT,
    end_time     TEXT
);

CREATE TABLE IF NOT EXISTS work_days (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,        -- Monday..Sunday
    day_number INTEGER NOT NULL             -- 1=Monday .. 7=Sunday
);

CREATE TABLE IF NOT EXISTS staff_schedule (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day_id            INTEGER NOT NULL REFERENCES work_days(id),
    is_working        INTEGER NOT NULL DEFAULT 1,
    custom_start_time TEXT,
    custom_end_time   TEXT
);

CREATE TABLE IF NOT EXISTS staff_shifts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    shift_id       INTEGER NOT NULL REFERENCES shifts(id),
    effective_from DATE DEFAULT (date('now')),
    is_current     INTEGER NOT NULL DEFAULT 1
);

-- =========================================
-- Patients (also serves as the patient-portal account)
-- =========================================
CREATE TABLE IF NOT EXISTS patients (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_number        TEXT UNIQUE,
    first_name            TEXT NOT NULL,
    last_name             TEXT NOT NULL,
    email                 TEXT UNIQUE,
    phone                 TEXT UNIQUE,
    password_hash         TEXT,                    -- NULL until patient activates portal access
    dob                   DATE,
    gender                TEXT,
    address               TEXT,
    emergency_contact_name  TEXT,
    emergency_contact_phone TEXT,
    insurance_provider    TEXT,
    policy_number         TEXT,
    allergies             TEXT,
    chronic_conditions    TEXT,
    current_medications   TEXT,
    medical_alerts        TEXT,
    blood_group           TEXT,
    receptionist_name     TEXT,
    signature_date        DATE,
    signature_data        TEXT,
    portal_active         INTEGER NOT NULL DEFAULT 0,
    status                TEXT NOT NULL DEFAULT 'active',
    registration_date     DATE NOT NULL DEFAULT (date('now')),
    created_at            DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at            DATETIME NOT NULL DEFAULT (datetime('now'))
);

-- =========================================
-- Services (procedures the clinic offers/bills)
-- =========================================
CREATE TABLE IF NOT EXISTS service_categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    color       TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS services (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id   INTEGER REFERENCES service_categories(id),
    name          TEXT NOT NULL,
    code          TEXT,
    description   TEXT,
    price         REAL NOT NULL DEFAULT 0,
    tax_rate      REAL NOT NULL DEFAULT 0,
    duration_minutes INTEGER DEFAULT 30,
    is_active     INTEGER NOT NULL DEFAULT 1,
    is_emergency  INTEGER NOT NULL DEFAULT 0,
    emergency_priority TEXT,
    color         TEXT,
    created_at    DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at    DATETIME NOT NULL DEFAULT (datetime('now')),
    duration_mins INTEGER GENERATED ALWAYS AS (duration_minutes) VIRTUAL
);

-- =========================================
-- Appointment requests (patient self-service booking, first-come-first-served)
-- Declared before appointments so appointments.request_id can reference it.
-- =========================================
CREATE TABLE IF NOT EXISTS appointment_requests (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id          INTEGER NOT NULL REFERENCES patients(id),
    preferred_doctor_id INTEGER REFERENCES users(id),
    service_id          INTEGER REFERENCES services(id),
    requested_date      TEXT NOT NULL,     -- date
    requested_time      TEXT NOT NULL,     -- HH:MM slot start
    reason              TEXT,
    status              TEXT NOT NULL DEFAULT 'pending',
    -- pending | confirmed | rejected | expired
    resolved_appointment_id INTEGER,
    resolved_by         INTEGER REFERENCES users(id),
    resolved_at         TEXT,
    created_at          DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_appt_requests_slot
    ON appointment_requests(requested_date, requested_time, status, created_at);

-- =========================================
-- Appointments
-- =========================================
CREATE TABLE IF NOT EXISTS appointments (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_number TEXT,
    patient_id        INTEGER NOT NULL REFERENCES patients(id),
    doctor_id         INTEGER REFERENCES users(id),  -- nullable: nurse-only appointments have no doctor
    service_id        INTEGER REFERENCES services(id),
    appointment_date  DATETIME NOT NULL,   -- authoritative full timestamp
    start_time        TEXT,                -- HH:MM, redundant convenience column for display
    end_time          TEXT,                -- HH:MM, derived from start_time + duration_mins
    type              TEXT DEFAULT 'consultation',
    room              TEXT,
    nurse_id          INTEGER REFERENCES users(id),  -- direct assignment for nurse-only procedures
    duration_mins     INTEGER DEFAULT 30,
    status            TEXT NOT NULL DEFAULT 'scheduled',
    -- scheduled | confirmed | waiting | in_progress | completed | cancelled | no_show
    reason            TEXT,
    notes             TEXT,
    emergency_priority TEXT,   -- critical | high | medium | low, NULL for non-emergency
    completed_at      DATETIME,
    created_by        TEXT NOT NULL DEFAULT 'reception',  -- reception | patient_portal
    request_id        INTEGER REFERENCES appointment_requests(id),
    created_at        DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at        DATETIME NOT NULL DEFAULT (datetime('now'))
);

-- Services actually rendered during a visit (billable line items)
CREATE TABLE IF NOT EXISTS appointment_services (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_id  INTEGER NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,
    service_id      INTEGER NOT NULL REFERENCES services(id),
    quantity        INTEGER NOT NULL DEFAULT 1,
    unit_price      REAL NOT NULL DEFAULT 0,
    price           REAL GENERATED ALWAYS AS (unit_price) VIRTUAL,
    total           REAL GENERATED ALWAYS AS (unit_price * quantity) VIRTUAL,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now'))
);

-- =========================================
-- Clinical notes (consult / pre-op / procedure / vitals)
-- =========================================
CREATE TABLE IF NOT EXISTS medical_notes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_id  INTEGER REFERENCES appointments(id) ON DELETE CASCADE,  -- nullable: walk-in consult notes may predate a booked visit
    patient_id      INTEGER NOT NULL REFERENCES patients(id),
    author_id       INTEGER NOT NULL REFERENCES users(id),
    note_type       TEXT NOT NULL,     -- pre_op | consultation | procedure | discharge
    content         TEXT NOT NULL,
    vitals_json     TEXT,
    note_date       DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vitals (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id         INTEGER NOT NULL REFERENCES patients(id),
    appointment_id     INTEGER REFERENCES appointments(id),
    recorded_by        INTEGER REFERENCES users(id),
    recorded_at        DATETIME NOT NULL DEFAULT (datetime('now')),
    bp_systolic        INTEGER,
    bp_diastolic       INTEGER,
    heart_rate         INTEGER,
    temperature        REAL,
    oxygen_saturation  INTEGER
);

CREATE INDEX IF NOT EXISTS idx_vitals_patient ON vitals(patient_id, recorded_at);

-- =========================================
-- Inventory (medications & supplies) — declared before prescriptions
-- so prescription_items can reference inventory_items.
-- =========================================
CREATE TABLE IF NOT EXISTS inventory_categories (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS inventory_items (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id      INTEGER REFERENCES inventory_categories(id),
    category         TEXT,           -- plain-text label some legacy queries filter/search directly
    name             TEXT NOT NULL,
    sku              TEXT UNIQUE,
    manufacturer     TEXT,
    unit             TEXT DEFAULT 'unit',
    current_stock    INTEGER NOT NULL DEFAULT 0,
    min_threshold    INTEGER NOT NULL DEFAULT 0,
    max_stock        INTEGER,
    location         TEXT,
    expiry_date      DATE,
    batch_number     TEXT,
    description      TEXT,
    notes            TEXT,
    price            REAL NOT NULL DEFAULT 0,
    requires_prescription INTEGER NOT NULL DEFAULT 0,
    nurse_eligible   INTEGER NOT NULL DEFAULT 0,   -- may a nurse prescribe this without doctor sign-off
    is_active        INTEGER NOT NULL DEFAULT 1,
    created_at       DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at       DATETIME NOT NULL DEFAULT (datetime('now')),
    unit_price       REAL GENERATED ALWAYS AS (price) VIRTUAL
);

CREATE TABLE IF NOT EXISTS inventory_transactions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id          INTEGER NOT NULL REFERENCES inventory_items(id),
    quantity         INTEGER NOT NULL,      -- negative = deducted, positive = restocked
    type             TEXT NOT NULL,         -- usage | restock | adjustment | wastage
    reason           TEXT,                  -- free-text note, separate from type
    reference_type   TEXT,                  -- prescription | manual
    reference_id     INTEGER,
    reference_number TEXT,
    staff_id         INTEGER REFERENCES users(id),
    transaction_date DATETIME NOT NULL DEFAULT (datetime('now')),
    change_qty       INTEGER GENERATED ALWAYS AS (quantity) VIRTUAL,
    performed_by     INTEGER GENERATED ALWAYS AS (staff_id) VIRTUAL,
    created_at       DATETIME GENERATED ALWAYS AS (transaction_date) VIRTUAL
);

-- =========================================
-- Prescriptions — written by doctor or nurse, fulfilled by RECEPTION
-- (no separate pharmacy role: reception is the single dispensing point)
-- =========================================
CREATE TABLE IF NOT EXISTS prescriptions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    prescription_number TEXT NOT NULL UNIQUE,
    patient_id          INTEGER NOT NULL REFERENCES patients(id),
    appointment_id      INTEGER REFERENCES appointments(id),
    prescribed_by       INTEGER NOT NULL REFERENCES users(id),
    prescribed_by_role  TEXT NOT NULL,     -- doctor | nurse
    status              TEXT NOT NULL DEFAULT 'pending_dispense',
    -- pending_dispense | dispensed | partially_dispensed | cancelled
    notes               TEXT,
    dispensed_by        INTEGER REFERENCES users(id),
    dispensed_at        TEXT,
    created_at          DATETIME NOT NULL DEFAULT (datetime('now')),
    -- aliases matching the naming legacy dashboard/report queries expect
    prescriber_id       INTEGER GENERATED ALWAYS AS (prescribed_by) VIRTUAL,
    prescription_date   DATETIME GENERATED ALWAYS AS (created_at) VIRTUAL
);

CREATE TABLE IF NOT EXISTS prescription_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    prescription_id   INTEGER NOT NULL REFERENCES prescriptions(id) ON DELETE CASCADE,
    inventory_item_id INTEGER NOT NULL REFERENCES inventory_items(id),
    dosage            TEXT,
    frequency         TEXT,
    duration          TEXT,
    instructions      TEXT,
    quantity          INTEGER NOT NULL,
    unit_price        REAL NOT NULL DEFAULT 0,
    dispensed         INTEGER NOT NULL DEFAULT 0,
    dispensed_qty     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_prescriptions_status ON prescriptions(status, created_at);

-- =========================================
-- Billing — invoices raised by reception (covers services + dispensed drugs)
-- =========================================
CREATE TABLE IF NOT EXISTS invoices (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT NOT NULL UNIQUE,
    patient_id     INTEGER NOT NULL REFERENCES patients(id),
    appointment_id INTEGER REFERENCES appointments(id),
    prescription_id INTEGER REFERENCES prescriptions(id),
    invoice_date   DATE NOT NULL DEFAULT (date('now')),
    subtotal       REAL NOT NULL DEFAULT 0,
    tax            REAL NOT NULL DEFAULT 0,
    discount       REAL NOT NULL DEFAULT 0,
    total          REAL NOT NULL DEFAULT 0,
    amount_paid    REAL NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'unpaid',   -- unpaid | partial | paid | cancelled
    due_date       DATE,
    notes          TEXT,
    discount_reason      TEXT,
    discount_status      TEXT,   -- pending | approved | rejected
    discount_approved_by INTEGER REFERENCES users(id),
    discount_approved_at DATETIME,
    discount_rejected_by INTEGER REFERENCES users(id),
    discount_rejected_at DATETIME,
    created_by     INTEGER REFERENCES users(id),
    created_at     DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at     DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS invoice_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id  INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    item_type   TEXT NOT NULL,      -- service | medication
    reference_id INTEGER,
    quantity    INTEGER NOT NULL DEFAULT 1,
    unit_price  REAL NOT NULL DEFAULT 0,
    line_total  REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS payments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id    INTEGER NOT NULL REFERENCES invoices(id),
    amount        REAL NOT NULL,
    payment_method TEXT NOT NULL DEFAULT 'cash',   -- cash | pos | transfer | cheque | free
    reference     TEXT,
    notes         TEXT,
    received_by   INTEGER REFERENCES users(id),
    payment_date  DATETIME NOT NULL DEFAULT (datetime('now')),
    created_at    DATETIME NOT NULL DEFAULT (datetime('now')),
    method        TEXT GENERATED ALWAYS AS (payment_method) VIRTUAL
);

-- =========================================
-- Nurse assists / tasks
-- =========================================
CREATE TABLE IF NOT EXISTS assists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nurse_id        INTEGER NOT NULL REFERENCES users(id),
    appointment_id  INTEGER NOT NULL REFERENCES appointments(id),
    status          TEXT NOT NULL DEFAULT 'assigned',  -- assigned | in_progress | completed
    notes           TEXT,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name    TEXT NOT NULL,
    description  TEXT,
    assigned_to  INTEGER NOT NULL REFERENCES users(id),
    assigned_by  INTEGER REFERENCES users(id),
    patient_id   INTEGER REFERENCES patients(id),
    due_date     TEXT,
    priority     TEXT DEFAULT 'medium',   -- high | medium | low
    status       TEXT NOT NULL DEFAULT 'pending',   -- pending | in_progress | completed
    completed_at DATETIME,
    notes        TEXT,
    created_at   DATETIME NOT NULL DEFAULT (datetime('now')),
    created_by   INTEGER GENERATED ALWAYS AS (assigned_by) VIRTUAL
);

-- =========================================
-- Notifications (used by patient portal + staff dashboards)
-- =========================================
CREATE TABLE IF NOT EXISTS notifications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_type TEXT NOT NULL,     -- user | patient
    recipient_id INTEGER NOT NULL,
    title        TEXT NOT NULL,
    body         TEXT,
    is_read      INTEGER NOT NULL DEFAULT 0,
    created_at   DATETIME NOT NULL DEFAULT (datetime('now'))
);

-- =========================================
-- Audit log
-- =========================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    patient_id  INTEGER,
    action      TEXT NOT NULL,
    table_name  TEXT,
    record_id   INTEGER,
    old_data    TEXT,
    new_data    TEXT,
    ip_address  TEXT,
    user_agent  TEXT,
    created_at  DATETIME NOT NULL DEFAULT (datetime('now'))
);

-- Generic clinic-wide key/value settings (superadmin/settings.py)
CREATE TABLE IF NOT EXISTS clinic_settings (
    setting_key   TEXT PRIMARY KEY,
    setting_value TEXT,
    updated_at    DATETIME NOT NULL DEFAULT (datetime('now'))
);

-- Landing page "Meet Your Smile Architects" team section (superadmin/team.py)
CREATE TABLE IF NOT EXISTS team_members (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    role_title    TEXT NOT NULL,
    bio           TEXT,
    photo_url     TEXT,
    tags          TEXT,              -- comma-separated, e.g. "Implantology,Laser Dentistry"
    display_order INTEGER NOT NULL DEFAULT 0,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at    DATETIME NOT NULL DEFAULT (datetime('now'))
);

-- Enforces first-come-first-served booking: one non-cancelled appointment
-- per doctor per exact datetime slot.
CREATE UNIQUE INDEX IF NOT EXISTS idx_appt_slot_unique
    ON appointments(doctor_id, appointment_date)
    WHERE status != 'cancelled';

CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(appointment_date);
CREATE INDEX IF NOT EXISTS idx_appointments_doctor ON appointments(doctor_id);
CREATE INDEX IF NOT EXISTS idx_invoices_patient ON invoices(patient_id);
CREATE INDEX IF NOT EXISTS idx_payments_invoice ON payments(invoice_id);
