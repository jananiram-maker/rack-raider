/**
 * Rack Raider AI Wardrobe Assistant — Client Application Logic
 */

document.addEventListener("DOMContentLoaded", () => {
  // Global State
  const state = {
    userId: "user0001",
    activeTab: "tab-brief",
    currentWeather: null,
    closetItems: [],
    selectedCategory: "all",
    selectedFormality: "",
    selectedSeason: "",
    selectedStatus: "active",
    searchQuery: "",
    uploadedImageBase64: "",
    activeSeason: "Summer"
  };

  // Helper: Convert gs:// URIs to HTTPS URLs
  function gcsUriToHttps(uri) {
    if (!uri) return null;
    if (uri.startsWith("gs://")) {
      const parts = uri.slice(5).split("/");
      const bucket = parts[0];
      const path = parts.slice(1).join("/");
      return `https://storage.googleapis.com/${bucket}/${path}`;
    }
    return uri;
  }

  // Color Mapping for Visual Chips
  const COLOR_MAP = {
    white: "#ffffff",
    ivory: "#fffff0",
    cream: "#fffdd0",
    black: "#111111",
    charcoal: "#333333",
    "charcoal grey": "#374151",
    grey: "#6b7280",
    gray: "#6b7280",
    navy: "#1e3a8a",
    "navy blue": "#1e3a8a",
    "navy/white": "#1e3a8a",
    blue: "#3b82f6",
    "indigo blue": "#312e81",
    denim: "#2563eb",
    camel: "#c19a6b",
    tan: "#d2b48c",
    brown: "#78350f",
    emerald: "#047857",
    "emerald green": "#059669",
    green: "#10b981",
    olive: "#556b2f",
    red: "#ef4444",
    burgundy: "#881337",
    pink: "#f43f5e",
    oatmeal: "#d6c7b2"
  };

  // Preset Image URIs
  const PRESET_IMAGES = {
    dress: "gs://wardrobe_sfs/sarah/outfits/emerald_dress_night.jpg",
    casual: "gs://wardrobe_sfs/sarah/outfits/tuesday_casual_denim.jpg",
    formal: "gs://wardrobe_sfs/sarah/outfits/formal_suit_meeting.jpg"
  };

  // Elements
  const tabButtons = document.querySelectorAll(".nav-item");
  const tabPanes = document.querySelectorAll(".tab-pane");
  const userSelect = document.getElementById("user-select");
  const userAvatarInitials = document.getElementById("user-avatar-initials");
  const closetCountBadge = document.getElementById("closet-count-badge");
  const quickStatItems = document.getElementById("quick-stat-items");
  const quickStatWears = document.getElementById("quick-stat-wears");

  // Page Heading Elements
  const pageTitle = document.getElementById("current-page-title");
  const pageSubtitle = document.getElementById("current-page-subtitle");

  const TAB_META = {
    "tab-brief": {
      title: "Today's Weather & Outfit",
      subtitle: ""
    },
    "tab-closet": {
      title: "Your Closet",
      subtitle: "View and manage your garments."
    },
    "tab-ingest": {
      title: "Add Items",
      subtitle: "Upload photos or add garments manually."
    },
    "tab-insights": {
      title: "Wardrobe Insights",
      subtitle: "Explore gaps and lifecycle recommendations."
    },
    "tab-chat": {
      title: "Chat with Stylist",
      subtitle: "Get styling advice and outfit suggestions."
    }
  };

  // Firebase auth state — declared before initApp() runs, since
  // fetchLiveWeather() (called from initApp) reads firebaseAuth via
  // getAuthHeaders() immediately on load.
  let firebaseAuth = null;
  let appDataLoaded = false;

  // Initialize
  initApp();
  initFirebaseAuth();

  function initApp() {
    setupNavigation();
    setupWeatherModule();
    setupOutfitGenerator();
    setupClosetModule();
    setupIngestionModule();
    setupGapAnalysisModule();
    setupCircularModule();
    setupChatModule();
    setupModal();

    // Weather doesn't need a signed-in user — safe to fetch immediately.
    // Closet/stats need a real user_id, so those are kicked off from the
    // Firebase auth state listener once someone actually signs in.
    fetchLiveWeather();
  }

  // -------------------------------------------------------------------------
  // Firebase Authentication (Google Sign-In)
  // -------------------------------------------------------------------------
  function initFirebaseAuth() {
    if (typeof firebase === "undefined" || typeof FIREBASE_CONFIG === "undefined") {
      console.error("[Auth] Firebase SDK or firebase-config.js not loaded — sign-in unavailable.");
      const statusEl = document.getElementById("auth-gate-status");
      if (statusEl) statusEl.textContent = "Sign-in is not configured. Contact the app owner.";
      return;
    }

    firebase.initializeApp(FIREBASE_CONFIG);
    firebaseAuth = firebase.auth();

    firebaseAuth.onAuthStateChanged(user => {
      if (user) {
        showApp(user);
      } else {
        appDataLoaded = false;
        showAuthGate();
      }
    });

    const signInBtn = document.getElementById("btn-google-signin");
    if (signInBtn) {
      signInBtn.addEventListener("click", async () => {
        const statusEl = document.getElementById("auth-gate-status");
        if (statusEl) statusEl.textContent = "";
        try {
          await firebaseAuth.signInWithPopup(new firebase.auth.GoogleAuthProvider());
        } catch (err) {
          if (statusEl) statusEl.textContent = "Sign-in failed: " + err.message;
        }
      });
    }

    const signOutBtn = document.getElementById("btn-sign-out");
    if (signOutBtn) {
      signOutBtn.addEventListener("click", () => firebaseAuth.signOut());
    }
  }

  function showApp(user) {
    state.userId = user.uid;

    document.getElementById("auth-gate")?.classList.add("hidden");
    document.getElementById("app-layout-root")?.classList.remove("hidden");

    const emailEl = document.getElementById("user-email-text");
    const initialsEl = document.getElementById("user-avatar-initials");
    const photoEl = document.getElementById("user-avatar-photo");
    if (emailEl) emailEl.textContent = user.email || user.displayName || "Signed in";
    if (user.photoURL && photoEl) {
      photoEl.src = user.photoURL;
      photoEl.classList.remove("hidden");
      initialsEl?.classList.add("hidden");
    } else if (initialsEl) {
      initialsEl.textContent = (user.displayName || user.email || "U").trim()[0].toUpperCase();
      initialsEl.classList.remove("hidden");
      photoEl?.classList.add("hidden");
    }

    // Only kick off the user-scoped data fetch once per sign-in, not on
    // every token refresh (onAuthStateChanged can fire more than once).
    if (!appDataLoaded) {
      appDataLoaded = true;
      fetchClosetAndStats();
    }
  }

  function showAuthGate() {
    document.getElementById("auth-gate")?.classList.remove("hidden");
    document.getElementById("app-layout-root")?.classList.add("hidden");
  }

  // -------------------------------------------------------------------------
  // API Helpers
  // -------------------------------------------------------------------------
  async function getAuthHeaders() {
    const headers = { "Content-Type": "application/json" };
    if (firebaseAuth && firebaseAuth.currentUser) {
      headers["Authorization"] = `Bearer ${await firebaseAuth.currentUser.getIdToken()}`;
    }
    return headers;
  }

  // -------------------------------------------------------------------------
  // 1. Navigation & Tab Switching
  // -------------------------------------------------------------------------
  function setupNavigation() {
    tabButtons.forEach(btn => {
      btn.addEventListener("click", () => {
        const targetTab = btn.getAttribute("data-tab");
        switchTab(targetTab);
      });
    });
  }

  function switchTab(tabId) {
    state.activeTab = tabId;
    tabButtons.forEach(b => {
      if (b.getAttribute("data-tab") === tabId) {
        b.classList.add("active");
      } else {
        b.classList.remove("active");
      }
    });

    tabPanes.forEach(pane => {
      if (pane.id === tabId) {
        pane.classList.add("active");
      } else {
        pane.classList.remove("active");
      }
    });

    if (TAB_META[tabId]) {
      pageTitle.textContent = TAB_META[tabId].title;
      pageSubtitle.textContent = TAB_META[tabId].subtitle;
    }

    // Auto-refresh data on tab change if appropriate
    if (tabId === "tab-closet") {
      fetchClosetAndStats();
    } else if (tabId === "tab-insights") {
      runGapAnalysis();
    }
  }

  // -------------------------------------------------------------------------
  // 2. User Switcher & Seeding
  // -------------------------------------------------------------------------
  function setupUserSwitcher() {
    // Set initial state from the default selected option
    updateUserContext();

    userSelect.addEventListener("change", (e) => {
      state.userId = e.target.value;
      updateUserContext();
      showToast(`Switched active wardrobe to ${e.target.options[e.target.selectedIndex].text}`, "info");
      fetchClosetAndStats();
    });
  }

  function updateUserContext() {
    const selectedOption = userSelect.options[userSelect.selectedIndex];
    const displayName = selectedOption ? selectedOption.textContent.trim() : "You";
    const firstName = displayName.split(" ")[0];

    let initials = "U0";
    if (state.userId.includes("user0001")) initials = "U0";
    else if (state.userId.includes("sarah")) initials = "SJ";
    else if (state.userId.includes("alex")) initials = "AR";
    else initials = "DG";
    userAvatarInitials.textContent = initials;

    // Update chat greeting and wardrobe badge with active user's name
    const greetingEl = document.getElementById("chat-greeting-text");
    if (greetingEl) {
      greetingEl.innerHTML = `Hello, <strong>${firstName}</strong>! I'm your <strong>Rack Raider AI Wardrobe Assistant</strong>. I have full context on your digital closet, wear frequency history, and current weather.`;
    }
    const wardrobeBadgeEl = document.getElementById("chat-wardrobe-name");
    if (wardrobeBadgeEl) {
      wardrobeBadgeEl.textContent = `${firstName}'s Wardrobe`;
    }
  }

  // -------------------------------------------------------------------------
  // 3. Live Weather Module
  // -------------------------------------------------------------------------
  function setupWeatherModule() {
    const cityInput = document.getElementById("weather-city-input");
    const refreshBtn = document.getElementById("btn-refresh-weather");

    refreshBtn.addEventListener("click", () => {
      const city = cityInput.value.trim() || "San Francisco";
      fetchLiveWeather(city);
    });

    cityInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        fetchLiveWeather(cityInput.value.trim() || "San Francisco");
      }
    });
  }

  async function fetchLiveWeather(city = "San Francisco") {
    try {
      const res = await fetch("/api/weather", {
        method: "POST",
        headers: await getAuthHeaders(),
        body: JSON.stringify({ city })
      });
      const data = await res.json();
      state.currentWeather = data;

      document.getElementById("weather-temp-val").textContent = `${data.temp_range[0]}°C`;
      document.getElementById("weather-temp-range").textContent = `${data.temp_range[0]}°C – ${data.temp_range[1]}°C`;
      document.getElementById("weather-condition-text").textContent = data.weather_condition;
      document.getElementById("weather-precip-val").textContent = `${Math.round(data.precipitation_risk * 100)}%`;
      document.getElementById("weather-layering-val").textContent = data.layering_recommended ? "Recommended" : "Optional";
      document.getElementById("weather-prompt-text").textContent = data.summary_prompt;

      // Update chat context badge
      const chatWeatherBadge = document.getElementById("chat-weather-badge");
      if (chatWeatherBadge) {
        chatWeatherBadge.innerHTML = `<i class="fa-solid fa-cloud-sun"></i> ${city} ${data.temp_range[0]}°C`;
      }
    } catch (err) {
      console.error("Weather fetch failed:", err);
      document.getElementById("weather-prompt-text").textContent = "Unable to reach weather API. Using default styling parameters.";
    }
  }

  // -------------------------------------------------------------------------
  // 4. Outfit Generator & Synthesis
  // -------------------------------------------------------------------------
  function setupOutfitGenerator() {
    const btnGen = document.getElementById("btn-generate-outfit");
    const occasionSelect = document.getElementById("outfit-occasion-select");
    const resultsArea = document.getElementById("outfit-results-area");

    btnGen.addEventListener("click", async () => {
      btnGen.disabled = true;
      btnGen.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> Synthesizing Combinations...`;
      resultsArea.innerHTML = `
        <div class="loading-spinner-box">
          <i class="fa-solid fa-wand-sparkles fa-spin"></i>
          <p>Analyzing color harmonies, weather layering, and formality rules...</p>
        </div>
      `;

      try {
        const city = document.getElementById("weather-city-input").value.trim() || "San Francisco";
        const occasion = occasionSelect.value;
        const userPrompt = document.getElementById("outfit-context-input").value.trim();
        const res = await fetch("/api/synthesize-outfits", {
          method: "POST",
          headers: await getAuthHeaders(),
          body: JSON.stringify({
            user_id: state.userId,
            city: city,
            occasion: occasion,
            user_prompt: userPrompt
          })
        });
        const data = await res.json();
        renderOutfitOptions(data);
      } catch (err) {
        resultsArea.innerHTML = `<div class="empty-state"><p class="error-msg">Failed to synthesize outfits: ${err.message}</p></div>`;
      } finally {
        btnGen.disabled = false;
        btnGen.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Synthesize Today's Outfits`;
      }
    });
  }

  function renderOutfitOptions(data) {
    const resultsArea = document.getElementById("outfit-results-area");
    const rawOptions = data.outfit_result?.outfit_options || [];

    if (!rawOptions.length) {
      resultsArea.innerHTML = `
        <div class="empty-state">
          <i class="fa-solid fa-shirt empty-icon"></i>
          <p>No suitable outfits found for this occasion. Seed or add garments to your closet first!</p>
        </div>
      `;
      return;
    }

    // Normalise field names: API may return selected_items or items
    const options = rawOptions.map(opt => ({
      ...opt,
      items: opt.selected_items || opt.items || []
    }));

    resultsArea.innerHTML = options.map((opt, idx) => {
      // Per-item thumbnail strip — show image if available, fallback to swatch
      const itemImagesHtml = opt.items.map(item => {
        const colorHex = COLOR_MAP[item.primary_color?.toLowerCase()] || "#64748b";
        const imageUrl = gcsUriToHttps(item.gcs_uri);
        let html = `<div class="outfit-item-img-wrap" title="${item.item_name}">`;
        if (imageUrl) {
          html += `<img src="${imageUrl}" alt="${item.item_name}" class="outfit-item-thumb" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">`;
        }
        const displayStyle = imageUrl ? 'display:none;' : 'display:flex;';
        html += `<div class="outfit-item-swatch" style="background:${colorHex}; ${displayStyle}"><i class="fa-solid fa-shirt"></i></div>`;
        html += `<span class="outfit-item-label">${item.category || ''}</span></div>`;
        return html;
      }).join("");

      // Text piece list (compact)
      const piecesHtml = opt.items.map(item => `
        <div class="outfit-piece-row">
          <span class="piece-cat-badge">${item.category || 'Piece'}</span>
          <span class="piece-name">${item.item_name}</span>
          ${item.primary_color ? `<span class="meta-tag" style="margin-left:auto">${item.primary_color}</span>` : ''}
        </div>
      `).join("");

      // Collect item IDs for wear logging
      const itemIds = opt.items
        .filter(i => i.item_id)
        .map(i => i.item_id)
        .join(",");

      // Short styling note — first sentence only to keep it concise
      const shortExplanation = (() => {
        const text = opt.styling_explanation || "";
        const firstSentence = text.split(/(?<=[.!?])\s/)[0] || text;
        return firstSentence.length > 120 ? firstSentence.slice(0, 117) + "..." : firstSentence;
      })();

      return `
        <div class="outfit-card">
          <!-- Per-item image thumbnails -->
          <div class="outfit-item-images-row">
            ${itemImagesHtml}
          </div>

          <div class="outfit-header" style="margin-top: 14px;">
            <div>
              <span class="outfit-structure-tag">${opt.base_structure || 'Option ' + (idx + 1)}</span>
              <h4 class="outfit-title">${opt.title || 'Curated Ensemble'}</h4>
            </div>
          </div>

          ${shortExplanation ? `<p class="outfit-styling-note">${shortExplanation}</p>` : ''}

          <div class="outfit-items-list" style="margin-top: 10px;">
            ${piecesHtml}
          </div>

          <button class="btn-log-outfit" onclick="window.logOutfitAsWorn('${opt.title.replace(/'/g, "\\'").replace(/"/g, '&quot;')}', '${itemIds}')">
            <i class="fa-solid fa-check"></i> Wear This Outfit Today
          </button>
        </div>
      `;
    }).join("");
  }

  window.logOutfitAsWorn = async (outfitTitle, itemIdsStr) => {
    const today = new Date().toISOString().split("T")[0];
    const itemIds = itemIdsStr ? itemIdsStr.split(",").filter(Boolean) : [];

    // Increment wear count for every item in the outfit
    if (itemIds.length) {
      try {
        const headers = await getAuthHeaders();
        await Promise.all(itemIds.map(id =>
          fetch(`/api/items/${id}?user_id=${state.userId}`, {
            method: "PATCH",
            headers,
            body: JSON.stringify({ increment_wear: true, worn_date: today })
          })
        ));
        showToast(`✓ Outfit "${outfitTitle}" saved! Wear counts updated for ${itemIds.length} piece${itemIds.length !== 1 ? 's' : ''}.`, "success");
      } catch (err) {
        showToast(`Outfit logged but wear count update failed: ${err.message}`, "error");
      }
    } else {
      // No item IDs available — just show confirmation
      showToast(`✓ Outfit "${outfitTitle}" marked as worn today!`, "success");
    }
    fetchClosetAndStats();
  };

  // -------------------------------------------------------------------------
  // 5. Digital Closet Module
  // -------------------------------------------------------------------------
  function setupClosetModule() {
    console.log("[Setup] setupClosetModule called");
    const btnAddGarment = document.getElementById("btn-open-add-modal");

    // Wires up one pill-row group (category, formality, season, status) so clicking
    // a pill toggles "active" within that row only and updates the matching state key.
    // refetch: the status row changes which items are even fetched from the server
    // (only the selected status is pulled down, to keep the common case fast), so it
    // needs a full re-fetch rather than just a client-side re-render.
    function setupPillRow(containerId, dataAttr, stateKey, refetch) {
      const container = document.getElementById(containerId);
      if (!container) return;
      const pills = container.querySelectorAll(".filter-pill");
      pills.forEach(pill => {
        pill.addEventListener("click", () => {
          pills.forEach(p => p.classList.remove("active"));
          pill.classList.add("active");
          state[stateKey] = pill.getAttribute(dataAttr);
          refetch ? fetchClosetAndStats() : renderClosetGrid();
        });
      });
    }

    setupPillRow("category-filter-pills", "data-cat", "selectedCategory", false);
    setupPillRow("formality-filter-pills", "data-formality", "selectedFormality", false);
    setupPillRow("season-filter-pills", "data-season", "selectedSeason", false);
    setupPillRow("status-filter-pills", "data-status", "selectedStatus", true);

    // Add Garment button - navigate to Add Items tab
    if (btnAddGarment) {
      btnAddGarment.addEventListener("click", () => switchTab("tab-ingest"));
    }

    // Delete item buttons with event delegation
    const grid = document.getElementById("closet-garment-grid");
    if (grid) {
      grid.addEventListener("click", (e) => {
        const btn = e.target.closest(".btn-delete-item");
        if (btn) {
          console.log("[Setup] Delete button clicked via delegation");
          const itemId = btn.getAttribute("data-item-id");
          const itemName = btn.getAttribute("data-item-name");
          window.deleteItem(itemId, itemName);
        }
      });
      console.log("[Setup] Delete event delegation registered on closet-garment-grid");
    } else {
      console.log("[Setup] WARNING: closet-garment-grid not found");
    }
  }

  async function fetchClosetAndStats() {
    try {
      // Only fetch the status subset currently selected (fast common case: just "active"),
      // rather than the whole collection every time — /api/stats gives us the header
      // counts across all statuses far more cheaply than pulling every item's full record.
      const headers = await getAuthHeaders();
      const res = await fetch(`/api/inventory?status=${encodeURIComponent(state.selectedStatus)}`, {
        headers
      });
      const data = await res.json();
      state.closetItems = data.items || [];

      const statsRes = await fetch(`/api/stats`, {
        headers
      });
      const statsData = await statsRes.json();
      closetCountBadge.textContent = statsData.active_count ?? 0;
      quickStatItems.textContent = `${statsData.active_count ?? 0} Items`;
      quickStatWears.textContent = `${statsData.total_wears || 0} Wears`;

      renderClosetGrid();
    } catch (err) {
      console.error("Closet fetch error:", err);
    }
  }

  function renderClosetGrid() {
    const grid = document.getElementById("closet-garment-grid");
    const seasonFilter = state.selectedSeason;
    const statusFilter = state.selectedStatus;
    const formalityFilter = state.selectedFormality;

    let filtered = state.closetItems.filter(item => {
      // Category filter
      if (state.selectedCategory !== "all" && item.category !== state.selectedCategory) {
        return false;
      }
      // Season filter
      if (seasonFilter && item.season_tag !== seasonFilter && item.season_tag !== "All-Season") {
        return false;
      }
      // Status filter
      if (statusFilter && item.status !== statusFilter) {
        return false;
      }
      // Formality filter
      if (formalityFilter && item.formality !== formalityFilter) {
        return false;
      }
      return true;
    });

    if (!filtered.length) {
      grid.innerHTML = `
        <div class="empty-state" style="grid-column: 1 / -1;">
          <i class="fa-solid fa-shirt empty-icon"></i>
          <p>No garments match the current filters.</p>
          <button class="btn-action-mini" style="margin-top: 10px;" onclick="switchTab('tab-ingest')">+ Add Items</button>
        </div>
      `;
      return;
    }

    grid.innerHTML = filtered.map(item => {
      const colorHex = COLOR_MAP[item.primary_color?.toLowerCase()] || "#64748b";
      const statusClass = item.status || "active";
      const lastWorn = item.last_worn_date ? `Worn: ${item.last_worn_date}` : "Unworn";
      const imageUrl = gcsUriToHttps(item.gcs_uri);
      const thumbnailHtml = imageUrl
        ? `<img src="${imageUrl}" alt="${item.item_name}" style="width: 100%; height: auto; border-radius: var(--radius-sm); display: block;" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
           <div style="width: 100%; aspect-ratio: 3 / 4; background: linear-gradient(135deg, ${colorHex}66 0%, ${colorHex}33 100%); border-radius: var(--radius-sm); display: none; align-items: center; justify-content: center;"><i class="fa-solid fa-shirt" style="font-size: 48px; color: ${colorHex}; opacity: 0.5;"></i></div>`
        : `<div style="width: 100%; aspect-ratio: 3 / 4; background: linear-gradient(135deg, ${colorHex}66 0%, ${colorHex}33 100%); border-radius: var(--radius-sm); display: flex; align-items: center; justify-content: center;"><i class="fa-solid fa-shirt" style="font-size: 48px; color: ${colorHex}; opacity: 0.5;"></i></div>`;

      return `
        <div class="garment-card">
          <div>
            ${thumbnailHtml}

            <div class="garment-card-top" style="margin-top: 10px;">
              <span class="garment-color-chip" style="background-color: ${colorHex};" title="${item.primary_color}"></span>
              <span class="garment-status-badge ${statusClass}">${statusClass}</span>
            </div>

            <h4 class="garment-title">${item.item_name}</h4>

            <div class="garment-meta-tags" style="margin-top: 10px;">
              <span class="meta-tag"><i class="fa-solid fa-tag"></i> ${item.category}</span>
              <span class="meta-tag">${item.material || 'Fabric'}</span>
              <span class="meta-tag">${item.formality || 'Casual'}</span>
              <span class="meta-tag">${item.season_tag || 'All-Season'}</span>
              <span class="meta-tag"><i class="fa-solid fa-temperature-half"></i> ${["Hot day", "Warm day", "Mild day", "Cool day", "Cold day"][item.warmth_rating - 1] || "Mild day"}</span>
            </div>

            <button class="btn-delete-item" data-item-id="${item.item_id}" data-item-name="${item.item_name}" title="Delete item" style="position: absolute; top: 8px; right: 8px; width: 28px; height: 28px; padding: 0; background: rgba(239, 68, 68, 0.2); border: none; color: #ef4444; border-radius: 4px; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 14px; transition: all 0.2s; opacity: 0.6;" onmouseover="this.style.opacity='1'; this.style.background='rgba(239, 68, 68, 0.4)';" onmouseout="this.style.opacity='0.6'; this.style.background='rgba(239, 68, 68, 0.2)';">
              <i class="fa-solid fa-trash"></i>
            </button>
          </div>
        </div>
      `;
    }).join("");
  }

  window.incrementItemWear = async (itemId) => {
    try {
      const today = new Date().toISOString().split("T")[0];
      await fetch(`/api/items/${itemId}`, {
        method: "PATCH",
        headers: await getAuthHeaders(),
        body: JSON.stringify({ increment_wear: true, worn_date: today })
      });
      showToast("Logged +1 wear for garment!", "success");
      fetchClosetAndStats();
    } catch (err) {
      showToast("Error updating wear: " + err.message, "error");
    }
  };

  window.deleteItem = async (itemId, itemName) => {
    console.log(`[Delete] Attempting to delete item: ${itemId} - ${itemName}`);
    if (!confirm(`Are you sure you want to delete "${itemName}"? This cannot be undone.`)) {
      console.log("[Delete] User cancelled deletion");
      return;
    }

    try {
      console.log(`[Delete] Sending DELETE request to /api/items/${itemId}`);
      const res = await fetch(`/api/items/${itemId}`, {
        method: "DELETE",
        headers: await getAuthHeaders()
      });
      console.log(`[Delete] Response status: ${res.status}`);
      const text = await res.text();
      console.log(`[Delete] Response body: ${text}`);
      showToast(`"${itemName}" deleted from wardrobe`, "success");
      fetchClosetAndStats();
    } catch (err) {
      console.error(`[Delete] Error: ${err.message}`);
      showToast("Error deleting item: " + err.message, "error");
    }
  };

  window.setItemStatus = async (itemId, newStatus) => {
    try {
      const res = await fetch(`/api/items/${itemId}`, {
        method: "PATCH",
        headers: await getAuthHeaders(),
        body: JSON.stringify({ status: newStatus })
      });
      if (!res.ok) throw new Error(`Server responded ${res.status}`);
      showToast(`Garment marked as ${newStatus}!`, "info");
      fetchClosetAndStats();
      if (document.getElementById("circular-columns-container")) {
        runCircularEvaluation();
      }
    } catch (err) {
      showToast("Error updating status: " + err.message, "error");
    }
  };

  // -------------------------------------------------------------------------
  // 6. Visual Ingestion Studio
  // -------------------------------------------------------------------------
  function setupIngestionModule() {
    console.log("Setting up ingestion module");
    const dropzone = document.getElementById("selfie-dropzone");
    const fileInput = document.getElementById("selfie-file-input");
    const browseBtn = document.getElementById("btn-browse-file");
    const previewContainer = document.getElementById("preview-container");
    const dropzoneUi = document.getElementById("dropzone-ui");
    const previewImg = document.getElementById("image-preview");
    const removePreviewBtn = document.getElementById("btn-remove-preview");
    const presetButtons = document.querySelectorAll(".preset-btn");
    const processBtn = document.getElementById("btn-process-ingest");
    const wornDateInput = document.getElementById("ingest-worn-date");

    console.log("Ingestion elements found:", { dropzone: !!dropzone, fileInput: !!fileInput, browseBtn: !!browseBtn });

    // Check if elements exist
    if (!dropzone || !fileInput || !browseBtn) {
      console.error("❌ Ingestion module elements missing - file upload won't work");
      return;
    }
    console.log("✓ Ingestion module setup successful");

    // Set today's date
    if (wornDateInput) {
      wornDateInput.value = new Date().toISOString().split("T")[0];
    }

    browseBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      fileInput.click();
    });

    dropzone.addEventListener("click", () => {
      if (!state.uploadedImageBase64) fileInput.click();
    });

    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });

    dropzone.addEventListener("dragleave", () => {
      dropzone.classList.remove("dragover");
    });

    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      if (e.dataTransfer.files.length) {
        handleImageFile(e.dataTransfer.files[0]);
      }
    });

    fileInput.addEventListener("change", (e) => {
      if (e.target.files.length) {
        handleImageFile(e.target.files[0]);
      }
    });

    if (removePreviewBtn) {
      removePreviewBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        state.uploadedImageBase64 = "";
        if (previewContainer) previewContainer.classList.add("hidden");
        if (dropzoneUi) dropzoneUi.classList.remove("hidden");
        fileInput.value = "";
      });
    }

    presetButtons.forEach(btn => {
      btn.addEventListener("click", () => {
        const presetKey = btn.getAttribute("data-preset");
        state.uploadedImageBase64 = PRESET_IMAGES[presetKey] || PRESET_IMAGES.dress;
        if (previewImg) {
          previewImg.src = "https://images.unsplash.com/photo-1515372039744-b8f02a3ae446?w=500&auto=format&fit=crop&q=60";
        }
        if (dropzoneUi) dropzoneUi.classList.add("hidden");
        if (previewContainer) previewContainer.classList.remove("hidden");
        showToast(`Selected preset: ${btn.textContent.trim()}`, "info");
      });
    });

    if (processBtn) {
      processBtn.addEventListener("click", processIngestion);
    }
  }

  function handleImageFile(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
      state.uploadedImageBase64 = e.target.result;
      document.getElementById("image-preview").src = e.target.result;
      document.getElementById("dropzone-ui").classList.add("hidden");
      document.getElementById("preview-container").classList.remove("hidden");
      showToast("Selfie image loaded! Click Process to analyze.", "info");
    };
    reader.readAsDataURL(file);
  }

  async function processIngestion() {
    const resultsBody = document.getElementById("ingestion-results-body");
    const processBtn = document.getElementById("btn-process-ingest");
    const wornDate = document.getElementById("ingest-worn-date").value;

    if (!state.uploadedImageBase64) {
      showToast("Please upload an image or select a preset first!", "error");
      return;
    }

    processBtn.disabled = true;
    processBtn.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> Analyzing Multimodal Image...`;
    resultsBody.innerHTML = `
      <div class="loading-spinner-box">
        <i class="fa-solid fa-microchip fa-spin"></i>
        <p>Isolating garments & calculating Vertex AI visual embeddings...</p>
      </div>
    `;

    try {
      const res = await fetch("/api/upload-outfit", {
        method: "POST",
        headers: await getAuthHeaders(),
        body: JSON.stringify({
          user_id: state.userId,
          image_data: state.uploadedImageBase64,
          worn_date: wornDate
        })
      });
      const data = await res.json();
      renderIngestionResults(data);
      fetchClosetAndStats();
    } catch (err) {
      resultsBody.innerHTML = `<div class="empty-state"><p class="error-msg">Ingestion failed: ${err.message}</p></div>`;
    } finally {
      processBtn.disabled = false;
      processBtn.innerHTML = `<i class="fa-solid fa-fingerprint"></i> Process Multimodal Ingestion & De-Duplication`;
    }
  }

  function renderIngestionResults(data) {
    const resultsBody = document.getElementById("ingestion-results-body");
    const garments = data.garments || [];

    resultsBody.innerHTML = `
      <div style="margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span style="font-size: 13px; font-weight: 600; color: var(--gold-primary);">
            Outfit ID: ${data.outfit_id || 'Logged Outfit'}
          </span>
          <span class="condition-chip">${data.detected_occasion || 'Occasion Inferred'}</span>
        </div>
        <p style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">
          ${data.outfit_description || 'Multimodal garment decomposition complete.'}
        </p>
      </div>

      <div class="decomp-garments-list">
        ${garments.map(g => {
          const isReWear = g.action === "INCREMENT_WEAR";
          const badgeClass = isReWear ? "logged_wear" : "new_item";
          const badgeIcon = isReWear ? "fa-arrows-rotate" : "fa-sparkles";
          const badgeText = isReWear 
            ? `Re-Worn Staple (${(g.similarity_score * 100).toFixed(1)}% Match > 0.88)`
            : `New Wardrobe Staple (${(g.similarity_score * 100).toFixed(1)}% Sim &le; 0.88)`;

          return `
            <div class="decomp-garment-card">
              <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                  <h4 style="font-size: 15px; font-weight: 600;">${g.item_name}</h4>
                  <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">
                    ${g.category} &bull; ${g.material || 'Fabric'} &bull; ${g.formality}
                  </div>
                </div>
                <span class="decomp-action-badge ${badgeClass}">
                  <i class="fa-solid ${badgeIcon}"></i> ${badgeText}
                </span>
              </div>

              <div style="display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: var(--text-secondary); border-top: 1px solid var(--border-subtle); padding-top: 8px;">
                <span>Wear Count: <strong style="color: var(--gold-primary);">${g.wear_count}</strong></span>
                <span>Expected: ${g.wear_frequency_expectation || 'Weekly'}</span>
                <span>Season: ${g.season_tag || 'All-Season'}</span>
              </div>
            </div>
          `;
        }).join("")}
      </div>
    `;
    showToast("Outfit photo cataloged and de-duplicated successfully!", "success");
  }

  // -------------------------------------------------------------------------
  // 7. Predictive Gap Analysis
  // -------------------------------------------------------------------------
  function setupGapAnalysisModule() {
    const btnRun = document.getElementById("btn-run-gap-analysis");
    btnRun.addEventListener("click", runGapAnalysis);
  }

  async function runGapAnalysis() {
    const btnRun = document.getElementById("btn-run-gap-analysis");
    const container = document.getElementById("gap-results-container");
    const occasion = document.getElementById("gap-occasion-select").value;

    btnRun.disabled = true;
    btnRun.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> Computing Graph...`;

    try {
      const res = await fetch("/api/gap-analysis", {
        method: "POST",
        headers: await getAuthHeaders(),
        body: JSON.stringify({
          user_id: state.userId,
          target_occasion: occasion
        })
      });
      const data = await res.json();
      renderGapAnalysis(data);
    } catch (err) {
      container.innerHTML = `<div class="empty-state"><p class="error-msg">Gap analysis failed: ${err.message}</p></div>`;
    } finally {
      btnRun.disabled = false;
      btnRun.innerHTML = `<i class="fa-solid fa-network-wired"></i> Analyze Wardrobe Gaps`;
    }
  }

  function renderGapAnalysis(data) {
    const container = document.getElementById("gap-results-container");
    const versatility = data.versatility_multipliers || [];
    const occasionBridges = data.occasion_bridges || [];
    const isolated = data.isolated_garments || [];

    container.innerHTML = `
      <!-- Versatility Multipliers (Bridge Staples) -->
      <div class="glass-card" style="grid-column: span 2;">
        <div class="card-header">
          <div class="card-title-group">
            <span class="card-eyebrow">CATEGORY 1</span>
            <h3>Versatility Multipliers (Bridge Staples)</h3>
          </div>
          <span class="staple-multiplier-badge">High ROI Additions</span>
        </div>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px;">
          ${versatility.map(vm => `
            <div class="staple-card">
              <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <h4 style="font-family: var(--font-serif); font-size: 16px; font-weight: 600;">${vm.staple_name}</h4>
                <span class="staple-multiplier-badge">+${vm.new_combinations_unlocked} Outfits</span>
              </div>
              <p style="font-size: 11px; color: var(--gold-primary); margin-top: 4px;">
                ${vm.category} &bull; ${vm.primary_color} &bull; ${vm.formality}
              </p>
              <p style="font-size: 12px; color: var(--text-secondary); margin-top: 10px; line-height: 1.5;">
                ${vm.versatility_rationale}
              </p>
              <div style="margin-top: 12px; padding-top: 8px; border-top: 1px solid var(--border-subtle); font-size: 11px; color: var(--emerald-accent);">
                <i class="fa-solid fa-link"></i> Connects ${vm.connected_isolated_count} underused isolated pieces
              </div>
            </div>
          `).join("")}
        </div>
      </div>

      <!-- Isolated Items Summary -->
      <div class="glass-card">
        <div class="card-header">
          <div class="card-title-group">
            <span class="card-eyebrow">UNDERUTILIZED PIECES</span>
            <h3>Isolated Garments (&le;1 Pairing)</h3>
          </div>
          <span class="badge" style="background: rgba(244, 63, 94, 0.15); color: #fb7185;">${isolated.length} Items</span>
        </div>

        <div style="display: flex; flex-direction: column; gap: 10px; max-height: 380px; overflow-y: auto;">
          ${isolated.length ? isolated.map(iso => `
            <div style="background: rgba(255, 255, 255, 0.03); padding: 10px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle);">
              <div style="font-weight: 600; font-size: 13px;">${iso.item_name}</div>
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">
                ${iso.category} &bull; ${iso.formality} &bull; Worn: ${iso.wear_count || 0} times
              </div>
            </div>
          `).join("") : `<p style="font-size: 12px; color: var(--text-secondary);">No isolated garments detected!</p>`}
        </div>
      </div>
    `;
  }

  // -------------------------------------------------------------------------
  // 8. Circular Fashion Module
  // -------------------------------------------------------------------------
  function setupCircularModule() {
    const btnRun = document.getElementById("btn-run-circular-eval");
    btnRun.addEventListener("click", runCircularEvaluation);
  }

  async function runCircularEvaluation() {
    const btnRun = document.getElementById("btn-run-circular-eval");
    const container = document.getElementById("circular-columns-container");
    const season = document.getElementById("circular-season-select").value;

    btnRun.disabled = true;
    btnRun.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> Auditing Lifecycle...`;

    try {
      const res = await fetch("/api/circular-action", {
        method: "POST",
        headers: await getAuthHeaders(),
        body: JSON.stringify({
          user_id: state.userId,
          current_season: season
        })
      });
      const data = await res.json();
      renderCircularDashboard(data);
    } catch (err) {
      container.innerHTML = `<div class="empty-state"><p class="error-msg">Circular evaluation failed: ${err.message}</p></div>`;
    } finally {
      btnRun.disabled = false;
      btnRun.innerHTML = `<i class="fa-solid fa-arrows-rotate"></i> Evaluate Lifecycle`;
    }
  }

  function renderCircularDashboard(data) {
    const container = document.getElementById("circular-columns-container");
    const styleIt = data.style_it_differently || [];
    const storage = data.move_to_storage || [];
    const donate = data.consider_donating || [];

    container.innerHTML = `
      <!-- Column 1: Style It Differently -->
      <div class="circular-column">
        <div class="column-header">
          <h4 style="color: var(--cyan-accent);"><i class="fa-solid fa-wand-magic-sparkles"></i> Style It Differently</h4>
          <span class="badge">${styleIt.length}</span>
        </div>
        <p style="font-size: 11px; color: var(--text-muted);">In-season items with low wear frequency</p>
        <div style="display: flex; flex-direction: column; gap: 10px;">
          ${styleIt.length ? styleIt.map(item => `
            <div class="garment-card" style="padding: 12px;">
              <h5 style="font-size: 13px; font-weight: 600;">${item.item_name}</h5>
              <p style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">
                ${item.recommendation || 'Pair with neutral essentials.'}
              </p>
              <button class="btn-action-mini" style="margin-top: 8px; width: 100%;" onclick="window.incrementItemWear('${item.item_id}')">
                Log Wear
              </button>
            </div>
          `).join("") : `<p style="font-size: 12px; color: var(--text-muted);">All in-season items well-utilized!</p>`}
        </div>
      </div>

      <!-- Column 2: Move to Storage -->
      <div class="circular-column">
        <div class="column-header">
          <h4 style="color: #facc15;"><i class="fa-solid fa-box-archive"></i> Move to Storage</h4>
          <span class="badge">${storage.length}</span>
        </div>
        <p style="font-size: 11px; color: var(--text-muted);">Out-of-season items ready for capsule rotation</p>
        <div style="display: flex; flex-direction: column; gap: 10px;">
          ${storage.length ? storage.map(item => `
            <div class="garment-card" style="padding: 12px;">
              <h5 style="font-size: 13px; font-weight: 600;">${item.item_name}</h5>
              <p style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">
                Season: ${item.season_tag || 'Off-Season'}
              </p>
              <button class="btn-action-mini" style="margin-top: 8px; width: 100%;" onclick="window.setItemStatus('${item.item_id}', 'stored')">
                Store Garment
              </button>
            </div>
          `).join("") : `<p style="font-size: 12px; color: var(--text-muted);">No seasonal items to store.</p>`}
        </div>
      </div>

      <!-- Column 3: Consider Donating -->
      <div class="circular-column">
        <div class="column-header">
          <h4 style="color: var(--coral-accent);"><i class="fa-solid fa-hand-holding-heart"></i> Consider Donating</h4>
          <span class="badge">${donate.length}</span>
        </div>
        <p style="font-size: 11px; color: var(--text-muted);">Dormant items with 0 wears in >365 days</p>
        <div style="display: flex; flex-direction: column; gap: 10px;">
          ${donate.length ? donate.map(item => `
            <div class="garment-card" style="padding: 12px;">
              <h5 style="font-size: 13px; font-weight: 600;">${item.item_name}</h5>
              <p style="font-size: 11px; color: var(--coral-accent); margin-top: 4px;">
                Dormancy: ${item.dormant_days || '>365'} days unworn
              </p>
              <button class="btn-action-mini" style="margin-top: 8px; width: 100%; color: var(--coral-accent);" onclick="window.setItemStatus('${item.item_id}', 'donated')">
                Mark as Donated
              </button>
            </div>
          `).join("") : `<p style="font-size: 12px; color: var(--text-muted);">Zero stagnant garments detected.</p>`}
        </div>
      </div>
    `;
  }

  // -------------------------------------------------------------------------
  // 9. AI Stylist Chat
  // -------------------------------------------------------------------------
  function setupChatModule() {
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input-field");
    const promptChips = document.querySelectorAll(".prompt-chip");
    const newChatBtn = document.getElementById("btn-new-chat");

    promptChips.forEach(chip => {
      chip.addEventListener("click", () => {
        chatInput.value = chip.getAttribute("data-prompt");
        chatForm.dispatchEvent(new Event("submit"));
      });
    });

    // Reset conversation (clear server-side session + restore welcome message)
    if (newChatBtn) {
      newChatBtn.addEventListener("click", async () => {
        try {
          await fetch(`/api/chat/reset`, { method: "POST", headers: await getAuthHeaders() });
        } catch (_) {}
        restoreChatWelcome();
        showToast("Conversation reset — starting fresh!", "info");
      });
    }

    chatForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const message = chatInput.value.trim();
      if (!message) return;

      appendChatMessage("user", message);
      chatInput.value = "";

      const city = document.getElementById("weather-city-input").value.trim() || "San Francisco";
      const loadingId = appendChatMessage("assistant", `<i class="fa-solid fa-circle-notch fa-spin"></i> Thinking...`);

      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: await getAuthHeaders(),
          body: JSON.stringify({
            user_id: state.userId,
            message: message,
            city: city
          })
        });
        const data = await res.json();
        updateChatMessage(loadingId, data.reply);

        // Update turn counter
        if (data.turn_count !== undefined) {
          const turnBadge = document.getElementById("chat-turn-badge");
          const turnCount = document.getElementById("chat-turn-count");
          if (turnBadge && turnCount) {
            turnCount.textContent = data.turn_count;
            turnBadge.style.display = "";
          }
        }
      } catch (err) {
        updateChatMessage(loadingId, `Sorry, I encountered an issue: ${err.message}`);
      }
    });
  }

  function restoreChatWelcome() {
    const list = document.getElementById("chat-messages-list");
    // Remove all messages except the static welcome
    const allMessages = list.querySelectorAll(".chat-message:not(#chat-welcome-message)");
    allMessages.forEach(m => m.remove());
    // Reset turn badge
    const turnBadge = document.getElementById("chat-turn-badge");
    if (turnBadge) turnBadge.style.display = "none";
  }


  function appendChatMessage(role, text) {
    const list = document.getElementById("chat-messages-list");
    const msgId = "msg-" + Date.now();
    const isUser = role === "user";
    const icon = isUser ? "fa-user" : "fa-sparkles";

    const div = document.createElement("div");
    div.className = `chat-message ${role}`;
    div.id = msgId;
    div.innerHTML = `
      <div class="msg-avatar"><i class="fa-solid ${icon}"></i></div>
      <div class="msg-bubble">${formatMarkdown(text)}</div>
    `;
    list.appendChild(div);
    list.scrollTop = list.scrollHeight;
    return msgId;
  }

  function updateChatMessage(msgId, newText) {
    const msgEl = document.getElementById(msgId);
    if (msgEl) {
      const bubble = msgEl.querySelector(".msg-bubble");
      if (bubble) {
        bubble.innerHTML = formatMarkdown(newText);
      }
    }
  }

  function formatMarkdown(text) {
    if (!text) return "";
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/\n\n/g, '<br><br>')
      .replace(/\n/g, '<br>');
  }

  // -------------------------------------------------------------------------
  // 10. Add Garment Modal
  // -------------------------------------------------------------------------
  function setupModal() {
    const modal = document.getElementById("add-item-modal");
    const closeBtn = document.getElementById("btn-close-modal");
    const cancelBtn = document.getElementById("btn-cancel-modal");
    const addForm = document.getElementById("add-item-form");
    closeBtn.addEventListener("click", () => modal.classList.add("hidden"));
    cancelBtn.addEventListener("click", () => modal.classList.add("hidden"));

    addForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const newItem = {
        user_id: state.userId,
        item_name: document.getElementById("new-item-name").value,
        category: document.getElementById("new-item-category").value,
        primary_color: document.getElementById("new-item-color").value,
        material: document.getElementById("new-item-material").value,
        formality: document.getElementById("new-item-formality").value,
        occasion: document.getElementById("new-item-occasion").value,
        season_tag: document.getElementById("new-item-season").value,
        warmth_rating: parseInt(document.getElementById("new-item-warmth").value, 10) || 3
      };

      try {
        const res = await fetch("/api/items", {
          method: "POST",
          headers: await getAuthHeaders(),
          body: JSON.stringify(newItem)
        });
        const data = await res.json();
        modal.classList.add("hidden");
        addForm.reset();
        showToast("New garment added to closet!", "success");
        fetchClosetAndStats();
      } catch (err) {
        showToast("Failed to add garment: " + err.message, "error");
      }
    });
  }

  // -------------------------------------------------------------------------
  // Toast Helper
  // -------------------------------------------------------------------------
  function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    const icon = type === "success" ? "fa-circle-check" : type === "error" ? "fa-circle-exclamation" : "fa-circle-info";

    toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(10px)";
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }
});
