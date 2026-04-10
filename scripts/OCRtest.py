import cv2
import os
import json
from ultralytics import YOLO
from google.cloud import vision

# SETUP
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'C:\\Users\\HP\\Desktop\\vv Final Year Project\\services.json'
model = YOLO('C:\\Users\\HP\\Desktop\\vv Final Year Project\\models\\LP.pt')
client = vision.ImageAnnotatorClient()

IMAGE_DIR = "D:\\images"
OUTPUT_DIR = "C:\\Users\\HP\\Desktop\\vv Final Year Project\\OCR_processed_data"
BOXED_DIR = os.path.join(OUTPUT_DIR, "boxed_images")
JSON_FILE = os.path.join(OUTPUT_DIR, "results.json")

os.makedirs(BOXED_DIR, exist_ok=True)


def get_cloud_ocr(crop):
    success, encoded_image = cv2.imencode('.jpg', crop)
    content = encoded_image.tobytes()
    image = vision.Image(content=content)
    response = client.text_detection(image=image)
    texts = response.text_annotations
    return texts[0].description.strip() if texts else "No Text Detected"


def preprocess_for_ocr(crop):
    return cv2.detailEnhance(crop, sigma_s=10, sigma_r=0.15)


def process_all():

    results_data = []

    for image_name in os.listdir(IMAGE_DIR):

        if not image_name.lower().endswith(('.jpg', '.jpeg', '.png')):
            continue

        image_path = os.path.join(IMAGE_DIR, image_name)
        frame = cv2.imread(image_path)

        if frame is None:
            print(f"❌ Failed: {image_name}")
            continue

        results = model(frame)[0]

        print(f"\n📸 Processing: {image_name}")

        detected_plates = []

        for i, box in enumerate(results.boxes):

            x1, y1, x2, y2 = map(int, box.xyxy[0])

            # Crop for OCR only (not saving)
            plate_crop = frame[y1:y2, x1:x2]

            if plate_crop.size == 0:
                continue

            processed_crop = preprocess_for_ocr(plate_crop)
            plate_text = get_cloud_ocr(processed_crop)

            detected_plates.append(plate_text)

            # DRAW BOUNDING BOX on original image
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, plate_text, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        # Save boxed image with SAME original filename
        save_path = os.path.join(BOXED_DIR, image_name)
        cv2.imwrite(save_path, frame)

        print(f"✅ Boxed image saved: {save_path}")

        # Add to JSON
        results_data.append({
            "image_name": image_name,
            "plates": detected_plates if detected_plates else ["No Plate Detected"]
        })

    # Save JSON
    with open(JSON_FILE, "w") as f:
        json.dump(results_data, f, indent=4)

    print("\n✅ JSON saved:", JSON_FILE)


# RUN
process_all()