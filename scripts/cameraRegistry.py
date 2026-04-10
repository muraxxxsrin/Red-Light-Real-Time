import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from DB.database import db
from datetime import datetime

cameras_collection = db["cameras"]


class CameraRegistry:

    def create_camera(self, location_name, latitude, longitude):

        camera_data = {
            "location_name": location_name,
            "latitude": latitude,
            "longitude": longitude,
            "created_at": datetime.utcnow()
        }

        result = cameras_collection.insert_one(camera_data)

        mongo_id = str(result.inserted_id)

        last_5 = mongo_id[-5:].upper()

        camera_id = f"SISTCAM{last_5}"

        cameras_collection.update_one(
            {"_id": result.inserted_id},
            {"$set": {"camera_id": camera_id}}
        )

        print(f"📷 Camera Registered: {camera_id}")

        return camera_id