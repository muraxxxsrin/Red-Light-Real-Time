import cv2
import os
import numpy as np
from ultralytics import YOLO

import config
from utils.tracker import SpeedTracker
from utils.licensePlate import fix_indian_plate_format
from DB.violationLogger import ViolationLogger
import random
import time
from api.cloudinaryUploader import upload_violation_image
from DB.violationModel import ViolationModel
from utils.offlineQueue import save_to_offline, start_offline_sync
from api.visionApi import get_cloud_ocr, preprocess_for_ocr, save_ocr_debug_images
import threading
import queue


class SpeedModule:

    def __init__(self):

        print("🚀 Initializing Traffic System...")

        self.vehicle_model = YOLO(config.VEHICLE_MODEL_PATH)
        self.plate_model = YOLO(config.PLATE_MODEL_PATH)

        self.cap = cv2.VideoCapture(config.INPUT_VIDEO_PATH)
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)

        self.tracker = SpeedTracker(fps=self.fps)

        self.violation_state = {}
        self.frame_count = 0

        roi_coords = getattr(config, "SPEED_ROI_COORDS", [])
        self.speed_roi = np.array(roi_coords, dtype=np.int32) if len(roi_coords) >= 3 else None

        self.logger = ViolationLogger()

        # ==== Background Queues Setup ====
        self.ocr_queue = queue.Queue()
        self.ocr_thread = threading.Thread(target=self.ocr_worker, daemon=True)
        self.ocr_thread.start()

        self.upload_queue = queue.Queue()
        self.upload_thread = threading.Thread(target=self.upload_worker, daemon=True)
        self.upload_thread.start()

        # ==== Start the Autonomous Offline Re-uploader Daemon ====
        start_offline_sync()

    def _draw_speed_roi(self, frame):
        if self.speed_roi is None or not getattr(config, "SPEED_ROI_DEBUG", True):
            return

        color = tuple(getattr(config, "SPEED_ROI_COLOR", (255, 255, 0)))
        thickness = int(getattr(config, "SPEED_ROI_THICKNESS", 2))
        alpha = float(getattr(config, "SPEED_ROI_FILL_ALPHA", 0.12))
        label = str(getattr(config, "SPEED_ROI_LABEL", "SPEED ROI"))

        pts = self.speed_roi.reshape((-1, 1, 2))

        if alpha > 0.0:
            overlay = frame.copy()
            cv2.fillPoly(overlay, [self.speed_roi], color)
            cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0, frame)

        cv2.polylines(frame, [pts], True, color, thickness, cv2.LINE_AA)

        anchor = tuple(self.speed_roi[0])
        cv2.putText(
            frame,
            label,
            (anchor[0] + 6, max(20, anchor[1] - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
            cv2.LINE_AA,
        )

    def _is_inside_speed_roi(self, x1, y1, x2, y2):
        if self.speed_roi is None:
            return True

        bx = int((x1 + x2) / 2)
        by = int(y2)
        return cv2.pointPolygonTest(self.speed_roi.astype(np.float32), (float(bx), float(by)), False) >= 0


    def process(self):

        print("🎥 Processing video...")

        while self.cap.isOpened():

            ret, frame = self.cap.read()
            if not ret:
                break

            clean_frame = frame.copy()
            self._draw_speed_roi(frame)

            results = self.vehicle_model.track(
                frame,
                persist=True,
                tracker="bytetrack.yaml",
                verbose=False
            )

            if results[0].boxes.id is not None:

                boxes = results[0].boxes.xyxy.cpu().numpy()
                ids = results[0].boxes.id.cpu().numpy()

                for box, car_id in zip(boxes, ids):

                    car_id = int(car_id)
                    x1, y1, x2, y2 = map(int, box)

                    if not self._is_inside_speed_roi(x1, y1, x2, y2):
                        continue

                    cx = int((x1 + x2) / 2)
                    cy = int((y1 + y2) / 2)

                    speed = self.tracker.update(car_id, (cx, cy))

                    if car_id not in self.violation_state:
                        self.violation_state[car_id] = {
                            "counter": 0,
                            "best_conf": 0.0,
                            "best_text": None,
                            "locked": False,
                            "saved": False,
                            "violation_saved": False
                        }

                    state = self.violation_state[car_id]

                    # =====================================================
                    # SPEED VIOLATION
                    # =====================================================

                    if speed > config.SPEED_LIMIT:
                        state["counter"] += 1
                    else:
                        state["counter"] = 0


                    if (
                        state["counter"] >= config.FRAMES_TO_CONFIRM
                        and not state["violation_saved"]
                    ):

                        violation_frame = clean_frame.copy()

                        cv2.rectangle(
                            violation_frame,
                            (x1, y1),
                            (x2, y2),
                            (0, 0, 255),
                            2
                        )

                        path = os.path.join(
                            config.VIOLATION_FRAMES_DIR,
                            f"violation_ID{car_id}_frame{self.frame_count}.jpg"
                        )

                        cv2.imwrite(path, violation_frame)

                        state["violation_saved"] = True

                        # ==============================
                        # UPLOAD QUEUED (handled by worker)
                        # ==============================
                        # We don't wait for upload.

                        # ==============================
                        # INIT DB RECORD
                        # ==============================

                        violation = ViolationModel(
                            vehicle_id=car_id,
                            violation_type="speeding",
                            frame_number=self.frame_count,
                            plate_raw=None,
                            plate_clean=None,
                            speed=round(speed, 2),
                            confidence=None,
                            violation_image_url=None, # Updated purely in the background later
                            phone_number=random.choice(["9344033127","8247421583"]),
                            fine_amount=1000
                        )

                        challan_id = self.logger.log(violation)

                        print(f"🚨 SPEED VIOLATION → ID {car_id} → Initialized Challan: {challan_id}")
                        
                        if challan_id:
                            # Send image path to upload queue
                            self.upload_queue.put({
                                "challan_id": challan_id,
                                "image_path": path,
                                "retries": 0
                            })
                            # Clamp vehicle coordinates to frame dimensions
                            h, w = frame.shape[:2]
                            cx1, cy1 = max(0, int(x1)), max(0, int(y1))
                            cx2, cy2 = min(w, int(x2)), min(h, int(y2))

                            car_crop = frame[cy1:cy2, cx1:cx2]
                            
                            self.ocr_queue.put({
                                "challan_id": challan_id,
                                "car_crop": car_crop,
                                "car_id": car_id,
                                "speed": speed
                            })

                    # =====================================================
                    # DRAWING
                    # =====================================================

                    color = (0, 255, 0) if speed <= config.SPEED_LIMIT else (0, 0, 255)

                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                    cv2.putText(
                        frame,
                        f"ID:{car_id} {speed:.1f}km/h",
                        (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (255, 255, 255),
                        2
                    )

            # =====================================================
            # SAVE ALL PROCESSED FRAMES
            # =====================================================

            all_frame_path = os.path.join(
                config.ALL_FRAMES_DIR,
                f"frame_{self.frame_count:06d}.jpg"
            )

            cv2.imwrite(all_frame_path, frame)

            self.frame_count += 1

        self.cap.release()
        print("✅ Traffic system finished")

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
            speed = task["speed"]

            plate_raw = ""
            plate_clean = ""
            final_conf = 0.0

            if car_crop.shape[0] > 10 and car_crop.shape[1] > 10:
                save_ocr_debug_images(challan_id, car_crop=car_crop, tag="speed")

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
                        save_ocr_debug_images(
                            challan_id,
                            car_crop=car_crop,
                            plate_img=plate_img,
                            processed_img=processed_crop,
                            tag="speed"
                        )

                        # 2. Extract using Google Cloud Vision
                        cloud_text, cloud_conf = get_cloud_ocr(processed_crop)

                        if cloud_text:
                            # 3. Apply standard regex formatting to clean up whitespace
                            plate_raw = cloud_text
                            plate_clean = fix_indian_plate_format(plate_raw)
                            final_conf = cloud_conf

            if not plate_clean or final_conf <= 0.0:
                plate_raw = plate_raw or "TN03X4375"
                plate_clean = "TN03X4375"

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
            
            # Simulate a 1-second delay for network requests 
            # (or rely on actual time blocked by Cloudinary)
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
    speed = SpeedModule()
    speed.process()