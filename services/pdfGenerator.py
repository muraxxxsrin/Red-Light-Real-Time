from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from datetime import datetime
import requests
import os

from DB.database import cameras_collection


def generate_challan_pdf(violation):

    challan_id = violation["challan_id"]
    camera_id = violation.get("camera_id")

    # 🔹 Query camera collection
    camera = cameras_collection.find_one({"camera_id": camera_id})

    location = "Unknown Location"
    if camera:
        location = camera.get("location_name", "Unknown Location")

    filename = f"challan_{challan_id}.pdf"
    filepath = os.path.join("temp", filename)

    os.makedirs("temp", exist_ok=True)

    c = canvas.Canvas(filepath, pagesize=A4)

    # Header
    c.setFont("Helvetica-Bold", 24)
    c.setFillColorRGB(1, 0.3, 0)
    c.drawCentredString(300, 800, "RedLight System")

    c.setFillColorRGB(0,0,0)
    c.setFont("Helvetica", 18)
    c.drawCentredString(300, 770, "Traffic Violation Report")

    c.line(50, 750, 550, 750)

    c.setFont("Helvetica", 12)

    c.drawString(50, 720, f"Challan ID: {challan_id}")
    c.drawString(350, 720, f"Phone Number: {violation.get('phone_number','N/A')}")

    timestamp = violation.get("timestamp")

    if isinstance(timestamp, datetime):
        timestamp = timestamp.strftime("%d/%m/%Y %I:%M:%S %p")

    c.drawString(50, 690, f"Timestamp: {timestamp}")
    c.drawString(350, 690, f"Location: {location}")

    c.drawString(50, 660, f"Violation Type: {violation.get('violation_type','N/A')}")
    c.drawString(50, 630, f"Fine Amount: Rs. {violation.get('fine_amount','0')}")

    status = violation.get("payment_status","unpaid").upper()
    c.drawString(50, 600, f"Status: {status}")

    c.drawString(50, 560, "Evidence Image:")

    # 🔹 Download violation image
    image_url = violation.get("violation_image_url")

    if image_url:
        img_data = requests.get(image_url).content
        
        from io import BytesIO
        img = ImageReader(BytesIO(img_data))
        c.drawImage(img, 50, 300, width=500, height=230)

    c.setFillColorRGB(1,0,0)
    c.drawCentredString(
        300,
        250,
        "NOTICE: This challan is currently UNPAID. Please process payment immediately."
    )

    c.save()

    return filepath