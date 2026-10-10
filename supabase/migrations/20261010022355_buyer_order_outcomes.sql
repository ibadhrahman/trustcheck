-- Private buyer identities, order claims, and buyer/seller outcome history.

CREATE TABLE IF NOT EXISTS public.buyer_accounts (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
);

ALTER TABLE public.orders
    ADD COLUMN IF NOT EXISTS buyer_id INTEGER REFERENCES public.buyer_accounts(id);
ALTER TABLE public.orders
    ADD COLUMN IF NOT EXISTS buyer_access_hmac VARCHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS ix_buyer_accounts_email ON public.buyer_accounts (email);
CREATE INDEX IF NOT EXISTS ix_buyer_accounts_id ON public.buyer_accounts (id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_orders_buyer_access_hmac ON public.orders (buyer_access_hmac);
CREATE INDEX IF NOT EXISTS ix_orders_buyer_id ON public.orders (buyer_id);

CREATE TABLE IF NOT EXISTS public.order_outcomes (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL UNIQUE REFERENCES public.orders(id),
    buyer_id INTEGER REFERENCES public.buyer_accounts(id),
    outcome VARCHAR(30) NOT NULL,
    reason VARCHAR(40),
    description TEXT,
    status VARCHAR(30) NOT NULL,
    reported_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    buyer_received_at TIMESTAMP WITHOUT TIME ZONE,
    problem_reported_at TIMESTAMP WITHOUT TIME ZONE,
    response_deadline TIMESTAMP WITHOUT TIME ZONE,
    seller_resolution_type VARCHAR(30),
    seller_response TEXT,
    seller_responded_at TIMESTAMP WITHOUT TIME ZONE,
    resolved_at TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE IF NOT EXISTS public.order_outcome_events (
    id SERIAL PRIMARY KEY,
    outcome_id INTEGER NOT NULL REFERENCES public.order_outcomes(id),
    actor_type VARCHAR(20) NOT NULL,
    actor_id INTEGER NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    resolution_type VARCHAR(30),
    message TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
);

ALTER TABLE public.order_outcomes
    ADD COLUMN IF NOT EXISTS buyer_received_at TIMESTAMP WITHOUT TIME ZONE;
UPDATE public.order_outcomes
    SET buyer_received_at = reported_at
    WHERE buyer_received_at IS NULL;

CREATE TABLE IF NOT EXISTS public.order_outcome_evidence (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES public.order_outcome_events(id),
    storage_key VARCHAR(80) NOT NULL UNIQUE,
    mime_type VARCHAR(50) NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_order_outcomes_id ON public.order_outcomes (id);
CREATE INDEX IF NOT EXISTS ix_order_outcomes_buyer ON public.order_outcomes (buyer_id);
CREATE INDEX IF NOT EXISTS ix_order_outcomes_status ON public.order_outcomes (status);
CREATE INDEX IF NOT EXISTS ix_order_outcome_events_id ON public.order_outcome_events (id);
CREATE INDEX IF NOT EXISTS ix_order_outcome_events_outcome_id ON public.order_outcome_events (outcome_id);
CREATE INDEX IF NOT EXISTS ix_order_outcome_evidence_id ON public.order_outcome_evidence (id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_order_outcome_evidence_storage_key ON public.order_outcome_evidence (storage_key);

ALTER TABLE public.buyer_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.order_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.order_outcome_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.order_outcome_evidence ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.buyer_accounts, public.order_outcomes,
    public.order_outcome_events, public.order_outcome_evidence
    FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated;
