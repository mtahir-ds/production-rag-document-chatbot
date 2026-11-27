import os
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

OUT_DIR = "sample_docs"
os.makedirs(OUT_DIR, exist_ok=True)
OUT_PATH = os.path.join(OUT_DIR, "onboarding_guide.pdf")

styles = getSampleStyleSheet()
title_style = ParagraphStyle("Title2", parent=styles["Title"], alignment=TA_CENTER)
h1 = styles["Heading1"]
body = styles["BodyText"]

story = [
    Paragraph("TechNova Solutions — New Employee Onboarding Guide", title_style),
    Spacer(1, 18),

    Paragraph("Section 1 - First Week Schedule", h1),
    Paragraph("• <b>Day 1:</b> IT setup (laptop, email, Slack, VPN), HR documentation, office tour", body),
    Paragraph("• <b>Day 2–3:</b> Department introduction, team meetings, system access provisioning", body),
    Paragraph("• <b>Day 4–5:</b> Role-specific training begins, assigned a Buddy (senior colleague)", body),
    Paragraph("• <b>Week 2:</b> First 1:1 with manager, 30-day goal setting", body),
    Spacer(1, 12),

    Paragraph("Section 2 - IT Provisioning", h1),
    Paragraph("• Laptop ready within 2 hours of Day 1 arrival", body),
    Paragraph("• Standard software: Slack, Zoom, MS Office 365, Jira, Confluence, GitHub", body),
    Paragraph("• VPN credentials issued by IT Security team on Day 1", body),
    Paragraph("• Email format: firstname.lastname@technova.com", body),
    Spacer(1, 12),

    Paragraph("Section 3 - Policies to Acknowledge (Day 1)", h1),
    Paragraph("• HR Policy Handbook (this must be signed within 24 hours)", body),
    Paragraph("• Information Security Policy", body),
    Paragraph("• Remote Work Policy (if applicable)", body),
    Paragraph("• Code of Conduct Agreement", body),
    Spacer(1, 12),

    Paragraph("Section 4 - Benefits Enrollment", h1),
    Paragraph("• Health insurance enrollment window: First 30 days only. After that, must wait for annual open enrollment.", body),
    Paragraph("• Provident Fund enrollment: Automatic from Month 1 of employment", body),
    Paragraph("• Gym membership subsidy: PKR 3,000/month available from Month 3", body),
    Paragraph("• Annual leave begins accruing from Day 1 but cannot be taken in the first 60 days.", body),
    Spacer(1, 12),

    Paragraph("Section 5 - Key Contacts", h1),
    Paragraph("• HR Manager: hr@technova.com", body),
    Paragraph("• IT Helpdesk: it-support@technova.com | ext. 2001", body),
    Paragraph("• Payroll: payroll@technova.com", body),
    Paragraph("• Security Incidents: security@technova.com | emergency hotline: +92-21-111-SECURE", body),
]

doc = SimpleDocTemplate(OUT_PATH, pagesize=A4)
doc.build(story)
print(f"Generated: {OUT_PATH}")