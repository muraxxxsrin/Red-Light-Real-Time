
import time
import requests
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from DB.database import violations_collection
from services.pdfGenerator import generate_challan_pdf
from services.pdfUploader import upload_pdf

import config


WHATSAPP_URL = f"https://graph.facebook.com/{config.WHATSAPP_API_VERSION}/{config.WHATSAPP_PHONE_NUMBER_ID}/messages"


HEADERS = {
    "Authorization": f"Bearer {config.WHATSAPP_ACCESS_TOKEN}",
    "Content-Type": "application/json"
}


class WhatsAppService:


    def send_template_message(self, violation):

        try:

            # Generate PDF
            pdf_path = generate_challan_pdf(violation)

            # Upload PDF
            pdf_url = upload_pdf(pdf_path, violation["challan_id"])

            phone = str(violation["phone_number"])

            if not phone.startswith("91"):
                phone = "91" + phone


            payload = {
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "template",
                "template": {
                    "name": "traffic_violation_notice_pdf",
                    "language": {"code": "en"},
                    "components": [

                        {
                            "type": "header",
                            "parameters": [
                                {
                                    "type": "document",
                                    "document": {
                                        "link": pdf_url,
                                        "filename": f"Challan_{violation['challan_id']}.pdf"
                                    }
                                }
                            ]
                        },

                        {
                            "type": "body",
                            "parameters": [
                                {
                                    "type": "text",
                                    "text": "TN03X4375"
                                },
                                {
                                    "type": "text",
                                    "text": violation.get("violation_type","UNKNOWN")
                                },
                                {
                                    "type": "text",
                                    "text": str(violation.get("fine_amount","0"))
                                },
                                {
                                    "type": "text",
                                    "text": f"https://sistchallan.in/pay/{violation['challan_id']}"
                                }
                            ]
                        }

                    ]
                }
            }


            response = requests.post(WHATSAPP_URL, headers=HEADERS, json=payload)

            print("WhatsApp Response:", response.status_code, response.text)


            if response.status_code == 200:

                violations_collection.update_one(
                    {"_id": violation["_id"]},
                    {
                        "$set": {
                            "message_sent": True,
                            "status": "notified"
                        }
                    }
                )

                os.remove(pdf_path)

                print("✅ Message Sent")

            else:
                print("❌ Failed")

        except Exception as e:
            print("Error:", e)



    def process_pending_messages(self):

        pending = violations_collection.find({
            "message_sent": False,
            "payment_status": "unpaid",
            "status": "detected"
        })

        for violation in pending:
            print(f"📲 Sending for {violation['challan_id']}")
            self.send_template_message(violation)



if __name__ == "__main__":

    service = WhatsAppService()

    print("📲 WhatsApp Polling Service Started...")

    while True:

        try:
            service.process_pending_messages()

        except Exception as e:
            print("Polling Error:", e)

        time.sleep(10)