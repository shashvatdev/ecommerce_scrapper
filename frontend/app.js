const API_BASE = "http://localhost:8000";

// --- GSAP Setup ---
gsap.registerPlugin(ScrollTrigger, ScrollToPlugin);

// Initial Page Load Animation
function initPageAnimations() {
    const tl = gsap.timeline();
    
    tl.fromTo(".nav", 
        { y: -50, opacity: 0 }, 
        { y: 0, opacity: 1, duration: 1, ease: "power3.out" }
    )
    .fromTo(".hero-line", 
        { y: 50, opacity: 0 }, 
        { y: 0, opacity: 1, duration: 1, stagger: 0.2, ease: "power4.out" }, 
        "-=0.5"
    )
    .fromTo(".hero-subtitle", 
        { y: 20, opacity: 0 }, 
        { y: 0, opacity: 1, duration: 1, ease: "power3.out" }, 
        "-=0.5"
    )
    .fromTo(".search-box", 
        { scale: 0.95, opacity: 0 }, 
        { scale: 1, opacity: 1, duration: 1, ease: "elastic.out(1, 0.5)" }, 
        "-=0.5"
    )
    .fromTo(".platform-badge", 
        { y: 10, opacity: 0 }, 
        { y: 0, opacity: 0.6, duration: 0.5, stagger: 0.1, ease: "power2.out" }, 
        "-=0.5"
    );

    // Navbar blur on scroll
    window.addEventListener('scroll', () => {
        const nav = document.querySelector('.nav');
        if (window.scrollY > 50) {
            nav.classList.add('scrolled');
        } else {
            nav.classList.remove('scrolled');
        }
    });

    // Magnetic Button Effect
    const magneticBtns = document.querySelectorAll('.magnetic-btn');
    magneticBtns.forEach(btn => {
        btn.addEventListener('mousemove', (e) => {
            const rect = btn.getBoundingClientRect();
            const x = e.clientX - rect.left - rect.width / 2;
            const y = e.clientY - rect.top - rect.height / 2;
            gsap.to(btn, { x: x * 0.3, y: y * 0.3, duration: 0.3, ease: "power2.out" });
        });
        btn.addEventListener('mouseleave', () => {
            gsap.to(btn, { x: 0, y: 0, duration: 0.5, ease: "elastic.out(1, 0.3)" });
        });
    });

    // Trust Metrics ScrollTrigger
    gsap.fromTo(".trust-metric", 
        { y: 50, opacity: 0 },
        { 
            y: 0, opacity: 1, duration: 1, stagger: 0.2, ease: "power3.out",
            scrollTrigger: {
                trigger: ".trust-section",
                start: "top 80%"
            }
        }
    );
}

document.addEventListener("DOMContentLoaded", () => {
    initPageAnimations();

    const form = document.getElementById("search-form");
    const urlInput = document.getElementById("url-input");
    const compareBtn = document.getElementById("compare-btn");
    const refreshBtn = document.getElementById("force-refresh-btn");
    const resultsSection = document.getElementById("results-section");
    const loadingState = document.getElementById("loading-state");

    const doSearch = async (url, forceRefresh = false) => {
        // Reset UI states
        hideError();
        
        // Collapse results if showing
        if (!resultsSection.hidden) {
            gsap.to(resultsSection, { opacity: 0, y: 20, duration: 0.5, onComplete: () => {
                resultsSection.hidden = true;
                showLoading();
            }});
        } else {
            showLoading();
        }

        compareBtn.disabled = true;
        refreshBtn.disabled = true;

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
            
            // Hide loading and show results with cinematic animation
            hideLoading(() => {
                renderComparison(data);
                revealResults(data.cached);
            });

        } catch (err) {
            hideLoading();
            showError(err.message);
        } finally {
            compareBtn.disabled = false;
            refreshBtn.disabled = false;
        }
    };

    form.addEventListener("submit", (e) => {
        e.preventDefault();
        const url = urlInput.value.trim();
        if (url) doSearch(url, false);
    });

    refreshBtn.addEventListener("click", () => {
        const url = urlInput.value.trim();
        if (url) doSearch(url, true);
    });
});

// --- UI Helpers ---

function showLoading() {
    const loadingState = document.getElementById("loading-state");
    loadingState.hidden = false;
    gsap.fromTo(loadingState, { opacity: 0, scale: 0.95 }, { opacity: 1, scale: 1, duration: 0.5 });
}

function hideLoading(onComplete = null) {
    const loadingState = document.getElementById("loading-state");
    gsap.to(loadingState, { opacity: 0, scale: 0.95, duration: 0.3, onComplete: () => {
        loadingState.hidden = true;
        if (onComplete) onComplete();
    }});
}

function showError(msg) {
    const toast = document.getElementById("error-toast");
    toast.textContent = msg;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 5000);
}

function hideError() {
    document.getElementById("error-toast").classList.remove("show");
}

