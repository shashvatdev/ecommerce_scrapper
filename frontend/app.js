/* ─────────────────────────────────────────────────────────────────
   EcomScraper — Frontend Application Logic
   ───────────────────────────────────────────────────────────────── */

const API = "http://localhost:8000";

// ── State ─────────────────────────────────────────────────────────
let selectedPlatform = "amazon";
let allProducts      = [];
let priceChart       = null;

// ── Init ──────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  checkHealth();
  loadDashboard();
  setInterval(checkHealth, 10000);

  // Allow Enter key to trigger scrape
  document.getElementById("scrape-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") startScrape();
  });
});

// ── Health Check ──────────────────────────────────────────────────
async function checkHealth() {
  const dot  = document.getElementById("status-dot");
  const text = document.getElementById("status-text");
  try {
    const res = await fetch(`${API}/health`, { signal: AbortSignal.timeout(4000) });
    if (res.ok) {
      dot.className  = "status-indicator online";
      text.textContent = "Backend Online";
    } else throw new Error();
  } catch {
    dot.className  = "status-indicator offline";
    text.textContent = "Backend Offline";
  }
}

// ── View Router ───────────────────────────────────────────────────
function showView(name) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));

  document.getElementById(`view-${name}`).classList.add("active");
  document.getElementById(`nav-${name}`)?.classList.add("active");

  const titles = {
    dashboard: ["Dashboard",    "Overview of all scraped products"],
    scrape:    ["Scrape Product", "Enter a URL or ASIN to fetch product data"],
    products:  ["All Products",   "Browse, filter, and sort your scraped data"],
    export:    ["Export Data",    "Download your data in CSV, JSON, or Excel format"],
  };
  const [title, sub] = titles[name] || ["", ""];
  document.getElementById("page-title").textContent    = title;
  document.getElementById("page-subtitle").textContent = sub;
}

// ── Platform Toggle ───────────────────────────────────────────────
function selectPlatform(platform) {
  selectedPlatform = platform;
  document.querySelectorAll(".toggle-btn").forEach(b => b.classList.remove("active"));
  document.getElementById(`toggle-${platform}`).classList.add("active");

  // Update placeholder hint
  const input = document.getElementById("scrape-input");
  if (platform === "amazon")   input.placeholder = "https://www.amazon.in/dp/B08N5WRWNW  or  B08N5WRWNW";
  if (platform === "flipkart") input.placeholder = "https://www.flipkart.com/product/p/itm?pid=XXXXX";
  if (platform === "both")     input.placeholder = "Enter Amazon URL or ASIN to compare on both platforms";
}

