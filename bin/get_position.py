import pyautogui
import time
import keyboard
import numpy as np
import cv2
from PIL import ImageGrab

print("'s' 키: 좌측상단 좌표 저장")
print("'d' 키: 우측하단 좌표 저장")
print("'q' 키: 종료")
print("종료하려면 Ctrl+C")

top_left = None
bottom_right = None
last_box = None

def draw_box_on_screen():
    """화면에 박스를 그려서 보여주기"""
    global top_left, bottom_right, last_box
    
    if top_left is None or bottom_right is None:
        return
    
    # 스크린샷 찍기
    screenshot = ImageGrab.grab()
    img = np.array(screenshot)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    
    # 박스 그리기
    x1, y1 = top_left
    x2, y2 = bottom_right
    
    # 좌표 정렬 (x1 < x2, y1 < y2)
    x_min, x_max = min(x1, x2), max(x1, x2)
    y_min, y_max = min(y1, y2), max(y1, y2)
    
    cv2.rectangle(img, (x_min, y_min), (x_max, y_max), (0, 255, 0), 2)
    
    # 좌표 텍스트 표시
    cv2.putText(img, f"[{x_min}, {y_min}, {x_max}, {y_max}]", 
                (x_min, y_min - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    
    # 화면 크기에 맞게 리사이즈 (너무 크면)
    height, width = img.shape[:2]
    max_height = 800
    if height > max_height:
        scale = max_height / height
        new_width = int(width * scale)
        img = cv2.resize(img, (new_width, max_height))
    
    cv2.imshow('Box Preview', img)
    cv2.waitKey(1)
    
    last_box = [x_min, y_min, x_max, y_max]

while True:
    if keyboard.is_pressed('s'):
        x, y = pyautogui.position()
        top_left = (x, y)
        print(f"좌측상단 좌표 저장: ({x}, {y})")
        if bottom_right is not None:
            draw_box_on_screen()
            if last_box:
                print(f"박스 좌표: {last_box}")
        time.sleep(0.3)
    
    if keyboard.is_pressed('d'):
        x, y = pyautogui.position()
        bottom_right = (x, y)
        print(f"우측하단 좌표 저장: ({x}, {y})")
        if top_left is not None:
            draw_box_on_screen()
            if last_box:
                print(f"박스 좌표: {last_box}")
        time.sleep(0.3)
    
    if keyboard.is_pressed('q'):
        print("종료합니다.")
        cv2.destroyAllWindows()
        break
    
    # 박스가 있으면 계속 업데이트
    if top_left is not None and bottom_right is not None:
        draw_box_on_screen()
    
    time.sleep(0.02)
