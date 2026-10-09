# TrustCheck

A verified order platform that protects small sellers and buyers on
Instagram and WhatsApp from fake payment screenshots, stolen product
photos and scam requests.

## The problem

Millions of small sellers in India sell through chat. Orders, photos and
payments are informal, so fraudsters send edited payment screenshots,
post copied or AI-generated product photos, and send fake UPI collect
requests.
## How it works

1. The seller registers a shop, uploads product photos (fingerprinted with
   SHA-256 and certified as original) and creates an order link with the
   product, price and UPI ID.
2. The seller shares the link in the WhatsApp or Instagram chat.
3. The buyer opens the link, sees the verified listing, pays in their own
   UPI app (TrustCheck never handles money), and uploads the payment
   screenshot on the order page.
4. Because the order is known, the backend compares the screenshot against
   the expected amount, payee, date and transaction ID using OCR, and runs
   image-forensics checks for editing traces.
5. The seller gets an explainable verdict and a reminder to confirm the
   credit in their bank app before shipping.

## Features

- Verified seller shop and tamper-proof photo certificates (SHA-256 +
  hash-chained ledger)
- Shareable order links for WhatsApp and Instagram
- Payment screenshot check against the known order (OCR + edit detection)
- Scam check for messages, links and UPI requests, with plain-language reasons
- Seller confirmation checklist and scam intelligence dashboard

## Tech stack

Python, FastAPI, SQLite, Tesseract OCR, Pillow, OpenCV, exifread,
HTML/CSS/JavaScript, QR code generation.

## Project status

Hackathon prototype. The image checks, SHA-256 certificates and ledger
work in the browser demo. The backend, order flow and OCR comparison are
in development.

## Limitations

- Scores are risk estimates, not proof. A clean or well-made fake can pass.
- A screenshot is never final proof of payment. Sellers must confirm the
  credit in their bank app.
- TrustCheck protects users who opt in. A scammer will not use the platform.

## Roadmap

Pretrained AI-image detection models, WhatsApp bot integration, regional
language support, and an API for marketplaces.

## Team

<Add team name and member names here>

## License

MIT
