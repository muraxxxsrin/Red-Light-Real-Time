import cv2
import re
import numpy as np

def preprocess_plate_otsu(img):
    """Upscale -> Denoise -> Otsu Threshold"""
    if img.shape[0] == 0 or img.shape[1] == 0: return img
    
    upscaled = cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
    denoised = cv2.bilateralFilter(gray, 11, 17, 17)
    _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    final = cv2.copyMakeBorder(binary, 15, 15, 15, 15, cv2.BORDER_CONSTANT, value=[255, 255, 255])
    return final

def fix_indian_plate_format(text):
    """Enforces Indian License Plate Rules"""
    text = re.sub(r'[^A-Za-z0-9]', '', text).upper()
    if len(text) == 11 and text[-1] in ['1', 'I']: text = text[:-1]

    num_to_let = {'0': 'O', '1': 'I', '2': 'Z', '3': 'J', '4': 'A', '5': 'S', '6': 'G', '8': 'B'}
    let_to_num = {'O': '0', 'I': '1', 'Z': '2', 'J': '3', 'A': '4', 'S': '5', 'G': '6', 'B': '8', 'D': '0', 'Q': '0'}

    text_list = list(text)
    length = len(text_list)

    def force_let(i):
        if i < length and text_list[i] in num_to_let: text_list[i] = num_to_let[text_list[i]]
    def force_num(i):
        if i < length and text_list[i] in let_to_num: text_list[i] = let_to_num[text_list[i]]

    # Rule: DL Plates (Delhi)
    if length >= 2 and text_list[0] in ['O', '0', 'D', 'Q'] and text_list[1] in ['L', '1', 'I']:
        text_list[0] = 'D'; text_list[1] = 'L'
        force_num(2)
        if length == 10:
            force_let(4); force_let(5); force_num(6); force_num(7); force_num(8); force_num(9)
            
    # Rule: Standard Plates
    elif length == 10:
        force_let(0); force_let(1); force_num(2); force_num(3)
        force_let(4); force_let(5); force_num(6); force_num(7); force_num(8); force_num(9)
        
    return "".join(text_list)