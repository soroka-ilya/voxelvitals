/**
 * VoxelVitals interactive UI enhancements
 * - Live search autocomplete suggestions
 * - Category filter tabs for curated server catalog
 * - One-click IP copy with visual feedback and robust fallback
 */

// Escape HTML entities to prevent any injection
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Telemetry & Visitor Interaction Tracking Beacon
function trackEvent(eventType, target, metadata = {}) {
  try {
    const payload = JSON.stringify({
      event_type: eventType,
      target: String(target || window.location.pathname),
      metadata: metadata || {}
    });
    if (navigator.sendBeacon) {
      const blob = new Blob([payload], { type: 'application/json' });
      navigator.sendBeacon('/api/analytics/event', blob);
    } else {
      fetch('/api/analytics/event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
        keepalive: true
      }).catch(() => {});
    }
  } catch (e) {
    // silently fail
  }
}

// 1. One-click IP Copy Helper with fallback
function copyIp(address, btn) {
  trackEvent('copy_ip', address, { source: btn ? 'card_or_detail' : 'direct' });
  const fallbackCopy = (text) => {
    const input = document.createElement('input');
    input.value = text;
    input.style.position = 'fixed';
    input.style.opacity = '0';
    document.body.appendChild(input);
    input.focus();
    input.select();
    try {
      document.execCommand('copy');
    } catch (err) {
      console.error('Fallback copy failed:', err);
    }
    document.body.removeChild(input);
  };

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(address).catch(() => {
      fallbackCopy(address);
    });
  } else {
    fallbackCopy(address);
  }

  if (btn) {
    const label = btn.querySelector('.copy-label') || btn;
    const originalHtml = label.innerHTML;
    label.innerText = 'Скопировано!';
    btn.classList.add('border-emerald-500/50', 'text-emerald-400');

    setTimeout(() => {
      label.innerHTML = originalHtml;
      btn.classList.remove('border-emerald-500/50', 'text-emerald-400');
    }, 1500);
  }
}

// Universal text copy helper with clipboard fallback
function copySnippet(text, btn) {
  const fallbackCopy = (val) => {
    const input = document.createElement('textarea');
    input.value = val;
    input.style.position = 'fixed';
    input.style.opacity = '0';
    document.body.appendChild(input);
    input.focus();
    input.select();
    try {
      document.execCommand('copy');
    } catch (err) {
      console.error('Fallback copy failed:', err);
    }
    document.body.removeChild(input);
  };

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).catch(() => {
      fallbackCopy(text);
    });
  } else {
    fallbackCopy(text);
  }

  if (btn) {
    const origText = btn.innerText;
    btn.innerText = 'Скопировано!';
    setTimeout(() => {
      btn.innerText = origText;
    }, 1500);
  }
}