function renderComparison(data) {
    const productHeader = document.getElementById("product-header");
    const cachedIndicator = document.getElementById("cached-indicator");
    
    // Title
    const title = data.amazon.title || data.flipkart.title || "Compared Product";
    productHeader.textContent = title;

    // Cache Indicator
    cachedIndicator.hidden = !data.cached;

    // Amazon
    document.getElementById("img-amazon").src = data.amazon.image_url || "";
    document.getElementById("price-amazon").textContent = data.amazon.price || "0";
    document.getElementById("price-amazon").dataset.val = data.amazon.price || 0;
    
    const amzMrp = data.amazon.mrp ? `₹${data.amazon.mrp}` : "";
    document.getElementById("mrp-amazon").textContent = amzMrp;
    
    document.getElementById("seller-amazon").textContent = data.amazon.seller || "Unknown";
    document.getElementById("rating-amazon").textContent = data.amazon.rating ? `${data.amazon.rating} ★` : "N/A";
    
    const amzStock = document.getElementById("stock-amazon");
    if (data.amazon.availability === "In Stock") {
        amzStock.textContent = "In Stock";
        amzStock.className = "stock-badge stock-in";
    } else {
        amzStock.textContent = data.amazon.availability || "Unknown";
        amzStock.className = "stock-badge stock-out";
    }
    document.getElementById("link-amazon").href = data.amazon.url;

    // Flipkart
    document.getElementById("img-flipkart").src = data.flipkart.image_url || "";
    document.getElementById("price-flipkart").textContent = data.flipkart.price || "0";
    document.getElementById("price-flipkart").dataset.val = data.flipkart.price || 0;
    
    const fkMrp = data.flipkart.mrp ? `₹${data.flipkart.mrp}` : "";
    document.getElementById("mrp-flipkart").textContent = fkMrp;
    
    document.getElementById("seller-flipkart").textContent = data.flipkart.seller || "Unknown";
    document.getElementById("rating-flipkart").textContent = data.flipkart.rating ? `${data.flipkart.rating} ★` : "N/A";
    
    const fkStock = document.getElementById("stock-flipkart");
    if (data.flipkart.availability === "In Stock") {
        fkStock.textContent = "In Stock";
        fkStock.className = "stock-badge stock-in";
    } else {
        fkStock.textContent = data.flipkart.availability || "Unknown";
        fkStock.className = "stock-badge stock-out";
    }
    document.getElementById("link-flipkart").href = data.flipkart.url;

    // Winner & Savings Logic
    const cardAmz = document.getElementById("card-amazon");
    const cardFk = document.getElementById("card-flipkart");
    cardAmz.classList.remove("winner");
    cardFk.classList.remove("winner");

    const savingsBanner = document.getElementById("savings-banner");
    const savingsVal = document.getElementById("savings-value");

    if (data.cheaper_store) {
        savingsBanner.style.display = "block";
        savingsVal.dataset.val = data.price_difference || 0;
        savingsVal.textContent = data.price_difference || 0;
        
        if (data.cheaper_store === "amazon") {
            cardAmz.classList.add("winner");
        } else {
            cardFk.classList.add("winner");
        }
    } else {
        savingsBanner.style.display = "none";
    }

    // AI Insights
    document.getElementById("ai-reasoning").textContent = data.match_info?.llm_reasoning || "Products matched based on attribute parity.";
    const conf = data.match_info?.confidence || 0;
    const fill = document.getElementById("ai-confidence-fill");
    fill.dataset.w = `${conf}%`; // Store for animation
}

function revealResults(isCached) {
    const resultsSection = document.getElementById("results-section");
    resultsSection.hidden = false;

    // Ensure we scroll down slightly to view results
    gsap.to(window, { duration: 1, scrollTo: { y: resultsSection, offsetY: 100 }, ease: "power3.inOut" });

    const tl = gsap.timeline();

    tl.fromTo(resultsSection, 
        { opacity: 0 }, 
        { opacity: 1, duration: 0.1 }
    )
    .fromTo("#product-header", 
        { y: 30, opacity: 0 }, 
        { y: 0, opacity: 1, duration: 0.8, ease: "power3.out" }
    );

    if (isCached) {
        tl.fromTo("#cached-indicator", 
            { scale: 0.8, opacity: 0 }, 
            { scale: 1, opacity: 1, duration: 0.5, ease: "back.out(1.7)" }, 
            "-=0.6"
        );
    }

    if (document.getElementById("savings-banner").style.display !== "none") {
        tl.fromTo("#savings-banner", 
            { y: 40, opacity: 0, scale: 0.95 }, 
            { y: 0, opacity: 1, scale: 1, duration: 0.8, ease: "elastic.out(1, 0.7)" }, 
            "-=0.4"
        );
    }

    tl.fromTo(".store-card", 
        { y: 50, opacity: 0 }, 
        { y: 0, opacity: 1, duration: 0.8, stagger: 0.15, ease: "power4.out" }, 
        "-=0.6"
    )
    .fromTo(".ai-insights", 
        { y: 40, opacity: 0 }, 
        { y: 0, opacity: 1, duration: 0.8, ease: "power3.out" }, 
        "-=0.4"
    )
    .fromTo(".history-section", 
        { y: 40, opacity: 0 }, 
        { y: 0, opacity: 1, duration: 0.8, ease: "power3.out" }, 
        "-=0.6"
    );

    // Number Counter Animations
    document.querySelectorAll('.counter').forEach(el => {
        const target = parseInt(el.dataset.val, 10);
        if (target) {
            gsap.fromTo(el, 
                { innerHTML: 0 }, 
                { innerHTML: target, duration: 2, ease: "power2.out", snap: { innerHTML: 1 }, 
                  onUpdate: function() {
                      el.innerHTML = parseInt(el.innerHTML).toLocaleString('en-IN');
                  }
                }
            );
        }
    });

    const savingsEl = document.getElementById("savings-value");
    if (savingsEl.dataset.val) {
        const target = parseInt(savingsEl.dataset.val, 10);
        gsap.fromTo(savingsEl, 
            { innerHTML: 0 }, 
            { innerHTML: target, duration: 2.5, ease: "power2.out", snap: { innerHTML: 1 },
              onUpdate: function() {
                  savingsEl.innerHTML = parseInt(savingsEl.innerHTML).toLocaleString('en-IN');
              }
            }
        );
    }

    // AI Confidence Bar Fill
    const fill = document.getElementById("ai-confidence-fill");
    gsap.fromTo(fill, 
        { width: "0%" }, 
        { width: fill.dataset.w, duration: 2, ease: "power4.out", delay: 0.5 }
    );
}
