import cv2
import pytesseract
from PIL import ImageGrab
import numpy as np

# For Windows, pytesseract might need the tesseract executable path set:
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Example champion slot positions (to be adjusted for your screen/client resolution)
# These are (x, y, w, h) tuples for each slot
ALLY_SLOTS = [
    (100, 200, 120, 40),  # Example values, update these!
    (100, 250, 120, 40),
    (100, 300, 120, 40),
    (100, 350, 120, 40),
    (100, 400, 120, 40),
]
ENEMY_SLOTS = [
    (1000, 200, 120, 40),
    (1000, 250, 120, 40),
    (1000, 300, 120, 40),
    (1000, 350, 120, 40),
    (1000, 400, 120, 40),
]

def grab_champion_names():
    # Take a screenshot of the whole screen
    screenshot = ImageGrab.grab()
    img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

    ally_names = []
    enemy_names = []

    for (x, y, w, h) in ALLY_SLOTS:
        crop = img[y:y+h, x:x+w]
        name = ocr_champion_name(crop)
        ally_names.append(name)

    for (x, y, w, h) in ENEMY_SLOTS:
        crop = img[y:y+h, x:x+w]
        name = ocr_champion_name(crop)
        enemy_names.append(name)

    return ally_names, enemy_names

def ocr_champion_name(img_crop):
    # Preprocess for better OCR
    gray = cv2.cvtColor(img_crop, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 160, 255, cv2.THRESH_BINARY)
    text = pytesseract.image_to_string(thresh, config='--psm 7')
    # Clean up text
    text = text.strip().replace("\n", " ").replace("\x0c", "")
    # Could add fuzzy matching to champion list here
    return text

if __name__ == "__main__":
    allies, enemies = grab_champion_names()
    print("Allies:", allies)
    print("Enemies:", enemies)