// Global query launcher
function queryAddress(address) {
  const input = document.getElementById('search-input');
  const form = document.getElementById('search-form');
  if (input) input.value = address;
  if (form) {
    if (typeof form.requestSubmit === 'function') {
      form.requestSubmit();
    } else {
      form.submit();
    }
  }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// 2. Catalog Multi-Select, Edition Filtering & Client Pagination
let currentEdition = 'all';
const selectedCategories = new Set();
const selectedVersions = new Set();
let catalogCurrentPage = 1;
const CATALOG_PAGE_SIZE = 6;

function renderCatalogPagination(totalPages) {
  const container = document.getElementById('catalog-pagination');
  if (!container) return;

  if (totalPages <= 1) {
    container.innerHTML = '';
    return;
  }

  let html = '';
  const prevDisabled = catalogCurrentPage <= 1;
  html += `
    <button type="button" 
            onclick="setCatalogPage(${catalogCurrentPage - 1})"
            ${prevDisabled ? 'disabled' : ''}
            class="px-2.5 py-1.5 rounded-lg text-xs font-medium border border-slate-200 dark:border-[#273147] transition-colors ${
              prevDisabled 
                ? 'opacity-40 cursor-not-allowed text-slate-400' 
                : 'bg-white dark:bg-[#161b26] text-slate-700 dark:text-slate-300 hover:border-emerald-500/50'
            }">
      ← Назад
    </button>
  `;

  for (let i = 1; i <= totalPages; i++) {
    const isActive = i === catalogCurrentPage;
    html += `
      <button type="button" 
              data-page-btn="${i}"
              onclick="setCatalogPage(${i})"
              class="w-8 h-8 rounded-lg text-xs font-semibold flex items-center justify-center transition-colors ${
                isActive
                  ? 'bg-emerald-500 text-slate-950 shadow-sm'
                  : 'bg-white dark:bg-[#161b26] border border-slate-200 dark:border-[#273147] text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
              }">
        ${i}
      </button>
    `;
  }

  const nextDisabled = catalogCurrentPage >= totalPages;
  html += `
    <button type="button" 
            onclick="setCatalogPage(${catalogCurrentPage + 1})"
            ${nextDisabled ? 'disabled' : ''}
            class="px-2.5 py-1.5 rounded-lg text-xs font-medium border border-slate-200 dark:border-[#273147] transition-colors ${
              nextDisabled 
                ? 'opacity-40 cursor-not-allowed text-slate-400' 
                : 'bg-white dark:bg-[#161b26] text-slate-700 dark:text-slate-300 hover:border-emerald-500/50'
            }">
      Вперед →
    </button>
  `;

  container.innerHTML = html;
}

function setCatalogPage(page) {
  catalogCurrentPage = page;
  trackEvent('catalog_pagination', `page_${page}`, { page });
  applyCatalogFilters(false);
  const catalogSection = document.getElementById('catalog-grid');
  if (catalogSection) {
    catalogSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

function applyCatalogFilters(resetPage = true) {
  if (resetPage) {
    catalogCurrentPage = 1;
  }
  const cards = Array.from(document.querySelectorAll('[data-catalog-card]'));
  const emptyState = document.getElementById('catalog-empty-state');
  const resetBtn = document.getElementById('reset-filters-btn');

  const matchingCards = [];
  cards.forEach(card => {
    const cardEdition = card.getAttribute('data-edition') || 'java';
    const cardCategory = (card.getAttribute('data-category') || '').trim().toLowerCase();
    const cardTagsStr = card.getAttribute('data-tags') || '';
    const cardTags = cardTagsStr ? cardTagsStr.split(',').map(t => t.trim().toLowerCase()) : [];
    const cardVersionsStr = card.getAttribute('data-versions') || '';
    const cardVersions = cardVersionsStr.split(',').map(v => v.trim());

    // 1. Edition check
    const matchEdition = (currentEdition === 'all' || cardEdition === currentEdition);

    // 2. Category multi-select check (matches category or tags)
    const matchCategory = (
      selectedCategories.size === 0 || 
      selectedCategories.has(cardCategory) || 
      cardTags.some(tag => selectedCategories.has(tag) || (selectedCategories.has('survival') && (tag === 'smp' || tag === 'vanilla')))
    );

    // 3. Version multi-select check
    const matchVersion = (selectedVersions.size === 0 || cardVersions.some(v => selectedVersions.has(v)));

    if (matchEdition && matchCategory && matchVersion) {
      matchingCards.push(card);
    } else {
      card.style.display = 'none';
    }
  });

  const totalPages = Math.ceil(matchingCards.length / CATALOG_PAGE_SIZE) || 1;
  if (catalogCurrentPage > totalPages) {
    catalogCurrentPage = 1;
  }

  const startIndex = (catalogCurrentPage - 1) * CATALOG_PAGE_SIZE;
  const endIndex = startIndex + CATALOG_PAGE_SIZE;

  matchingCards.forEach((card, index) => {
    if (index >= startIndex && index < endIndex) {
      card.style.display = '';
    } else {
      card.style.display = 'none';
    }
  });

  if (emptyState) {
    emptyState.classList.toggle('hidden', matchingCards.length > 0);
  }

  renderCatalogPagination(totalPages);

  // Update labels
  const catLabel = document.getElementById('category-filter-label');
  if (catLabel) {
    catLabel.textContent = selectedCategories.size === 0 
      ? 'Категории: Все' 
      : `Категории (${selectedCategories.size})`;
  }

  const verLabel = document.getElementById('version-filter-label');
  if (verLabel) {
    verLabel.textContent = selectedVersions.size === 0 
      ? 'Версия: Все' 
      : `Версии (${selectedVersions.size})`;
  }

  // Toggle reset button
  if (resetBtn) {
    const isFiltered = currentEdition !== 'all' || selectedCategories.size > 0 || selectedVersions.size > 0;
    resetBtn.classList.toggle('hidden', !isFiltered);
  }
}

function resetAllFilters() {
  currentEdition = 'all';
  selectedCategories.clear();
  selectedVersions.clear();

  // Reset checkboxes
  document.querySelectorAll('.category-checkbox').forEach(cb => { cb.checked = false; });
  document.querySelectorAll('.version-checkbox').forEach(cb => { cb.checked = false; });

  // Reset edition tabs
  document.querySelectorAll('.edition-tab').forEach(tab => {
    const isAll = tab.getAttribute('data-edition-filter') === 'all';
    tab.classList.toggle('bg-emerald-500', isAll);
    tab.classList.toggle('text-slate-950', isAll);
    tab.classList.toggle('font-semibold', isAll);
    tab.classList.toggle('text-slate-400', !isAll);
  });

  // Sync search bedrock input
  const searchBedrock = document.getElementById('search-bedrock-input');
  if (searchBedrock) searchBedrock.value = 'false';

  applyCatalogFilters();
}

function initCatalogFilter() {
  const editionTabs = document.querySelectorAll('.edition-tab');
  const catBtn = document.getElementById('category-dropdown-btn');
  const catMenu = document.getElementById('category-dropdown-menu');
  const verBtn = document.getElementById('version-dropdown-btn');
  const verMenu = document.getElementById('version-dropdown-menu');
  const resetBtn = document.getElementById('reset-filters-btn');

  // Edition tabs
  editionTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      currentEdition = tab.getAttribute('data-edition-filter') || 'all';

      editionTabs.forEach(t => {
        t.classList.remove('bg-emerald-500', 'text-slate-950', 'font-semibold');
        t.classList.add('text-slate-400');
      });
      tab.classList.remove('text-slate-400');
      tab.classList.add('bg-emerald-500', 'text-slate-950', 'font-semibold');

      // Sync with search form bedrock input
      const searchBedrock = document.getElementById('search-bedrock-input');
      if (searchBedrock) {
        searchBedrock.value = currentEdition === 'bedrock' ? 'true' : 'false';
      }

      applyCatalogFilters();
    });
  });

  // Dropdowns toggling
  if (catBtn && catMenu) {
    catBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      catMenu.classList.toggle('hidden');
      if (verMenu) verMenu.classList.add('hidden');
    });
  }

  if (verBtn && verMenu) {
    verBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      verMenu.classList.toggle('hidden');
      if (catMenu) catMenu.classList.add('hidden');
    });
  }

  // Close menus on outside click
  document.addEventListener('click', (e) => {
    if (catMenu && !catMenu.contains(e.target) && e.target !== catBtn) {
      catMenu.classList.add('hidden');
    }
    if (verMenu && !verMenu.contains(e.target) && e.target !== verBtn) {
      verMenu.classList.add('hidden');
    }
  });

  // Category checkboxes
  document.querySelectorAll('.category-checkbox').forEach(cb => {
    cb.addEventListener('change', () => {
      if (cb.checked) {
        selectedCategories.add(cb.value);
      } else {
        selectedCategories.delete(cb.value);
      }
      applyCatalogFilters();
    });
  });

  // Version checkboxes
  document.querySelectorAll('.version-checkbox').forEach(cb => {
    cb.addEventListener('change', () => {
      if (cb.checked) {
        selectedVersions.add(cb.value);
      } else {
        selectedVersions.delete(cb.value);
      }
      applyCatalogFilters();
    });
  });

  if (resetBtn) {
    resetBtn.addEventListener('click', resetAllFilters);
  }

  // Ensure initial labels and counts are synchronized
  applyCatalogFilters();
}

