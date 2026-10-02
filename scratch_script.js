    function toggleMenu() {
      document.getElementById('hamburgerMenu').classList.toggle('open');
    }
    document.addEventListener('click', function (e) {
      const menu = document.getElementById('hamburgerMenu');
      if (menu && !menu.contains(e.target)) {
        menu.classList.remove('open');
      }
    });

    // 全域設定物件快取
    let currentSettings = {
      FALL_CONF_THRESHOLD: 0.35,
      FALL_CONFIRM_SECONDS: 2.0,
      DEBOUNCE_ASPECT_RATIO: 1.25,
      DEBOUNCE_TILT_ANGLE: 60,
      STATIONARY_MINUTES: 10,
      ENABLE_FALL_NOTIF: true,
      ENABLE_INTRUSION_NOTIF: true,
      INCLUDE_SNAPSHOT: true,
      INCLUDE_VIDEO: true,
      ALERT_COOLDOWN_SECONDS: 30,
      ENABLE_AUTO_CALL: true,
      L2_COUNTDOWN_SECONDS: 15,
      EMERGENCY_CONTACT_NAME: "陳美玲（女兒）",
      EMERGENCY_CONTACT_PHONE: "0912-345-678"
    };

    // ====== 載入後端真實設定 ======
    function loadSettings() {
      fetch('/api/settings')
        .then(res => res.json())
        .then(settings => {
          currentSettings = Object.assign({}, currentSettings, settings);
          populateUI(currentSettings);
          document.getElementById("syncStatusText").textContent = "邊緣 AI 核心已同步 (" + new Date().toLocaleTimeString() + ")";
          refreshAnalyticsData();
        })
        .catch(err => {
          console.error("載入設定失敗:", err);
          document.getElementById("syncStatusText").textContent = "同步異常，使用離線設定";
          refreshAnalyticsData();
        });
    }

    // ====== 將設定填入 UI 表單 ======
    function populateUI(s) {
      // 1. 一級
      if (s.STATIONARY_MINUTES !== undefined) {
        document.getElementById("cfgStationaryMinutes").value = s.STATIONARY_MINUTES;
        updateStationaryLabel(s.STATIONARY_MINUTES);
      }
      // 2. 二級
      if (s.FALL_CONF_THRESHOLD !== undefined) {
        const confVal = Math.round(s.FALL_CONF_THRESHOLD * 100);
        document.getElementById("cfgFallConf").value = confVal;
        updateConfLabel(confVal);
      }
      if (s.FALL_CONFIRM_SECONDS !== undefined) {
        document.getElementById("cfgFallSec").value = s.FALL_CONFIRM_SECONDS;
        updateSecLabel(s.FALL_CONFIRM_SECONDS);
        const dSec = document.getElementById("cfgDebounceSec");
        if (dSec) dSec.value = s.FALL_CONFIRM_SECONDS;
        const dLbl = document.getElementById("lblDebounceSec");
        if (dLbl) dLbl.textContent = `${parseFloat(s.FALL_CONFIRM_SECONDS).toFixed(1)} 秒`;
      }
      if (s.DEBOUNCE_ASPECT_RATIO !== undefined) {
        const ar = document.getElementById("cfgAspectRatio");
        if (ar) ar.value = s.DEBOUNCE_ASPECT_RATIO;
        updateAspectRatioLabel(s.DEBOUNCE_ASPECT_RATIO);
      }
      if (s.DEBOUNCE_TILT_ANGLE !== undefined) {
        const ta = document.getElementById("cfgTiltAngle");
        if (ta) ta.value = s.DEBOUNCE_TILT_ANGLE;
        updateTiltAngleLabel(s.DEBOUNCE_TILT_ANGLE);
      }
      if (s.ENABLE_FALL_NOTIF !== undefined) {
        document.getElementById("cfgEnableFallNotif").checked = !!s.ENABLE_FALL_NOTIF;
      }
      if (s.ENABLE_INTRUSION_NOTIF !== undefined) {
        document.getElementById("cfgEnableIntrusionNotif").checked = !!s.ENABLE_INTRUSION_NOTIF;
      }
      if (s.INCLUDE_SNAPSHOT !== undefined) {
        document.getElementById("cfgIncludeSnapshot").checked = !!s.INCLUDE_SNAPSHOT;
      }
      if (s.INCLUDE_VIDEO !== undefined) {
        document.getElementById("cfgIncludeVideo").checked = !!s.INCLUDE_VIDEO;
      }
      if (s.ALERT_COOLDOWN_SECONDS !== undefined) {
        document.getElementById("cfgAlertCooldown").value = s.ALERT_COOLDOWN_SECONDS;
      }
      // 3. 三級
      if (s.ENABLE_AUTO_CALL !== undefined) {
        document.getElementById("cfgEnableAutoCall").checked = !!s.ENABLE_AUTO_CALL;
      }
      if (s.L2_COUNTDOWN_SECONDS !== undefined) {
        selectCountdownSec(s.L2_COUNTDOWN_SECONDS, false);
      }
      if (s.EMERGENCY_CONTACT_NAME !== undefined) {
        document.getElementById("cfgContactName").value = s.EMERGENCY_CONTACT_NAME;
      }
      if (s.EMERGENCY_CONTACT_PHONE !== undefined) {
        document.getElementById("cfgContactPhone").value = s.EMERGENCY_CONTACT_PHONE;
      }
    }

    // ====== 即時滑桿數值文字更新 ======
    function updateStationaryLabel(val) {
      document.getElementById("lblStationaryMinutes").textContent = `${val} 分鐘`;
    }
    function updateConfLabel(val) {
      document.getElementById("lblFallConf").textContent = (val / 100).toFixed(2);
    }
    function updateSecLabel(val) {
      document.getElementById("lblFallSec").textContent = `${parseFloat(val).toFixed(1)} 秒`;
      const dSec = document.getElementById("cfgDebounceSec");
      const dLbl = document.getElementById("lblDebounceSec");
      if (dSec) dSec.value = val;
      if (dLbl) dLbl.textContent = `${parseFloat(val).toFixed(1)} 秒`;
      currentSettings.FALL_CONFIRM_SECONDS = parseFloat(val);
    }

    // ====== 姿態防誤判微調控制函式 ======
    function syncDebounceSec(val) {
      document.getElementById("lblDebounceSec").textContent = `${parseFloat(val).toFixed(1)} 秒`;
      const fSec = document.getElementById("cfgFallSec");
      const fLbl = document.getElementById("lblFallSec");
      if (fSec) fSec.value = val;
      if (fLbl) fLbl.textContent = `${parseFloat(val).toFixed(1)} 秒`;
      currentSettings.FALL_CONFIRM_SECONDS = parseFloat(val);
    }

    function updateAspectRatioLabel(val) {
      const el = document.getElementById("lblAspectRatio");
      if (el) el.textContent = parseFloat(val).toFixed(2);
      currentSettings.DEBOUNCE_ASPECT_RATIO = parseFloat(val);
    }

    function updateTiltAngleLabel(val) {
      const el = document.getElementById("lblTiltAngle");
      if (el) el.textContent = `${val}°`;
      currentSettings.DEBOUNCE_TILT_ANGLE = parseInt(val);
    }

    function saveDebounceSettings() {
      saveAllSettings();
    }

    // ====== 倒數秒數 Pill 切換 ======
    function selectCountdownSec(sec, updateState = true) {
      document.querySelectorAll("#countdownRadioGroup .radio-pill").forEach(el => {
        if (parseInt(el.getAttribute("data-sec")) === parseInt(sec)) {
          el.classList.add("active");
        } else {
          el.classList.remove("active");
        }
      });
      document.getElementById("lblCountdownSec").textContent = `${sec} 秒`;
      if (updateState) {
        currentSettings.L2_COUNTDOWN_SECONDS = parseInt(sec);
      }
    }

    // ====== 儲存所有設定到後端 ======
    function saveAllSettings() {
      const payload = {
        STATIONARY_MINUTES: parseInt(document.getElementById("cfgStationaryMinutes").value),
        FALL_CONF_THRESHOLD: parseFloat((document.getElementById("cfgFallConf").value / 100).toFixed(2)),
        FALL_CONFIRM_SECONDS: parseFloat(document.getElementById("cfgFallSec").value),
        DEBOUNCE_ASPECT_RATIO: parseFloat(document.getElementById("cfgAspectRatio") ? document.getElementById("cfgAspectRatio").value : (currentSettings.DEBOUNCE_ASPECT_RATIO || 1.25)),
        DEBOUNCE_TILT_ANGLE: parseInt(document.getElementById("cfgTiltAngle") ? document.getElementById("cfgTiltAngle").value : (currentSettings.DEBOUNCE_TILT_ANGLE || 60)),
        ENABLE_FALL_NOTIF: document.getElementById("cfgEnableFallNotif").checked,
        ENABLE_INTRUSION_NOTIF: document.getElementById("cfgEnableIntrusionNotif").checked,
        INCLUDE_SNAPSHOT: document.getElementById("cfgIncludeSnapshot").checked,
        INCLUDE_VIDEO: document.getElementById("cfgIncludeVideo").checked,
        ALERT_COOLDOWN_SECONDS: parseInt(document.getElementById("cfgAlertCooldown").value),
        ENABLE_AUTO_CALL: document.getElementById("cfgEnableAutoCall").checked,
        L2_COUNTDOWN_SECONDS: parseInt(currentSettings.L2_COUNTDOWN_SECONDS || 15),
        EMERGENCY_CONTACT_NAME: document.getElementById("cfgContactName").value.trim(),
        EMERGENCY_CONTACT_PHONE: document.getElementById("cfgContactPhone").value.trim()
      };

      fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
        .then(res => res.json())
        .then(data => {
          if (data.success) {
            currentSettings = Object.assign({}, currentSettings, data.settings);
            document.getElementById("syncStatusText").textContent = "邊緣 AI 核心已同步 (" + new Date().toLocaleTimeString() + ")";
            showSaveToast();
          } else {
            alert("儲存失敗，請檢查網路連線。");
          }
        })
        .catch(err => {
          console.error("儲存設定失敗:", err);
          alert("儲存設定發生錯誤。");
        });
    }

    // ====== 載入與計算統計資料 (24 小時時段統計與區域分布，連接實體資料庫) ======
    function refreshAnalyticsData() {
      fetch('/api/records/all')
        .then(res => res.json())
        .then(data => {
          renderHourChart(data.events || []);
          renderZoneDistribution(data.cameras || [], data.events || [], data.zones || [], data.zone_counts || {});
        })
        .catch(err => console.error("載入統計失敗:", err));
    }

    function renderHourChart(events) {
      const totalEvents = events.length;
      const statTotalEl = document.getElementById("statTotalEvents");
      if (statTotalEl) statTotalEl.textContent = totalEvents;

      // 6 個時段統計：00-04, 04-08, 08-12, 12-16, 16-20, 20-24
      const slotCounts = [0, 0, 0, 0, 0, 0];
      const slotLabels = ["深夜 (00-04)", "清晨 (04-08)", "上午 (08-12)", "下午 (12-16)", "傍晚 (16-20)", "夜間 (20-24)"];

      events.forEach(ev => {
        let hour = 6;
        if (ev.time_str) {
          const parts = ev.time_str.split(" ");
          if (parts[1]) {
            const h = parseInt(parts[1].split(":")[0]);
            if (!isNaN(h)) hour = h;
          }
        } else if (ev.mtime) {
          hour = new Date(ev.mtime * 1000).getHours();
        }

        const slotIdx = Math.min(5, Math.floor(hour / 4));
        slotCounts[slotIdx]++;
      });

      const maxCount = Math.max(0, ...slotCounts);
      let peakIdx = 1; // 預設清晨
      let maxSlotCount = -1;

      slotCounts.forEach((count, i) => {
        const barEl = document.getElementById(`barSlot${i}`);
        const valEl = document.getElementById(`valSlot${i}`);
        if (valEl) valEl.textContent = count;

        const pctHeight = maxCount > 0 ? Math.max(8, Math.round((count / maxCount) * 85)) : 6;
        if (barEl) {
          barEl.style.height = `${pctHeight}%`;
          barEl.classList.remove("peak");
        }

        if (count > maxSlotCount) {
          maxSlotCount = count;
          peakIdx = i;
        }
      });

      const peakBar = document.getElementById(`barSlot${peakIdx}`);
      const statPeakEl = document.getElementById("statPeakHour");
      const tipEl = document.getElementById("hourAlertTip");

      if (totalEvents > 0 && maxSlotCount > 0) {
        if (peakBar) peakBar.classList.add("peak");
        if (statPeakEl) statPeakEl.textContent = slotLabels[peakIdx];
        if (tipEl) {
          if (peakIdx === 1) {
            tipEl.innerHTML = `💡 <strong>時段警示：</strong>清晨 04:00～08:00 為長輩起床如廁高峰，請注意走道防滑與感應夜燈輔助。`;
          } else if (peakIdx === 4) {
            tipEl.innerHTML = `💡 <strong>時段警示：</strong>傍晚 16:00～20:00 活動較頻繁，多發生於走道與客廳，請留意地毯與電線障礙。`;
          } else if (peakIdx === 0) {
            tipEl.innerHTML = `💡 <strong>時段警示：</strong>深夜 00:00～04:00 如廁活動風險偏高，建議加強走道感應照明與長輩防護。`;
          } else {
            tipEl.innerHTML = `💡 <strong>時段警示：</strong>${slotLabels[peakIdx]} 為近期發生次數最多時段 (${maxSlotCount}次)，請加強照護關注。`;
          }
        }
      } else {
        if (statPeakEl) statPeakEl.textContent = "尚無事件";
        if (tipEl) tipEl.innerHTML = `💡 <strong>資料庫即時狀態：</strong>目前黑盒子事件資料庫中無異常跌倒紀錄，各時段作息安全平穩。`;
      }
    }

    function renderZoneDistribution(cameras, events, zones, persistentZoneCounts) {
      const container = document.getElementById("zoneListContainer");
      if (!container) return;

      const zoneCounts = {};

      // 1. 從 zones.json (資料庫) 載入所有已配置監控區域
      if (zones && zones.length > 0) {
        zones.forEach(z => {
          zoneCounts[z] = 0;
        });
      }

      // 2. 從 cameras.json (資料庫) 載入每台攝影機所屬空間 (確保不遺漏)
      if (cameras && cameras.length > 0) {
        cameras.forEach(c => {
          const zName = c.zone || "未設定區域";
          if (zoneCounts[zName] === undefined) zoneCounts[zName] = 0;
        });
      }

      // 若完全沒有區域設定
      if (Object.keys(zoneCounts).length === 0) {
        container.innerHTML = `<div style="text-align:center; padding:16px; color:#8e929d; font-size:13px;">資料庫中尚未建立監控區域</div>`;
        return;
      }

      // 3. 套用真實累積次數
      let total = 0;
      if (persistentZoneCounts) {
        Object.keys(persistentZoneCounts).forEach(z => {
          if (zoneCounts[z] === undefined) zoneCounts[z] = 0;
          zoneCounts[z] = persistentZoneCounts[z];
        });
      }

      // 計算總數
      Object.values(zoneCounts).forEach(count => {
        total += count;
      });
      container.innerHTML = "";

      let maxZone = "尚無異常紀錄";
      let maxPct = 0;
      let maxCount = 0;

      const sortedZones = Object.keys(zoneCounts).sort((a, b) => {
        if (zoneCounts[b] !== zoneCounts[a]) return zoneCounts[b] - zoneCounts[a];
        return a.localeCompare(b, "zh-Hant");
      });

      sortedZones.forEach(zone => {
        const count = zoneCounts[zone];
        const pct = total > 0 ? Math.round((count / total) * 100) : 0;
        if (count > maxCount) {
          maxPct = pct;
          maxZone = zone;
          maxCount = count;
        }
        const isHigh = total > 0 && pct >= 50 && count > 0;

        const row = document.createElement("div");
        row.className = "zone-row";
        row.innerHTML = `
        <div class="zone-info">
          <span style="color:#ffffff;">📍 ${zone}</span>
          <strong style="color:${isHigh ? '#ff7875' : '#ebd07a'};">${count} 次 (${pct}%)</strong>
        </div>
        <div class="zone-track"><div class="zone-fill ${isHigh ? 'high' : ''}" style="width: ${count > 0 ? Math.max(6, pct) : 0}%;"></div></div>
      `;
        container.appendChild(row);
      });

      const highestNameEl = document.getElementById("highestRiskZoneName");
      const highestPctEl = document.getElementById("highestRiskZonePct");
      if (highestNameEl) {
        if (total > 0 && maxCount > 0) {
          highestNameEl.textContent = maxZone;
          if (highestPctEl) highestPctEl.textContent = `(累計 ${maxCount} 次 · 佔比約 ${maxPct}%)`;
        } else {
          highestNameEl.textContent = "目前無跌倒紀錄";
          if (highestPctEl) highestPctEl.textContent = "(各空間狀態安全良好)";
        }
      }
    }

    function showSaveToast() {
      const toast = document.getElementById("saveFeedbackToast");
      toast.classList.add("show");
      setTimeout(() => {
        toast.classList.remove("show");
      }, 3200);
    }

    // ====== 1. 一級模擬觸發 ======
    const toastL1 = document.getElementById("toastL1");
    document.getElementById("triggerL1").addEventListener("click", () => {
      const mins = document.getElementById("cfgStationaryMinutes").value;
      document.getElementById("toastL1Msg").textContent = `長輩在浴室已滯留 ${mins} 分鐘未移動，請關心確認長輩狀態。`;
      toastL1.classList.add("show");
      setTimeout(() => toastL1.classList.remove("show"), 6000);
    });
    function hideToast() { toastL1.classList.remove("show"); }

    // ====== 2. 二級動態倒數模擬 ======
    const overlayL2 = document.getElementById("overlayL2");
    const overlayL3 = document.getElementById("overlayL3");
    const ringNumber = document.getElementById("ringNumber");
    const ringProgress = document.getElementById("ringProgress");

    const RADIUS = 58;
    const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
    ringProgress.style.strokeDasharray = `${CIRCUMFERENCE} ${CIRCUMFERENCE}`;

    let countdownTimer = null;
    let remainingTime = 15;
    let currentTotalDuration = 15;

    function closeL2() {
      clearInterval(countdownTimer);
      overlayL2.classList.remove("is-open");
    }

    function openL2() {
      clearInterval(countdownTimer);
      currentTotalDuration = parseInt(currentSettings.L2_COUNTDOWN_SECONDS || 15);
      remainingTime = currentTotalDuration;
      ringNumber.textContent = remainingTime;
      ringProgress.style.strokeDashoffset = '0';

      // 依目前設定顯示置信度
      const confVal = (document.getElementById("cfgFallConf").value / 100).toFixed(2);
      document.getElementById("modalL2Conf").textContent = Math.max(0.85, parseFloat(confVal) + 0.15).toFixed(2);

      overlayL2.classList.add("is-open");

      countdownTimer = setInterval(() => {
        remainingTime--;
        ringNumber.textContent = remainingTime;

        const offset = CIRCUMFERENCE - (remainingTime / currentTotalDuration) * CIRCUMFERENCE;
        ringProgress.style.strokeDashoffset = offset;

        if (remainingTime <= 0) {
          clearInterval(countdownTimer);
          overlayL2.classList.remove("is-open");
        }
      }, 1000);
    }

    document.getElementById("triggerL2").addEventListener("click", openL2);
    document.getElementById("cancelL2").addEventListener("click", closeL2);
    document.getElementById("closeL2Cross").addEventListener("click", closeL2);

    // 初始化載入
    setTimeout(() => {
      loadSettings();
    }, 100);
  </script>
</body>

</html>
