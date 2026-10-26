/**
 * VoxelVitals interactive UI enhancements
 * - Live search autocomplete suggestions
 * - Category filter tabs for curated server catalog
 * - One-click IP copy with visual feedback
 */

// 1. One-click IP Copy Helper
function copyIp(address, btn) {
  if (!navigator.clipboard) {
    const input = document.createElement('input');
    input.value = address;
    document.body.appendChild(input);
    input.select();
    document.execCommand('copy');
    document.body.removeChild(input);
  } else {
    navigator.clipboard.writeText(address).catch(err => {
      console.error('Clipboard copy failed:', err);
    });
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

// 2. Catalog Category Filtering
function initCatalogFilter() {
  const filterBtns = document.querySelectorAll('[data-category-filter]');
  const cards = document.querySelectorAll('[data-catalog-card]');
  if (!filterBtns.length || !cards.length) return;

  filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const selected = btn.getAttribute('data-category-filter');

      // Update button active states
      filterBtns.forEach(b => {
        b.classList.remove('bg-emerald-500', 'text-slate-950', 'font-semibold');
        b.classList.add('bg-[#161b26]', 'text-slate-400', 'border-[#273147]');
      });
      btn.classList.remove('bg-[#161b26]', 'text-slate-400', 'border-[#273147]');
      btn.classList.add('bg-emerald-500', 'text-slate-950', 'font-semibold');

      // Filter cards
      cards.forEach(card => {
        const cat = card.getAttribute('data-category');
        if (selected === 'all' || cat === selected) {
          card.style.display = '';
        } else {
          card.style.display = 'none';
        }
      });
    });
  });
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
           data-address="${item.address}">
        <div class="flex items-center gap-3 min-w-0">
          <img src="${item.icon}" alt="${item.name}" class="w-8 h-8 rounded-lg bg-[#0c0f17] border border-[#273147] flex-shrink-0" />
          <div class="min-w-0 text-left">
            <div class="flex items-center gap-2">
              <span class="text-xs font-semibold text-white truncate">${item.name}</span>
              <span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#273147] text-slate-300 font-medium">${item.category_label || item.category}</span>
            </div>
            <p class="text-[11px] font-mono text-emerald-400 truncate">${item.address}</p>
          </div>
        </div>
        <div class="flex items-center gap-2 flex-shrink-0">
          <span class="text-[11px] text-slate-400 hidden sm:inline">Выбрать</span>
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
        selectSuggestion(addr);
      });
    });
  }

  function selectSuggestion(addr) {
    input.value = addr;
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

  input.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    const q = input.value.trim();
    debounceTimer = setTimeout(() => {
      fetchSuggestions(q);
    }, 120);
  });

  input.addEventListener('focus', () => {
    fetchSuggestions(input.value.trim());
  });

  // Keyboard navigation
  input.addEventListener('keydown', (e) => {
    const items = dropdown.querySelectorAll('.suggestion-item');
    if (dropdown.classList.contains('hidden') || items.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = (activeIndex + 1) % items.length;
      updateActiveItem(items);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = (activeIndex - 1 + items.length) % items.length;
      updateActiveItem(items);
    } else if (e.key === 'Enter') {
      if (activeIndex >= 0 && items[activeIndex]) {
        e.preventDefault();
        const addr = items[activeIndex].getAttribute('data-address');
        selectSuggestion(addr);
      }
    } else if (e.key === 'Escape') {
      dropdown.classList.add('hidden');
      activeIndex = -1;
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

  // Close dropdown on outside click
  document.addEventListener('click', (e) => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.classList.add('hidden');
      activeIndex = -1;
    }
  });
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  initCatalogFilter();
  initAutocomplete();
});
