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
    const resetBtn = document.getElementById('reset-btn');
    const statusText = document.getElementById('status-text');
    const statusDot = document.getElementById('status-dot');
    const progressBar = document.querySelector('.progress-bar-container');
    const logConsole = document.getElementById('log-console');
    const exportCard = document.getElementById('export-card');
    const exportCountBadge = document.getElementById('export-count-badge');
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

    function addTableRowAndMarker(item) {
        if (!item || !item.Name) return;
        
        // Add to Table
        const tr = document.createElement('tr');
        const emailDisp = (item.Emails && item.Emails !== 'N/A') ? item.Emails : '-';
        tr.innerHTML = `
            <td><strong>${item.Name}</strong></td>
            <td>${item.Area || '-'}</td>
            <td>${item.Phone || 'N/A'}</td>
            <td class="${emailDisp !== '-' ? 'text-success' : 'text-muted'}">${emailDisp}</td>
        `;
        liveTableBody.appendChild(tr);
        
        // Add to Map
        if (item.Latitude && item.Longitude && markersLayer && map) {
            const lat = parseFloat(item.Latitude);
            const lng = parseFloat(item.Longitude);
            if (!isNaN(lat) && !isNaN(lng)) {
                const marker = L.marker([lat, lng]).addTo(markersLayer);
                marker.bindPopup(`
                    <strong>${item.Name}</strong><br>
                    📍 ${item.Area || ''}<br>
                    📞 ${item.Phone && item.Phone !== 'N/A' ? item.Phone : 'No phone'}<br>
                    ✉️ ${emailDisp}
                `);
                map.flyTo([lat, lng], 12, { animate: true, duration: 1.5 });
            }
        }
    }

    function updateExportAvailability(count) {
        if (count > 0) {
            exportCard.classList.remove('disabled');
            if (exportCountBadge) {
                exportCountBadge.textContent = `${count} leads ready`;
            }
        }
    }

    // Clear legacy shared localStorage & clean any query params from address bar
    try { localStorage.removeItem('gmaps_current_job_id'); } catch (e) {}
    if (window.location.search) {
        window.history.replaceState({}, '', window.location.pathname);
    }

    // --- PER-TAB ISOLATED SESSION RESTORATION ---
    // Uses sessionStorage internally so each browser tab is 100% independent.
    // The browser address bar stays clean at http://localhost:7860/
    async function restoreSession() {
        let tabJobId = sessionStorage.getItem('tab_job_id');

        // If this is a fresh tab without a job, stay clean and ready for a new search
        if (!tabJobId) return;

        try {
            const res = await fetch(`/api/status/${tabJobId}?full=1`);
            if (!res.ok) {
                // Job expired or deleted, clear tab state
                sessionStorage.removeItem('tab_job_id');
                return;
            }
            const data = await res.json();
            
            if (data && (data.results_count > 0 || data.status === 'running' || data.status === 'queued')) {
                currentJobId = tabJobId;
                sessionStorage.setItem('tab_job_id', tabJobId);
                
                if (resetBtn) resetBtn.style.display = 'block';
                
                // Restore log console
                if (data.logs && data.logs.length > 0) {
                    logConsole.innerHTML = '';
                    data.logs.forEach(log => {
                        let type = 'normal';
                        if (log.includes('❌')) type = 'error';
                        if (log.includes('✅') || log.includes('🎉')) type = 'success';
                        if (log.includes('🚀') || log.includes('🔍')) type = 'info';
                        appendLog(log, type);
                    });
                }
                appendLog(`🔄 Tab session restored! ${data.results_count} previously extracted leads recovered safely.`, 'success');

                // Restore live table & map
                if (data.new_data && data.new_data.length > 0) {
                    liveDataCard.style.display = 'block';
                    initMap();
                    liveTableBody.innerHTML = '';
                    data.new_data.forEach(item => addTableRowAndMarker(item));
                }

                // Unlock export immediately
                updateExportAvailability(data.results_count);

                // Handle status
                if (data.status === 'running' || data.status === 'queued') {
                    startBtn.disabled = true;
                    stopBtn.disabled = false;
                    progressBar.classList.add('active');
                    statusText.textContent = `Status: Scraping... (${data.results_count} collected)`;
                    statusDot.className = 'pulse-dot running';
                    startPolling();
                } else if (data.status === 'stopped') {
                    statusText.textContent = `Status: Stopped & Saved (${data.results_count} leads ready)`;
                    statusDot.className = 'pulse-dot completed';
                    resetUI(false);
                } else if (data.status === 'completed') {
                    statusText.textContent = `Status: Completed (${data.results_count} leads ready)`;
                    statusDot.className = 'pulse-dot completed';
                    resetUI(false);
                } else {
                    statusText.textContent = `Status: Ready (${data.results_count} leads ready)`;
                    statusDot.className = 'pulse-dot';
                    resetUI(false);
                }
            }
        } catch (err) {
            console.error("Error restoring tab session:", err);
        }
    }

    // Call restoreSession on page load
    restoreSession();

    // Start New Search / Clear This Tab's Session
    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            if (confirm("Clear this tab and start a new search? (Any unsaved file downloads can still be exported now)")) {
                sessionStorage.removeItem('tab_job_id');
                currentJobId = null;
                if (pollInterval) clearInterval(pollInterval);
                pollInterval = null;
                liveTableBody.innerHTML = '';
                liveDataCard.style.display = 'none';
                logConsole.innerHTML = '<p class="log-info">Waiting to start...</p>';
                exportCard.classList.add('disabled');
                if (exportCountBadge) exportCountBadge.textContent = '0 leads ready';
                resetBtn.style.display = 'none';
                resetUI(true);
            }
        });
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const query = document.getElementById('query').value;
        const area = document.getElementById('area').value;
        const pincode = document.getElementById('pincode').value;
        const radius = document.getElementById('radius').value;
        const phone_filter = document.getElementById('phone_filter') ? document.getElementById('phone_filter').value : 'all';
        const max_results = document.getElementById('max_results').value;
        const max_threads = document.getElementById('max_threads') ? document.getElementById('max_threads').value : 2;
        const proxy = document.getElementById('proxy') ? document.getElementById('proxy').value : '';

        // Reset UI
        startBtn.disabled = true;
        stopBtn.disabled = false;
        if (resetBtn) resetBtn.style.display = 'block';
        exportCard.classList.add('disabled');
        if (exportCountBadge) exportCountBadge.textContent = '0 leads ready';
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
                body: JSON.stringify({ query, area, pincode, radius, phone_filter, max_results, max_threads, proxy })
            });
            const data = await res.json();
            
            if (res.ok) {
                currentJobId = data.job_id;
                // Save to this tab's isolated storage only (URL stays clean)
                sessionStorage.setItem('tab_job_id', currentJobId);
                
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
        appendLog("🛑 Stop signal sent. Saving all extracted data to disk...", 'error');
        statusText.textContent = "Status: Stopping & Saving...";
        
        await fetch(`/api/stop/${currentJobId}`, { method: 'POST' });
    });

    let pollCount = 0;
    let retryFailures = 0;

    function startPolling() {
        if (pollInterval) clearInterval(pollInterval);
        pollCount = 0;
        retryFailures = 0;
        
        pollInterval = setInterval(async () => {
            if (!currentJobId) return;
            pollCount++;
            
            // Safety cap: stop polling after 3 hours
            if (pollCount > 3600) {
                clearInterval(pollInterval);
                pollInterval = null;
                progressBar.classList.remove('active');
                statusText.textContent = "Status: Timeout";
                statusDot.className = 'pulse-dot error';
                appendLog("⚠️ Polling timeout reached. All collected leads are safely saved below.", 'error');
                resetUI(false);
                return;
            }
            
            try {
                const res = await fetch(`/api/status/${currentJobId}`);
                if (!res.ok) {
                    if (res.status === 404) {
                        clearInterval(pollInterval);
                        pollInterval = null;
                        progressBar.classList.remove('active');
                        statusText.textContent = "Status: Job Expired";
                        statusDot.className = 'pulse-dot error';
                        appendLog("❌ Job not found on server.", 'error');
                        resetUI(false);
                        return;
                    }
                    throw new Error(`Status check failed (${res.status})`);
                }
                
                const data = await res.json();
                retryFailures = 0; // Reset retry counter on success
                
                // Print logs
                if (data.logs && data.logs.length > 0) {
                    data.logs.forEach(log => {
                        let type = 'normal';
                        if (log.includes('❌')) type = 'error';
                        if (log.includes('✅') || log.includes('🎉')) type = 'success';
                        if (log.includes('🚀') || log.includes('🔍')) type = 'info';
                        appendLog(log, type);
                    });
                }

                // Update Live Data Table & Map
                if (data.new_data && data.new_data.length > 0) {
                    if (liveDataCard.style.display === 'none') {
                        liveDataCard.style.display = 'block';
                        initMap();
                    }
                    
                    data.new_data.forEach(item => addTableRowAndMarker(item));
                }

                // UNLOCK DOWNLOAD IMMEDIATELY: As soon as 1+ leads are scraped, user can download!
                if (data.results_count > 0) {
                    updateExportAvailability(data.results_count);
                }

                if (data.status === 'running') {
                    statusText.textContent = `Status: Scraping... (${data.results_count} collected)`;
                }

                if (data.status === 'completed' || data.status === 'stopped' || data.status === 'error' || data.status === 'interrupted' || data.status === 'not_found') {
                    clearInterval(pollInterval);
                    pollInterval = null;
                    progressBar.classList.remove('active');
                    
                    if (data.status === 'completed') {
                        statusText.textContent = `Status: Completed (${data.results_count} items)`;
                        statusDot.className = 'pulse-dot completed';
                        appendLog(`🎉 Scraping finished! All ${data.results_count} items ready to download.`, 'success');
                    } else if (data.status === 'stopped') {
                        statusText.textContent = `Status: Stopped & Saved (${data.results_count} items)`;
                        statusDot.className = 'pulse-dot completed';
                        appendLog(`💾 Safe Stop: ${data.results_count} items collected so far are fully saved. You can download them below!`, 'success');
                    } else if (data.status === 'interrupted') {
                        statusText.textContent = `Status: Interrupted (${data.results_count} items saved)`;
                        statusDot.className = 'pulse-dot error';
                    } else {
                        statusText.textContent = "Status: Error";
                        statusDot.className = 'pulse-dot error';
                    }
                    
                    updateExportAvailability(data.results_count);
                    resetUI(false);
                }
            } catch (err) {
                console.error("Polling error:", err);
                retryFailures++;
                if (retryFailures <= 5) {
                    appendLog(`⚠️ Network lag, retrying connection (${retryFailures}/5)...`, 'normal');
                    return;
                }
                clearInterval(pollInterval);
                pollInterval = null;
                progressBar.classList.remove('active');
                statusText.textContent = "Status: Network Lag";
                statusDot.className = 'pulse-dot error';
                appendLog(`❌ Connection notice: ${err.message}. Any data collected is saved on disk.`, 'error');
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
            const phoneFilterVal = document.getElementById('phone_filter') ? encodeURIComponent(document.getElementById('phone_filter').value) : 'all';
            window.location.href = `/api/download/${currentJobId}/${format}?fields=${fieldsParam}&phone_filter=${phoneFilterVal}`;
        });
    });
});
