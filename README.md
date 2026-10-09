# 🛡️ Trustcheck

**A verified order and anti-fraud platform for independent social media sellers (Instagram & WhatsApp).** 

---

## 🚀 The Problem
Social commerce is booming, but trust remains a massive hurdle. Independent sellers on platforms like Instagram and WhatsApp frequently fall victim to fake payment screenshots, while buyers fear being scammed by unverified products or malicious phishing links. There is currently no native layer of security for these transactions.

## 💡 The Solution
Trustcheck bridges the trust gap between buyers and sellers through an automated verification pipeline. We provide a decentralized layer of security for off-platform social media sales.

### Core Features
* **🧾 Automated Payment Verification:** Extracts data from payment screenshots and cross-references it against the known order details to instantly detect forged or reused transaction receipts.
* **📸 Cryptographic Product Certification:** Generates **SHA-256 fingerprints** for product photos. This guarantees image authenticity, preventing "bait-and-switch" tactics and proving the seller possesses the actual item.
* **🚨 Scam & Phishing Detection Engine:** Actively parses chat text to flag malicious messages, suspicious links, and fraudulent UPI payment requests to protect both parties.

## 🛠️ Tech Stack
* **Language:** Python
* **Backend Framework:** FastAPI
* **Cryptography:** SHA-256 Hashing

## ⚙️ How it Works
1. **Order Initiation:** The seller registers the order details via Trustcheck and generates a secure link for the buyer.
2. **Photo Certification:** The seller uploads the product photo, locking it with a SHA-256 hash that the buyer can verify.
3. **Payment & Security:** The buyer uploads their payment screenshot. Trustcheck validates the receipt and scans all accompanying communication for scam triggers before clearing the order.
