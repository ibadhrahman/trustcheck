-- Buyers use the private order reference supplied by the seller; no buyer account is required.
ALTER TABLE public.order_outcomes
    ALTER COLUMN buyer_id DROP NOT NULL;

ALTER TABLE public.order_outcomes
    ALTER COLUMN buyer_received_at DROP NOT NULL;

COMMENT ON COLUMN public.orders.buyer_access_hmac IS
    'HMAC of the private buyer order reference. Plaintext is returned only when the seller creates or rotates the reference.';
