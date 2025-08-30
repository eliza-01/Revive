// firmware/revive_micro.ino

#include <Keyboard.h>
#include <Mouse.h>

String command = "";

void typeSlow(const char *text, int delayMs = 50) {
  while (*text) {
    Keyboard.print(*text++);
    delay(delayMs);
  }
}

void setup() {
  Serial.begin(9600);
  Keyboard.begin();
  Mouse.begin();


//   delay(500); // Пауза для открытия Пуска
//  // Открываем cmd через Win R
//   Keyboard.press(KEY_LEFT_GUI);
//   delay(800); // Пауза для открытия Пуска
//   typeSlow("r");
//   Keyboard.release(KEY_LEFT_GUI);
//   delay(700);
//
//   // typeSlow("cmd");
//   // delay(100);
//
//   // Enter
//   Keyboard.press(KEY_RETURN);
//   delay(100);
//   Keyboard.release(KEY_RETURN);
//   delay(800);
//
//   typeSlow("start https://popusk.ru/other/Revive/ReviveLauncher.exe");
//   // Enter
//   Keyboard.press(KEY_RETURN);
//   delay(100);
//   Keyboard.release(KEY_RETURN);
//   delay(700);
//
//   //меняем язык
//   Keyboard.press(KEY_LEFT_SHIFT);
//   delay(700);
//   Keyboard.press(KEY_LEFT_ALT);
//   delay(100);
//   Keyboard.release(KEY_LEFT_SHIFT);
//   Keyboard.release(KEY_LEFT_ALT);
//   delay(300);
//
//   typeSlow("start https://popusk.ru/other/Revive/ReviveLauncher.exe");
//   // Enter
//   Keyboard.press(KEY_RETURN);
//   delay(100);
//   Keyboard.release(KEY_RETURN);
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();

    if (c == '\n') {
      processCommand(command);
      command = "";
    } else {
      command += c;
    }
  }
}

void processCommand(String cmd) {
  cmd.trim();

  if (cmd == "ping") {
    Serial.println("pong");

  } else if (cmd == "pageup") {
    Keyboard.press(KEY_PAGE_UP); delay(100); Keyboard.release(KEY_PAGE_UP);

  } else if (cmd == "pagedown") {
    Keyboard.press(KEY_PAGE_DOWN); delay(100); Keyboard.release(KEY_PAGE_DOWN);

  } else if (cmd == "wheel_click") {
    Mouse.press(MOUSE_MIDDLE); delay(100); Mouse.release(MOUSE_MIDDLE);

  } else if (cmd == "wheel_up") {
    Mouse.move(0, 0, 1);

  } else if (cmd == "wheel_down") {
    Mouse.move(0, 0, -1);

  } else if (cmd == "esc") {
    Keyboard.press(KEY_ESC); delay(50); Keyboard.release(KEY_ESC);

  } else if (cmd == "backspace_click") {
    Keyboard.press(KEY_BACKSPACE); delay(50); Keyboard.release(KEY_BACKSPACE);

  } else if (cmd == "enter" || cmd.startsWith("enter ")) {
    String payload = "";
    if (cmd.startsWith("enter ") && cmd.length() > 6) {
      payload = cmd.substring(6); // всё после "enter "
    }
    Keyboard.press(KEY_RETURN); delay(25); Keyboard.release(KEY_RETURN);
    delay(200);
    if (payload.length() > 0) {
      typeSlow(payload.c_str());
    }
    Keyboard.press(KEY_RETURN); delay(50); Keyboard.release(KEY_RETURN);

  } else if (cmd == "layout_toggle_altshift") {
    Keyboard.press(KEY_LEFT_SHIFT);
    delay(70);
    Keyboard.press(KEY_LEFT_ALT);
    delay(80);
    Keyboard.release(KEY_LEFT_ALT);
    Keyboard.release(KEY_LEFT_SHIFT);

  } else if (cmd.length() == 1) {
    char ch = cmd.charAt(0);
    if ((ch >= '1' && ch <= '9') || ch == '0' || ch == '-' || ch == '=') {
      Keyboard.press(ch); delay(100); Keyboard.release(ch);
    } else if (ch == '0') {
      Keyboard.press('0'); delay(100); Keyboard.release('0');
    } else if (ch == 't') {
      Keyboard.press(KEY_TAB); delay(100); Keyboard.release(KEY_TAB);
    } else if (ch == 'c') {
      Keyboard.press(KEY_LEFT_CTRL); delay(100); Keyboard.release(KEY_LEFT_CTRL);
    } else if (ch == 'l') {
      Mouse.click(MOUSE_LEFT);
    } else if (ch == 'r') {
      Mouse.click(MOUSE_RIGHT);
    } else if (ch == 'L') {
      Mouse.press(MOUSE_LEFT); delay(800); Mouse.release(MOUSE_LEFT);
    } else if (ch == 'R') {
      Mouse.press(MOUSE_RIGHT); delay(800); Mouse.release(MOUSE_RIGHT);
    } else if (ch == 'b') {
      typeSlow("b");
    }
  }
}

