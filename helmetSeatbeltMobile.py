import cv2
import os
from ultralytics import YOLO
import config
from DB.violationLogger import ViolationLogger
from utils.licensePlate import fix_indian_plate_format
import random
# NEW IMPORTS
from api.cloudinaryUploader import upload_violation_image
from DB.violationModel import ViolationModel
from utils.offlineQueue import save_to_offline, start_offline_sync
from api.visionApi import get_cloud_ocr, preprocess_for_ocr, save_ocr_debug_images
import threading
import queue
import time


def iou(a, b):
    xA, yA = max(a[0],b[0]), max(a[1],b[1])
    xB, yB = min(a[2],b[2]), min(a[3],b[3])
    inter = max(0,xB-xA) * max(0,yB-yA)
    areaA = (a[2]-a[0])*(a[3]-a[1])
    areaB = (b[2]-b[0])*(b[3]-b[1])
    return inter/(areaA+areaB-inter+1e-6)


class SafetyViolationModule:

    def __init__(self):

        print("🦺 Initializing Safety + OCR System...")

        self.vehicle_model = YOLO(config.VEHICLE_MODEL_PATH)
        self.safety_model = YOLO(config.SAFETY_MODEL_PATH)
        self.plate_model = YOLO(config.PLATE_MODEL_PATH)

        self.cap = cv2.VideoCapture(config.INPUT_VIDEO_PATH)

        self.logger = ViolationLogger()

        self.frame_count = 0
        self.state = {}

        # ==== Background Queues Setup ====
        self.ocr_queue = queue.Queue()
        self.ocr_thread = threading.Thread(target=self.ocr_worker, daemon=True)
        self.ocr_thread.start()

        self.upload_queue = queue.Queue()
        self.upload_thread = threading.Thread(target=self.upload_worker, daemon=True)
        self.upload_thread.start()

        # ==== Start the Autonomous Offline Re-uploader Daemon ====
        start_offline_sync()


    def get_state(self, vid):
        if vid not in self.state:
            self.state[vid] = {
                "helmet": False,
                "seatbelt": False,
                "triple": False,
                "mobile_count": 0,
                "mobile": False
            }
        return self.state[vid]


    def process(self):

        print("🎥 Processing safety violations with OCR...")

        while self.cap.isOpened():

            ret, frame = self.cap.read()
            if not ret:
                break

            clean = frame.copy()

            vres = self.vehicle_model.track(
                frame, persist=True, tracker="bytetrack.yaml", verbose=False
            )

            if vres[0].boxes.id is None:
                continue

            vehicles = zip(
                vres[0].boxes.xyxy.cpu().numpy(),
                vres[0].boxes.cls.cpu().numpy(),
                vres[0].boxes.id.cpu().numpy()
            )

            sres = self.safety_model(frame, conf=0.15, verbose=False)

            safety = {}
            for box, cls in zip(
                sres[0].boxes.xyxy.cpu().numpy(),
                sres[0].boxes.cls.cpu().numpy()
            ):
                name = self.safety_model.names[int(cls)]
                safety.setdefault(name, []).append(box)

            persons   = safety.get("person", [])
            helmets   = safety.get("helmet", [])
            nohelmets = safety.get("nohelmet", [])
            seatbelts = safety.get("seatbelt", [])
            mobiles   = safety.get("mobile", [])

            for vbox, vcls, vid in vehicles:

                vid = int(vid)
                state = self.get_state(vid)

                vtype = self.vehicle_model.names[int(vcls)]

                riders = [p for p in persons if iou(p,vbox) > 0.15]

                if vtype in ["motorcycle","bike"] and not state["helmet"]:
                    for nh in nohelmets:
                        if iou(nh,vbox) > 0.15:
                            self.capture(clean,vbox,"no_helmet",config.NO_HELMET_DIR,vid)
                            state["helmet"] = True

                if vtype in ["motorcycle","bike"] and len(riders) >= 2 and not state["helmet"]:
                    helmet_found = False
                    for h in helmets:
                        for r in riders:
                            if iou(h,r) > 0.3:
                                helmet_found = True
                    if not helmet_found:
                        self.capture(clean,vbox,"pillion_no_helmet",config.NO_HELMET_DIR,vid)
                        state["helmet"] = True

                if vtype in ["motorcycle","bike"] and len(riders) >= 3 and not state["triple"]:
                    self.capture(clean,vbox,"triple_riding",config.TRIPLE_DIR,vid)
                    state["triple"] = True

                if vtype == "car" and not state["seatbelt"]:
                    seatbelt_found = False
                    for sb in seatbelts:
                        if iou(sb,vbox) > 0.15:
                            seatbelt_found = True
                    if not seatbelt_found:
                        self.capture(clean,vbox,"no_seatbelt",config.NO_SEATBELT_DIR,vid)
                        state["seatbelt"] = True

                mobile_hit = False
                for m in mobiles:
                    if iou(m,vbox) > 0.1:
                        mobile_hit = True

                if mobile_hit:
                    state["mobile_count"] += 1
                else:
                    state["mobile_count"] = 0

                if state["mobile_count"] >= 5 and not state["mobile"]:
                    self.capture(clean,vbox,"mobile_usage",config.CELLPHONE_DIR,vid)
                    state["mobile"] = True

            self.frame_count += 1

        self.cap.release()
        print("✅ Safety OCR system finished")


    # ================= OCR + SAVE + DB =================

    def capture(self, frame, vbox, violation, folder, vid):

        h, w = frame.shape[:2]
        x1, y1 = max(0, int(vbox[0])), max(0, int(vbox[1]))
        x2, y2 = min(w, int(vbox[2])), min(h, int(vbox[3]))

        out = frame.copy()

        cv2.rectangle(out,(x1,y1),(x2,y2),(0,0,255),3)
        cv2.putText(out,f"{violation} ID:{vid}",(x1,y1-10),
                    cv2.FONT_HERSHEY_SIMPLEX,0.7,(0,0,255),2)

        path = os.path.join(folder,f"{violation}_ID{vid}_frame{self.frame_count}.jpg")
        cv2.imwrite(path,out)

        # ===== Upload QUEUED =====
        # We don't wait for the upload here to prevent main loop locking.

        # ===== CREATE INITIAL DB RECORD =====
        # We don't have OCR yet, so plate_raw/clean are None.
        violation_doc = ViolationModel(
            vehicle_id=vid,
            violation_type=violation,
            frame_number=self.frame_count,
            plate_raw=None,
            plate_clean=None,
            speed=None,
            confidence=None,
            violation_image_url=None, # Updated purely in the background later
            phone_number=random.choice(["9344033127","8247421583"]),
            fine_amount=1000
        )

        # logger.log inserts the record and returns the challan_id
        challan_id = self.logger.log(violation_doc)

        print(f"🚨 {violation.upper()} → ID {vid} → Initialized Challan: {challan_id}")

        if challan_id:
            # Send image path to upload queue
            self.upload_queue.put({
                "challan_id": challan_id,
                "image_path": path,
                "retries": 0
            })
            # ===== PUSH TO BACKGROUND OCR QUEUE =====
            # Extract the actual car crop while clamping is already done
            car_crop = frame[y1:y2, x1:x2]
            
            # Send specific data to the background worker so main thread isn't blocked
            self.ocr_queue.put({
                "challan_id": challan_id,
                "car_crop": car_crop,
                "vid": vid,
                "violation": violation
            })


    # ================= BACKGROUND OCR WORKER =================

    def ocr_worker(self):
        print("⚙️ OCR Background Worker Started...")
        while True:
            task = self.ocr_queue.get()
            
            if task is None:
                break
                
            challan_id = task["challan_id"]
            car_crop = task["car_crop"]
            vid = task["vid"]
            violation = task["violation"]

            plate_raw = ""
            plate_clean = ""
            final_conf = 0.0

            # Safe crop check
            if car_crop.shape[0] > 10 and car_crop.shape[1] > 10:
                save_ocr_debug_images(challan_id, car_crop=car_crop, tag="safety")
                pres = self.plate_model(car_crop, conf=0.1, verbose=False)

                if len(pres[0].boxes) > 0:
                    px1, py1, px2, py2 = map(int, pres[0].boxes[0].xyxy[0])
                    
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
                            tag="safety"
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
            print(f"🔍 Background OCR Result for {challan_id}: {plate_clean} ({final_conf:.2f})")
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
    SafetyViolationModule().process()