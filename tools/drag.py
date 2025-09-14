# tools/drag.py
import time
from core.arduino.connection import ReviveController

c = ReviveController()
time.sleep(1)

# зажмём ПКМ вашим протоколом
c.send("R-press")
# 1 секунду ведём вправо
for _ in range(50):
    c.move_rel(10, 0)  # 10 тиков вправо каждые 20мс
    time.sleep(0.02)
# отпустим ПКМ
c.send("R-release")
