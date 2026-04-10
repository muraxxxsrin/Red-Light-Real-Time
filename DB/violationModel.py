from datetime import datetime


class ViolationModel:

    def __init__(
        self,
        vehicle_id,
        violation_type,
        frame_number,
        plate_raw=None,
        plate_clean=None,
        speed=None,
        confidence=None,
        violation_image_url=None,
        phone_number=9344033127,
        fine_amount=1000
    ):

        self.vehicle_id = vehicle_id
        self.violation_type = violation_type
        self.frame_number = frame_number

        self.plate_raw = plate_raw
        self.plate_clean = plate_clean
        self.speed = speed
        self.confidence = confidence

        self.violation_image_url = violation_image_url
        self.phone_number = phone_number

        self.fine_amount = fine_amount

        # Lifecycle
        self.message_sent = False
        self.payment_status = "unpaid"
        self.payment_id = None
        self.paid_at = None

        self.status = "detected"
        self.timestamp = datetime.now()

    def to_dict(self):

        return {
            "vehicle_id": self.vehicle_id,
            "violation_type": self.violation_type,
            "frame_number": self.frame_number,

            "plate_raw": self.plate_raw,
            "plate_clean": self.plate_clean,

            "speed": self.speed,
            "confidence": self.confidence,

            "violation_image_url": self.violation_image_url,
            "phone_number": self.phone_number,

            "fine_amount": self.fine_amount,

            "message_sent": self.message_sent,
            "payment_status": self.payment_status,
            "payment_id": self.payment_id,
            "paid_at": self.paid_at,

            "status": self.status,
            "timestamp": self.timestamp
        }