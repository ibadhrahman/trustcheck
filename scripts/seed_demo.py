"""
TrustCheck — Demo Data Seeder
Populates realistic seller accounts, certified products, append-only ledger entries,
orders with referral codes, and audit records for hackathon evaluation and testing.
"""
import hashlib
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.auth import hash_password
from app.db import Base, SessionLocal, engine
from app.ledger import append_ledger_entry
from app.analysis.duplicate_detection import record_payment_reference
from app.models import (
    AuditEvent,
    Order,
    OrderReferralCode,
    PhotoCertificate,
    Product,
    SellerProfile,
    SellerReferralCode,
    User,
    PaymentSubmission,
)


def seed():
    print("[*] Initialising database tables...")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # Check if already seeded
        existing = db.query(User).filter(User.email == "seller@artisan.in").first()
        if existing:
            print("[+] Demo data already present! Skipping seed.")
            return

        print("[*] Creating Demo Seller 1: Aura Handcrafted Studio...")
        seller1 = User(
            email="seller@artisan.in",
            hashed_password=hash_password("Password123!"),
            is_active=True,
        )
        db.add(seller1)
        db.flush()

        profile1 = SellerProfile(
            user_id=seller1.id,
            business_name="Aura Handcrafted Studio",
            contact_name="Priya Sharma",
            phone="+91 98201 23456",
            upi_id="aurahandcrafts@okhdfcbank",
            bio="Handmade pashmina, ceramics & brassware from Bengaluru. Verify your TC-XXXXXXXX code before payment.",
        )
        db.add(profile1)

        src1 = SellerReferralCode(
            seller_id=seller1.id,
            code="SL-AURA-7K9M",
        )
        db.add(src1)

        print("[*] Creating Demo Seller 2: Vintage Leather Works...")
        seller2 = User(
            email="rohit@vintageleather.in",
            hashed_password=hash_password("Password123!"),
            is_active=True,
        )
        db.add(seller2)
        db.flush()

        profile2 = SellerProfile(
            user_id=seller2.id,
            business_name="Vintage Leather Works",
            contact_name="Rohit Verma",
            phone="+91 94123 45678",
            upi_id="rohit.leather@oksbi",
            bio="Handcrafted full-grain leather goods from Kanpur. Bank transfer confirmation required.",
        )
        db.add(profile2)

        src2 = SellerReferralCode(
            seller_id=seller2.id,
            code="SL-LETH-4P2W",
        )
        db.add(src2)
        db.flush()

        # Products for Seller 1
        print("[*] Creating Products and Photo Certificates for Seller 1...")
        p1 = Product(
            seller_id=seller1.id,
            name="Kashmiri Pashmina Shawl (Hand-woven)",
            description="Pure Pashmina wool handcrafted in Srinagar with authentic GI weave pattern.",
            price=4499.00,
        )
        p2 = Product(
            seller_id=seller1.id,
            name="Terracotta Ceramic Vase (Hand-painted)",
            description="Traditional terracotta vase painted with natural mineral pigments.",
            price=1299.00,
        )
        p3 = Product(
            seller_id=seller1.id,
            name="Pure Brass Diya Stand (Hand-carved)",
            description="Solid brass 5-tier traditional oil lamp engraved with peacock motifs.",
            price=899.00,
        )
        db.add_all([p1, p2, p3])
        db.flush()

        # Photo Certificates & Ledger entries
        sha_p1 = hashlib.sha256(b"kashmiri_pashmina_original_master_photo_aura").hexdigest()
        cert1 = PhotoCertificate(
            product_id=p1.id,
            seller_id=seller1.id,
            certificate_id="9a4f2c1e8b7d603a1f5e2d4c8a7b9e01",
            filename="pashmina_master_cert.jpg",
            sha256_hash=sha_p1,
            phash="b4c8d1e2f3a4b5c6",
            file_size_bytes=245890,
            image_width=1920,
            image_height=1080,
            mime_type="image/jpeg",
        )
        db.add(cert1)
        db.flush()
        append_ledger_entry(
            db,
            certificate_id=cert1.id,
            event_type="certificate_created",
            event_data={"product_id": p1.id, "sha256": sha_p1, "filename": cert1.filename},
        )

        sha_p2 = hashlib.sha256(b"terracotta_vase_master_photo_aura").hexdigest()
        cert2 = PhotoCertificate(
            product_id=p2.id,
            seller_id=seller1.id,
            certificate_id="7e1c3b5d9a0f2e4c6b8a1d3f5e7c9b02",
            filename="terracotta_vase_cert.png",
            sha256_hash=sha_p2,
            phash="a1b2c3d4e5f60718",
            file_size_bytes=184320,
            image_width=1200,
            image_height=1200,
            mime_type="image/png",
        )
        db.add(cert2)
        db.flush()
        append_ledger_entry(
            db,
            certificate_id=cert2.id,
            event_type="certificate_created",
            event_data={"product_id": p2.id, "sha256": sha_p2, "filename": cert2.filename},
        )

        # Orders for Seller 1
        print("[*] Creating Demo Orders with Referral Codes...")
        # Order 1: Pending (ready to test verification)
        o1 = Order(
            seller_id=seller1.id,
            expected_amount=4499.00,
            expected_upi_id="aurahandcrafts@okhdfcbank",
            expected_payee_name="Priya Sharma",
            customer_label="sneha_insta_dm",
            status="pending",
            private_note="Order placed via Instagram DM. Awaiting buyer payment screenshot.",
        )
        db.add(o1)
        db.flush()
        orc1 = OrderReferralCode(
            order_id=o1.id,
            seller_id=seller1.id,
            code="TC-7K9M4Q2X",
            is_active=True,
        )
        db.add(orc1)

        # Order 2: Needs Review (Duplicate detection demo)
        o2 = Order(
            seller_id=seller1.id,
            expected_amount=1299.00,
            expected_upi_id="aurahandcrafts@okhdfcbank",
            expected_payee_name="Priya Sharma",
            customer_label="vikram_whatsapp",
            status="needs_review",
            private_note="Buyer submitted transaction reference 320145678912. Reused reference flagged.",
        )
        db.add(o2)
        db.flush()
        orc2 = OrderReferralCode(
            order_id=o2.id,
            seller_id=seller1.id,
            code="TC-3W8L2P9Y",
            is_active=True,
        )
        db.add(orc2)

        # Record a prior payment submission and transaction reference for duplicate testing
        sub_dup = PaymentSubmission(
            order_id=o2.id,
            seller_id=seller1.id,
            risk_score=75,
            risk_verdict="suspicious",
            risk_reasons_json='[{"level": "error", "text": "Duplicate transaction reference detected."}]',
        )
        db.add(sub_dup)
        db.flush()
        record_payment_reference(
            db,
            seller_id=seller1.id,
            order_id=o2.id,
            submission_id=sub_dup.id,
            tx_ref="320145678912",
        )

        # Order 3: Seller Confirmed
        o3 = Order(
            seller_id=seller1.id,
            expected_amount=899.00,
            expected_upi_id="aurahandcrafts@okhdfcbank",
            expected_payee_name="Priya Sharma",
            customer_label="ananya_delhi",
            status="seller_confirmed",
            private_note="Bank credit verified in HDFC SmartHub app. Tracking #DTDC89421.",
        )
        db.add(o3)
        db.flush()
        orc3 = OrderReferralCode(
            order_id=o3.id,
            seller_id=seller1.id,
            code="TC-9B4N1X5V",
            is_active=True,
        )
        db.add(orc3)

        # Audit Events
        db.add_all([
            AuditEvent(user_id=seller1.id, event_type="seller_registered", entity_type="user", entity_id=seller1.id),
            AuditEvent(user_id=seller1.id, event_type="product_created", entity_type="product", entity_id=p1.id),
            AuditEvent(user_id=seller1.id, event_type="certificate_created", entity_type="certificate", entity_id=cert1.id),
            AuditEvent(user_id=seller1.id, event_type="order_created", entity_type="order", entity_id=o1.id),
            AuditEvent(user_id=seller1.id, event_type="order_created", entity_type="order", entity_id=o2.id),
            AuditEvent(user_id=seller1.id, event_type="payment_flagged", entity_type="payment", entity_id=sub_dup.id),
            AuditEvent(user_id=seller1.id, event_type="payment_confirmed", entity_type="order", entity_id=o3.id),
        ])

        db.commit()
        print("[+] Demo data seeded successfully!")
        print("\nDemo Accounts Created:")
        print("  1. Email: seller@artisan.in | Password: Password123!")
        print("     Store: Aura Handcrafted Studio | UPI: aurahandcrafts@okhdfcbank")
        print("     Seller Code: SL-AURA-7K9M")
        print("     Pending Order Referral Code: TC-7K9M4Q2X (INR 4,499.00)")
        print("     Duplicate Demo Reference: 320145678912")
        print("  2. Email: rohit@vintageleather.in | Password: Password123!")
        print("     Store: Vintage Leather Works | UPI: rohit.leather@oksbi")

    except Exception as e:
        db.rollback()
        print(f"[-] Error seeding data: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
