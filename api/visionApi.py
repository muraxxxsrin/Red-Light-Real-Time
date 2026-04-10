import cv2
import os
from google.cloud import vision
import config

# 1. SETUP
# Ensure 'services.json' is in the same folder as this script
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'services.json'

# Initialize Client
client = vision.ImageAnnotatorClient()


def save_ocr_debug_images(challan_id, car_crop=None, plate_img=None, processed_img=None, tag="ocr"):
    """Save intermediate OCR images for debugging in config.LP_DETECT_DIR."""
    if not getattr(config, "OCR_DEBUG_SAVE", False):
        return

    safe_id = str(challan_id).replace("/", "_").replace("\\", "_")
    base_name = f"{tag}_{safe_id}"

    try:
        if car_crop is not None and getattr(car_crop, "size", 0) > 0:
            cv2.imwrite(os.path.join(config.LP_DETECT_DIR, f"{base_name}_01_car.jpg"), car_crop)

        if plate_img is not None and getattr(plate_img, "size", 0) > 0:
            cv2.imwrite(os.path.join(config.LP_DETECT_DIR, f"{base_name}_02_plate.jpg"), plate_img)

        if processed_img is not None and getattr(processed_img, "size", 0) > 0:
            cv2.imwrite(os.path.join(config.LP_DETECT_DIR, f"{base_name}_03_processed.jpg"), processed_img)
    except Exception as e:
        print(f"❌ OCR debug save failed for {challan_id}: {e}")


def _extract_word_confidence(response):
    """Compute mean word confidence from full_text_annotation if available."""
    try:
        words_conf = []
        for page in response.full_text_annotation.pages:
            for block in page.blocks:
                for paragraph in block.paragraphs:
                    for word in paragraph.words:
                        if hasattr(word, "confidence") and word.confidence is not None:
                            words_conf.append(float(word.confidence))
        if words_conf:
            return sum(words_conf) / len(words_conf)
    except Exception:
        # Keep OCR robust even if confidence tree is missing in a response.
        pass
    return 0.0

def get_cloud_ocr(crop):
    """Sends cropped image to Google Cloud Vision API.

    Returns:
        tuple[str | None, float]: (detected_text, confidence_0_to_1)
    """
    success, encoded_image = cv2.imencode('.jpg', crop)
    if not success:
        print("❌ Cloud Vision: Image Encoding Error")
        return None, 0.0
        
    content = encoded_image.tobytes()
    image = vision.Image(content=content)
    
    try:
        # Prefer document_text_detection to get richer full_text_annotation confidence.
        response = client.document_text_detection(image=image)
        if response.error.message:
            print(f"❌ Cloud Vision API Error (document): {response.error.message}")
            return None, 0.0

        detected_text = None
        if response.full_text_annotation and response.full_text_annotation.text:
            detected_text = response.full_text_annotation.text.strip()

        confidence = _extract_word_confidence(response)

        # Fallback for cases where document API yields empty text for tiny plate crops.
        if not detected_text:
            fallback = client.text_detection(image=image)
            if fallback.error.message:
                print(f"❌ Cloud Vision API Error (text): {fallback.error.message}")
                return None, 0.0
            texts = fallback.text_annotations
            detected_text = texts[0].description.strip() if texts else None

        return detected_text, confidence

    except Exception as e:
        print(f"❌ Cloud Vision Integration Error: {e}")
        return None, 0.0

def preprocess_for_ocr(crop):
    """Enhances plate crop for OCR reliability."""
    if crop is None or crop.size == 0:
        return crop

    # Upscale tiny plate crops so OCR can resolve character edges.
    h, w = crop.shape[:2]
    if min(h, w) < 120:
        scale = max(2.5, 140.0 / float(min(h, w)))
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 7, 50, 50)

    # Improve local contrast for dark/uneven lighting.
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Emphasize character strokes.
    blur = cv2.GaussianBlur(enhanced, (0, 0), 1.2)
    sharpened = cv2.addWeighted(enhanced, 1.6, blur, -0.6, 0)

    # Create high-contrast text mask.
    binary = cv2.adaptiveThreshold(
        sharpened,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        7,
    )

    # Reduce tiny noise while preserving character continuity.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

    # Add margin so border characters are not clipped by OCR.
    padded = cv2.copyMakeBorder(cleaned, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)

    # Convert back to BGR because imencode and upstream pipeline expect image arrays.
    return cv2.cvtColor(padded, cv2.COLOR_GRAY2BGR)
