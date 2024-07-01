import os
import requests
from datetime import datetime, timedelta
from PIL import Image
import pdf2image
import base64


def fetch_paper(prefix, offset=0):
    date = datetime.now() - timedelta(days=offset)
    path_to_pdf = f"https://cdn.freedomforum.org/dfp/pdf{date.day}/{prefix}.pdf"
    pdf_file = f"archive/{prefix}_{date.strftime('%Y%m%d')}.pdf"
    jpg_file = f"archive/{prefix}_{date.strftime('%Y%m%d')}.jpg"
    root_path = os.getcwd() + "/"

    # Check if JPG already exists
    if not os.path.exists(jpg_file):
        # Try to download PDF
        response = requests.get(path_to_pdf)
        if response.status_code == 200:
            # Save PDF
            with open(pdf_file, 'wb') as f:
                f.write(response.content)

            # Convert PDF to JPG
            images = pdf2image.convert_from_path(
                pdf_file, dpi=300, first_page=1, last_page=1)
            if images:
                img = images[0]
                # Resize image to have long edge of 1568 pixels
                width, height = img.size
                if width > height:
                    new_width = 1568
                    new_height = int(height * (1568 / width))
                else:
                    new_height = 1568
                    new_width = int(width * (1568 / height))
                img = img.resize((new_width, new_height))
                img.save(jpg_file, format="JPEG", quality=85)

            return jpg_file
    else:
        return jpg_file

    return False


def jpg_to_base64(file_path):
    """
    Load a JPEG file and return its base64-encoded data.
    """
    if not os.path.exists(file_path):
        return None

    with open(file_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
    return encoded_string


if __name__ == "__main__":
    # Usage
    newspapers = ["WSJ"]
    # Uncomment to add New York Times
    # newspapers.append("NY_NYT")

    # Example usage
    for prefix in newspapers:
        result = fetch_paper(prefix)
        if result:
            print(f"Successfully fetched and converted: {result}")
        else:
            print(f"Failed to fetch or convert: {prefix}")