// 3. Search Autocomplete Suggestions
function initAutocomplete() {
  const input = document.getElementById('search-input');
  const dropdown = document.getElementById('autocomplete-dropdown');
  const form = document.getElementById('search-form');
  if (!input || !dropdown) return;

  let debounceTimer = null;
  let activeIndex = -1;

  async function fetchSuggestions(query) {
    try {
      const res = await fetch(`/api/suggestions?q=${encodeURIComponent(query)}&limit=6`);
      if (!res.ok) return;
      const suggestions = await res.json();
      renderDropdown(suggestions);
    } catch (err) {
      console.error('Autocomplete fetch error:', err);
    }
  }

  function renderDropdown(items) {
    if (!items || items.length === 0) {
      dropdown.innerHTML = '';
      dropdown.classList.add('hidden');
      activeIndex = -1;
      return;
    }

    dropdown.innerHTML = items.map((item, index) => `
      <div class="suggestion-item p-3 hover:bg-slate-100 dark:hover:bg-[#1c2233] border-l-2 border-transparent cursor-pointer flex items-center justify-between gap-3 transition-colors ${index === 0 ? 'rounded-t-xl' : ''} ${index === items.length - 1 ? 'rounded-b-xl' : ''}" 
           data-index="${index}" 
           data-address="${escapeHtml(item.address)}"
           data-edition="${escapeHtml(item.edition || 'java')}">
        <div class="flex items-center gap-3 min-w-0">
          <img src="${escapeHtml(item.icon)}" onerror="this.src='${escapeHtml(item.fallback_icon || '')}';" alt="${escapeHtml(item.name)}" class="w-8 h-8 rounded-lg bg-slate-100 dark:bg-[#0c0f17] border border-slate-200 dark:border-[#273147] object-contain flex-shrink-0" />
          <div class="min-w-0 text-left">
            <div class="flex items-center gap-2">
              <span class="text-xs font-semibold text-slate-900 dark:text-white truncate">${escapeHtml(item.name)}</span>
              <span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 dark:bg-[#273147] text-slate-700 dark:text-slate-300 font-medium border border-slate-200 dark:border-transparent">${escapeHtml(item.category_label || item.category)}</span>
            </div>
            <p class="text-[11px] font-mono text-emerald-500 dark:text-emerald-400 truncate">${escapeHtml(item.address)}</p>
          </div>
        </div>
        <div class="flex items-center gap-2 flex-shrink-0">
          <span class="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-100 dark:bg-[#0c0f17] text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-[#273147]/60">${escapeHtml(item.edition || 'java')}</span>
          <svg class="w-4 h-4 text-slate-400 dark:text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
          </svg>
        </div>
      </div>
    `).join('');

    dropdown.classList.remove('hidden');
    activeIndex = -1;

    // Attach click events
    dropdown.querySelectorAll('.suggestion-item').forEach(el => {
      el.addEventListener('click', () => {
        const addr = el.getAttribute('data-address');
        const edition = el.getAttribute('data-edition') || 'java';
        selectSuggestion(addr, edition);
      });
    });
  }

  function selectSuggestion(addr, edition = 'java') {
    input.value = addr;
    const bedrockInput = document.getElementById('search-bedrock-input');
    if (bedrockInput) {
      bedrockInput.value = edition === 'bedrock' ? 'true' : 'false';
    }
    dropdown.innerHTML = '';
    dropdown.classList.add('hidden');
    if (form) {
      if (typeof form.requestSubmit === 'function') {
        form.requestSubmit();
      } else {
        form.submit();
      }
    }
  }

  let originalTyped = '';

  input.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    originalTyped = input.value;
    const q = input.value.trim();
    debounceTimer = setTimeout(() => {
      fetchSuggestions(q);
    }, 120);
  });

  input.addEventListener('focus', () => {
    originalTyped = input.value;
    fetchSuggestions(input.value.trim());
  });

  // Keyboard navigation
  input.addEventListener('keydown', (e) => {
    const items = dropdown.querySelectorAll('.suggestion-item');
    if (dropdown.classList.contains('hidden') || items.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (activeIndex < items.length - 1) {
        activeIndex++;
        updateActiveItem(items);
      } else {
        activeIndex = -1;
        input.value = originalTyped;
        updateActiveItem(items);
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (activeIndex > 0) {
        activeIndex--;
        updateActiveItem(items);
      } else if (activeIndex === 0) {
        activeIndex = -1;
        input.value = originalTyped;
        updateActiveItem(items);
      } else {
        activeIndex = items.length - 1;
        updateActiveItem(items);
      }
    } else if (e.key === 'Enter') {
      if (activeIndex >= 0 && items[activeIndex]) {
        e.preventDefault();
        const addr = items[activeIndex].getAttribute('data-address');
        const edition = items[activeIndex].getAttribute('data-edition') || 'java';
        selectSuggestion(addr, edition);
      } else {
        dropdown.classList.add('hidden');
        activeIndex = -1;
      }
    } else if (e.key === 'Escape') {
      dropdown.classList.add('hidden');
      activeIndex = -1;
      input.value = originalTyped;
    }
  });

  function updateActiveItem(items) {
    items.forEach((item, idx) => {
      if (idx === activeIndex) {
        item.classList.add('bg-slate-100', 'dark:bg-[#1c2233]', 'border-emerald-500');
        item.classList.remove('border-transparent');
        input.value = item.getAttribute('data-address');
      } else {
        item.classList.remove('bg-slate-100', 'dark:bg-[#1c2233]', 'border-emerald-500');
        item.classList.add('border-transparent');
      }
    });
  }

  // Close dropdown on outside click or form submission
  if (form) {
    form.addEventListener('submit', () => {
      dropdown.classList.add('hidden');
      activeIndex = -1;
    });
  }

  document.addEventListener('click', (e) => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.classList.add('hidden');
      activeIndex = -1;
    }
  });

  // Zero-shift skeleton injection: swaps skeleton directly into exact target slot
  document.body.addEventListener('htmx:beforeRequest', (evt) => {
    if (evt.detail.target && evt.detail.target.id === 'search-result') {
      evt.detail.target.innerHTML = `
        <div class="rounded-xl border border-slate-200 dark:border-[#273147] bg-white dark:bg-[#161b26] p-5 shadow-sm">
          <div class="flex items-start justify-between gap-4">
            <div class="flex items-center gap-4 w-full">
              <div class="w-14 h-14 rounded-lg skeleton-box flex-shrink-0"></div>
              <div class="flex-1 space-y-2">
                <div class="h-5 w-48 rounded skeleton-box"></div>
                <div class="h-3 w-28 rounded skeleton-box"></div>
              </div>
            </div>
            <div class="h-6 w-20 rounded skeleton-box flex-shrink-0"></div>
          </div>
          <div class="mt-4 pt-4 border-t border-slate-200 dark:border-[#273147]/60 space-y-2">
            <div class="h-4 w-3/4 rounded skeleton-box"></div>
            <div class="h-4 w-1/2 rounded skeleton-box"></div>
          </div>
          <div class="mt-4 pt-3 flex items-center justify-between">
            <div class="h-4 w-32 rounded skeleton-box"></div>
            <div class="h-4 w-24 rounded skeleton-box"></div>
          </div>
        </div>
      `;
    }
  });
}

