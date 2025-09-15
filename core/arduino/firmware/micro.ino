// firmware/revive_micro.ino

#include <Keyboard.h>
#include <Mouse.h>

String command = "";

void typeSlow(const char *text, int delayMs = 25) {
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
  // убрать \n\r в конце
  while (cmd.length() && (cmd[cmd.length()-1] == '\n' || cmd[cmd.length()-1] == '\r')) {
    cmd.remove(cmd.length()-1);
  }

  // БЫЛО: cmd.trim();    // <-- это срезало нужный пробел после "/target "
  // СТАЛО: тримаем только слева, чтобы не терять хвостовые пробелы в payload
  while (cmd.length() && (cmd[0] == ' ' || cmd[0] == '\t')) {
    cmd.remove(0, 1);
  }

  // --- относительное движение курсора по HID (игры видят Raw Input) ---
  if (cmd.startsWith("mv ")) {
    int sp1 = cmd.indexOf(' ', 3);
    if (sp1 > 0) {
      long dx = cmd.substring(3, sp1).toInt();
      long dy = cmd.substring(sp1 + 1).toInt();
      // Mouse.move принимает -127..127 за тик — нарежем шаги
      while (dx != 0 || dy != 0) {
        int stepx = (dx > 127) ? 127 : (dx < -127 ? -127 : (int)dx);
        int stepy = (dy > 127) ? 127 : (dy < -127 ? -127 : (int)dy);
        Mouse.move(stepx, stepy, 0);
        dx -= stepx;
        dy -= stepy;
      }
    }
    return;
  }

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

  } else if (cmd == "press_enter") {
    Keyboard.press(KEY_RETURN); delay(40); Keyboard.release(KEY_RETURN);

  } else if (cmd.startsWith("enter_text ")) {   // печать без Enter
    String payload = cmd.substring(11);         // после "enter_text "
    if (payload.length() > 0) {
      typeSlow(payload.c_str());
    }

  } else if (cmd == "enter_text") {             // пустая печать (ничего не делаем)
    // no-op

  } else if (cmd == "enter" || cmd.startsWith("enter ")) {
    String payload = "";
    if (cmd.startsWith("enter ") && cmd.length() > 6) {
      payload = cmd.substring(6);
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

  } else if (cmd == "alt") {
    Keyboard.press(KEY_LEFT_ALT); delay(80); Keyboard.release(KEY_LEFT_ALT);

  } else if (cmd == "altB") {
    // Alt + B: нажать вместе, отпустить вместе
    Keyboard.press(KEY_LEFT_ALT);
    Keyboard.press('b');
    delay(80);
    Keyboard.releaseAll();

  } else if (cmd == "L-press") {
    Mouse.press(MOUSE_LEFT);
  } else if (cmd == "L-release") {
    Mouse.release(MOUSE_LEFT);
  } else if (cmd == "R-press") {
    Mouse.press(MOUSE_RIGHT);
  } else if (cmd == "R-release") {
    Mouse.release(MOUSE_RIGHT);
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
    } else if (ch == 'b') {
      typeSlow("b");
    }
  }
}

