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

// 1. One-click IP Copy Helper with fallback
function copyIp(address, btn) {
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

  const label = btn.querySelector('.copy-label') || btn;
  const originalHtml = label.innerHTML;
  label.innerText = 'Скопировано!';
  btn.classList.add('border-emerald-500/50', 'text-emerald-400');

  setTimeout(() => {
    label.innerHTML = originalHtml;
    btn.classList.remove('border-emerald-500/50', 'text-emerald-400');
  }, 1500);
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

// 2. Catalog Multi-Select & Edition Filtering
let currentEdition = 'all';
const selectedCategories = new Set();
const selectedVersions = new Set();

function applyCatalogFilters() {
  const cards = document.querySelectorAll('[data-catalog-card]');
  const emptyState = document.getElementById('catalog-empty-state');
  const resetBtn = document.getElementById('reset-filters-btn');
  let visibleCount = 0;

  cards.forEach(card => {
    const cardEdition = card.getAttribute('data-edition') || 'java';
    const cardCategory = card.getAttribute('data-category') || '';
    const cardVersionsStr = card.getAttribute('data-versions') || '';
    const cardVersions = cardVersionsStr.split(',').map(v => v.trim());

    // 1. Edition check
    const matchEdition = (currentEdition === 'all' || cardEdition === currentEdition);

    // 2. Category multi-select check
    const matchCategory = (selectedCategories.size === 0 || selectedCategories.has(cardCategory));

    // 3. Version multi-select check
    const matchVersion = (selectedVersions.size === 0 || cardVersions.some(v => selectedVersions.has(v)));

    if (matchEdition && matchCategory && matchVersion) {
      card.style.display = '';
      visibleCount++;
    } else {
      card.style.display = 'none';
    }
  });

  if (emptyState) {
    emptyState.classList.toggle('hidden', visibleCount > 0);
  }

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
      <div class="suggestion-item p-3 hover:bg-[#1c2233] cursor-pointer flex items-center justify-between gap-3 transition-colors ${index === 0 ? 'rounded-t-xl' : ''} ${index === items.length - 1 ? 'rounded-b-xl' : ''}" 
           data-index="${index}" 
           data-address="${escapeHtml(item.address)}"
           data-edition="${escapeHtml(item.edition || 'java')}">
        <div class="flex items-center gap-3 min-w-0">
          <img src="${escapeHtml(item.icon)}" onerror="this.src='${escapeHtml(item.fallback_icon || '')}';" alt="${escapeHtml(item.name)}" class="w-8 h-8 rounded-lg bg-[#0c0f17] border border-[#273147] object-contain flex-shrink-0" />
          <div class="min-w-0 text-left">
            <div class="flex items-center gap-2">
              <span class="text-xs font-semibold text-white truncate">${escapeHtml(item.name)}</span>
              <span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#273147] text-slate-300 font-medium">${escapeHtml(item.category_label || item.category)}</span>
            </div>
            <p class="text-[11px] font-mono text-emerald-400 truncate">${escapeHtml(item.address)}</p>
          </div>
        </div>
        <div class="flex items-center gap-2 flex-shrink-0">
          <span class="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-[#0c0f17] text-slate-400 border border-[#273147]/60">${escapeHtml(item.edition || 'java')}</span>
          <svg class="w-4 h-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
    if (bedrockInput && edition === 'bedrock') {
      bedrockInput.value = 'true';
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
        item.classList.add('bg-[#1c2233]', 'border-l-2', 'border-emerald-500');
        input.value = item.getAttribute('data-address');
      } else {
        item.classList.remove('bg-[#1c2233]', 'border-l-2', 'border-emerald-500');
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
        <div class="rounded-xl border border-[#273147] bg-[#161b26] p-5 shadow-sm">
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
          <div class="mt-4 pt-4 border-t border-[#273147]/60 space-y-2">
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

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  initCatalogFilter();
  initAutocomplete();
});