// 4. Toast Notification
function showToast(message, duration = 3000, actionLabel = null, actionFn = null) {
  let toast = document.getElementById('voxel-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'voxel-toast';
    toast.className = 'fixed bottom-5 right-5 z-50 px-4 py-2.5 rounded-xl text-xs font-medium bg-white dark:bg-[#161b26] border border-slate-200 dark:border-[#273147] text-slate-900 dark:text-slate-100 shadow-xl transition-all duration-300 opacity-0 translate-y-3 pointer-events-none flex items-center gap-2.5';
    document.body.appendChild(toast);
  }
  let actionHtml = '';
  if (actionLabel && typeof actionFn === 'function') {
    window._lastToastAction = actionFn;
    actionHtml = `<button type="button" onclick="if(window._lastToastAction){window._lastToastAction();}" class="underline text-emerald-500 hover:text-emerald-400 font-semibold ml-1 cursor-pointer pointer-events-auto">${escapeHtml(actionLabel)}</button>`;
  }
  toast.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400 flex-shrink-0"></span><span class="truncate">${escapeHtml(message)}</span>${actionHtml}`;
  toast.classList.remove('opacity-0', 'translate-y-3', 'pointer-events-none');
  toast.classList.add('opacity-100', 'translate-y-0', 'pointer-events-auto');

  if (window._toastTimeout) clearTimeout(window._toastTimeout);
  window._toastTimeout = setTimeout(() => {
    toast.classList.remove('opacity-100', 'translate-y-0', 'pointer-events-auto');
    toast.classList.add('opacity-0', 'translate-y-3', 'pointer-events-none');
  }, duration);
}

