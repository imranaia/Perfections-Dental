-- =========================================
-- Perfections Dental Services — Demo Seed Data
-- Password for every seeded account (staff + patient portal): 1234
-- =========================================

INSERT INTO roles (name, description) VALUES
('superadmin', 'Full clinic administration and oversight'),
('doctor', 'Clinical consultation, diagnosis, and prescribing'),
('nurse', 'Chairside assistance and nurse-eligible prescribing'),
('reception', 'Front desk, billing, and prescription dispensing');

INSERT INTO shifts (name, display_name, start_time, end_time) VALUES
('morning', 'Morning Shift', '08:00', '14:00'),
('afternoon', 'Afternoon Shift', '12:00', '18:00'),
('evening', 'Evening Shift', '14:00', '20:00');

INSERT INTO work_days (name, day_number) VALUES
('Monday', 1), ('Tuesday', 2), ('Wednesday', 3), ('Thursday', 4),
('Friday', 5), ('Saturday', 6), ('Sunday', 7);

-- password_hash below = werkzeug generate_password_hash('1234')
INSERT INTO users (employee_id, role_id, first_name, last_name, email, password_hash, phone, license_number, specialization, qualifications, experience_years, gender, status)
VALUES
('EMP-0001', (SELECT id FROM roles WHERE name='superadmin'), 'Saadu', 'Dodo', 'admin@perfectionsdental.ng',
 'scrypt:32768:8:1$Zll1reeBxGLRArec$13cc7ef23ba15a30db4fb834c06a31230e8a41e6088f3dd93da39b434e3160892b336d735d8b4a6f45800f48a18385d5cd030859729572f649da03fcfe4819ad',
 '+2348023456701', 'BDS/MSc/2007', 'Implantology', 'BDS, MSc (Implantology)', 18, 'Male', 'active'),

('EMP-0002', (SELECT id FROM roles WHERE name='doctor'), 'Fatima', 'Bello', 'doctor@perfectionsdental.ng',
 'scrypt:32768:8:1$Zll1reeBxGLRArec$13cc7ef23ba15a30db4fb834c06a31230e8a41e6088f3dd93da39b434e3160892b336d735d8b4a6f45800f48a18385d5cd030859729572f649da03fcfe4819ad',
 '+2348023456702', 'ORTHO/2011', 'Orthodontics', 'BDS, Certified Invisalign Provider', 12, 'Female', 'active'),

('EMP-0003', (SELECT id FROM roles WHERE name='nurse'), 'Grace', 'Adeyemi', 'nurse@perfectionsdental.ng',
 'scrypt:32768:8:1$Zll1reeBxGLRArec$13cc7ef23ba15a30db4fb834c06a31230e8a41e6088f3dd93da39b434e3160892b336d735d8b4a6f45800f48a18385d5cd030859729572f649da03fcfe4819ad',
 '+2348023456703', NULL, 'Chairside Assisting', 'RN', 6, 'Female', 'active'),

('EMP-0004', (SELECT id FROM roles WHERE name='reception'), 'Ifeoma', 'Chukwu', 'reception@perfectionsdental.ng',
 'scrypt:32768:8:1$Zll1reeBxGLRArec$13cc7ef23ba15a30db4fb834c06a31230e8a41e6088f3dd93da39b434e3160892b336d735d8b4a6f45800f48a18385d5cd030859729572f649da03fcfe4819ad',
 '+2348023456704', NULL, 'Front Desk & Billing', NULL, 3, 'Female', 'active');

INSERT INTO service_categories (name) VALUES ('General'), ('Cosmetic'), ('Surgical'), ('Orthodontics');

INSERT INTO services (category_id, name, description, price, duration_minutes) VALUES
((SELECT id FROM service_categories WHERE name='General'), 'Dental Consultation', 'Initial examination and diagnosis', 5000, 30),
((SELECT id FROM service_categories WHERE name='General'), 'Scaling & Polishing', 'Professional teeth cleaning', 15000, 45),
((SELECT id FROM service_categories WHERE name='Cosmetic'), 'Teeth Whitening', 'In-office whitening treatment', 45000, 60),
((SELECT id FROM service_categories WHERE name='Surgical'), 'Tooth Extraction', 'Simple extraction', 20000, 30),
((SELECT id FROM service_categories WHERE name='Surgical'), 'Root Canal Therapy', 'Single canal root treatment', 60000, 90),
((SELECT id FROM service_categories WHERE name='Orthodontics'), 'Braces Fitting', 'Custom braces installation', 250000, 120);

INSERT INTO inventory_categories (name) VALUES ('Analgesics'), ('Antibiotics'), ('Antiseptics'), ('Consumables');

INSERT INTO inventory_items (category_id, name, sku, unit, current_stock, min_threshold, price, requires_prescription, nurse_eligible) VALUES
((SELECT id FROM inventory_categories WHERE name='Analgesics'), 'Paracetamol 500mg', 'MED-PARA-500', 'tablet', 500, 50, 20, 0, 1),
((SELECT id FROM inventory_categories WHERE name='Analgesics'), 'Ibuprofen 400mg', 'MED-IBU-400', 'tablet', 300, 50, 35, 0, 1),
((SELECT id FROM inventory_categories WHERE name='Antibiotics'), 'Amoxicillin 500mg', 'MED-AMOX-500', 'capsule', 200, 30, 60, 1, 0),
((SELECT id FROM inventory_categories WHERE name='Antibiotics'), 'Metronidazole 400mg', 'MED-METRO-400', 'tablet', 150, 30, 45, 1, 0),
((SELECT id FROM inventory_categories WHERE name='Antiseptics'), 'Chlorhexidine Mouthwash', 'CONS-CHLX-100', 'bottle', 80, 10, 1200, 0, 1),
((SELECT id FROM inventory_categories WHERE name='Consumables'), 'Dental Floss', 'CONS-FLOSS', 'pack', 120, 20, 500, 0, 1);

INSERT INTO patients (patient_number, first_name, last_name, email, phone, password_hash, dob, gender, address, allergies, current_medications, portal_active, registration_date)
VALUES
('PT-0001', 'Amara', 'Nwosu', 'amara.nwosu@example.com', '+2348011112222',
 'scrypt:32768:8:1$Zll1reeBxGLRArec$13cc7ef23ba15a30db4fb834c06a31230e8a41e6088f3dd93da39b434e3160892b336d735d8b4a6f45800f48a18385d5cd030859729572f649da03fcfe4819ad',
 '1990-04-12', 'Female', 'Wuse 2, Abuja', 'Penicillin', 'None', 1, date('now', '-30 days')),
('PT-0002', 'Bala', 'Kure', 'bala.kure@example.com', '+2348033334444', NULL,
 '1985-11-02', 'Male', 'Garki, Abuja', 'None', 'Lisinopril 10mg', 0, date('now', '-10 days'));
