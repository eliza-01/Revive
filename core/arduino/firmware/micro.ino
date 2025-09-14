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

  // дальше всё как было...
  if (cmd.startsWith("mv ")) {
    ...
  } else if (cmd == "ping") {
    ...
  } else if (cmd.startsWith("enter_text ")) {
    String payload = cmd.substring(11);  // хвостовые пробелы теперь сохраняются
    if (payload.length() > 0) {
      typeSlow(payload.c_str());
    }
  } else if (cmd == "enter" || cmd.startsWith("enter ")) {
    String payload = "";
    if (cmd.startsWith("enter ") && cmd.length() > 6) {
      payload = cmd.substring(6);        // и тут тоже сохраняются
    }
    Keyboard.press(KEY_RETURN); delay(25); Keyboard.release(KEY_RETURN);
    delay(200);
    if (payload.length() > 0) {
      typeSlow(payload.c_str());
    }
    Keyboard.press(KEY_RETURN); delay(50); Keyboard.release(KEY_RETURN);
  }
  // ...остальные ветки без изменений
}
