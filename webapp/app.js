/* Photo Generator Mini App.
 *
 * Логика:
 *   1. Загрузить prompts.json и построить галерею превью.
 *   2. Клик по карточке => подставить промпт в textarea.
 *   3. Переключатель RU/EN => переключать язык промптов.
 *   4. «Сгенерировать» => либо Telegram.WebApp.sendData (режим по умолчанию),
 *      либо прямой POST на apiBase/generate (если задан apiBase в config.js).
 */
(function () {
  "use strict";

  var CONFIG = window.BOT_CONFIG || {};
  var API_BASE = String(CONFIG.apiBase || "").replace(/\/+$/, "");
  var MAX_PROMPT = 2000;

  var LANGS = { ru: "RU", en: "EN" };
  var LANG_NAMES = { ru: "Русский", en: "English" };

  var state = {
    all: [],
    visible: [],
    lang: readLang(),
    current: null, // выбранный объект промпта
  };

  var tg = window.Telegram && window.Telegram.WebApp;

  /* ----------------------------- helpers ----------------------------- */
  function byId(id) { return document.getElementById(id); }

  function readLang() {
    try { return localStorage.getItem("pg_lang") === "en" ? "en" : "ru"; }
    catch (e) { return "ru"; }
  }
  function saveLang(l) {
    try { localStorage.setItem("pg_lang", l); } catch (e) {}
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function titleOf(item) {
    return state.lang === "ru" ? (item.title_ru || item.theme) : (item.title_en || item.theme);
  }
  function promptOf(item) {
    if (state.lang === "ru") return item.prompt_ru || item.prompt_en || "";
    return item.prompt_en || item.prompt_ru || "";
  }

  function setStatus(text, kind) {
    var el = byId("status");
    el.textContent = text || "";
    el.className = "status" + (kind ? " status--" + kind : "");
  }
  function setBusy(busy) {
    byId("generate").disabled = busy;
    byId("generate").textContent = busy ? "⏳ Генерация…" : "✨ Сгенерировать";
  }

  function showNotice(text) {
    byId("notice-text").textContent = text;
    byId("notice").hidden = false;
  }
  function hideNotice() { byId("notice").hidden = true; }

  /* --------------------------- telegram init --------------------------- */
  function initTelegram() {
    if (!tg) return;
    try {
      if (typeof tg.ready === "function") tg.ready();
      if (typeof tg.expand === "function") tg.expand();
      if (typeof tg.setHeaderColor === "function") tg.setHeaderColor("palette");
    } catch (e) { /* не critical */ }
  }

  /* ------------------------------ prompts ------------------------------ */
  function loadPrompts() {
    fetch("prompts.json", { cache: "no-cache" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        var list = data;
        if (data && !Array.isArray(data) && Array.isArray(data.prompts)) list = data.prompts;
        if (!Array.isArray(list) || !list.length) throw new Error("empty");
        state.all = list;
        applyFilter();
      })
      .catch(function () {
        showNotice("Не удалось загрузить prompts.json — проверьте развертывание Mini App.");
      });
  }

  /* ------------------------------ render ------------------------------ */
  function renderGallery() {
    var gallery = byId("gallery");
    gallery.innerHTML = "";

    if (!state.visible.length) {
      gallery.innerHTML = '<p class="empty">Ничего не найдено.</p>';
      return;
    }

    state.visible.forEach(function (item) {
      var card = document.createElement("button");
      card.type = "button";
      card.className = "card" + (state.current && state.current.theme === item.theme ? " card--active" : "");
      card.dataset.theme = item.theme;

      var img = document.createElement("img");
      img.className = "card-img";
      img.loading = "lazy";
      img.alt = titleOf(item);
      img.src = item.preview_url || "";
      img.onerror = function () {
        img.classList.add("card-img--missing");
        img.removeAttribute("src");
        img.textContent = "🖼️";
      };

      var title = document.createElement("span");
      title.className = "card-title";
      title.textContent = titleOf(item);

      card.appendChild(img);
      card.appendChild(title);
      card.addEventListener("click", function () { selectPrompt(item); });
      gallery.appendChild(card);
    });
  }

  function applyFilter() {
    var q = byId("search").value.trim().toLowerCase();
    state.visible = state.all.filter(function (item) {
      if (!q) return true;
      var hay = [item.theme, item.title_ru, item.title_en, item.prompt_ru, item.prompt_en]
        .concat(item.tags || [])
        .join(" ")
        .toLowerCase();
      return hay.indexOf(q) !== -1;
    });
    renderGallery();
  }

  function selectPrompt(item) {
    state.current = item;
    var ta = byId("prompt");
    ta.value = promptOf(item);
    updateCounter();

    var cards = document.querySelectorAll(".card");
    cards.forEach(function (c) {
      c.classList.toggle("card--active", c.dataset.theme === item.theme);
    });

    ta.focus();
    if (typeof ta.scrollIntoView === "function") {
      ta.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    setStatus("");
  }

  function updateCounter() {
    var len = byId("prompt").value.length;
    var el = byId("counter");
    el.textContent = len + " / " + MAX_PROMPT;
    el.classList.toggle("counter--warn", len > MAX_PROMPT);
  }

  /* ------------------------------- actions ------------------------------- */
  function toggleLang() {
    state.lang = state.lang === "ru" ? "en" : "ru";
    saveLang(state.lang);
    byId("lang-toggle").textContent = LANGS[state.lang];
    renderGallery();
    if (state.current) {
      byId("prompt").value = promptOf(state.current);
      updateCounter();
    }
  }

  function randomPrompt() {
    if (!state.all.length) return;
    var item = state.all[Math.floor(Math.random() * state.all.length)];
    selectPrompt(item);
  }

  function copyPrompt() {
    var text = byId("prompt").value;
    if (!text) { setStatus("⚠️ Нет промпта для копирования.", "error"); return; }
    var done = function () { setStatus("✅ Промпт скопирован.", "ok"); };
    var fail = function () { setStatus("⚠️ Не удалось скопировать.", "error"); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, fail);
    } else {
      try {
        var ta = byId("prompt");
        ta.select();
        document.execCommand("copy");
        done();
      } catch (e) { fail(); }
    }
  }

  function generate() {
    var prompt = byId("prompt").value.trim();
    if (!prompt) { setStatus("⚠️ Выберите тему или введите промпт.", "error"); return; }
    if (prompt.length > MAX_PROMPT) {
      setStatus("⚠️ Промпт слишком длинный (макс. " + MAX_PROMPT + " знаков).", "error");
      return;
    }

    var item = state.current;
    var payload = {
      action: "generate",
      prompt: prompt,
      lang: state.lang,
      theme: item ? item.theme : null,
      theme_title: item ? titleOf(item) : null,
    };

    setBusy(true);
    setStatus("⏳ Отправляю запрос…");

    if (API_BASE) {
      directGenerate(prompt, payload);
    } else {
      sendViaTelegram(payload);
    }
  }

  function sendViaTelegram(payload) {
    if (!tg || typeof tg.sendData !== "function") {
      setBusy(false);
      setStatus("⚠️ Возвращение данных боту unavailable в этом режиме. " +
        "Задайте apiBase в config.js для прямого HTTP-режима.", "error");
      return;
    }
    try {
      tg.sendData(JSON.stringify(payload));
      // Mini App закроется после sendData; бот пришлёт изображение в чат.
    } catch (e) {
      setBusy(false);
      setStatus("⚠️ Ошибка отправки данных боту.", "error");
    }
  }

  function directGenerate(prompt, payload) {
    fetch(API_BASE + "/generate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Init-Data": tg ? (tg.initData || "") : "",
      },
      body: JSON.stringify({ prompt: prompt, lang: state.lang, theme: payload.theme }),
    })
      .then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, data: d }; });
      })
      .then(function (res) {
        setBusy(false);
        if (!res.ok) {
          var msg = (res.data && res.data.error) ? res.data.error : "Ошибка сервера.";
          setStatus("⚠️ " + msg, "error");
          return;
        }
        if (!res.data.image) { setStatus("⚠️ Сервер не вернул изображение.", "error"); return; }
        showResult(res.data.image, prompt);
        setStatus("✅ Изображение получено.", "ok");
      })
      .catch(function () {
        setBusy(false);
        setStatus("⚠️ Не удалось связаться с сервером бота.", "error");
      });
  }

  var currentResultSrc = "";
  function showResult(dataUrl, prompt) {
    currentResultSrc = dataUrl;
    byId("result-img").src = dataUrl;
    byId("result").hidden = false;
    if (typeof byId("result").scrollIntoView === "function") {
      byId("result").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }
  function downloadResult() {
    if (!currentResultSrc) return;
    try {
      var a = document.createElement("a");
      a.href = currentResultSrc;
      a.download = "generated-" + Date.now() + ".jpg";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (e) { /* ignore */ }
  }

  /* -------------------------------- bind -------------------------------- */
  function bind() {
    byId("lang-toggle").addEventListener("click", toggleLang);
    byId("search").addEventListener("input", applyFilter);
    byId("prompt").addEventListener("input", updateCounter);
    byId("random").addEventListener("click", randomPrompt);
    byId("copy").addEventListener("click", copyPrompt);
    byId("generate").addEventListener("click", generate);
    byId("close-result").addEventListener("click", function () {
      byId("result").hidden = true;
    });
    byId("download").addEventListener("click", downloadResult);
    byId("notice-close").addEventListener("click", hideNotice);
  }

  function start() {
    initTelegram();
    byId("lang-toggle").textContent = LANGS[state.lang];
    bind();
    loadPrompts();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