// ── Scrape ────────────────────────────────────────────────────────
async function startScrape() {
  const input  = document.getElementById("scrape-input").value.trim();
  if (!input) { showToast("Please enter a URL or ASIN", "error"); return; }

  const btn    = document.getElementById("scrape-btn");
  const status = document.getElementById("scrape-status");
  const msgEl  = document.getElementById("scrape-status-msg");
  const result = document.getElementById("scrape-result");

  btn.disabled = true;
  result.innerHTML = "";
  status.style.display = "flex";
  msgEl.textContent = `Launching browser and loading ${selectedPlatform === "both" ? "Amazon & Flipkart" : selectedPlatform}...`;

  // Detect input type
  const isAsin = /^[A-Z0-9]{10}$/.test(input.replace(/\s/g, ""));
  const payload = { input, type: isAsin ? "asin" : "url" };

  try {
    let data;
    if (selectedPlatform === "both") {
      msgEl.textContent = "Scraping Amazon and Flipkart simultaneously...";
      const res = await fetch(`${API}/scrape/both`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      data = await res.json();
      result.innerHTML = renderBothResult(data);
    } else {
      const endpoint = selectedPlatform === "amazon" ? "/scrape/amazon" : "/scrape/flipkart";
      const res = await fetch(`${API}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      data = await res.json();
      if (data.success) {
        result.innerHTML = renderScrapeResult(data.product);
        showToast("Product scraped successfully! ✅", "success");
      } else {
        throw new Error(data.detail || "Scraping failed");
      }
    }

    // Refresh dashboard stats
    loadDashboardStats();
  } catch (err) {
    result.innerHTML = `<div class="result-card" style="padding:20px;color:#f87171;">
      ❌ Error: ${err.message}
    </div>`;
    showToast(err.message, "error");
  } finally {
    status.style.display = "none";
    btn.disabled = false;
  }
}

function renderScrapeResult(p) {
  const imgHtml = p.image_url
    ? `<img class="result-img" src="${p.image_url}" alt="${escHtml(p.title || '')}" onerror="this.style.display='none'" />`
    : `<div class="result-img-placeholder">🛍️</div>`;

  const availability = p.availability?.toLowerCase().includes("in stock")
    ? `<span class="avail-in">✓ In Stock</span>`
    : `<span class="avail-out">✗ ${escHtml(p.availability || 'Unknown')}</span>`;

  return `
    <div class="result-card">
      <div class="result-header">
        ${imgHtml}
        <div class="result-info">
          <div class="result-title">${escHtml(p.title || 'N/A')}</div>
          ${p.brand ? `<div class="result-brand">by ${escHtml(p.brand)}</div>` : ''}
          <div class="result-prices">
            <span class="result-price">${p.price ? `₹${fmt(p.price)}` : 'N/A'}</span>
            ${p.mrp ? `<span class="result-mrp">₹${fmt(p.mrp)}</span>` : ''}
            ${p.discount ? `<span class="result-discount">${p.discount}% off</span>` : ''}
          </div>
          <div class="result-meta-row">
            ${p.rating ? `<span>⭐ ${p.rating} ${p.review_count ? `(${fmtNum(p.review_count)} reviews)` : ''}</span>` : ''}
            ${availability}
            ${p.seller ? `<span>Sold by ${escHtml(p.seller)}</span>` : ''}
          </div>
        </div>
      </div>
      <div class="result-footer">
        <a href="${p.product_url}" target="_blank" rel="noopener" class="btn btn-ghost btn-sm">🔗 Open on ${capitalize(p.platform)}</a>
        <button class="btn btn-sm" style="background:rgba(124,58,237,0.15);color:#a78bfa;border:1px solid rgba(124,58,237,0.3);"
          onclick="openProductModal(${p.id})">📈 View Price History</button>
      </div>
    </div>`;
}

function renderBothResult(data) {
  let html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:12px;">';
  for (const [platform, result] of Object.entries(data)) {
    if (result.success) {
      html += `<div>${renderScrapeResult(result.product)}</div>`;
    } else {
      html += `<div class="result-card" style="padding:20px;color:#f87171;">
        <strong>${capitalize(platform)}</strong><br/>❌ ${result.error}
      </div>`;
    }
  }
  html += '</div>';
  return html;
}

// ── Dashboard ─────────────────────────────────────────────────────
async function loadDashboard() {
  await loadDashboardStats();
  await loadRecentProducts();
}

async function loadDashboardStats() {
  try {
    const res  = await fetch(`${API}/stats`);
    const data = await res.json();
    document.getElementById("stat-total-val").textContent    = data.total_products ?? 0;
    document.getElementById("stat-amazon-val").textContent   = data.amazon_count ?? 0;
    document.getElementById("stat-flipkart-val").textContent = data.flipkart_count ?? 0;
    document.getElementById("stat-avg-val").textContent      = data.average_price ? `₹${fmt(data.average_price)}` : "—";
  } catch { /* offline */ }
}

async function loadRecentProducts() {
  try {
    const res      = await fetch(`${API}/products`);
    const products = await res.json();
    const container = document.getElementById("dashboard-products");
    if (!products.length) {
      container.innerHTML = `<div class="empty-state">No products yet. <a href="#" onclick="showView('scrape')">Scrape one!</a></div>`;
      return;
    }
    container.innerHTML = products.slice(0, 8).map(renderProductCard).join("");
  } catch {
    document.getElementById("dashboard-products").innerHTML =
      `<div class="empty-state">Could not load products. Is the backend running?</div>`;
  }
}

// ── All Products View ─────────────────────────────────────────────
async function loadProducts() {
  const platform = document.getElementById("filter-platform")?.value || "";
  const url = platform ? `${API}/products?platform=${platform}` : `${API}/products`;
  try {
    const res = await fetch(url);
    allProducts = await res.json();
    renderProducts(allProducts);
  } catch {
    document.getElementById("all-products-grid").innerHTML =
      `<div class="empty-state">Could not load products. Is the backend running?</div>`;
  }
}

function renderProducts(products) {
  const grid = document.getElementById("all-products-grid");
  if (!products.length) {
    grid.innerHTML = `<div class="empty-state">No products match your filters.</div>`;
    return;
  }
  grid.innerHTML = products.map(renderProductCard).join("");
}

function filterProducts() {
  const q = document.getElementById("filter-search").value.toLowerCase();
  const filtered = q
    ? allProducts.filter(p => (p.title || "").toLowerCase().includes(q) || (p.brand || "").toLowerCase().includes(q))
    : allProducts;
  renderProducts(filtered);
}

function sortProducts() {
  const by = document.getElementById("sort-by").value;
  const sorted = [...allProducts];
  if (by === "price-asc")   sorted.sort((a,b) => (a.price||0) - (b.price||0));
  if (by === "price-desc")  sorted.sort((a,b) => (b.price||0) - (a.price||0));
  if (by === "rating")      sorted.sort((a,b) => (b.rating||0) - (a.rating||0));
  if (by === "discount")    sorted.sort((a,b) => (b.discount||0) - (a.discount||0));
  if (by === "newest")      sorted.sort((a,b) => new Date(b.scraped_at) - new Date(a.scraped_at));
  renderProducts(sorted);
}

// ── Product Card ──────────────────────────────────────────────────
function renderProductCard(p) {
  const imgHtml = p.image_url
    ? `<img src="${p.image_url}" alt="${escHtml(p.title || '')}" loading="lazy" onerror="this.parentElement.innerHTML='<div class=\\'product-image-placeholder\\'>🛍️</div>'" />`
    : `<div class="product-image-placeholder">🛍️</div>`;

  const avail = p.availability?.toLowerCase().includes("in stock")
    ? `<span class="avail-in">✓ In Stock</span>`
    : `<span class="avail-out">✗ OOS</span>`;

  return `
    <div class="product-card" onclick="openProductModal(${p.id})">
      <div class="product-image-wrap">
        ${imgHtml}
        <span class="platform-badge ${p.platform}">${p.platform === 'amazon' ? '🟠 Amazon' : '🔵 Flipkart'}</span>
        ${p.discount ? `<span class="discount-badge">${p.discount}% off</span>` : ''}
      </div>
      <div class="product-body">
        <div class="product-title">${escHtml(p.title || 'Unknown Product')}</div>
        <div class="product-prices">
          <span class="product-price">${p.price ? `₹${fmt(p.price)}` : 'N/A'}</span>
          ${p.mrp ? `<span class="product-mrp">₹${fmt(p.mrp)}</span>` : ''}
        </div>
        <div class="product-meta">
          <div class="product-rating">
            ${p.rating ? `<span class="stars">★</span>${p.rating}` : '<span style="color:var(--text-muted)">No rating</span>'}
            ${p.review_count ? `<span style="color:var(--text-muted);font-size:0.7rem;">(${fmtNum(p.review_count)})</span>` : ''}
          </div>
          ${avail}
        </div>
      </div>
      <div class="product-actions">
        <a href="${p.product_url}" target="_blank" rel="noopener" class="btn btn-ghost btn-sm"
           onclick="event.stopPropagation()">🔗 View</a>
        <button class="btn btn-danger btn-sm" onclick="event.stopPropagation(); deleteProduct(${p.id})">🗑️ Delete</button>
      </div>
    </div>`;
}

// ── Product Modal ─────────────────────────────────────────────────
async function openProductModal(id) {
  const overlay = document.getElementById("modal-overlay");
  const content = document.getElementById("modal-content");
  overlay.classList.add("open");
  content.innerHTML = `<div style="padding:40px;text-align:center;"><div class="loader" style="margin:auto"></div></div>`;

  try {
    const res = await fetch(`${API}/products/${id}`);
    const p   = await res.json();

    const imgHtml = p.image_url
      ? `<img class="modal-product-img" src="${p.image_url}" alt="${escHtml(p.title || '')}" onerror="this.style.display='none'" />`
      : `<div class="modal-product-img-placeholder">🛍️</div>`;

    content.innerHTML = `
      <div class="modal-product-header">
        ${imgHtml}
        <div class="modal-product-info">
          <div class="modal-product-title">${escHtml(p.title || 'Unknown')}</div>
          ${p.brand ? `<div class="modal-product-brand">by ${escHtml(p.brand)}</div>` : ''}
          <div class="modal-price-row">
            <span class="modal-price">${p.price ? `₹${fmt(p.price)}` : 'N/A'}</span>
            ${p.mrp ? `<span class="modal-mrp">₹${fmt(p.mrp)}</span>` : ''}
            ${p.discount ? `<span class="modal-disc">${p.discount}% off</span>` : ''}
          </div>
          <div class="modal-meta-grid">
            ${p.rating ? `<div class="modal-meta-item">⭐ <strong>${p.rating}</strong> / 5</div>` : ''}
            ${p.review_count ? `<div class="modal-meta-item">💬 <strong>${fmtNum(p.review_count)}</strong> reviews</div>` : ''}
            ${p.seller ? `<div class="modal-meta-item">🏪 <strong>${escHtml(p.seller)}</strong></div>` : ''}
            ${p.availability ? `<div class="modal-meta-item">📦 <strong>${escHtml(p.availability)}</strong></div>` : ''}
          </div>
        </div>
      </div>

      <div class="modal-body">
        ${p.price_history?.length > 1 ? `
          <div class="modal-section-title">📈 Price History</div>
          <div class="modal-chart-wrap">
            <canvas id="price-chart-${p.id}"></canvas>
          </div>` : ''}

        <div class="modal-section-title">Actions</div>
        <div class="modal-actions">
          <a href="${p.product_url}" target="_blank" rel="noopener" class="btn btn-primary btn-sm">
            🔗 Open on ${capitalize(p.platform)}
          </a>
          <button class="btn btn-ghost btn-sm" onclick="rescrapeProduct('${p.product_url}', '${p.platform}', ${p.id})">
            🔄 Re-scrape
          </button>
          <button class="btn btn-danger btn-sm" onclick="deleteProduct(${p.id}); closeModal();">
            🗑️ Delete
          </button>
        </div>

        <div style="margin-top:16px;font-size:0.75rem;color:var(--text-muted);">
          First scraped: ${new Date(p.scraped_at).toLocaleString()} &nbsp;|&nbsp;
          Last updated: ${new Date(p.last_updated).toLocaleString()}
        </div>
      </div>`;

    // Render chart if history exists
    if (p.price_history?.length > 1) {
      renderPriceChart(p.id, p.price_history);
    }
  } catch (err) {
    content.innerHTML = `<div style="padding:30px;color:#f87171;">Failed to load product: ${err.message}</div>`;
  }
}

function closeModal() {
  document.getElementById("modal-overlay").classList.remove("open");
  if (priceChart) { priceChart.destroy(); priceChart = null; }
}

function renderPriceChart(id, history) {
  const ctx = document.getElementById(`price-chart-${id}`)?.getContext("2d");
  if (!ctx) return;

  const labels = history.map(h => {
    const d = new Date(h.recorded_at);
    return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  });
  const data = history.map(h => h.price);

  if (priceChart) priceChart.destroy();

  priceChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "Price (₹)",
        data,
        borderColor: "#7c3aed",
        backgroundColor: "rgba(124,58,237,0.12)",
        borderWidth: 2,
        pointRadius: 4,
        pointBackgroundColor: "#a78bfa",
        fill: true,
        tension: 0.4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `₹${fmt(ctx.raw)}`,
          },
        },
      },
      scales: {
        x: { ticks: { color: "#64748b", font: { size: 11 } }, grid: { color: "rgba(255,255,255,0.04)" } },
        y: {
          ticks: { color: "#64748b", font: { size: 11 }, callback: v => `₹${fmt(v)}` },
          grid: { color: "rgba(255,255,255,0.04)" },
        },
      },
    },
  });
}

// ── Re-scrape ─────────────────────────────────────────────────────
async function rescrapeProduct(url, platform, id) {
  showToast("Re-scraping...", "info");
  closeModal();
  try {
    const endpoint = platform === "amazon" ? "/scrape/amazon" : "/scrape/flipkart";
    const res = await fetch(`${API}${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input: url, type: "url" }),
    });
    const data = await res.json();
    if (data.success) {
      showToast("Re-scraped successfully! ✅", "success");
      loadDashboardStats();
    } else throw new Error(data.detail);
  } catch (err) {
    showToast(`Re-scrape failed: ${err.message}`, "error");
  }
}

