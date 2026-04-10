import cloudinary
import cloudinary.uploader
import config


# Configure Cloudinary using your existing config.py
cloudinary.config(
    cloud_name=config.CLOUDINARY_CLOUD_NAME,
    api_key=config.CLOUDINARY_API_KEY,
    api_secret=config.CLOUDINARY_API_SECRET
)


def upload_violation_image(image_path):
    """
    Uploads an image to Cloudinary
    Returns secure URL if successful
    """

    try:
        result = cloudinary.uploader.upload(
            image_path,
            folder="traffic_violations",
            timeout=10
        )

        return result.get("secure_url")

    except Exception as e:
        print("❌ Cloudinary Upload Error:", e)
        return None