// 5. Quick Connect Hub & Launcher Protocol Handler
let currentQcAddress = '';
let currentQcHost = '';
let currentQcPort = '';
let currentQcEdition = 'java';
let currentQcName = '';
let currentQcActiveTab = 'any';
let currentJavaAddress = '';

function isFeaturedBedrock(address) {
  const clean = (address || '').toLowerCase();
  const featured = ['hive', 'hivebedrock', 'cubecraft', 'lbsg', 'lifeboat', 'galaxite', 'mineville', 'inpvp'];
  return featured.some(k => clean.includes(k));
}

function closeQuickConnectModal() {
  const modal = document.getElementById('quick-connect-modal') || document.getElementById('java-launcher-modal');
  if (modal) modal.classList.add('hidden');
}

function closeJavaLauncherModal() {
  closeQuickConnectModal();
}

function copyTextToClipboard(text, onSuccess, onFail) {
  if (!text) return;
  const fallback = () => {
    try {
      const input = document.createElement('input');
      input.value = text;
      input.style.position = 'fixed';
      input.style.opacity = '0';
      document.body.appendChild(input);
      input.focus();
      input.select();
      const successful = document.execCommand('copy');
      document.body.removeChild(input);
      if (successful) {
        if (onSuccess) onSuccess();
      } else {
        if (onFail) onFail();
      }
    } catch (e) {
      if (onFail) onFail(e);
    }
  };

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => {
      if (onSuccess) onSuccess();
    }).catch(() => {
      fallback();
    });
  } else {
    fallback();
  }
}

