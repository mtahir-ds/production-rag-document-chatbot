import os
from docx import Document
from docx.shared import Pt

OUT_DIR = "sample_docs"
os.makedirs(OUT_DIR, exist_ok=True)
OUT_PATH = os.path.join(OUT_DIR, "remote_work_policy.docx")

doc = Document()
doc.add_heading("TechNova Solutions — Remote Work & Equipment Policy", level=0)

doc.add_heading("Section 1 - Eligibility", level=1)
doc.add_paragraph("Employees with tenure > 6 months are eligible for remote work.", style="List Bullet")
doc.add_paragraph("Probationary employees (first 6 months) must work from the office 5 days/week.", style="List Bullet")
doc.add_paragraph("Remote work is available Monday to Thursday. Fridays are mandatory office days for all staff.", style="List Bullet")

doc.add_heading("Section 2 - Equipment Stipend", level=1)
rows = [
    ("Category", "Annual Stipend (PKR)", "Notes"),
    ("Home Internet", "36,000", "Reimbursed monthly (3,000/mo)"),
    ("Ergonomic Chair", "25,000", "One-time, every 3 years"),
    ("Monitor", "40,000", "One-time, every 4 years"),
    ("Keyboard & Mouse", "8,000", "Replaced every 2 years"),
    ("Total (Year 1)", "109,000", "Subject to manager approval"),
]
table = doc.add_table(rows=len(rows), cols=3)
table.style = "Table Grid"
for i, row in enumerate(rows):
    for j, val in enumerate(row):
        cell = table.cell(i, j)
        cell.text = val
        if i == 0 or i == len(rows) - 1:
            for run in cell.paragraphs[0].runs:
                run.bold = True

doc.add_heading("Section 3 - Security Requirements", level=1)
doc.add_paragraph("Employees must use company-approved VPN at all times when working remotely.", style="List Bullet")
doc.add_paragraph("Home network must use WPA3 encryption. WEP/WPA networks are strictly prohibited.", style="List Bullet")
doc.add_paragraph("Screens must be locked within 2 minutes of inactivity (enforced via MDM policy).", style="List Bullet")
doc.add_paragraph("Sensitive documents must not be printed at home.", style="List Bullet")

doc.add_heading("Section 4 - Performance Expectations", level=1)
doc.add_paragraph("Remote employees must be reachable on Slack between 09:00 and 17:00 PKT.", style="List Bullet")
doc.add_paragraph("Core collaboration hours are 10:00–13:00 PKT daily.", style="List Bullet")
doc.add_paragraph("Attendance is tracked via badge-in on office days. Three unexcused absences in a month trigger HR review.", style="List Bullet")

doc.save(OUT_PATH)
print(f"Generated: {OUT_PATH}")