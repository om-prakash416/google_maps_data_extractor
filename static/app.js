document.addEventListener('DOMContentLoaded', () => {

    // Help Modal Logic
    const helpBtn = document.getElementById('help-btn');
    const helpModal = document.getElementById('help-modal');
    const closeModal = document.getElementById('close-modal');

    if (helpBtn && helpModal && closeModal) {
        helpBtn.addEventListener('click', () => {
            helpModal.style.display = 'flex';
        });

        closeModal.addEventListener('click', () => {
            helpModal.style.display = 'none';
        });

        helpModal.addEventListener('click', (e) => {
            if (e.target === helpModal) {
                helpModal.style.display = 'none';
            }
        });
    }

    const form = document.getElementById('scrape-form');
    const startBtn = document.getElementById('start-btn');
    const stopBtn = document.getElementById('stop-btn');
    const statusText = document.getElementById('status-text');
    const statusDot = document.getElementById('status-dot');
    const progressBar = document.querySelector('.progress-bar-container');
    const logConsole = document.getElementById('log-console');
    const exportCard = document.getElementById('export-card');
    const exportBtns = document.querySelectorAll('.btn-export');

    let currentJobId = null;
    let pollInterval = null;

    function appendLog(msg, type = 'normal') {
        const p = document.createElement('p');
        p.className = `log-${type}`;
        p.textContent = msg;
        logConsole.appendChild(p);
        logConsole.scrollTop = logConsole.scrollHeight;
    }

    const liveDataCard = document.getElementById('live-data-card');
    const liveTableBody = document.getElementById('live-table-body');
    
    // Map variables
    let map = null;
    let markersLayer = null;

    function initMap() {
        if (!map) {
            map = L.map('leads-map').setView([20.5937, 78.9629], 4); // Default to India
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; OpenStreetMap contributors'
            }).addTo(map);
            markersLayer = L.layerGroup().addTo(map);
            
            // Fix map sizing issues when inside a hidden div
            setTimeout(() => { map.invalidateSize(); }, 500);
        }
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const query = document.getElementById('query').value;
        const area = document.getElementById('area').value;
        const pincode = document.getElementById('pincode').value;
        const radius = document.getElementById('radius').value;
        const max_results = document.getElementById('max_results').value;
        const max_threads = document.getElementById('max_threads') ? document.getElementById('max_threads').value : 2;
        const proxy = document.getElementById('proxy') ? document.getElementById('proxy').value : '';

        // Reset UI
        startBtn.disabled = true;
        stopBtn.disabled = false;
        exportCard.classList.add('disabled');
        logConsole.innerHTML = '';
        liveTableBody.innerHTML = '';
        liveDataCard.style.display = 'none';
        progressBar.classList.add('active');
        
        if (markersLayer) markersLayer.clearLayers();
        
        statusText.textContent = "Status: Queuing...";
        statusDot.className = 'pulse-dot running';

        try {
            const res = await fetch('/api/scrape', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, area, pincode, radius, max_results, max_threads, proxy })
            });
            const data = await res.json();
            
            if (res.ok) {
                currentJobId = data.job_id;
                appendLog(`✅ ${data.message}`, 'success');
                startPolling();
            } else {
                throw new Error(data.error || "Failed to start job");
            }
        } catch (err) {
            appendLog(`❌ Error: ${err.message}`, 'error');
            resetUI(false);
        }
    });

    stopBtn.addEventListener('click', async () => {
        if (!currentJobId) return;
        
        stopBtn.disabled = true;
        appendLog("🛑 Stop signal sent. Waiting for graceful exit...", 'error');
        statusText.textContent = "Status: Stopping...";
        
        await fetch(`/api/stop/${currentJobId}`, { method: 'POST' });
    });

    function startPolling() {
        if (pollInterval) clearInterval(pollInterval);
        
        pollInterval = setInterval(async () => {
            if (!currentJobId) return;
            
            try {
                const res = await fetch(`/api/status/${currentJobId}`);
                if (!res.ok) {
                    if (res.status === 404) {
                        throw new Error("Job not found (404). The server may have restarted due to memory limits.");
                    }
                    throw new Error("Status check failed");
                }
                
                const data = await res.json();
                
                // Print logs
                data.logs.forEach(log => {
                    let type = 'normal';
                    if (log.includes('❌')) type = 'error';
                    if (log.includes('✅') || log.includes('🎉')) type = 'success';
                    if (log.includes('🚀') || log.includes('🔍')) type = 'info';
                    appendLog(log, type);
                });

                // Update Live Data Table & Map
                if (data.new_data && data.new_data.length > 0) {
                    if (liveDataCard.style.display === 'none') {
                        liveDataCard.style.display = 'block';
                        initMap();
                    }
                    
                    data.new_data.forEach(item => {
                        // Add to Table
                        const tr = document.createElement('tr');
                        const emailDisp = item.Emails !== 'N/A' ? item.Emails : '-';
                        tr.innerHTML = `
                            <td>${item.Name}</td>
                            <td>${item.Area}</td>
                            <td>${item.Phone}</td>
                            <td class="${emailDisp !== '-' ? 'text-success' : 'text-muted'}">${emailDisp}</td>
                        `;
                        liveTableBody.appendChild(tr);
                        
                        // Add to Map
                        if (item.Latitude && item.Longitude && markersLayer) {
                            const lat = parseFloat(item.Latitude);
                            const lng = parseFloat(item.Longitude);
                            if (!isNaN(lat) && !isNaN(lng)) {
                                const marker = L.marker([lat, lng]).addTo(markersLayer);
                                marker.bindPopup(`
                                    <strong>${item.Name}</strong><br>
                                    📍 ${item.Area}<br>
                                    📞 ${item.Phone !== 'N/A' ? item.Phone : 'No phone'}<br>
                                    ✉️ ${emailDisp}
                                `);
                                
                                // Pan to the latest marker smoothly
                                map.flyTo([lat, lng], 12, { animate: true, duration: 1.5 });
                            }
                        }
                    });
                }

                if (data.status === 'running') {
                    statusText.textContent = "Status: Scraping...";
                }

                if (data.status === 'completed' || data.status === 'error') {
                    clearInterval(pollInterval);
                    pollInterval = null;
                    progressBar.classList.remove('active');
                    
                    if (data.status === 'completed') {
                        statusText.textContent = `Status: Completed (${data.results_count} items)`;
                        statusDot.className = 'pulse-dot completed';
                        if (data.results_count > 0) {
                            exportCard.classList.remove('disabled');
                        }
                    } else {
                        statusText.textContent = "Status: Error";
                        statusDot.className = 'pulse-dot error';
                    }
                    
                    resetUI(false);
                }
            } catch (err) {
                console.error("Polling error:", err);
                clearInterval(pollInterval);
                pollInterval = null;
                progressBar.classList.remove('active');
                statusText.textContent = "Status: Server Error";
                statusDot.className = 'pulse-dot error';
                appendLog(`❌ Polling error: ${err.message}`, 'error');
                resetUI(false);
            }
        }, 3000); // poll every 3 seconds
    }

    function resetUI(clearData = true) {
        startBtn.disabled = false;
        stopBtn.disabled = true;
        if (clearData) {
            progressBar.classList.remove('active');
            statusDot.className = 'pulse-dot';
            statusText.textContent = "Status: Ready";
        }
    }

    exportBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            if (!currentJobId) return;
            const format = btn.getAttribute('data-format');
            
            // Get selected fields
            const checkboxes = document.querySelectorAll('#field-checkboxes input[type="checkbox"]:checked');
            const selectedFields = Array.from(checkboxes).map(cb => cb.value);
            
            if (selectedFields.length === 0) {
                alert('Please select at least one field to export!');
                return;
            }
            
            const fieldsParam = encodeURIComponent(selectedFields.join(','));
            window.location.href = `/api/download/${currentJobId}/${format}?fields=${fieldsParam}`;
        });
    });
});
