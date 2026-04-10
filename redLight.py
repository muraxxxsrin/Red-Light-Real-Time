import cv2
import os
import time
from ultralytics import YOLO

import config
from DB.violationLogger import ViolationLogger
from utils.licensePlate import fix_indian_plate_format

from api.cloudinaryUploader import upload_violation_image
from DB.violationModel import ViolationModel
from utils.offlineQueue import save_to_offline, start_offline_sync
from api.visionApi import get_cloud_ocr, preprocess_for_ocr
import threading
import queue
import random


class redWrongViolation:

    def __init__(self):

        print("🚦 Initializing Red Light + Wrong Way + OCR System...")

        self.vehicle_model = YOLO(config.VEHICLE_MODEL_PATH)
        self.plate_model = YOLO(config.PLATE_MODEL_PATH)

        self.cap = cv2.VideoCapture(config.INPUT_VIDEO_PATH)

        self.logger = ViolationLogger()

        self.last_positions = {}
        self.redlight_triggered = set()
        self.wrongway_triggered = set()

        self.frame_count = 0

        # ===== Traffic signal timing =====
        self.CYCLE_TIME = 100
        self.RED_TIME = 20
        self.cycle_start = time.time()

        # ==== Background Queues Setup ====
        self.ocr_queue = queue.Queue()
        self.ocr_thread = threading.Thread(target=self.ocr_worker, daemon=True)
        self.ocr_thread.start()

        self.upload_queue = queue.Queue()
        self.upload_thread = threading.Thread(target=self.upload_worker, daemon=True)
        self.upload_thread.start()

        # ==== Start the Autonomous Offline Re-uploader Daemon ====
        start_offline_sync()


    def process(self):

        print("🎥 Processing traffic violations with timed signal...")

        while self.cap.isOpened():

            ret, frame = self.cap.read()
            if not ret:
                break

            clean_frame = frame.copy()

            elapsed = time.time() - self.cycle_start
            phase = elapsed % self.CYCLE_TIME
            is_red = phase < self.RED_TIME

            results = self.vehicle_model.track(
                frame,
                persist=True,
                tracker="bytetrack.yaml",
                verbose=False
            )

            line_color = (0, 0, 255) if is_red else (0, 255, 0)

            cv2.line(
                frame,
                (config.STOP_LINE_X, config.STOP_LINE_Y),
                (frame.shape[1], config.STOP_LINE_Y),
                line_color,
                3
            )

            # Draw vertical divider line
            cv2.line(
                frame,
                (config.STOP_LINE_X, 0),
                (config.STOP_LINE_X, frame.shape[0]),
                (128, 128, 128),  # Gray divider
                2
            )

            cv2.putText(
                frame,
                "RED" if is_red else "GREEN",
                (config.STOP_LINE_X + 10, config.STOP_LINE_Y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                line_color,
                2
            )

            if results[0].boxes.id is not None:

                boxes = results[0].boxes.xyxy.cpu().numpy()
                ids = results[0].boxes.id.cpu().numpy()

                for box, car_id in zip(boxes, ids):

                    car_id = int(car_id)
                    x1, y1, x2, y2 = map(int, box)

                    cx = (x1 + x2) // 2
                    cy = (y1 + y2) // 2

                    prev = self.last_positions.get(car_id)
                    self.last_positions[car_id] = (cx, cy)

                    violation_type = None

                    # ===== RED LIGHT =====
                    if prev and is_red:
                        if prev[1] < config.STOP_LINE_Y and cy >= config.STOP_LINE_Y:
                            # Only flag violations on RIGHT SIDE (cx > STOP_LINE_X, beyond divider)
                            if cx > config.STOP_LINE_X:
                                if car_id not in self.redlight_triggered:
                                    self.redlight_triggered.add(car_id)
                                    violation_type = "red_light_jump"

                    # ===== WRONG WAY =====
                    if prev:
                        dy = cy - prev[1]
                        if dy < -5 and car_id not in self.wrongway_triggered:
                            self.wrongway_triggered.add(car_id)
                            violation_type = "wrong_way"

                    # =====================================================
                    # IF VIOLATION DETECTED
                    # =====================================================

                    if violation_type:

                        violation_frame = clean_frame.copy()

                        cv2.rectangle(
                            violation_frame,
                            (x1, y1),
                            (x2, y2),
                            (0, 0, 255),
                            3
                        )

                        cv2.putText(
                            violation_frame,
                            f"{violation_type} ID:{car_id}",
                            (x1, y1 - 5),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (0, 0, 255),
                            2
                        )

                        out_dir = (
                            config.REDLIGHT_DIR
                            if violation_type == "red_light_jump"
                            else config.WRONGWAY_DIR
                        )

                        v_path = os.path.join(
                            out_dir,
                            f"{violation_type}_ID{car_id}_frame{self.frame_count}.jpg"
                        )

                        cv2.imwrite(v_path, violation_frame)

                        # ===== INITIALIZE DB RECORD FIRST =====
                        violation_doc = ViolationModel(
                            vehicle_id=car_id,
                            violation_type=violation_type,
                            frame_number=self.frame_count,
                            plate_raw=None,
                            plate_clean=None,
                            speed=None,
                            confidence=None,
                            violation_image_url=None, # Filled via background thread
                            phone_number=random.choice(["9344033127","8247421583"]),
                            fine_amount=1000
                        )

                        challan_id = self.logger.log(violation_doc)
                        
                        print(f"🚨 {violation_type.upper()} → ID {car_id} → Initialized Challan: {challan_id}")
                        
                        if challan_id:
                            # 1. SEND CACHED IMAGE TO CLOUD WORKER
                            self.upload_queue.put({
                                "challan_id": challan_id,
                                "image_path": v_path,
                                "retries": 0
                            })
                            
                            # 2. SEND CROP TO OCR WORKER
                            car_crop = clean_frame[y1:y2, x1:x2]
                            self.ocr_queue.put({
                                "challan_id": challan_id,
                                "car_crop": car_crop,
                                "car_id": car_id
                            })

                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

                    cv2.putText(
                        frame,
                        f"ID:{car_id}",
                        (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (255,255,255),
                        2
                    )

            cv2.imwrite(
                os.path.join(config.REDWRONG_DIR, f"frame_{self.frame_count:06d}.jpg"),
                frame
            )

            self.frame_count += 1

        self.cap.release()
        print("✅ Traffic rule system finished")

    # ================= BACKGROUND OCR WORKER =================

    def ocr_worker(self):
        print("⚙️ OCR Background Worker Started...")
        while True:
            task = self.ocr_queue.get()
            
            if task is None:
                break
                
            challan_id = task["challan_id"]
            car_crop = task["car_crop"]
            car_id = task["car_id"]

            plate_raw = "TN03X4375"
            plate_clean = "TN03X4375"
            final_conf = 0.0

            if car_crop.shape[0] > 10 and car_crop.shape[1] > 10:

                plate_results = self.plate_model(
                    car_crop,
                    conf=0.1,
                    verbose=False
                )

                if len(plate_results[0].boxes) > 0:

                    px1, py1, px2, py2 = map(
                        int,
                        plate_results[0].boxes[0].xyxy[0]
                    )
                    
                    # Clamp inner plate coordinates
                    ph, pw = car_crop.shape[:2]
                    px1, py1 = max(0, px1), max(0, py1)
                    px2, py2 = min(pw, px2), min(ph, py2)

                    if (px2 - px1) > 0 and (py2 - py1) > 0:
                        plate_img = car_crop[py1:py2, px1:px2]

                        # 1. Preprocess using user-provided sharpening
                        processed_crop = preprocess_for_ocr(plate_img)

                        # 2. Extract using Google Cloud Vision
                        cloud_text = get_cloud_ocr(processed_crop)

                        if cloud_text:
                            # 3. Apply standard regex formatting to clean up whitespace
                            plate_raw = cloud_text
                            plate_clean = fix_indian_plate_format(plate_raw)
                            final_conf = 1.0 # Google doesn't return character-level conf in simplistic text_annotations

            # ===== UPDATE THE DATABASE VIA CHALLAN ID =====
            print(f"🔍 Background OCR Result for {challan_id} (ID:{car_id}): {plate_clean} ({final_conf:.2f})")
            self.logger.update_ocr(challan_id, plate_raw, plate_clean, final_conf)

            self.ocr_queue.task_done()

    # ================= BACKGROUND CLOUD WORKER =================
    
    def upload_worker(self):
        print("☁️ Cloudinary Upload Worker Started...")
        while True:
            task = self.upload_queue.get()
            
            if task is None:
                break
                
            challan_id = task["challan_id"]
            image_path = task["image_path"]
            retries = task["retries"]
            
            # Rely on actual time blocked by Cloudinary
            image_url = upload_violation_image(image_path)
            
            if image_url:
                print(f"✅ Cloudinary Success: {challan_id}")
                self.logger.update_image_url(challan_id, image_url)
            else:
                if retries < 3: # Retry 3 times
                    print(f"🔄 Retrying upload for {challan_id} (Attempt {retries + 1}/3)")
                    # Pushing it back into the queue allows other items to process
                    time.sleep(2) # Backoff
                    self.upload_queue.put({
                        "challan_id": challan_id,
                        "image_path": image_path,
                        "retries": retries + 1
                    })
                else:
                    print(f"❌ Cloudinary retries exhausted for {challan_id}. Saving to backup buffer.")
                    save_to_offline(challan_id, image_path)
                    
            self.upload_queue.task_done()


if __name__ == "__main__":
    redWrongViolation().process()