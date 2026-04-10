import config
from DB.database import violations_collection
from datetime import datetime


class ViolationLogger:

    def __init__(self):
        pass

    def log(self, violation_model):

        try:
            violation_data = violation_model.to_dict()
            violation_data["timestamp"] = datetime.utcnow()
            violation_data["camera_id"] = config.CAMERA_ID

            # Step 1: Insert first (Mongo generates _id)
            result = violations_collection.insert_one(violation_data)

            # Step 2: Extract _id
            mongo_id = str(result.inserted_id)

            # Take last 10 characters and convert to uppercase
            last_10 = mongo_id[-10:].upper()

            vehicle_id = str(violation_data.get("vehicle_id", "0"))

            # Step 3: Create challan ID
            challan_id = f"SIST{last_10}{vehicle_id}"
            

            # Step 4: Update same document
            violations_collection.update_one(
                {"_id": result.inserted_id},
                {"$set": {"challan_id": challan_id}}
            )

            print(f"📜 Challan Generated: {challan_id}")
            return challan_id

        except Exception as e:
            print("❌ Mongo Insert Error:", e)
            return None

    def update_ocr(self, challan_id, plate_raw, plate_clean, confidence):
        try:
            violations_collection.update_one(
                {"challan_id": challan_id},
                {
                    "$set": {
                        "plate_raw": plate_raw,
                        "plate_clean": plate_clean,
                        "confidence": confidence
                    }
                }
            )
            print(f"📝 OCR Updated for Challan: {challan_id} -> {plate_clean} (Conf: {confidence:.2f})")
        except Exception as e:
            print(f"❌ Mongo Update Error for {challan_id}:", e)

    def update_image_url(self, challan_id, image_url):
        try:
            violations_collection.update_one(
                {"challan_id": challan_id},
                {"$set": {"violation_image_url": image_url}}
            )
            print(f"☁️ Cloudinary URL Updated for Challan: {challan_id}")
        except Exception as e:
            print(f"❌ Mongo Image Update Error for {challan_id}:", e)
