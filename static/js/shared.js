document.addEventListener("DOMContentLoaded", () => {
  const mount = document.getElementById("topnav-mount");
  if (!mount) return;

  const currentPath = window.location.pathname.split("/").pop() || "index.html";
  const decodedPath = decodeURIComponent(currentPath);

  // 判斷是否為首頁
  const isIndexPage = decodedPath === "" || decodedPath === "index.html";

  const navItems = [
    { title: "功能索引", href: "index.html" },
    { title: "即時監看", href: "即時影像.html" },
    { title: "危險區域警報", href: "危險區域入侵越界警報.html" },
    { title: "歷史紀錄", href: "跌倒與異常姿態偵測.html" },
    { title: "隱私開關設定", href: "隱私模式開關.html" },
    { title: "警報設定", href: "三階段警報.html" }
  ];

  // 若為首頁則不渲染漢堡按鈕與下拉選單，其餘頁面正常顯示
  mount.innerHTML = `
    <header class="navbar-header">
      <a class="nav-brand" href="index.html">
        <span class="brand-title">Edge-Vision</span>
      </a>

      ${!isIndexPage
      ? `
      <div class="hamburger-menu-wrapper" id="hamburgerMenuWrapper">
        <button class="hamburger-btn" id="hamburgerBtn" type="button" aria-label="選單">
          <span></span>
          <span></span>
          <span></span>
        </button>

        <div class="hamburger-dropdown" id="hamburgerDropdown">
          ${navItems
        .map(
          (item) => `
            <a class="dropdown-item ${decodedPath === item.href ? "active" : ""}" href="${item.href}">
              <span>${item.title}</span>
            </a>
          `
        )
        .join("")}
        </div>
      </div>
      `
      : ""
    }
    </header>
  `;

  const wrapper = document.getElementById("hamburgerMenuWrapper");
  const btn = document.getElementById("hamburgerBtn");

  if (btn && wrapper) {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      wrapper.classList.toggle("open");
    });
    document.addEventListener("click", (e) => {
      if (!wrapper.contains(e.target)) {
        wrapper.classList.remove("open");
      }
    });
  }
});

document.addEventListener("DOMContentLoaded", () => {
  if (!document.getElementById("backToTopStyles")) {
    const style = document.createElement("style");
    style.id = "backToTopStyles";
    style.textContent = `
      .btn-back-to-top {
        position: fixed !important;
        bottom: 28px !important;
        right: 28px !important;
        width: 44px !important;
        height: 44px !important;
        background-color: #14161d !important;
        border: 1.5px solid #d4af37 !important;
        color: #f1c40f !important;
        border-radius: 0px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        cursor: pointer !important;
        z-index: 9999 !important;
        box-shadow: none !important;
        opacity: 0 !important;
        visibility: hidden !important;
        transform: translateY(12px) !important;
        transition: opacity 0.25s ease, transform 0.25s ease, background-color 0.2s ease, border-color 0.2s ease !important;
        outline: none !important;
      }
      .btn-back-to-top.is-visible {
        opacity: 1 !important;
        visibility: visible !important;
        transform: translateY(0) !important;
      }
      .btn-back-to-top:hover {
        background-color: #252834 !important;
        border-color: #f39c12 !important;
        color: #ffffff !important;
      }
      .btn-back-to-top:active {
        transform: scale(0.94) !important;
      }
    `;
    document.head.appendChild(style);
  }

  const backBtn = document.createElement("button");
  backBtn.id = "backToTopBtn";
  backBtn.className = "btn-back-to-top";
  backBtn.title = "回到最頂部";
  backBtn.setAttribute("aria-label", "回到最頂部");
  backBtn.innerHTML = `
    <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="18 15 12 9 6 15"></polyline>
    </svg>
  `;
  document.body.appendChild(backBtn);

  const checkScroll = () => {
    const scrollPos = window.pageYOffset || document.documentElement.scrollTop || document.body.scrollTop || 0;
    if (scrollPos > 50) {
      backBtn.classList.add("is-visible");
    } else {
      backBtn.classList.remove("is-visible");
    }
  };

  window.addEventListener("scroll", checkScroll, { passive: true });
  document.addEventListener("scroll", checkScroll, { passive: true });

  backBtn.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
    document.documentElement.scrollTo({ top: 0, behavior: "smooth" });
    document.body.scrollTo({ top: 0, behavior: "smooth" });
  });
});

// ====== 全域系統設定彈窗功能 ======
function ensureSettingsModal() {
  if (document.getElementById("settingsModal")) return;

  const modalHtml = `
  <div class="cam-modal-backdrop" id="settingsModal">
    <div class="cam-modal-window" style="max-width: 500px;">
      <div class="modal-topbar">
        <div class="modal-title">系統設定</div>
        <button class="modal-close-btn" onclick="closeSettingsModal()">&times;</button>
      </div>
      <div style="padding: 20px;">
        <div style="margin-bottom: 16px;">
          <p style="font-size:14px; color:#fff; line-height:1.5;">系統設定（包含 Discord Webhook URL）已整併至「警報設定與 AI 模型中心」頁面中進行統一管理。</p>
          <p style="font-size:12px; color:#8e929d; margin-top:8px;">請前往該頁面的「警報發送策略」區塊進行設定。</p>
        </div>
        <div style="text-align: right;">
          <button class="btn-primary" onclick="closeSettingsModal()" style="background:#1a1e28; border:1px solid #4a5568; color:#fff;">我知道了</button>
        </div>
      </div>
    </div>
  </div>`;
  document.body.insertAdjacentHTML("beforeend", modalHtml);

  const sModal = document.getElementById("settingsModal");
  if (sModal) {
    sModal.addEventListener("click", (e) => {
      if (e.target === sModal) {
        closeSettingsModal();
      }
    });
  }
}

function openSettingsModal() {
  ensureSettingsModal();
  const modal = document.getElementById("settingsModal");
  if (modal) modal.classList.add("open");
  fetch("/api/settings")
    .then((res) => res.json())
    .then((data) => {
      const input = document.getElementById("discordWebhookInput");
      if (input && data && data.DISCORD_WEBHOOK_URL !== undefined) {
        input.value = data.DISCORD_WEBHOOK_URL;
      }
    })
    .catch((err) => console.error("無法取得系統設定:", err));
}

function closeSettingsModal() {
  const modal = document.getElementById("settingsModal");
  if (modal) modal.classList.remove("open");
}

function saveSettings() {
  const input = document.getElementById("discordWebhookInput");
  const webhook = input ? input.value.trim() : "";
  fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ DISCORD_WEBHOOK_URL: webhook })
  })
    .then((res) => res.json())
    .then((data) => {
      if (data && data.success) {
        alert("系統設定已儲存！");
        closeSettingsModal();
      } else {
        alert("儲存設定失敗，請確認後端回應。");
      }
    })
    .catch((err) => {
      console.error(err);
      alert("儲存設定時發生網路錯誤。");
    });
}

// 點擊背景遮罩自動關閉
document.addEventListener("click", (e) => {
  const sModal = document.getElementById("settingsModal");
  if (sModal && e.target === sModal) {
    closeSettingsModal();
  }
});