import os

OUT_DIR = "sample_docs"
os.makedirs(OUT_DIR, exist_ok=True)
OUT_PATH = os.path.join(OUT_DIR, "travel_expense_policy.md")

content = """# TechNova Solutions — Travel & Expense Policy

## 1. Pre-Approval Requirements
- All business travel must be approved by direct manager and Finance at least **5 business days** in advance.
- International travel requires CEO approval if exceeding **PKR 500,000** total cost.
- Emergency travel (< 24 hours notice) requires VP-level approval.

## 2. Flight Booking
- Economy class is standard for all flights under **6 hours**.
- Business class permitted for flights **6+ hours** with VP approval.
- Preferred booking window: **14–21 days** in advance for best rates.
- Employees must use the approved travel portal (Concur). Personal bookings require prior written approval.

## 3. Daily Allowance (Per Diem)
| Destination     | Meals (PKR) | Incidentals (PKR) | Total Per Diem (PKR) |
|----------------|-------------|-------------------|----------------------|
| Karachi        | 2,500       | 500               | 3,000                |
| Lahore         | 2,500       | 500               | 3,000                |
| Islamabad      | 2,500       | 500               | 3,000                |
| Dubai (AED)    | 150         | 50                | 200 AED              |
| London (GBP)   | 60          | 20                | 80 GBP               |

## 4. Hotel Accommodation
- Maximum hotel rate: PKR 15,000/night for domestic, USD 200/night for international.
- Hotel must be within **5 km** of the meeting venue unless approved otherwise.

## 5. Expense Submission
- All receipts must be submitted within **10 business days** of return.
- Expenses submitted after **30 days** are **not reimbursable**.
- Receipts required for any expense over **PKR 1,000**.
- Alcohol is **not reimbursable** under any circumstances.

## 6. Ground Transportation
- Taxis/ride-hailing: Reimbursable with receipt.
- Personal vehicle: PKR 18 per kilometer.
- Rental car: Requires manager pre-approval; compact class only.
"""

with open(OUT_PATH, "w", encoding="utf-8") as f:
    f.write(content)
print(f"Generated: {OUT_PATH}")