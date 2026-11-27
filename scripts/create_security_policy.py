import os

OUT_DIR = "sample_docs"
os.makedirs(OUT_DIR, exist_ok=True)
OUT_PATH = os.path.join(OUT_DIR, "security_policy.txt")

content = """TechNova Solutions — Information Security Policy v2.3

1. PASSWORD POLICY
   - Minimum length: 14 characters
   - Must contain: uppercase, lowercase, numbers, and at least 2 special characters
   - Passwords expire every 90 days
   - Last 12 passwords cannot be reused
   - Multi-Factor Authentication (MFA) is mandatory for all accounts
   - MFA method: Authenticator app preferred; SMS as fallback only

2. DATA CLASSIFICATION
   - Level 1 (Public): Marketing materials, job postings
   - Level 2 (Internal): Process documents, non-sensitive communications
   - Level 3 (Confidential): Client data, financial reports, HR records
   - Level 4 (Restricted): Source code, encryption keys, board communications
   - Level 3 and Level 4 data must be encrypted at rest using AES-256

3. INCIDENT RESPONSE
   - Security incidents must be reported to security@technova.com within 1 hour of detection
   - P1 (Critical) incidents: Response within 15 minutes, all-hands war room initiated
   - P2 (High) incidents: Response within 2 hours
   - P3 (Medium) incidents: Response within 24 hours
   - Incident log must be maintained for 7 years per regulatory requirement

4. ACCESS CONTROL
   - Principle of Least Privilege applied to all system accounts
   - Access reviews conducted quarterly
   - Terminated employee accounts disabled within 2 hours of HR notification
   - Privileged Access Workstations (PAW) required for admin-level access

5. DEVICE SECURITY
   - All company devices encrypted with BitLocker (Windows) or FileVault (Mac)
   - Mobile Device Management (MDM) enrollment mandatory within 24 hours of provisioning
   - Lost or stolen devices must be reported within 30 minutes
"""

with open(OUT_PATH, "w", encoding="utf-8") as f:
    f.write(content)
print(f"Generated: {OUT_PATH}")