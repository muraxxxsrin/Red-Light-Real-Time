# import os, sys
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# import requests
# import config

# WHATSAPP_URL = f"https://graph.facebook.com/{config.WHATSAPP_API_VERSION}/{config.WHATSAPP_PHONE_NUMBER_ID}/messages"

# HEADERS = {
#     "Authorization": f"Bearer {config.WHATSAPP_ACCESS_TOKEN}",
#     "Content-Type": "application/json"
# }

# phone = "919344033127"   # your allowed test number

# payload = {
#     "messaging_product": "whatsapp",
#     "to": phone,
#     "type": "template",
#     "template": {
#         "name": "traffic_violation_notice_pdf",   # exact template name
#         "language": {"code": "en"},
#         "components": [

#             {
#                 "type": "header",
#                 "parameters": [
#                     {
#                         "type": "document",
#                         "document": {
#                             "link": "https://res.cloudinary.com/dmqk4xtad/raw/upload/v1775659029/traffic_challans/challan_SISTAAFD8E42E814.pdf",
#                             "filename": "Challan_Report_SIST87BEF8202C11.pdf"
#                         }
#                     }
#                 ]
#             },

#             {
#                 "type": "body",
#                 "parameters": [
#                     {"type": "text", "text": "TN10AB1234"},
#                     {"type": "text", "text": "Speeding"},
#                     {"type": "text", "text": "1000"},
#                     {"type": "text", "text": "https://sistchallan.in/pay/SIST12345"}
#                 ]
#             }

#         ]
#     }
# }

# response = requests.post(WHATSAPP_URL, headers=HEADERS, json=payload)

# print("Status:", response.status_code)
# print(response.text)
import os
import sys
import requests
import json

# Ensures the script can find your config.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

# API Endpoint using your config values
WHATSAPP_URL = f"https://graph.facebook.com/{config.WHATSAPP_API_VERSION}/{config.WHATSAPP_PHONE_NUMBER_ID}/messages"

HEADERS = {
    "Authorization": f"Bearer {config.WHATSAPP_ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

# The verified number from your earlier screenshot
phone = "919344033127" 

# Clean payload for the "hello_world" template
payload = {
    "messaging_product": "whatsapp",
    "to": phone,
    "type": "template",
    "template": {
        "name": "hello_world",
        "language": {
            "code": "en_US"
        }
    }
}

def send_viva_test():
    print(f"🚀 Attempting to send 'hello_world' to {phone}...")
    
    try:
        response = requests.post(WHATSAPP_URL, headers=HEADERS, json=payload)
        
        print(f"Status: {response.status_code}")
        print(f"Response Body: {response.text}")

        if response.status_code == 200:
            print("\n✅ SUCCESS! If it's not on your phone yet:")
            print("1. Send 'Hi' from your phone to +1 555 164 5556 to open the window.")
            print("2. Ensure your Temporary Access Token hasn't expired since yesterday.")
        else:
            print("\n❌ FAILED. Check the error message in 'Response Body' above.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    send_viva_test()

