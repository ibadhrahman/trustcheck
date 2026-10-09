-- TrustCheck schema for Supabase PostgreSQL.

CREATE TABLE IF NOT EXISTS users (
	id SERIAL NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	hashed_password VARCHAR(255) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS audit_events (
	id SERIAL NOT NULL, 
	user_id INTEGER, 
	event_type VARCHAR(80) NOT NULL, 
	entity_type VARCHAR(50), 
	entity_id INTEGER, 
	detail VARCHAR(500), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS products (
	id SERIAL NOT NULL, 
	seller_id INTEGER NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	description TEXT, 
	price FLOAT NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(seller_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS scam_checks (
	id SERIAL NOT NULL, 
	user_id INTEGER, 
	content_type VARCHAR(30) NOT NULL, 
	content_length INTEGER NOT NULL, 
	risk_score INTEGER NOT NULL, 
	risk_verdict VARCHAR(20) NOT NULL, 
	indicators_json TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS seller_profiles (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	business_name VARCHAR(200), 
	contact_name VARCHAR(200), 
	phone VARCHAR(20), 
	upi_id VARCHAR(100), 
	bio TEXT, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS seller_referral_codes (
	id SERIAL NOT NULL, 
	seller_id INTEGER NOT NULL, 
	code VARCHAR(32) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_seller_ref_code UNIQUE (code), 
	UNIQUE (seller_id), 
	FOREIGN KEY(seller_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS orders (
	id SERIAL NOT NULL, 
	seller_id INTEGER NOT NULL, 
	product_id INTEGER, 
	quantity INTEGER NOT NULL, 
	expected_amount FLOAT NOT NULL, 
	expected_payee_name VARCHAR(200), 
	expected_upi_id VARCHAR(100), 
	customer_label VARCHAR(200), 
	private_note TEXT, 
	status VARCHAR(30) NOT NULL, 
	last_risk_verdict VARCHAR(20), 
	last_risk_score INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(seller_id) REFERENCES users (id), 
	FOREIGN KEY(product_id) REFERENCES products (id)
);

CREATE TABLE IF NOT EXISTS photo_certificates (
	id SERIAL NOT NULL, 
	product_id INTEGER NOT NULL, 
	seller_id INTEGER NOT NULL, 
	certificate_id VARCHAR(64) NOT NULL, 
	filename VARCHAR(255) NOT NULL, 
	sha256_hash VARCHAR(64) NOT NULL, 
	phash VARCHAR(64), 
	file_size_bytes INTEGER NOT NULL, 
	image_width INTEGER, 
	image_height INTEGER, 
	mime_type VARCHAR(50) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(product_id) REFERENCES products (id), 
	FOREIGN KEY(seller_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS ledger_entries (
	id SERIAL NOT NULL, 
	certificate_id INTEGER NOT NULL, 
	event_type VARCHAR(50) NOT NULL, 
	event_data TEXT, 
	record_hash VARCHAR(64) NOT NULL, 
	prev_record_hash VARCHAR(64), 
	timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(certificate_id) REFERENCES photo_certificates (id)
);

CREATE TABLE IF NOT EXISTS order_referral_codes (
	id SERIAL NOT NULL, 
	order_id INTEGER NOT NULL, 
	seller_id INTEGER NOT NULL, 
	code VARCHAR(32) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_order_ref_code UNIQUE (code), 
	UNIQUE (order_id), 
	FOREIGN KEY(order_id) REFERENCES orders (id), 
	FOREIGN KEY(seller_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS payment_submissions (
	id SERIAL NOT NULL, 
	order_id INTEGER NOT NULL, 
	seller_id INTEGER NOT NULL, 
	verification_tx_id VARCHAR(32), 
	submitted_tx_id VARCHAR(100), 
	screenshot_sha256 VARCHAR(64), 
	screenshot_phash VARCHAR(64), 
	screenshot_file_size INTEGER, 
	extracted_amount FLOAT, 
	extracted_tx_id VARCHAR(100), 
	extracted_date VARCHAR(50), 
	extracted_payee_name VARCHAR(200), 
	tx_ref_hmac VARCHAR(64), 
	risk_score INTEGER, 
	risk_verdict VARCHAR(20), 
	risk_reasons_json TEXT, 
	extracted_json TEXT, 
	forensics_json TEXT, 
	duplicate_json TEXT, 
	comparison_json TEXT, 
	screenshot_viewpoint VARCHAR(20), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(order_id) REFERENCES orders (id), 
	FOREIGN KEY(seller_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS payment_references (
	id SERIAL NOT NULL, 
	seller_id INTEGER NOT NULL, 
	order_id INTEGER NOT NULL, 
	submission_id INTEGER NOT NULL, 
	tx_ref_hmac VARCHAR(64) NOT NULL, 
	first_seen_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(seller_id) REFERENCES users (id), 
	FOREIGN KEY(order_id) REFERENCES orders (id), 
	FOREIGN KEY(submission_id) REFERENCES payment_submissions (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email);

CREATE INDEX IF NOT EXISTS ix_users_id ON users (id);

CREATE INDEX IF NOT EXISTS ix_audit_events_id ON audit_events (id);

CREATE INDEX IF NOT EXISTS ix_audit_user ON audit_events (user_id);

CREATE INDEX IF NOT EXISTS ix_products_id ON products (id);

CREATE INDEX IF NOT EXISTS ix_products_seller ON products (seller_id);

CREATE INDEX IF NOT EXISTS ix_scam_checks_id ON scam_checks (id);

CREATE INDEX IF NOT EXISTS ix_seller_profiles_id ON seller_profiles (id);

CREATE UNIQUE INDEX IF NOT EXISTS ix_seller_referral_codes_code ON seller_referral_codes (code);

CREATE INDEX IF NOT EXISTS ix_seller_referral_codes_id ON seller_referral_codes (id);

CREATE INDEX IF NOT EXISTS ix_orders_id ON orders (id);

CREATE INDEX IF NOT EXISTS ix_orders_seller ON orders (seller_id);

CREATE INDEX IF NOT EXISTS ix_certs_seller ON photo_certificates (seller_id);

CREATE UNIQUE INDEX IF NOT EXISTS ix_photo_certificates_certificate_id ON photo_certificates (certificate_id);

CREATE INDEX IF NOT EXISTS ix_photo_certificates_id ON photo_certificates (id);

CREATE INDEX IF NOT EXISTS ix_ledger_entries_id ON ledger_entries (id);

CREATE UNIQUE INDEX IF NOT EXISTS ix_order_referral_codes_code ON order_referral_codes (code);

CREATE INDEX IF NOT EXISTS ix_order_referral_codes_id ON order_referral_codes (id);

CREATE INDEX IF NOT EXISTS ix_payment_submissions_id ON payment_submissions (id);

CREATE INDEX IF NOT EXISTS ix_payment_submissions_tx_ref_hmac ON payment_submissions (tx_ref_hmac);

CREATE INDEX IF NOT EXISTS ix_payment_submissions_verification_tx_id ON payment_submissions (verification_tx_id);

CREATE INDEX IF NOT EXISTS ix_submissions_order ON payment_submissions (order_id);

CREATE INDEX IF NOT EXISTS ix_pay_ref_hmac ON payment_references (tx_ref_hmac);

CREATE INDEX IF NOT EXISTS ix_payment_references_id ON payment_references (id);

CREATE INDEX IF NOT EXISTS ix_payment_references_tx_ref_hmac ON payment_references (tx_ref_hmac);

ALTER TABLE public."users" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public."users" FROM PUBLIC, anon, authenticated;

ALTER TABLE public."audit_events" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public."audit_events" FROM PUBLIC, anon, authenticated;

ALTER TABLE public."products" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public."products" FROM PUBLIC, anon, authenticated;

ALTER TABLE public."scam_checks" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public."scam_checks" FROM PUBLIC, anon, authenticated;

ALTER TABLE public."seller_profiles" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public."seller_profiles" FROM PUBLIC, anon, authenticated;

ALTER TABLE public."seller_referral_codes" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public."seller_referral_codes" FROM PUBLIC, anon, authenticated;

ALTER TABLE public."orders" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public."orders" FROM PUBLIC, anon, authenticated;

ALTER TABLE public."photo_certificates" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public."photo_certificates" FROM PUBLIC, anon, authenticated;

ALTER TABLE public."ledger_entries" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public."ledger_entries" FROM PUBLIC, anon, authenticated;

ALTER TABLE public."order_referral_codes" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public."order_referral_codes" FROM PUBLIC, anon, authenticated;

ALTER TABLE public."payment_submissions" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public."payment_submissions" FROM PUBLIC, anon, authenticated;

ALTER TABLE public."payment_references" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public."payment_references" FROM PUBLIC, anon, authenticated;

REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, anon, authenticated;

ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated;
