// Frontend logic for Stock Research Dashboard
// - Uses fetch() to call /api/<symbol>
// - Renders results, recent searches, Chart.js chart
// - Supports Export to Excel/CSV (via backend) and PDF (client-side using jsPDF)

(() => {
  const symbolInput = document.getElementById("symbol-input");
  const fetchBtn = document.getElementById("fetch-btn");
  const downloadPdfBtn = document.getElementById("download-pdf");
  const exportXlsxBtn = document.getElementById("export-xlsx");
  const exportCsvBtn = document.getElementById("export-csv");

  const resultsSection = document.getElementById("results");
  const companyNameEl = document.getElementById("company-name");
  const symbolEl = document.getElementById("symbol");
  const sectorEl = document.getElementById("sector");
  const marketCapEl = document.getElementById("market-cap");
  const peRatioEl = document.getElementById("pe-ratio");
  const revenueEl = document.getElementById("revenue-latest");
  const netIncomeEl = document.getElementById("netincome-latest");
  const annualReportEl = document.getElementById("annual-report-link");
  const rawInfoEl = document.getElementById("raw-info");
  const errorEl = document.getElementById("error");
  const recentList = document.getElementById("recent-list");
  const revenueChartCanvas = document.getElementById("revenue-chart");

  let revenueChart = null;
  let lastSymbol = null;
  let lastData = null;

  function fmtNumber(n) {
    if (n === null || n === undefined) return "N/A";
    if (typeof n === "number") {
      // render large numbers with suffixes
      const abs = Math.abs(n);
      if (abs >= 1e12) return (n / 1e12).toFixed(2) + "T";
      if (abs >= 1e9) return (n / 1e9).toFixed(2) + "B";
      if (abs >= 1e6) return (n / 1e6).toFixed(2) + "M";
      if (abs >= 1e3) return (n / 1e3).toFixed(2) + "K";
      return n.toLocaleString();
    }
    return String(n);
  }

  function showError(msg) {
    errorEl.textContent = msg;
    setTimeout(() => {
      // keep visible for a little while
    }, 3000);
  }

  function clearError() {
    errorEl.textContent = "";
  }

  function renderResults(data) {
    lastData = data;
    companyNameEl.textContent = data.companyName || data.symbol;
    symbolEl.textContent = data.symbol;
    sectorEl.textContent = data.sector || "N/A";
    marketCapEl.textContent = fmtNumber(data.marketCap);
    peRatioEl.textContent = data.peRatio ? data.peRatio : "N/A";
    revenueEl.textContent = fmtNumber(data.revenue);
    netIncomeEl.textContent = fmtNumber(data.netIncome);

    // annual report link
    if (data.latestAnnualReportLink) {
      annualReportEl.innerHTML = `<a href="${data.latestAnnualReportLink}" target="_blank" rel="noopener noreferrer">Open report / investor page</a>`;
    } else {
      annualReportEl.textContent = "N/A";
    }

    // raw info
    rawInfoEl.textContent = JSON.stringify(data.rawInfo || {}, null, 2);

    // revenue history chart
    if (data.revenueHistory && data.revenueHistory.length > 0) {
      const labels = data.revenueHistory.map((r) => r.year);
      const values = data.revenueHistory.map((r) => (r.revenue === null ? null : Number(r.revenue)));

      if (revenueChart) {
        revenueChart.data.labels = labels;
        revenueChart.data.datasets[0].data = values;
        revenueChart.update();
      } else {
        revenueChart = new Chart(revenueChartCanvas.getContext("2d"), {
          type: "bar",
          data: {
            labels,
            datasets: [
              {
                label: "Revenue",
                data: values,
                backgroundColor: "rgba(31,111,235,0.85)",
              },
            ],
          },
          options: {
            plugins: {
              legend: { display: false },
            },
            scales: {
              y: {
                ticks: {
                  callback: function (value) {
                    // format y ticks
                    if (Math.abs(value) >= 1e9) return value / 1e9 + "B";
                    if (Math.abs(value) >= 1e6) return value / 1e6 + "M";
                    return value;
                  },
                },
              },
            },
            responsive: true,
            maintainAspectRatio: false,
          },
        });
      }
    } else {
      // No revenue history
      if (revenueChart) {
        revenueChart.destroy();
        revenueChart = null;
      }
      revenueChartCanvas.getContext("2d").clearRect(0, 0, revenueChartCanvas.width, revenueChartCanvas.height);
    }

    // enable export buttons
    downloadPdfBtn.disabled = false;
    exportXlsxBtn.disabled = false;
    exportCsvBtn.disabled = false;
    resultsSection.classList.remove("hidden");
  }

  async function fetchRecent() {
    try {
      const res = await fetch("/api/recent");
      if (!res.ok) return;
      const payload = await res.json();
      const recent = payload.recent || [];
      recentList.innerHTML = "";
      for (const item of recent) {
        const li = document.createElement("li");
        const time = new Date(item.timestamp).toLocaleString();
        li.innerHTML = `<strong>${item.symbol}</strong> — ${item.company || ""} <span class="muted">(${time})</span>`;
        li.style.cursor = "pointer";
        li.addEventListener("click", () => {
          symbolInput.value = item.symbol;
          doFetch();
        });
        recentList.appendChild(li);
      }
    } catch (err) {
      // ignore recent fetch errors
    }
  }

  async function doFetch() {
    clearError();
    const symbol = (symbolInput.value || "").trim().toUpperCase();
    if (!symbol) {
      showError("Please enter a stock symbol (e.g., AAPL).");
      return;
    }
    fetchBtn.disabled = true;
    fetchBtn.textContent = "Fetching...";
    try {
      const res = await fetch(`/api/${encodeURIComponent(symbol)}`);
      if (res.status === 404) {
        const payload = await res.json();
        showError(payload.error || "Symbol not found.");
        fetchBtn.disabled = false;
        fetchBtn.textContent = "Fetch Data";
        return;
      }
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        showError(payload.error || `Request failed: ${res.status}`);
        fetchBtn.disabled = false;
        fetchBtn.textContent = "Fetch Data";
        return;
      }
      const data = await res.json();
      lastSymbol = symbol;
      renderResults(data);
      await fetchRecent();
    } catch (err) {
      showError("Network or server error. Please try again.");
    } finally {
      fetchBtn.disabled = false;
      fetchBtn.textContent = "Fetch Data";
    }
  }

  // Export XLSX via backend
  function exportFile(fmt) {
    if (!lastSymbol) {
      showError("No symbol loaded to export.");
      return;
    }
    const url = `/export/${encodeURIComponent(lastSymbol)}?format=${fmt}`;
    // Programmatically download
    window.location.href = url;
  }

  // Client-side PDF export using jsPDF
  async function downloadPDF() {
    if (!lastData) {
      showError("No symbol loaded to export.");
      return;
    }
    try {
      const { jsPDF } = window.jspdf;
      const doc = new jsPDF({ unit: "pt", format: "a4" });
      const left = 40;
      let y = 40;
      doc.setFontSize(16);
      doc.text(`${lastData.companyName} (${lastData.symbol})`, left, y);
      y += 22;
      doc.setFontSize(10);
      doc.text(`Sector: ${lastData.sector || "N/A"}`, left, y);
      y += 14;
      doc.text(`Market Cap: ${lastData.marketCap !== null ? lastData.marketCap.toString() : "N/A"}`, left, y);
      y += 14;
      doc.text(`P/E Ratio: ${lastData.peRatio || "N/A"}`, left, y);
      y += 22;
      doc.setFontSize(12);
      doc.text("Financials:", left, y);
      y += 14;
      doc.setFontSize(10);
      doc.text(`Revenue (Latest): ${lastData.revenue !== null ? lastData.revenue.toString() : "N/A"}`, left, y);
      y += 12;
      doc.text(`Net Income (Latest): ${lastData.netIncome !== null ? lastData.netIncome.toString() : "N/A"}`, left, y);
      y += 16;
      doc.text("Revenue history:", left, y);
      y += 12;
      // Draw simple table
      const rev = lastData.revenueHistory || [];
      if (rev.length === 0) {
        doc.text("No revenue history available.", left, y);
        y += 12;
      } else {
        for (const r of rev) {
          doc.text(`${r.year}: ${r.revenue !== null ? r.revenue.toString() : "N/A"}`, left + 8, y);
          y += 12;
        }
      }
      // Add link
      y += 10;
      doc.setTextColor(0, 102, 204);
      doc.textWithLink("Open latest annual report / investor page", left, y, { url: lastData.latestAnnualReportLink });
      // Save
      doc.save(`${lastData.symbol}_report.pdf`);
    } catch (err) {
      console.error(err);
      showError("Failed to generate PDF.");
    }
  }

  // Event listeners
  fetchBtn.addEventListener("click", doFetch);
  symbolInput.addEventListener("keyup", (e) => {
    if (e.key === "Enter") doFetch();
  });
  exportXlsxBtn.addEventListener("click", () => exportFile("xlsx"));
  exportCsvBtn.addEventListener("click", () => exportFile("csv"));
  downloadPdfBtn.addEventListener("click", downloadPDF);

  // Initial load
  fetchRecent();
})();