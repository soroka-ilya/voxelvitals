/**
 * Chart.js initialization for Minecraft server telemetry
 */
let currentTelemetryChart = null;

function renderTelemetryChart(canvasId, historyData) {
  const ctx = document.getElementById(canvasId);
  if (!ctx || !historyData || historyData.length === 0) return;

  if (currentTelemetryChart) {
    try {
      currentTelemetryChart.destroy();
    } catch (e) {
      // ignore
    }
  }

  const labels = historyData.map(point => {
    const d = new Date(point.timestamp);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  });

  const playersData = historyData.map(point => point.players_online);
  const pingData = historyData.map(point => point.ping_ms);
  const isDark = document.documentElement.classList.contains('dark');

  currentTelemetryChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Players Online',
          data: playersData,
          borderColor: '#10b981',
          backgroundColor: 'rgba(16, 185, 129, 0.08)',
          fill: true,
          tension: 0.25,
          borderWidth: 2,
          pointRadius: historyData.length > 30 ? 0 : 3,
          pointHoverRadius: 5,
          yAxisID: 'yPlayers'
        },
        {
          label: 'Latency (ms)',
          data: pingData,
          borderColor: '#f59e0b',
          backgroundColor: 'transparent',
          borderDash: [4, 4],
          fill: false,
          tension: 0.25,
          borderWidth: 1.5,
          pointRadius: 0,
          pointHoverRadius: 4,
          yAxisID: 'yPing'
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          labels: {
            color: document.documentElement.classList.contains('dark') ? '#94a3b8' : '#475569',
            font: { family: 'Plus Jakarta Sans', size: 12 },
            boxWidth: 12
          }
        },
        tooltip: {
          backgroundColor: document.documentElement.classList.contains('dark') ? '#161b26' : '#ffffff',
          titleColor: document.documentElement.classList.contains('dark') ? '#f1f5f9' : '#0f172a',
          bodyColor: document.documentElement.classList.contains('dark') ? '#94a3b8' : '#475569',
          borderColor: document.documentElement.classList.contains('dark') ? '#273147' : '#e2e8f0',
          borderWidth: 1,
          padding: 10,
          displayColors: true,
          cornerRadius: 6
        }
      },
      scales: {
        x: {
          grid: { color: document.documentElement.classList.contains('dark') ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.05)' },
          ticks: { color: '#64748b', maxTicksLimit: 12, font: { size: 11 } }
        },
        yPlayers: {
          type: 'linear',
          display: true,
          position: 'left',
          beginAtZero: true,
          grid: { color: document.documentElement.classList.contains('dark') ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.05)' },
          ticks: { color: '#10b981', font: { size: 11 } }
        },
        yPing: {
          type: 'linear',
          display: true,
          position: 'right',
          beginAtZero: true,
          grid: { drawOnChartArea: false },
          ticks: { color: '#f59e0b', font: { size: 11 } }
        }
      }
    }
  });
  return currentTelemetryChart;
}

window.addEventListener('themechange', (e) => {
  if (!currentTelemetryChart) return;
  const isDark = (e.detail && typeof e.detail.isDark === 'boolean')
    ? e.detail.isDark
    : document.documentElement.classList.contains('dark');

  if (currentTelemetryChart.options.plugins?.legend?.labels) {
    currentTelemetryChart.options.plugins.legend.labels.color = isDark ? '#94a3b8' : '#475569';
  }
  if (currentTelemetryChart.options.plugins?.tooltip) {
    currentTelemetryChart.options.plugins.tooltip.backgroundColor = isDark ? '#161b26' : '#ffffff';
    currentTelemetryChart.options.plugins.tooltip.titleColor = isDark ? '#f1f5f9' : '#0f172a';
    currentTelemetryChart.options.plugins.tooltip.bodyColor = isDark ? '#94a3b8' : '#475569';
    currentTelemetryChart.options.plugins.tooltip.borderColor = isDark ? '#273147' : '#e2e8f0';
  }
  const gridColor = isDark ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.05)';
  if (currentTelemetryChart.options.scales?.x?.grid) {
    currentTelemetryChart.options.scales.x.grid.color = gridColor;
  }
  if (currentTelemetryChart.options.scales?.yPlayers?.grid) {
    currentTelemetryChart.options.scales.yPlayers.grid.color = gridColor;
  }
  currentTelemetryChart.update();
});
