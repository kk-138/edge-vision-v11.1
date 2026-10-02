/*  每一頁的 <head> 裡加一行 script src="/static/js/theme-toggle.js"></script> */
(function () {
  var STORAGE_KEY = "edge_vision_theme";   // "dark" | "light"
  var root = document.documentElement;
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
 
  // 身分選擇頁（首頁 "/"）：不提供深淺色切換，固定維持原本的樣子
  var isLoginPage = location.pathname === "/" || /login/i.test(location.pathname);
 
  // ---------- 1. 讀取上次的選擇（放在 <head> 立刻套用，避免畫面閃一下） ----------
  var saved = "dark";
  try { saved = localStorage.getItem(STORAGE_KEY) || "dark"; } catch (e) {}
  if (saved === "light" && !isLoginPage) root.classList.add("theme-light");
 
  // 換色完成前先藏住畫面，避免先閃一下舊配色（最多 1.5 秒，保險起見一定會顯示）
  root.classList.add("ev-recolor-pending");
  setTimeout(function () { root.classList.remove("ev-recolor-pending"); }, 1500);
 
  // ---------- 2. 注入樣式 ----------
  var css = `
    /* ===== 卡片色條輪流上色（::before / ::after 畫的色條）===== */
    .ev-stripe-before::before { background: var(--ev-stripe) !important; }
    .ev-stripe-after::after   { background: var(--ev-stripe) !important; }
 
    /* ===== 換色中先隱藏 ===== */
    html.ev-recolor-pending body { visibility: hidden; }
 
    /* 身分選擇頁：整頁不放大，照顧者登入按鈕才不會超出畫面 */
    body:has(.hero) { zoom: 1 !important; }
 
    /* ===== 換頁淡入淡出 =====
       新版 Chrome / Safari：瀏覽器內建跨頁轉場（連 window.location 換頁也有效） */
    @view-transition { navigation: auto; }
    ::view-transition-old(root),
    ::view-transition-new(root) { animation-duration: 0.45s; animation-timing-function: ease; }
 
    /* 舊版瀏覽器的備援：進頁淡入、點連結離開時淡出 */
    html.ev-fade-fallback body { animation: evPageIn 0.45s ease both; }
    html.ev-fade-fallback.ev-leaving body {
      opacity: 0;
      transition: opacity 0.25s ease;
    }
    @keyframes evPageIn { from { opacity: 0; } to { opacity: 1; } }
 
    /* ===== 格子淡入：每次捲動到畫面裡都會重新淡入（原地淡入，不移動） =====
       用 animation 而不是 transition，才不會蓋掉各頁原本的 hover 動畫 */
    html .ev-reveal:not(.ev-in) {
      opacity: 0;
    }
    html .ev-reveal.ev-in {
      animation: evFadeIn 0.7s ease both;
      animation-delay: calc(var(--ev-i, 0) * 70ms);
    }
    /* 往上捲回來的格子：直接顯示，不淡入 */
    html .ev-reveal.ev-in.ev-noanim {
      animation: none;
      opacity: 1;
    }
    @keyframes evFadeIn {
      from { opacity: 0; }
      to   { opacity: 1; }
    }
 
    @media (prefers-reduced-motion: reduce) {
      ::view-transition-old(root), ::view-transition-new(root) { animation: none; }
      html.ev-fade-fallback body { animation: none; }
      html.ev-fade-fallback.ev-leaving body { transition: none; }
      html .ev-reveal:not(.ev-in), html .ev-reveal.ev-in { opacity: 1; animation: none; }
    }
 
    /* ===== 太陽／月亮切換按鈕（固定在左下角） ===== */
    .ev-theme-toggle {
      position: fixed;
      left: 20px;
      bottom: 20px;
      z-index: 9999;
      width: 44px;
      height: 44px;
      padding: 0;
      display: grid;
      place-items: center;
      background: rgba(23, 28, 35, 0.7);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
      border: 1.5px solid rgba(120, 227, 245, 0.45);
      border-radius: 0;
      color: #78E3F5;
      cursor: pointer;
      overflow: hidden;
      transition: background 0.2s ease, border-color 0.2s ease;
    }
    .ev-theme-toggle:hover {
      background: rgba(30, 37, 48, 0.9);
      border-color: #78E3F5;
    }
    .ev-theme-toggle:focus-visible {
      outline: 2px solid #78E3F5;
      outline-offset: 2px;
    }
    .ev-theme-toggle svg {
      grid-area: 1 / 1;
      width: 22px;
      height: 22px;
      transition: transform 0.5s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.35s ease;
    }
    /* 深色模式：顯示太陽（點了變淺色）；淺色模式：顯示月亮（點了變深色）；切換時旋轉交替 */
    .ev-theme-toggle .ic-sun  { opacity: 1; transform: none; }
    .ev-theme-toggle .ic-moon { opacity: 0; transform: rotate(90deg) scale(0.4); }
    html.theme-light .ev-theme-toggle .ic-sun  { opacity: 0; transform: rotate(-90deg) scale(0.4); }
    html.theme-light .ev-theme-toggle .ic-moon { opacity: 1; transform: none; }
  `;
  var style = document.createElement("style");
  style.id = "ev-theme-style";
  style.textContent = css;
  (document.head || root).appendChild(style);
 
 
  // ---------- 2.5 全站換色 ----------
  // 各頁面原本寫死的舊配色（#101024、#78E3F5…），在這裡統一換成新配色，
  // 不用一頁一頁改 HTML。舊色 → 角色 → 依深淺模式取新色（透明度保留原本的）
  var ROLE_OF = {};
  function addRole(role, hexes) {
    hexes.forEach(function (h) { var c = hexToRgb(h); ROLE_OF[c.join(",")] = role; });
  }
  function hexToRgb(h) {
    h = h.replace("#", "");
    if (h.length === 3 || h.length === 4) h = h.split("").map(function (x) { return x + x; }).join("");
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  }
  addRole("bg",      ["#101024", "#0b0c10", "#0C0C1C", "#0a0a1a"]);
  addRole("bgMid",   ["#1B2238", "#131729"]);
  addRole("bgHi",    ["#2A3450"]);
  addRole("card",    ["#171C23", "#16161a", "#1a1a20", "#202027", "#131729"]);
  addRole("surface", ["#1E2530", "#24242c", "#0d0d0f"]);
  addRole("border",  ["#2A3140", "#20263A"]);
  addRole("text",    ["#F5F1EA", "#f5f5f7", "#e0e0e0", "#ffffff"]);
  addRole("muted",   ["#9A9FB0", "#9e9ea7"]);
  addRole("offline", ["#5A6275"]);
  addRole("primary", ["#78E3F5", "#d4af37", "#f1c40f"]);
  addRole("primaryLight", ["#B4F1FA", "#D4F7FC", "#ebd07a"]);
  addRole("primaryDim",   ["#4FB8CC", "#997c22", "#f39c12"]);
  addRole("fence",   ["#D8FF5A"]);
  addRole("online",  ["#8EF5B5"]);
  addRole("alert",   ["#FF8066"]);
  addRole("alertRed",["#FF4D6A"]);
 
  var PALETTE = {
    // 深色：石板藍底、米白字、米杏強調
    dark: {
      bg: "#26344A", bgMid: "#2F4058", bgHi: "#4B6587",
      card: "#2E3E55", surface: "#34465F", border: "#5C7291",
      text: "#F7F6F2", muted: "#C8C6C6", offline: "#8E97A6",
      primary: "#F0E5CF", primaryLight: "#F7F6F2", primaryDim: "#D8CBB0",
      fence: "#E6C97E", online: "#A9DDB9", alert: "#FF9478", alertRed: "#FF6B80"
    },
    // 淺色：米白／米杏底、石板藍字與強調、霧灰框線
    light: {
      bg: "#F7F6F2", bgMid: "#EEF0F2", bgHi: "#DCE3EC",
      card: "#FDFCF9", surface: "#F1EEE6", border: "#C8C6C6",
      text: "#34475F", muted: "#7D828B", offline: "#A3A6AB",
      primary: "#4B6587", primaryLight: "#3A5070", primaryDim: "#6F86A5",
      fence: "#9A7428", online: "#3D7F5A", alert: "#D65A40", alertRed: "#CC3550"
    }
  };
  Object.keys(PALETTE).forEach(function (k) {
    var p = PALETTE[k];
    Object.keys(p).forEach(function (r) { p[r] = hexToRgb(p[r]); });
  });
 
  // ===== 卡片上方／左側粗色條的顏色（深淺模式共用）=====
  var STRIPE = {
    fence:   "#9BB8CD",   // 原本黃綠（圍籬／滯留）→ 鼠尾草綠
    primary: "#ADB2D4",   // 原本冰藍（系統）→ 灰藍
    alert:   "#EDC6B1",   // 原本珊瑚橘（警報／跌倒）→ 蜜桃
    other:   "#9CAFAA"    // 其他 → 霧灰
  };
  Object.keys(STRIPE).forEach(function (k) { STRIPE[k] = hexToRgb(STRIPE[k]); });
 
  // ===== 每張卡片輪流用的色條顏色（照頁面上的順序：第 1 張、第 2 張…循環）=====
  var STRIPE_CYCLE = ["#9BB8CD", "#ADB2D4", "#9CAFAA", "#EDC6B1"]
  // 這些是「狀態提示」色條（例如未審查事件），維持原本意義，不參與輪流
  var STRIPE_SKIP = ".incident-card, .ev-theme-toggle";
 
  // ===== 卡片透明度（0 = 全透明，1 = 完全不透明；null = 用各頁原本的設定）=====
  var CARD_OPACITY = {
    dark: 0.55,
    light: 0.75
  };
 
  // ===== 框線透明度（0 = 看不到，1 = 完全不透明）；框線顏色在下面 PALETTE 的 border =====
  var BORDER_OPACITY = {
    dark: 0.6,
    light: 1
  };
 
  function currentTheme() {
    return root.classList.contains("theme-light") ? "light" : "dark";
  }
 
  function mapColor(r, g, b, a, prop, theme) {
    var pal = PALETTE[theme];
    var role = ROLE_OF[r + "," + g + "," + b];
    var isTextProp = prop === "color" || prop === "-webkit-text-fill-color" || prop === "caret-color";
    if (prop === "stripe" && a > 0) {
      var sc = STRIPE[role === "fence" ? "fence" : (role === "alert" || role === "alertRed") ? "alert"
               : (role === "primary" || role === "primaryLight" || role === "primaryDim") ? "primary" : "other"];
      return sc.concat(a);
    }
 
    if (r === 0 && g === 0 && b === 0) {
      if (isTextProp) return pal.bg.concat(a);                       // 冰藍按鈕上的黑字
      if (theme === "light" && a < 1) return [75, 101, 135, +(a * 0.3).toFixed(3)]; // 陰影變淡
      return null;                                                   // 影片黑底維持
    }
    if (!role) {
      var lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
      if (lum < 0.16) role = isTextProp ? "bg" : "card";            // 其他深色底
      else if (lum > 0.86 && Math.max(r, g, b) - Math.min(r, g, b) < 30) role = "text"; // 其他白字
      else return null;                                              // 其他顏色不動
    }
    if (isTextProp && (role === "bg" || role === "bgMid" || role === "card" || role === "surface")) role = "bg";
    // 卡片、輸入框的細框線：原本是「半透明白字色」，統一改用 border 顏色
    var isBorderProp = /border|outline/.test(prop);
    if (isBorderProp && (role === "text" || role === "border") && a < 0.6) {
      role = "border";
      a = BORDER_OPACITY[theme];
    }
    // 半透明卡片（玻璃感）的透明度：有設定就用設定值，null 則沿用各頁原本的
    if ((role === "card" || role === "surface") && a < 1 && CARD_OPACITY[theme] != null) a = CARD_OPACITY[theme];
    return pal[role].concat(a);
  }
 
  var COLOR_RE = /#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b|rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)\s*(?:[,\/]\s*([\d.]+%?))?\s*\)/g;
 
  // 背景的左右對稱漸層（邊緣 → 中間 → 邊緣）改成平滑曲線，中間不會出現一條明顯的線
  // BAND_SOFT 越大，中間顏色越集中；越小，越往兩側擴散（建議 1～3）
  var BAND_SOFT = 1.6;
  var BAND_RE = /linear-gradient\(\s*90deg[^;]*?(?:#2A3450|rgb\(42,\s*52,\s*80\))\s*50%[^;]*?100%\s*\)/gi;
  function smoothBand(theme) {
    var pal = PALETTE[theme], from = pal.bg, to = pal.bgHi, stops = [];
    for (var x = 0; x <= 100; x += 5) {
      var t = Math.pow((1 - Math.cos(Math.PI * (1 - Math.abs(x - 50) / 50))) / 2, BAND_SOFT);
      var c = [0, 1, 2].map(function (k) { return Math.round(from[k] + (to[k] - from[k]) * t); });
      stops.push("rgb(" + c.join(", ") + ") " + x + "%");
    }
    return "linear-gradient(90deg, " + stops.join(", ") + ")";
  }
 
  function recolorValue(value, prop, theme) {
    if (!value || (value.indexOf("#") < 0 && value.indexOf("rgb") < 0)) return value;
    var hasBand = false;
    value = value.replace(BAND_RE, function () { hasBand = true; return "__EV_BAND__"; });
    var out = recolorColors(value, prop, theme);
    return hasBand ? out.split("__EV_BAND__").join(smoothBand(theme)) : out;
  }
 
  function recolorColors(value, prop, theme) {
    return value.replace(COLOR_RE, function (m, hex, r, g, b, a) {
      var rgb, alpha = 1;
      if (hex) {
        rgb = hexToRgb(hex);
        if (hex.length === 8) alpha = parseInt(hex.slice(6, 8), 16) / 255;
        if (hex.length === 4) alpha = parseInt(hex[3] + hex[3], 16) / 255;
      } else {
        rgb = [+r, +g, +b];
        if (a != null) alpha = a.slice(-1) === "%" ? parseFloat(a) / 100 : parseFloat(a);
      }
      var out = mapColor(rgb[0], rgb[1], rgb[2], alpha, prop, theme);
      if (!out) return m;
      return out[3] >= 1 ? "rgb(" + out[0] + ", " + out[1] + ", " + out[2] + ")"
                         : "rgba(" + out[0] + ", " + out[1] + ", " + out[2] + ", " + out[3] + ")";
    });
  }
 
  // 記住每條規則／每個元素「原本」的顏色，切換模式時都從原色重新換算
  var ruleOriginals = new WeakMap();
  var elOriginals = new WeakMap();
  var elWritten = new WeakMap();
 
  function snapshot(style) {
    var list = [];
    for (var i = 0; i < style.length; i++) {
      var prop = style[i];
      var val = style.getPropertyValue(prop);
      if (val && (val.indexOf("#") >= 0 || val.indexOf("rgb") >= 0)) {
        list.push([prop, val, style.getPropertyPriority(prop)]);
      }
    }
    return list;
  }
 
  // 用 ::before / ::after 畫的細色條（寬或高 6px 以下），例如統計卡左邊那條
  var stripeKeys = {};
  function pseudoKey(sel) {
    var m = sel && sel.match(/^\s*(\.[\w-]+)[^,]*?(::?(?:before|after))\s*$/);
    return m ? m[1] + m[2] : null;
  }
  function findStripes(rules) {
    for (var i = 0; i < rules.length; i++) {
      var r = rules[i];
      if (r.style && r.selectorText) {
        var k = pseudoKey(r.selectorText);
        var w = parseFloat(r.style.getPropertyValue("width")), h = parseFloat(r.style.getPropertyValue("height"));
        if (k && ((w > 0 && w <= 6) || (h > 0 && h <= 6 && !/%/.test(r.style.getPropertyValue("height"))))) stripeKeys[k] = true;
      }
      if (r.cssRules) findStripes(r.cssRules);
    }
  }
 
  function apply(style, list, theme, isStripeRule) {
    list.forEach(function (it) {
      var prop = it[0];
      if (isStripeRule && /^background/.test(prop)) prop = "stripe";
      // 卡片上方／左側的粗色條（3px 以上）→ 用 STRIPE 色票
      if (/^border-(top|left)-color$/.test(prop) &&
          parseFloat(style.getPropertyValue(prop.replace("color", "width"))) >= 3) prop = "stripe";
      var nv = recolorValue(it[1], prop, theme);
      if (style.getPropertyValue(it[0]) !== nv) style.setProperty(it[0], nv, it[2]);
    });
  }
 
  function walkRules(rules, theme) {
    for (var i = 0; i < rules.length; i++) {
      var rule = rules[i];
      if (rule.style) {
        var list = ruleOriginals.get(rule);
        if (!list) { list = snapshot(rule.style); ruleOriginals.set(rule, list); }
        if (list.length) apply(rule.style, list, theme, !!stripeKeys[pseudoKey(rule.selectorText)]);
      }
      if (rule.cssRules) walkRules(rule.cssRules, theme);
    }
  }
 
  function recolorElement(el, theme) {
    var current = el.getAttribute("style");
    var list = elOriginals.get(el);
    if (!list || current !== elWritten.get(el)) {      // 第一次，或頁面程式改過樣式
      list = snapshot(el.style);
      elOriginals.set(el, list);
    }
    if (list.length) apply(el.style, list, theme);
    elWritten.set(el, el.getAttribute("style"));
  }
 
  function recolorTree(node, theme) {
    if (node.nodeType !== 1) return;
    if (node.hasAttribute && node.hasAttribute("style")) recolorElement(node, theme);
    if (node.querySelectorAll) node.querySelectorAll("[style]").forEach(function (el) { recolorElement(el, theme); });
  }
 
  function recolorAll() {
    var theme = currentTheme();
    for (var j = 0; j < document.styleSheets.length; j++) {
      try { findStripes(document.styleSheets[j].cssRules); } catch (e) {}
    }
    for (var i = 0; i < document.styleSheets.length; i++) {
      var rules = null;
      try { rules = document.styleSheets[i].cssRules; } catch (e) {}   // 外部網站的樣式讀不到就跳過
      if (rules) walkRules(rules, theme);
    }
    if (document.body) recolorTree(document.body, theme);
    paintStripes();
  }
 
  // 找出頁面上有色條的卡片，依順序輪流上色
  function paintStripes() {
    if (!document.body) return;
    var n = 0;
    var els = document.body.querySelectorAll("*");
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (el.closest && el.closest(STRIPE_SKIP)) continue;
      var cs = getComputedStyle(el);
      var side = null;
      if (parseFloat(cs.borderTopWidth) >= 3 && cs.borderTopStyle !== "none" && parseFloat(cs.borderRightWidth) < 3) side = "top";
      else if (parseFloat(cs.borderLeftWidth) >= 3 && cs.borderLeftStyle !== "none" && parseFloat(cs.borderRightWidth) < 3) side = "left";
      var pseudo = null;
      if (!side) {
        ["before", "after"].some(function (p) {
          var ps = getComputedStyle(el, "::" + p);
          if (ps.content === "none" || ps.position !== "absolute") return false;
          var w = parseFloat(ps.width), h = parseFloat(ps.height);
          if (((w > 0 && w <= 6 && h > 20) || (h > 0 && h <= 6 && w > 20)) &&
              ps.backgroundColor !== "rgba(0, 0, 0, 0)") { pseudo = p; return true; }
          return false;
        });
      }
      if (!side && !pseudo) continue;
      var color = STRIPE_CYCLE[n++ % STRIPE_CYCLE.length];
      if (side) {
        if (el.style.getPropertyValue("border-" + side + "-color") !== color) {
          el.style.setProperty("border-" + side + "-color", color, "important");
          elWritten.set(el, el.getAttribute("style"));
        }
      } else {
        el.classList.add("ev-stripe-" + pseudo);
        el.style.setProperty("--ev-stripe", color);
        elWritten.set(el, el.getAttribute("style"));
      }
    }
  }
  var stripeTimer = null;
  function paintStripesSoon() {
    clearTimeout(stripeTimer);
    stripeTimer = setTimeout(paintStripes, 120);
  }
 
  function watchInlineStyles() {
    if (!window.MutationObserver) return;
    new MutationObserver(function (mutations) {
      var theme = currentTheme();
      mutations.forEach(function (m) {
        if (m.type === "attributes") {
          if (m.target.getAttribute("style") !== elWritten.get(m.target)) recolorElement(m.target, theme);
        } else {
          if (m.addedNodes.length) paintStripesSoon();
          m.addedNodes.forEach(function (n) {
            if (n.nodeType === 1) recolorTree(n, theme);
            if (n.nodeName === "STYLE" || n.nodeName === "LINK") setTimeout(recolorAll, 0);
          });
        }
      });
    }).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["style"] });
  }
 
  // ---------- 3. 太陽／月亮按鈕 ----------
  var SUN =
    '<svg class="ic-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">' +
    '<circle cx="12" cy="12" r="4.5"/>' +
    '<line x1="12" y1="1.5" x2="12" y2="4"/><line x1="12" y1="20" x2="12" y2="22.5"/>' +
    '<line x1="1.5" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="22.5" y2="12"/>' +
    '<line x1="4.6" y1="4.6" x2="6.4" y2="6.4"/><line x1="17.6" y1="17.6" x2="19.4" y2="19.4"/>' +
    '<line x1="4.6" y1="19.4" x2="6.4" y2="17.6"/><line x1="17.6" y1="6.4" x2="19.4" y2="4.6"/>' +
    '</svg>';
  var MOON =
    '<svg class="ic-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M20.5 14.5A8.5 8.5 0 1 1 9.5 3.5a7 7 0 0 0 11 11z"/>' +
    '</svg>';
 
  function updateLabel(btn) {
    var isLight = root.classList.contains("theme-light");
    var text = isLight ? "目前為淺色模式，點擊切換成深色" : "目前為深色模式，點擊切換成淺色";
    btn.setAttribute("aria-label", text);
    btn.title = text;
  }
 
  function addButton() {
    if (isLoginPage) return;                       // 身分選擇頁不顯示切換按鈕
    if (document.querySelector(".ev-theme-toggle")) return;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ev-theme-toggle";
    btn.innerHTML = SUN + MOON;
    updateLabel(btn);
 
    btn.addEventListener("click", function () {
      var isLight = root.classList.toggle("theme-light");
      try { localStorage.setItem(STORAGE_KEY, isLight ? "light" : "dark"); } catch (e) {}
      recolorAll();
      updateLabel(btn);
    });
 
    document.body.appendChild(btn);
  }
 
  // ---------- 4. 格子淡入：捲動到畫面裡才出現 ----------
  // 各頁面上的卡片、框框（找不到的 class 會自動略過）
  var REVEAL_SELECTOR = [
    ".page-head", ".header-actions-row",
    ".status-pill", ".metric-card", ".cam-card",
    ".setting-card", ".level-card", ".analysis-card", ".control-group",
    ".category-tabs", ".filter-bar",
    ".incident-card", ".daily-table", ".zone-row",
    ".analytics-sidebar > *", ".analysis-section-header", ".analytics-section-header"
  ].join(",");
 
  function initReveal() {
    if (reduceMotion || isLoginPage || !("IntersectionObserver" in window)) return;
 
    var SHOW_RATIO = 0.12;   // 露出 12% 就開始淡入
    var io = new IntersectionObserver(function (entries) {
      var i = 0;             // 同一批進入畫面的格子，一格接一格依序出現
      entries.forEach(function (entry) {
        var el = entry.target;
        // 露出 12%，或很高的格子已露出 120px 以上，就淡入
        var shown = entry.intersectionRatio >= SHOW_RATIO || entry.intersectionRect.height >= 120;
        var rootTop = entry.rootBounds ? entry.rootBounds.top : 0;
        var rootBottom = entry.rootBounds ? entry.rootBounds.bottom : window.innerHeight;
        var fromAbove = entry.boundingClientRect.top < rootTop;   // 格子在畫面上方（往上捲時出現）
 
        if (entry.isIntersecting && shown) {
          if (!el.classList.contains("ev-in")) {
            if (fromAbove) {
              el.classList.add("ev-noanim");                       // 往上捲：直接顯示
            } else {
              el.classList.remove("ev-noanim");                    // 往下捲：淡入
              el.style.setProperty("--ev-i", Math.min(i++, 8));
            }
            el.classList.add("ev-in");
          }
        } else if (!entry.isIntersecting && entry.boundingClientRect.top >= rootBottom) {
          // 格子從畫面「下方」離開（往上捲時），才重置；下次往下捲到這裡會再淡入
          // 從上方離開（往下捲時）則保持顯示，往上捲回來不會再淡入
          el.classList.remove("ev-in", "ev-noanim");
        }
      });
    }, { threshold: [0, 0.04, 0.08, SHOW_RATIO, 0.25], rootMargin: "0px 0px -6% 0px" });
 
    function watch(el) {
      if (el.classList.contains("ev-reveal")) return;   // 已經在處理的不重複
      el.classList.add("ev-reveal");
      io.observe(el);
    }
 
    document.querySelectorAll(REVEAL_SELECTOR).forEach(watch);
 
    // 之後才由程式載入的格子（例如事件清單、區域統計）也一起處理
    if (window.MutationObserver) {
      new MutationObserver(function (mutations) {
        mutations.forEach(function (m) {
          m.addedNodes.forEach(function (n) {
            if (n.nodeType !== 1) return;
            if (n.matches && n.matches(REVEAL_SELECTOR)) watch(n);
            if (n.querySelectorAll) n.querySelectorAll(REVEAL_SELECTOR).forEach(watch);
          });
        });
      }).observe(document.body, { childList: true, subtree: true });
    }
  }
 
  // ---------- 5. 換頁淡入淡出（瀏覽器不支援跨頁轉場時的備援） ----------
  var supportsViewTransition = ("PageRevealEvent" in window) || ("onpagereveal" in window);
  if (!supportsViewTransition) {
    root.classList.add("ev-fade-fallback");
 
    // 點站內連結：先淡出再換頁
    document.addEventListener("click", function (e) {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      var a = e.target.closest && e.target.closest("a[href]");
      if (!a || a.target === "_blank" || a.hasAttribute("download")) return;
      var url = new URL(a.href, location.href);
      if (url.origin !== location.origin) return;                         // 外部網站不處理
      if (url.pathname === location.pathname && url.hash) return;        // 同頁錨點不處理
      e.preventDefault();
      root.classList.add("ev-leaving");
      setTimeout(function () { location.href = url.href; }, 250);
    });
 
    // 按「上一頁」回來時，把淡出狀態清掉，避免畫面停在透明
    window.addEventListener("pageshow", function () {
      root.classList.remove("ev-leaving");
    });
  }
 
  // ---------- 6. 頁面載入後啟動 ----------
  function start() {
    recolorAll();
    root.classList.remove("ev-recolor-pending");
    watchInlineStyles();
    addButton();
    initReveal();
  }
  // 外部樣式表晚一點載完時，再補換一次
  window.addEventListener("load", recolorAll);
  document.addEventListener("load", function (e) {
    if (e.target && e.target.tagName === "LINK") recolorAll();
  }, true);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();