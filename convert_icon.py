# convert_icon.py
from rembg import remove
from PIL import Image

print("⏳ AI 배경 제거(누끼) 및 .ico 변환 중...")

# 1. 원본 이미지 불러오기 및 배경 제거
input_img = Image.open('icon_raw.png')
output_img = remove(input_img)

# 2. 고화질 투명 PNG 및 Windows 전용 .ico 저장
output_img.save('app_icon.png', 'PNG')
output_img.save('app_icon.ico', format='ICO', sizes=[(256, 256)])

print("✨ 완료! 'app_icon.ico' 파일이 성공적으로 생성되었습니다.")