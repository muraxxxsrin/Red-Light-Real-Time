import cloudinary
import cloudinary.uploader
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config


# Configure Cloudinary
cloudinary.config(
    cloud_name=config.CLOUDINARY_CLOUD_NAME,
    api_key=config.CLOUDINARY_API_KEY,
    api_secret=config.CLOUDINARY_API_SECRET
)


def upload_pdf(pdf_path, challan_id):

    try:

        result = cloudinary.uploader.upload(
            pdf_path,
            resource_type="raw",   # Changed to raw for direct file delivery
            folder="traffic_challans",
            public_id=f"challan_{challan_id}.pdf",
            
        )

        pdf_url = result["secure_url"]

        print("📄 PDF Uploaded:", pdf_url)

        return pdf_url

    except Exception as e:
        print("❌ PDF Upload Failed:", e)
        return None
# pdf_path = r"C:\\Users\\HP\\Downloads\\Challan_Report_SIST87BEF8202C11.pdf"

# url = upload_pdf(pdf_path, "SIST87BEF8202C11")

# print("Public URL:", url)