function parseHostPort(address, edition = 'java') {
  const clean = (address || '').trim();
  const defaultPort = edition === 'bedrock' ? '19132' : '25565';
  const lastColon = clean.lastIndexOf(':');
  if (lastColon > 0 && lastColon < clean.length - 1) {
    const potentialPort = clean.substring(lastColon + 1);
    if (/^\d+$/.test(potentialPort)) {
      return { host: clean.substring(0, lastColon), port: potentialPort };
    }
  }
  return { host: clean, port: defaultPort };
}

function copyQuickAddress(btn = null) {
  if (currentQcAddress) {
    copyIp(currentQcAddress, btn);
  }
}

function copyCurrentJavaIp(btn = null) {
  copyQuickAddress(btn);
}

function copyQuickHost(btn = null) {
  if (!currentQcHost) return;
  copyTextToClipboard(currentQcHost, () => {
    showToast(`Хост скопирован: ${currentQcHost}`);
    if (btn) {
      const orig = btn.textContent;
      btn.textContent = '✓ Скопирован';
      setTimeout(() => { btn.textContent = orig; }, 1800);
    }
  }, () => {
    showToast(`Хост: ${currentQcHost}`);
  });
}

function copyQuickPort(btn = null) {
  if (!currentQcPort) return;
  copyTextToClipboard(currentQcPort, () => {
    showToast(`Порт скопирован: ${currentQcPort}`);
    if (btn) {
      const orig = btn.textContent;
      btn.textContent = '✓ Скопирован';
      setTimeout(() => { btn.textContent = orig; }, 1800);
    }
  }, () => {
    showToast(`Порт: ${currentQcPort}`);
  });
}

function confirmAnyLauncher() {
  if (currentQcAddress) {
    copyIp(currentQcAddress);
  }
  const remCb = document.getElementById('qc-remember-choice') || document.getElementById('java-remember-choice');
  if (remCb?.checked) {
    localStorage.setItem('preferred_minecraft_launcher', 'any');
    localStorage.setItem('preferred_java_client', 'any');
  }
  showToast('IP скопирован! Вставьте в лаунчере через Ctrl+V');
  closeQuickConnectModal();
}

function finishQuickConnectModal() {
  const remCb = document.getElementById('qc-remember-choice') || document.getElementById('java-remember-choice');
  if (remCb?.checked && currentQcEdition === 'java') {
    localStorage.setItem('preferred_minecraft_launcher', currentQcActiveTab);
    localStorage.setItem('preferred_java_client', currentQcActiveTab);
  }
  closeQuickConnectModal();
}

function switchQuickConnectTab(tabName) {
  currentQcActiveTab = tabName;
  const tabs = ['any', 'lunar', 'badlion', 'bedrock'];
  tabs.forEach(t => {
    const panel = document.getElementById(`qc-panel-${t}`);
    const btn = document.getElementById(`qc-tab-btn-${t}`);
    const isActive = t === tabName;
    if (panel) panel.classList.toggle('hidden', !isActive);
    if (btn) {
      if (isActive) {
        btn.className = 'py-1.5 px-1 rounded-lg transition-colors text-center text-slate-900 dark:text-white bg-white dark:bg-[#161b26] shadow-sm';
      } else {
        btn.className = 'py-1.5 px-1 rounded-lg transition-colors text-center text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white';
      }
    }
  });
}

