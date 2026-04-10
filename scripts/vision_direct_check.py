import argparse
import os
import sys
import cv2
from google.cloud import vision

# Make project-root imports work when running from scripts/.
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from api.visionApi import preprocess_for_ocr


def mean_word_confidence(response):
    words_conf = []
    try:
        for page in response.full_text_annotation.pages:
            for block in page.blocks:
                for paragraph in block.paragraphs:
                    for word in paragraph.words:
                        if hasattr(word, "confidence") and word.confidence is not None:
                            words_conf.append(float(word.confidence))
    except Exception:
        return 0.0
    return (sum(words_conf) / len(words_conf)) if words_conf else 0.0


def run_cloud_text_detection(image_bgr):
    ok, encoded = cv2.imencode(".jpg", image_bgr)
    if not ok:
        raise RuntimeError("Failed to encode image for Vision API")

    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=encoded.tobytes())
    response = client.text_detection(image=image)

    if response.error.message:
        raise RuntimeError(f"Vision API Error: {response.error.message}")

    text = response.text_annotations[0].description.strip() if response.text_annotations else ""
    confidence = mean_word_confidence(response)
    return text, confidence, response


def main():
    parser = argparse.ArgumentParser(description="Direct Google Vision OCR check for one image")
    parser.add_argument("image_path", help="Path to image file")
    parser.add_argument("--skip-preprocess", action="store_true", help="Run OCR on original image only")
    args = parser.parse_args()

    creds = os.path.join(ROOT_DIR, "services.json")
    if os.path.exists(creds):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds

    if not os.path.exists(args.image_path):
        raise FileNotFoundError(f"Image not found: {args.image_path}")

    image = cv2.imread(args.image_path)
    if image is None:
        raise RuntimeError("Could not load image with OpenCV")

    print(f"Image: {args.image_path}")
    print(f"Shape: {image.shape}")

    raw_text, raw_conf, raw_response = run_cloud_text_detection(image)
    print("\n=== OCR on original image ===")
    print(f"Detected text: {raw_text if raw_text else '<none>'}")
    print(f"Mean word confidence: {raw_conf:.4f}")
    print(f"Text annotations count: {len(raw_response.text_annotations)}")

    if not args.skip_preprocess:
        processed = preprocess_for_ocr(image)
        proc_text, proc_conf, proc_response = run_cloud_text_detection(processed)
        print("\n=== OCR on preprocessed image ===")
        print(f"Detected text: {proc_text if proc_text else '<none>'}")
        print(f"Mean word confidence: {proc_conf:.4f}")
        print(f"Text annotations count: {len(proc_response.text_annotations)}")


if __name__ == "__main__":
    main()
