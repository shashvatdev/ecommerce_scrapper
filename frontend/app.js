const API_BASE = "http://localhost:8000";

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("search-form");
  const urlInput = document.getElementById("url-input");
  const compareBtn = document.getElementById("compare-btn");
  const errorDiv = document.getElementById("search-error");
  
  const loadingState = document.getElementById("loading-state");
  const compareSection = document.getElementById("compare-section");

  const forceRefreshBtn = document.getElementById("force-refresh-btn");

  const doSearch = async (url, forceRefresh = false) => {
    // Reset UI states
    errorDiv.hidden = true;
    compareSection.hidden = true;
    loadingState.hidden = false;
    compareBtn.disabled = true;
    forceRefreshBtn.disabled = true;

    try {
      const response = await fetch(`${API_BASE}/compare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, force_refresh: forceRefresh })
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || "Failed to compare product");
      }

      const data = await response.json();
      renderComparison(data);
    } catch (err) {
      errorDiv.textContent = err.message;
      errorDiv.hidden = false;
      loadingState.hidden = true;
    } finally {
      compareBtn.disabled = false;
      forceRefreshBtn.disabled = false;
    }
  };

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const url = urlInput.value.trim();
    if (url) doSearch(url, false);
  });

  forceRefreshBtn.addEventListener("click", () => {
    const url = urlInput.value.trim();
    if (url) doSearch(url, true);
  });
});

function renderComparison(data) {
  const loadingState = document.getElementById("loading-state");
  const compareSection = document.getElementById("compare-section");
  const productHeader = document.getElementById("product-header");
  const savingsBanner = document.getElementById("savings-banner");

  const amazonCol = document.getElementById("amazon-body");
  const flipkartCol = document.getElementById("flipkart-body");

  const cachedIndicator = document.getElementById("cached-indicator");

  // Cached indicator
  if (data.cached) {
    cachedIndicator.hidden = false;
  } else {
    cachedIndicator.hidden = true;
  }

  // Title rendering
  const title = data.amazon.title || data.flipkart.title || "Compared Product";
  
  let matchHtml = '';
  if (data.matched) {
    const conf = data.confidence || 0;
    const confColor = conf >= 90 ? '#10b981' : conf >= 70 ? '#f59e0b' : '#ef4444';
    matchHtml = `<div class="match-confidence" style="color: ${confColor}; font-size: 14px; font-weight: 500; margin-top: 8px;">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align: text-bottom; margin-right: 4px;">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline>
      </svg>
      Match Confidence: ${conf}%
    </div>`;
  } else if (data.comparison && data.comparison.rejection_reason) {
    matchHtml = `<div class="match-confidence" style="color: #ef4444; font-size: 14px; font-weight: 500; margin-top: 8px;">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align: text-bottom; margin-right: 4px;">
        <circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line>
      </svg>
      No Match Found (${data.comparison.rejection_reason})
    </div>`;
  }
  
  productHeader.innerHTML = `<h2 class="product-title">${title}</h2>${matchHtml}`;

  // Savings rendering
  if (data.cheaper_store && data.price_difference > 0) {
    savingsBanner.innerHTML = `
      <div class="savings-text">
        <span class="savings-amount">Save ₹${data.price_difference.toLocaleString()}</span> on ${data.cheaper_store === 'amazon' ? 'Amazon' : 'Flipkart'}
      </div>
    `;
    savingsBanner.hidden = false;
  } else {
    savingsBanner.hidden = true;
  }

  // Render columns
  amazonCol.innerHTML = renderColumnBody(data.amazon, "amazon");
  flipkartCol.innerHTML = renderColumnBody(data.flipkart, "flipkart");

  // Specifications
  renderSpecs(data.amazon.specs, data.flipkart.specs);

  // Reviews
  renderReviews(data.amazon.reviews_snippet, data.flipkart.reviews_snippet);

  // Show result
  loadingState.hidden = true;
  compareSection.hidden = false;
}

function renderColumnBody(prod, platform) {
  if (!prod || !prod.found) {
    return `
      <div class="pd-notfound">
        <p class="pd-notfound-text">Product not found on this platform</p>
      </div>
    `;
  }

  const isOOS = prod.availability === "Out of Stock" || !prod.price;
  const priceDisplay = prod.price ? `₹${prod.price.toLocaleString()}` : "—";
  const mrpDisplay = prod.mrp ? `₹${prod.mrp.toLocaleString()}` : "";
  const discountDisplay = prod.discount ? `${prod.discount}% OFF` : "";

  return `
    <div class="pd-img-wrap">
      <img class="pd-img" src="${prod.image_url || 'https://via.placeholder.com/200'}" alt="${prod.title}"/>
    </div>
    
    <div class="pd-price-row">
      <div class="pd-price-wrap">
        <span class="pd-price">${priceDisplay}</span>
        ${mrpDisplay ? `<span class="pd-mrp">${mrpDisplay}</span>` : ""}
        ${discountDisplay ? `<span class="pd-discount">${discountDisplay}</span>` : ""}
      </div>
    </div>

    <div class="pd-badge-row">
      <span class="badge ${isOOS ? 'badge-oos' : 'badge-instock'}">
        ${isOOS ? 'Out of Stock' : 'In Stock'}
      </span>
      ${prod.rating ? `
        <span class="badge badge-rating">
          ★ ${prod.rating} (${prod.review_count?.toLocaleString() || 0} reviews)
        </span>
      ` : ''}
    </div>

    <div class="pd-meta">
      <div class="pd-meta-item">
        <span class="pd-meta-lbl">Seller</span>
        <span class="pd-meta-val">${prod.seller || "Unknown"}</span>
      </div>
      <div class="pd-meta-item">
        <span class="pd-meta-lbl">Delivery</span>
        <span class="pd-meta-val">${prod.availability}</span>
      </div>
    </div>

    <a href="${prod.product_url}" target="_blank" rel="noopener" class="pd-action">
      Go to Store
    </a>
  `;
}

function renderSpecs(amzSpecs = {}, fkSpecs = {}) {
  const table = document.getElementById("specs-table");
  const section = document.getElementById("specs-section");

  // Merge keys
  const keys = Array.from(new Set([...Object.keys(amzSpecs), ...Object.keys(fkSpecs)]));

  if (keys.length === 0) {
    section.hidden = true;
    return;
  }

  let html = `
    <thead>
      <tr>
        <th class="specs-key">Feature</th>
        <th class="specs-val">Amazon</th>
        <th class="specs-val">Flipkart</th>
      </tr>
    </thead>
    <tbody>
  `;

  keys.forEach(key => {
    html += `
      <tr>
        <td class="specs-key">${key}</td>
        <td class="specs-val">${amzSpecs[key] || "—"}</td>
        <td class="specs-val">${fkSpecs[key] || "—"}</td>
      </tr>
    `;
  });

  html += `</tbody>`;
  table.innerHTML = html;
  section.hidden = false;
}

function renderReviews(amzReviews = [], fkReviews = []) {
  const grid = document.getElementById("reviews-grid");
  const section = document.getElementById("reviews-section");

  if (amzReviews.length === 0 && fkReviews.length === 0) {
    section.hidden = true;
    return;
  }

  let html = "";

  // Amazon Reviews Col
  html += `
    <div>
      <h4 class="reviews-col-title">Amazon Reviews</h4>
      ${amzReviews.length > 0 ? amzReviews.map(r => `
        <div class="review-card">${r}</div>
      `).join('') : '<p style="color:var(--text-muted); font-size: 13px;">No review text captured</p>'}
    </div>
  `;

  // Flipkart Reviews Col
  html += `
    <div>
      <h4 class="reviews-col-title">Flipkart Reviews</h4>
      ${fkReviews.length > 0 ? fkReviews.map(r => `
        <div class="review-card">${r}</div>
      `).join('') : '<p style="color:var(--text-muted); font-size: 13px;">No review text captured</p>'}
    </div>
  `;

  grid.innerHTML = html;
  section.hidden = false;
}