function openQuickConnectModal(address, edition = 'java', customName = '', initialTab = null) {
  const cleanAddr = (address || '').trim();
  const hp = parseHostPort(cleanAddr, edition);
  currentQcHost = hp.host;
  currentQcPort = hp.port;
  currentQcAddress = cleanAddr;
  currentJavaAddress = cleanAddr;
  currentQcEdition = edition;
  currentQcName = customName || currentQcHost;

  const addrEl = document.getElementById('qc-modal-address') || document.getElementById('java-modal-address');
  if (addrEl) addrEl.textContent = cleanAddr;

  const badge = document.getElementById('qc-modal-edition-badge');
  if (badge) {
    badge.textContent = edition === 'bedrock' ? 'Bedrock' : 'Java';
    badge.className = edition === 'bedrock'
      ? 'px-2 py-0.5 rounded text-[10px] font-bold uppercase font-mono bg-amber-500/10 text-amber-500 border border-amber-500/20'
      : 'px-2 py-0.5 rounded text-[10px] font-bold uppercase font-mono bg-emerald-500/10 text-emerald-500 border border-emerald-500/20';
  }

  const hostEl = document.getElementById('qc-bedrock-host');
  if (hostEl) hostEl.textContent = currentQcHost;
  const portEl = document.getElementById('qc-bedrock-port');
  if (portEl) portEl.textContent = currentQcPort;

  const isFeatured = isFeaturedBedrock(currentQcHost);
  const featBanner = document.getElementById('qc-bedrock-featured-banner');
  if (featBanner) featBanner.classList.toggle('hidden', !isFeatured);

  // Tab navigation bar adaptation
  const tabsNav = document.getElementById('qc-tabs-nav');
  if (edition === 'bedrock') {
    if (tabsNav) tabsNav.classList.add('hidden');
    switchQuickConnectTab('bedrock');
  } else {
    if (tabsNav) tabsNav.classList.remove('hidden');
    let targetTab = initialTab;
    if (!targetTab) {
      const savedPref = localStorage.getItem('preferred_minecraft_launcher') || localStorage.getItem('preferred_java_client');
      if (savedPref === 'lunar' || savedPref === 'badlion') {
        targetTab = savedPref;
      } else {
        targetTab = 'any';
      }
    }
    switchQuickConnectTab(targetTab);
  }

  const savedPref = localStorage.getItem('preferred_minecraft_launcher') || localStorage.getItem('preferred_java_client');
  const resetBtn = document.getElementById('qc-reset-btn');
  if (resetBtn) resetBtn.classList.toggle('hidden', !savedPref);
  const remCb = document.getElementById('qc-remember-choice') || document.getElementById('java-remember-choice');
  if (remCb) remCb.checked = !!savedPref;

  const modal = document.getElementById('quick-connect-modal') || document.getElementById('java-launcher-modal');
  if (modal) modal.classList.remove('hidden');
}

function launchClient(clientType) {
  if (!currentQcAddress && !currentJavaAddress) return;
  const targetAddr = currentQcAddress || currentJavaAddress;
  const remCb = document.getElementById('qc-remember-choice') || document.getElementById('java-remember-choice');
  if (remCb?.checked) {
    localStorage.setItem('preferred_minecraft_launcher', clientType);
    localStorage.setItem('preferred_java_client', clientType);
  }

  if (clientType === 'lunar') {
    window.location.href = `lunarclient://play?serverAddress=${encodeURIComponent(targetAddr)}`;
    showToast(`Запуск Lunar Client... IP ${targetAddr} в буфере!`);
  } else if (clientType === 'badlion') {
    window.location.href = `badlion://join?server=${encodeURIComponent(targetAddr)}`;
    showToast(`Запуск Badlion Client... IP ${targetAddr} в буфере!`);
  }
  closeQuickConnectModal();
}

function launchJavaClient(clientType) {
  launchClient(clientType);
}

function triggerBedrockUri() {
  const sName = encodeURIComponent(currentQcName || currentQcHost);
  const uri = `minecraft://?addExternalServer=${sName}|${currentQcHost}:${currentQcPort}`;
  try {
    window.location.href = uri;
    showToast('Minecraft Bedrock запускается! Если сервер не добавился — скопируйте хост и порт.');
  } catch (e) {
    console.warn('Bedrock URI failed', e);
  }
}

function resetPreferredLauncher() {
  localStorage.removeItem('preferred_minecraft_launcher');
  localStorage.removeItem('preferred_java_client');
  const remCb = document.getElementById('qc-remember-choice');
  if (remCb) remCb.checked = false;
  const resetBtn = document.getElementById('qc-reset-btn');
  if (resetBtn) resetBtn.classList.add('hidden');
  showToast('Сохраненный лаунчер сброшен');
}

