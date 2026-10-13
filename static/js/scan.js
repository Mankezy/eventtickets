/* QR nazorat sahifasi: kamera (jsQR) + qo'lda kiritish.
 * Muhim: natija FAQAT server javobidan keyin ko'rsatiladi.
 * Server bilan aloqa bo'lmasa, "tasdiqlandi" deyilmaydi. */
(function () {
  const verifyUrl = window.VERIFY_URL;
  if (!verifyUrl) return;

  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')
    ? document.querySelector('[name=csrfmiddlewaretoken]').value
    : getCookie('csrftoken');

  function getCookie(name) {
    const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }

  const resultBox = document.getElementById('resultBox');
  const video = document.getElementById('qrVideo');
  const placeholder = document.getElementById('scannerPlaceholder');
  const startBtn = document.getElementById('startCamBtn');
  const stopBtn = document.getElementById('stopCamBtn');
  const camError = document.getElementById('camError');
  const manualForm = document.getElementById('manualForm');
  const manualCode = document.getElementById('manualCode');
  const logBody = document.getElementById('logBody');

  let stream = null;
  let scanning = false;
  let lastScanned = { code: '', at: 0 };
  const RESULT_LABELS = {
    ok: ['ok', 'bi-check-circle-fill', 'RUXSAT'],
    already_used: ['warn', 'bi-exclamation-triangle-fill', 'ALLAQACHON ISHLATILGAN'],
    not_found: ['err', 'bi-x-circle-fill', 'TOPILMADI'],
    bad_signature: ['err', 'bi-shield-x', 'YAROQSIZ KOD'],
    cancelled: ['err', 'bi-x-octagon-fill', 'BEKOR QILINGAN'],
    wrong_event: ['err', 'bi-signpost-split', 'BOSHQA TADBIR'],
    wrong_order: ['err', 'bi-cash-coin', "TO'LANMAGAN"],
    forbidden: ['err', 'bi-lock', 'RUXSAT YO\'Q'],
    error: ['err', 'bi-wifi-off', 'SERVER BILAN ALOQA YO\'Q'],
  };

  function renderResult(data) {
    const [cls, icon, label] = RESULT_LABELS[data.result] || RESULT_LABELS.error;
    let html = `<div class="scan-result ${cls}">
      <div class="d-flex align-items-center gap-2">
        <i class="bi ${icon} big"></i>
        <div>
          <div class="fw-bold text-uppercase small">${label}</div>
          <div class="fw-semibold">${escapeHtml(data.message || '')}</div>
        </div>
      </div>`;
    if (data.serial) {
      html += `<hr class="my-2"><div class="small">
        <div><strong>${escapeHtml(data.event_title || '')}</strong> — ${escapeHtml(data.ticket_type || '')}</div>
        <div>Seriya: <span class="font-monospace">${escapeHtml(data.serial)}</span> · Egasi: ${escapeHtml(data.holder || '')}</div>`;
      if (data.used_at) {
        html += `<div class="mt-1"><i class="bi bi-clock-history me-1"></i>Oldingi kirish: <strong>${escapeHtml(data.used_at)}</strong>${data.used_by ? ' · ' + escapeHtml(data.used_by) : ''}</div>`;
      }
      html += `</div>`;
    }
    html += `</div>`;
    resultBox.innerHTML = html;
  }

  function renderOffline() {
    const [cls, icon, label] = RESULT_LABELS.error;
    resultBox.innerHTML = `<div class="scan-result ${cls}">
      <div class="d-flex align-items-center gap-2">
        <i class="bi ${icon} big"></i>
        <div><div class="fw-bold text-uppercase small">${label}</div>
        <div class="fw-semibold">Chipta tasdiqlanmadi — server javob bermadi. Qayta urinib ko'ring.</div></div>
      </div></div>`;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  async function sendCode(code) {
    if (!code) return;
    try {
      const resp = await fetch(verifyUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ code }),
      });
      const data = await resp.json().catch(() => ({}));
      renderResult(data);
      addLogRow(data);
      return data;
    } catch (e) {
      // Tarmoq xatosi — hech qachon "tasdiqlandi" ko'rsatilmaydi
      renderOffline();
    }
  }

  function addLogRow(data) {
    if (!logBody) return;
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, '0');
    const mm = String(now.getMinutes()).padStart(2, '0');
    const ss = String(now.getSeconds()).padStart(2, '0');
    const [cls, , label] = RESULT_LABELS[data.result] || RESULT_LABELS.error;
    const badgeCls = cls === 'ok' ? 'bg-success' : cls === 'warn' ? 'bg-warning text-dark' : 'bg-danger';
    const emptyRow = logBody.querySelector('.text-muted');
    if (emptyRow && emptyRow.closest('tr')) emptyRow.closest('tr').remove();
    logBody.insertAdjacentHTML('afterbegin',
      `<tr><td class="small">${hh}:${mm}:${ss}</td>
       <td class="small font-monospace">${escapeHtml(data.serial || '—')}</td>
       <td class="small">siz</td>
       <td><span class="badge ${badgeCls}">${escapeHtml(label)}</span></td></tr>`);
  }

  // --- Qo'lda kiritish ---
  if (manualForm) {
    manualForm.addEventListener('submit', function (e) {
      e.preventDefault();
      sendCode(manualCode.value.trim());
    });
  }

  // --- Kamera ---
  async function startCamera() {
    camError.style.display = 'none';
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' } },
        audio: false,
      });
      video.srcObject = stream;
      video.style.display = 'block';
      placeholder.style.display = 'none';
      await video.play();
      startBtn.style.display = 'none';
      stopBtn.style.display = '';
      scanning = true;
      requestAnimationFrame(tick);
    } catch (err) {
      camError.style.display = 'block';
    }
  }

  function stopCamera() {
    scanning = false;
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
    video.style.display = 'none';
    placeholder.style.display = '';
    startBtn.style.display = '';
    stopBtn.style.display = 'none';
  }

  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d', { willReadFrequently: true });

  function tick() {
    if (!scanning) return;
    if (video.readyState === video.HAVE_ENOUGH_DATA) {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
      if (typeof jsQR === 'function') {
        const found = jsQR(img.data, img.width, img.height, { inversionAttempts: 'dontInvert' });
        if (found && found.data) {
          const now = Date.now();
          // Bir xil kodni 5 soniya ichida takror yubormaslik
          if (found.data !== lastScanned.code || now - lastScanned.at > 5000) {
            lastScanned = { code: found.data, at: now };
            navigator.vibrate && navigator.vibrate(120);
            sendCode(found.data);
          }
        }
      }
    }
    requestAnimationFrame(tick);
  }

  if (startBtn) startBtn.addEventListener('click', startCamera);
  if (stopBtn) stopBtn.addEventListener('click', stopCamera);
})();
