// Конфигурация Mini App. Загрузите этот файл ДО app.js.
//
// apiBase — адрес прямого HTTP-API бота (ОПЦИОНАЛЬНО).
//   - Пустая строка  => данные отправляются боту через Telegram.WebApp.sendData
//                       — это рекомендуемый и simplest путь (работает, когда
//                         Mini App открыт кнопкой из reply-клавиатуры).
//   - Задан адрес    => Mini App POST-ит промпт на /generate напрямую и сам
//                        отображает результат (нужно для промптов >4096 байт
//                        или если sendData недоступен).
window.BOT_CONFIG = {
  apiBase: "", // например: "https://your-bot.example.com"
};