function launchMinecraft(address, edition = 'java', customNameOrBtn = '', btn = null) {
  let customName = '';
  let triggerBtn = btn;
  if (typeof customNameOrBtn === 'object' && customNameOrBtn !== null) {
    triggerBtn = customNameOrBtn;
  } else if (typeof customNameOrBtn === 'string') {
    customName = customNameOrBtn;
  }

  const cleanAddr = (address || '').trim();
  const isBedrock = edition === 'bedrock' || (edition !== 'java' && (cleanAddr.includes('bedrock') || cleanAddr.includes('19132')));

  trackEvent('launch_client', cleanAddr, { edition: isBedrock ? 'bedrock' : 'java', custom_name: customName });
  copyIp(cleanAddr, triggerBtn);

  if (isBedrock) {
    const isFeatured = isFeaturedBedrock(cleanAddr);
    if (isFeatured) {
      openQuickConnectModal(cleanAddr, 'bedrock', customName, 'bedrock');
      showToast('Сервер встроен во вкладку «Серверы» Bedrock! IP скопирован.');
    } else {
      const hp = parseHostPort(cleanAddr, 'bedrock');
      const sName = encodeURIComponent(customName || hp.host);
      try {
        window.location.href = `minecraft://?addExternalServer=${sName}|${hp.host}:${hp.port}`;
      } catch (err) {
        console.warn('Bedrock URI trigger failed:', err);
      }
      openQuickConnectModal(cleanAddr, 'bedrock', customName, 'bedrock');
      showToast('Запуск Minecraft Bedrock... Хост и порт в окне подключения.');
    }
    return;
  }

  // Java Edition: check preferred launcher
  const preferred = localStorage.getItem('preferred_minecraft_launcher') || localStorage.getItem('preferred_java_client');
  if (preferred === 'lunar') {
    window.location.href = `lunarclient://play?serverAddress=${encodeURIComponent(cleanAddr)}`;
    showToast(`Запуск Lunar Client... IP скопирован!`, 4000, 'Сменить', () => {
      resetPreferredLauncher();
      openQuickConnectModal(cleanAddr, 'java', customName, 'any');
    });
    return;
  } else if (preferred === 'badlion') {
    window.location.href = `badlion://join?server=${encodeURIComponent(cleanAddr)}`;
    showToast(`Запуск Badlion Client... IP скопирован!`, 4000, 'Сменить', () => {
      resetPreferredLauncher();
      openQuickConnectModal(cleanAddr, 'java', customName, 'any');
    });
    return;
  } else if (preferred === 'any') {
    showToast(`IP скопирован для прямого подключения (Ctrl+V)!`, 4000, 'Сменить', () => {
      resetPreferredLauncher();
      openQuickConnectModal(cleanAddr, 'java', customName, 'any');
    });
    return;
  }

  // Open Quick Connect Hub for any launcher / instructions
  openQuickConnectModal(cleanAddr, 'java', customName, 'any');
}

// 6. Theme Switcher (Dark / Light / Auto Browser Sync)
function applyTheme(isDark) {
  if (isDark) {
    document.documentElement.classList.add('dark');
    document.documentElement.classList.remove('light');
  } else {
    document.documentElement.classList.remove('dark');
    document.documentElement.classList.add('light');
  }
  updateThemeIcons(isDark);
  window.dispatchEvent(new CustomEvent('themechange', { detail: { isDark } }));
}

function updateThemeIcons(isDark) {
  const moon = document.getElementById('theme-icon-moon');
  const sun = document.getElementById('theme-icon-sun');
  if (moon && sun) {
    moon.classList.toggle('hidden', !isDark);
    sun.classList.toggle('hidden', isDark);
  }
}

function toggleTheme() {
  const isDark = document.documentElement.classList.contains('dark');
  const newDark = !isDark;
  localStorage.setItem('theme', newDark ? 'dark' : 'light');
  applyTheme(newDark);
  trackEvent('toggle_theme', newDark ? 'dark' : 'light', {});
}

function initTheme() {
  const saved = localStorage.getItem('theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)');

  if (saved === 'dark') {
    applyTheme(true);
  } else if (saved === 'light') {
    applyTheme(false);
  } else {
    // Follow browser/system setting automatically
    applyTheme(prefersDark.matches);
  }

  // React immediately to browser/system theme changes
  prefersDark.addEventListener('change', (e) => {
    // If user hasn't explicitly overridden theme in current session, or system changes
    applyTheme(e.matches);
    localStorage.removeItem('theme'); // keep in sync with automatic browser preference
  });
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initCatalogFilter();
  initAutocomplete();
});

