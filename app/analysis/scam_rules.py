"""
Rule-based scam message and link checker.

Checks suspicious messages, UPI IDs, URLs, and payment instructions
for common social-engineering and fraud indicators.

Uses transparent, documented rules — never visits URLs or executes content.
"""
from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------

class _Rule:
    def __init__(self, pattern: str, description: str, severity: str, is_regex: bool = False):
        self.pattern = pattern
        self.description = description
        self.severity = severity  # low | medium | high
        self.is_regex = is_regex

    def matches(self, text: str) -> bool:
        lower = text.lower()
        if self.is_regex:
            return bool(re.search(self.pattern, lower, re.IGNORECASE))
        return self.pattern.lower() in lower


_RULES: list[_Rule] = [
    # --- Urgency / Threats ---
    _Rule("urgent", "Uses urgency language to pressure the recipient.", "medium"),
    _Rule("immediately", "Demands immediate action — a common pressure tactic.", "medium"),
    _Rule("last chance", "Creates artificial deadline — common in scam messages.", "medium"),
    _Rule("account will be blocked", "Threatens account suspension to create panic.", "high"),
    _Rule("account will be suspended", "Threatens account suspension.", "high"),
    _Rule("your account has been compromised", "Falsely claims compromise to steal credentials.", "high"),
    _Rule("act now", "High-pressure call to action.", "medium"),
    _Rule("limited time", "Artificial urgency tactic.", "low"),

    # --- Credential harvesting ---
    _Rule("enter your otp", "Requests OTP — legitimate services never ask for your OTP.", "high"),
    _Rule("share your otp", "Requests OTP over message — always fraudulent.", "high"),
    _Rule("your otp is", "Impersonates an OTP delivery to confuse the recipient.", "high"),
    _Rule("enter your pin", "Requests PIN — legitimate services never ask for PINs.", "high"),
    _Rule("your cvv", "Requests CVV — never share this.", "high"),
    _Rule("send your password", "Requests password — always a scam.", "high"),
    _Rule("verify your account", "Vague verification request used to collect credentials.", "medium"),
    _Rule("confirm your details", "Vague details request.", "medium"),
    _Rule("kyc update", "KYC update requests via message are a common fraud vector.", "high"),
    _Rule("complete your kyc", "Pressure KYC completion — verify only through official bank apps.", "high"),

    # --- Suspicious payment instructions ---
    _Rule("pay on this number", "Non-standard payment instructions.", "medium"),
    _Rule("send money to", "Unsolicited payment request.", "medium"),
    _Rule("pay ₹", "Direct payment demand in message — verify via official channel.", "low"),
    _Rule("cashback", "Cashback promises used to trick users into payments.", "medium"),
    _Rule("you have won", "Classic lottery/prize scam indicator.", "high"),
    _Rule("prize money", "Prize money claims are common fraud hooks.", "high"),
    _Rule("claim your reward", "Reward claim used to steal credentials or money.", "high"),
    _Rule("refund", "Refund scams trick sellers/buyers into authorising payments.", "medium"),
    _Rule("scan to receive", "Scanning a QR code sends money — never 'receives' it.", "high"),
    _Rule("scan this qr to get", "QR code scam: victims scan to pay, not receive.", "high"),

    # --- Remote access ---
    _Rule("anydesk", "AnyDesk is a remote-access tool commonly used by scammers.", "high"),
    _Rule("teamviewer", "TeamViewer remote access — do not allow strangers to connect.", "high"),
    _Rule("quicksupport", "QuickSupport is used for remote access — common in tech-support scams.", "high"),
    _Rule("screen share", "Screen sharing with strangers exposes sensitive information.", "medium"),
    _Rule("install this app", "Requests installation of an app — common malware vector.", "high"),
    _Rule("download and install", "Unsolicited install request.", "high"),

    # --- Deceptive URL patterns ---
    _Rule(r"https?://[^\s]*\.xyz[/\s]", "XYZ domains are commonly used for phishing.", "medium", is_regex=True),
    _Rule(r"https?://[^\s]*-support[./]", "Fake support URLs are a phishing indicator.", "high", is_regex=True),
    _Rule(r"https?://[^\s]*secure[^\s]*login", "Fake secure login pages used for credential theft.", "high", is_regex=True),
    _Rule(r"https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "Direct IP address URL — very unusual for legitimate services.", "high", is_regex=True),
    _Rule(r"bit\.ly|tinyurl|t\.co|goo\.gl|rb\.gy", "Shortened URLs hide the real destination.", "medium", is_regex=True),
    _Rule(r"https?://[^\s]*paypal[^\s]*\.(?!com)", "Typosquatting PayPal domain.", "high", is_regex=True),
    _Rule(r"https?://[^\s]*google[^\s]*\.(?!com)", "Typosquatting Google domain.", "high", is_regex=True),
    _Rule(r"https?://[^\s]*paytm[^\s]*\.(?!com|in)", "Suspicious Paytm look-alike domain.", "high", is_regex=True),
    _Rule(r"https?://[^\s]*upi[^\s]*\.(?!org|in)", "Suspicious UPI look-alike domain.", "high", is_regex=True),

    # --- Suspicious UPI IDs ---
    _Rule(r"@(?:ybl|okhdfcbank|okaxis|okicici|oksbi)\b", "Legitimate UPI suffixes — verify the prefix is correct.", "low", is_regex=True),
    _Rule(r"\b(paytm|gpay|phonepe|bhim)\b.*\blink\b", "Payment link via message — verify before clicking.", "medium", is_regex=True),

    # --- Social engineering ---
    _Rule("i am from the bank", "Banks never contact customers asking for credentials.", "high"),
    _Rule("rbi officer", "RBI does not contact individuals to transfer money.", "high"),
    _Rule("cyber crime department", "Scammers impersonate cyber crime officials.", "high"),
    _Rule("your sim will be blocked", "SIM blocking threats are used in OTP fraud.", "high"),
    _Rule("click the link below", "Generic link-click instruction — be cautious.", "low"),
    _Rule("do not share this with anyone", "Secrecy instructions prevent victims from seeking advice.", "medium"),
]

_SEVERITY_SCORE = {"low": 10, "medium": 25, "high": 45}


def check_scam(content: str, content_type: str = "message") -> dict:
    """
    Run all rules against the input content.
    Returns a structured result with risk score, verdict, and indicators.

    Never visits URLs. Never executes content.
    """
    triggered: list[dict] = []

    for rule in _RULES:
        if rule.matches(content):
            triggered.append({
                "pattern": rule.pattern if not rule.is_regex else f"regex: {rule.pattern}",
                "description": rule.description,
                "severity": rule.severity,
            })

    # Score: cap at 100
    raw_score = sum(_SEVERITY_SCORE.get(r["severity"], 0) for r in triggered)
    score = min(raw_score, 100)

    # Verdict
    if score >= 60:
        verdict = "dangerous"
    elif score >= 25:
        verdict = "caution"
    else:
        verdict = "safe"

    # Build safe next steps
    safe_steps = _build_safe_steps(triggered, content_type)

    return {
        "risk_score": score,
        "verdict": verdict,
        "indicators": triggered,
        "safe_next_steps": safe_steps,
        "disclaimer": (
            "This is a rule-based heuristic check. "
            "It cannot guarantee a message or link is safe or malicious. "
            "When in doubt, contact the institution directly through their official website or app."
        ),
    }


def _build_safe_steps(triggered: list[dict], content_type: str) -> list[str]:
    steps = []
    descriptions = {r["description"] for r in triggered}
    severities = {r["severity"] for r in triggered}

    if "high" in severities:
        steps.append("Do not respond to or act on this message until you have verified it through official channels.")

    if any("OTP" in d or "PIN" in d or "password" in d.lower() for d in descriptions):
        steps.append("Never share OTPs, PINs, or passwords with anyone — not even bank employees.")

    if any("remote" in d.lower() or "anydesk" in d.lower() or "teamviewer" in d.lower() for d in descriptions):
        steps.append("Do not install remote-access software on request. Disconnect immediately if connected.")

    if any("QR" in d or "scan" in d.lower() for d in descriptions):
        steps.append("Scanning a QR code usually SENDS money, not receives it. Be very careful.")

    if any("URL" in d or "domain" in d.lower() or "link" in d.lower() for d in descriptions):
        steps.append("Do not click links in suspicious messages. Navigate to the official site manually.")
        steps.append("Check the full URL carefully — scammers use look-alike domain names.")

    if any("KYC" in d for d in descriptions):
        steps.append("Complete KYC updates only through your bank's official app or branch — never via a message link.")

    if content_type == "upi_id":
        steps.append("Verify UPI IDs by making a small test transfer and confirming the recipient name before sending large amounts.")

    steps.append("If you believe this is a fraud attempt, report it at cybercrime.gov.in or call 1930.")

    return steps
