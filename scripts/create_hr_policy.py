import os
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

OUT_DIR = "sample_docs"
os.makedirs(OUT_DIR, exist_ok=True)
OUT_PATH = os.path.join(OUT_DIR, "hr_policy.pdf")

styles = getSampleStyleSheet()
title_style = ParagraphStyle("Title2", parent=styles["Title"], alignment=TA_CENTER)
h1 = styles["Heading1"]
body = styles["BodyText"]

story = [
    Paragraph("TechNova Solutions — Human Resources Policy Handbook", title_style),
    Spacer(1, 18),

    Paragraph("Section 1 - Leave Policy", h1),
    Paragraph("• <b>Annual Leave:</b> Full-time employees receive 21 paid leave days per year. Part-time employees receive 10 days.", body),
    Paragraph("• <b>Sick Leave:</b> 10 days per year, non-carry-forward. Medical certificate required after 3 consecutive days.", body),
    Paragraph("• <b>Maternity Leave:</b> 16 weeks fully paid. <b>Paternity Leave:</b> 2 weeks fully paid.", body),
    Paragraph("• <b>Unpaid Leave:</b> Up to 6 months with 30 days written notice.", body),
    Paragraph("• <b>Public Holidays:</b> 11 gazetted holidays + 3 floating days.", body),
    Spacer(1, 12),

    Paragraph("Section 2 - Compensation &amp; Benefits", h1),
    Paragraph("• <b>Health Insurance:</b> TechNova covers 80% of premium. Dependent coverage available at 40% subsidy.", body),
    Paragraph("• <b>Annual Bonus:</b> Up to 15% of base salary, paid in March, subject to performance rating ≥ 3.5/5.", body),
    Paragraph("• <b>Provident Fund:</b> Company contributes 10% of gross salary. Employee mandatory contribution: 8%.", body),
    Paragraph("• <b>Gratuity:</b> 1 month salary per year of service after completing 3 years.", body),
    Paragraph("• <b>Education Allowance:</b> PKR 50,000 per year for job-related certifications.", body),
    Spacer(1, 12),

    Paragraph("Section 3 - Performance Management", h1),
    Paragraph("• Reviews are conducted bi-annually: in June and December.", body),
    Paragraph("• KPI categories: Technical Skills (40%), Collaboration (30%), Innovation (30%).", body),
    Paragraph("• Employees rated below 2.5/5 for two consecutive reviews are placed on a Performance Improvement Plan (PIP).", body),
    Paragraph("• Promotion decisions are made in January based on the December review.", body),
    Spacer(1, 12),

    Paragraph("Section 4 - Code of Conduct", h1),
    Paragraph("• Conflicts of interest must be disclosed to HR within 5 business days of occurrence.", body),
    Paragraph("• Gifts exceeding PKR 5,000 in value must be reported to the Ethics Committee.", body),
    Paragraph("• Social media policy: employees must not share client data or unreleased product information.", body),
    Paragraph("• Disciplinary process: Verbal Warning → Written Warning → Final Warning → Termination.", body),
]

doc = SimpleDocTemplate(OUT_PATH, pagesize=A4)
doc.build(story)
print(f"Generated: {OUT_PATH}")