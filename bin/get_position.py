import pyautogui
import time
import keyboard  # pip install keyboard 필요

print("마우스를 원하는 위치에 가져다 놓고 's' 키를 누르면 좌표+색상 출력됩니다.")
print("종료하려면 Ctrl+C")

while True:
    if keyboard.is_pressed('s'):
        x, y = pyautogui.position()
        r, g, b = pyautogui.pixel(x, y)
        print(f"좌표: ({x}, {y})   색상: ({r}, {g}, {b})")
        time.sleep(0.3)  # 중복 입력 방지ssss
    time.sleep(0.02)