// ── Delete Product ────────────────────────────────────────────────
async function deleteProduct(id) {
  if (!confirm("Delete this product? This cannot be undone.")) return;
  try {
    const res = await fetch(`${API}/products/${id}`, { method: "DELETE" });
    const data = await res.json();
    if (data.success) {
      showToast("Product deleted.", "success");
      loadDashboard();
      loadProducts();
    }
  } catch (err) {
    showToast(`Delete failed: ${err.message}`, "error");
  }
}

// ── Export ────────────────────────────────────────────────────────
function downloadExport(format) {
  const urls = { csv: "/export/csv", json: "/export/json", excel: "/export/excel" };
  const url = `${API}${urls[format]}`;
  const a = document.createElement("a");
  a.href = url;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
  showToast(`Downloading ${format.toUpperCase()} file...`, "info");
}

// ── Toast ─────────────────────────────────────────────────────────
let toastTimer = null;
function showToast(msg, type = "info") {
  let el = document.getElementById("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.className   = `show ${type}`;
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3500);
}

// ── Helpers ───────────────────────────────────────────────────────
function fmt(n)    { return Number(n).toLocaleString("en-IN"); }
function fmtNum(n) { return Number(n).toLocaleString("en-IN"); }
function capitalize(s) { return s ? s[0].toUpperCase() + s.slice(1) : ""; }
function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
