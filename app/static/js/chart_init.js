/**
 * Chart.js initialization for Minecraft server telemetry
 */
function renderTelemetryChart(canvasId, historyData) {
  const ctx = document.getElementById(canvasId);
  if (!ctx || !historyData || historyData.length === 0) return;

  const labels = historyData.map(point => {
    const d = new Date(point.timestamp);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  });

  const playersData = historyData.map(point => point.players_online);
  const pingData = historyData.map(point => point.ping_ms);

  new Chart(ctx, {
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
            color: '#94a3b8',
            font: { family: 'Plus Jakarta Sans', size: 12 },
            boxWidth: 12
          }
        },
        tooltip: {
          backgroundColor: '#161b26',
          titleColor: '#f1f5f9',
          bodyColor: '#94a3b8',
          borderColor: '#273147',
          borderWidth: 1,
          padding: 10,
          displayColors: true,
          cornerRadius: 6
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255, 255, 255, 0.04)' },
          ticks: { color: '#64748b', maxTicksLimit: 12, font: { size: 11 } }
        },
        yPlayers: {
          type: 'linear',
          display: true,
          position: 'left',
          beginAtZero: true,
          grid: { color: 'rgba(255, 255, 255, 0.04)' },
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
}
