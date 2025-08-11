#create venv
cd C:/sv/Projects/Revive
python -m venv venv
venv\Scripts\activate

#install requirements
pip install -r requirements.txt

#activate venv
venv\Scripts\activate

#Tesseract dir
C:\Program Files\Tesseract-OCR
Win + R → ввести sysdm.cpl → Enter.
Вкладка Дополнительно → Переменные среды.
В списке Системные переменные найти Path, нажать Изменить.
Нажать Создать и вставить:
C:\Program Files\Tesseract-OCR

#l2 test account
eliza.83501@gmail.com
power55power

#Вход
cd C:/sv/Projects/Revive
venv\Scripts\activate
python main.py

#Структура
revive_project/
├── main.py                      ← точка входа, запускает GUI
├── version.txt                  ← текущая версия (для автообновления)

├── ui/
│   └── launcher_ui.py           ← основной GUI Revive

├── core/
│   ├── updater.py               ← логика автообновления
│   ├── connection_test.py       ← 
│   ├── revive_bot.py            ← базовая координация фич
│   └── features/                ← отдельные фичи
│       ├── resurrection.py      ← автоподъём после смерти
│       ├── buffing.py           ← автоматический баф
│       └── teleporting.py       ← телепортация в нужную локацию

├── assets/
│   └── icon.ico                 ← иконка для exe, прошивки, другие ресурсы

└── firmware/
    └── firmware_name.hex      ← прошивка для Arduino Micro 

#Репо с прошивками. Для Digistamp
https://raw.githubusercontent.com/digistump/arduino-boards-index/master/package_digistump_index.json
https://github.com/digistump/DigistumpArduino/releases/download/1.6.7/digistump-avr-1.6.7.zip
https://github.com/digistump/DigistumpArduino

cd C:\Users\Админ\AppData\Local\Arduino15\packages\digistump\tools\micronucleus\2.0a4
micronucleus.exe 1.ino.hex

#рабочий скетч
https://github.com/digistump/DigistumpArduino/blob/master/digistump-avr/libraries/DigisparkMouse/examples/Mouse/Mouse.ino

#Zadig driver update libusb-win32 (v1.4.0.0)
#обрати внимание на общение в talker.py в DigisparkCommunication

#Вступление, установка драйверов
https://amperkot.ru/blog/start-with-digispark/

#Загрузка обновления на хостинг
✅ Что понадобится:
1. Установим WinSCP CLI (если ещё не стоит)
Скачай и установи:
https://winscp.net/eng/download.php

По умолчанию WinSCP.com появляется в:

java
Копировать
Редактировать
C:\Program Files (x86)\WinSCP\WinSCP.com

✅ 2. Файл с FTP-доступом — deploy/ftp_credentials.txt
Пример содержимого:

host=ftp.yourhost.com
user=your_username
pass=your_password
remote_path=/public_html/revive/

#расчет сегментов
	#HP
	# rel_x = 23 / 1366 ≈ 0.0146
	# rel_y = 73 / 728 ≈ 0.1002
	# rel_w = 149 / 1366 ≈ 0.1090
	# rel_h = 11 / 728 ≈ 0.0151

	#В деревню
	# rel_x = 644 / 1366 ≈ 0.4714
	# rel_y = 321 / 728 ≈ 0.4409
	# rel_w = 94 / 1366 ≈ 0.0688
	# rel_h = 20 / 728 ≈ 0,.0274

#UPX сжатие. Путь к каталогу в release.bat абсолютный. UPX лежит в assets

#python двигает курсор внутри l2 только от имени администратора

#программно полученные
ALIVE_COLORS = [
    (154, 41, 30),
    (132, 28, 16),
    (165, 48, 33),
    (148, 36, 24),
    (159, 44, 30),
    (126, 50, 38),
    (134, 88, 79),
    (140, 97, 90),
    (123, 69, 57),
    (123, 60, 49),
]
DEAD_COLORS = [
    (41, 28, 8),
    (49, 24, 16),
    (66, 40, 33),
    (49, 32, 24),
    (55, 40, 35),
    (57, 44, 41),
    (63, 47, 41),
    (74, 56, 57)
]

#размеры окон для extractors
title bar: 32px (высота на win10 для всех разрешений?)
панель состояния :172x85px (у Кирилла. Видимо общий размер для всех разрешений?)
окно В деревню: 140х130px

# TAB Fix
2️⃣ Через Notepad++ (если есть)
Открой файл profile.py.
Ctrl+H (замена).
В поле Find what вставь \t (включи Match using Regular Expression или галочку Extended).
В поле Replace with вставь 4 пробела.
Нажми Replace All.
Сохрани.

#по шаблонам. Структура:
core/servers/l2mad/templates/<rus/eng>/<dashboard/death>/<teleport/buffer>:
dashboard/:
- dashboard_init.png
- dashboard_blocked.png
dashboard/teleport/:
- dashboard_teleport_button.png
teleport/villages/:
villages/Giran/:
- Giran.png
- DragonValley.png
- AntharasLair.png
villages/Aden/:
- Aden.png
- SilentValley.png
- ForsakenPlains.png
villages/Goddard/:
- Goddard.png
- VarkaSilenos.png
- HotSprings.png
- MonasteryOfSilence.png
dashboard/buffer/:
- dashboard_buffer_button.png
- dashboard_buffer_useProfile.png
- dashboard_buffer_useMage.png
- dashboard_buffer_useFighter.png
- dashboard_buffer_restoreHp.png
- dashboard_buffer_init.png
death/:
- to_village_button.png