document.addEventListener('DOMContentLoaded', () => {
    // --- State Management ---
    const state = {
        isAdvanced: false,
        activeDownloads: new Map(), // id -> { intervalId, element }
        currentVideoData: null,
        videoInfo: null
    };

    // --- Elements ---
        const els = {
            urlInput: document.getElementById('urlInput'),
            fetchBtn: document.getElementById('fetchBtn'),
            modeToggle: document.getElementById('modeToggle'), // Re-added
            videoInfoSection: document.getElementById('videoInfoSection'),
            thumbnailImg: document.getElementById('thumbnailImg'),
            videoTitle: document.getElementById('videoTitle'),
            videoChannel: document.getElementById('videoChannel'),
            videoDuration: document.getElementById('videoDuration'),
            simpleOptions: document.getElementById('simpleOptions'),
            advancedOptions: document.getElementById('advancedOptions'),
            formatBtns: document.querySelectorAll('.format-btn'),
            qualitySelect: document.getElementById('simpleQualitySelect'),
            downloadBtn: document.getElementById('downloadBtn'),
            downloadsSection: document.getElementById('downloadsSection'),
            downloadsList: document.getElementById('downloadsList'),
            audioFormatGroup: document.getElementById('audioFormatGroup'),
            audioFormatSelect: document.getElementById('audioFormatSelect'),
            formatsTableBody: document.getElementById('formatsTableBody')
        };
    
            // --- Initialization ---
            // Auto-focus URL input on load
            els.urlInput.focus();
            
            // Check for app updates
            checkAppUpdates();
            
            // --- Event Listeners ---
            // ...
        
            async function checkAppUpdates() {
                try {
                    const response = await fetch('/api/app_update_status');
                    const data = await response.json();
                    
                    if (data.update_available) {
                        const bar = document.getElementById('updateBar');
                        const badge = document.getElementById('newVersionBadge');
                        const btn = document.getElementById('triggerUpdateBtn');
                        
                        badge.textContent = `v${data.latest_version}`;
                        bar.classList.remove('hidden');
                        
                        btn.onclick = async () => {
                            if (!confirm('The application will restart to apply updates. Continue?')) return;
                            
                            btn.disabled = true;
                            btn.textContent = "Updating...";
                            
                            try {
                                const res = await fetch('/api/apply_app_update', { method: 'POST' });
                                if (res.ok) {
                                    showToast('Update started. App will restart shortly...', 'success');
                                } else {
                                    throw new Error('Update failed to start');
                                }
                            } catch (e) {
                                showToast('Update error: ' + e.message, 'error');
                                btn.disabled = false;
                                btn.textContent = "Update Now";
                            }
                        };
                    }
                } catch (e) {
                    console.error("Update check failed:", e);
                }
            }        els.fetchBtn.addEventListener('click', fetchVideoInfo);
        
        els.urlInput.addEventListener('keyup', (e) => {
            if (e.key === 'Enter') {
                fetchVideoInfo();
            }
        });
    
        els.modeToggle.addEventListener('change', (e) => { // Re-added listener
            state.isAdvanced = e.target.checked;
            updateViewMode();
        });
    
        els.formatBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                // Toggle active class
                els.formatBtns.forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                
                const type = e.target.dataset.type;
                if (type === 'audio') {
                    els.qualitySelect.closest('.option-group').classList.add('hidden');
                    els.audioFormatGroup.classList.remove('hidden');
                } else {
                    els.qualitySelect.closest('.option-group').classList.remove('hidden');
                    els.audioFormatGroup.classList.add('hidden');
                }
            });
        });
    
        els.downloadBtn.addEventListener('click', startSimpleDownload);
    
        // --- Core Functions ---
    
        function updateViewMode() { // Logic restored
            if (!state.videoInfo) return; // Nothing to show yet
    
            if (state.isAdvanced) {
                els.simpleOptions.classList.add('hidden');
                els.advancedOptions.classList.remove('hidden');
                populateAdvancedTable(state.videoInfo.formats || []); 
            } else {
                els.simpleOptions.classList.remove('hidden');
                els.advancedOptions.classList.add('hidden');
                // Re-populate simple dropdown just in case
                populateSimpleDropdown(state.videoInfo.resolutions);
            }
        }

    async function fetchVideoInfo() {
        const url = els.urlInput.value.trim();
        if (!url) {
            showToast('Please enter a YouTube URL', 'error');
            return;
        }

        els.fetchBtn.disabled = true;
        els.fetchBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Analyzing...';
        
        try {
            // Send POST request to match backend endpoint
            const response = await fetch('/api/video_info', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ url: url })
            });

            if (!response.ok) throw new Error('Failed to fetch info');
            
            const data = await response.json();
            state.videoInfo = data; // Store globally
            
            // Update UI
            els.thumbnailImg.src = data.thumbnail;
            els.videoTitle.textContent = data.title;
            els.videoChannel.textContent = data.uploader;
            els.videoDuration.textContent = formatDuration(data.duration);
            
            // Populate Simple Mode
            populateSimpleDropdown(data.resolutions);
            
            // Show Section immediately
            els.videoInfoSection.style.display = 'block';
            els.videoInfoSection.classList.remove('hidden'); // Ensure hidden class is gone
            
            // Apply animations/layout changes
            setTimeout(() => {
                els.videoInfoSection.classList.add('visible');
                const logo = document.querySelector('.centered-logo');
                if (logo) logo.classList.add('shrink');
            }, 10);
            
            try {
                updateViewMode(); 
            } catch (viewErr) {
                console.error("Error updating view mode:", viewErr);
            }

        } catch (error) {
            showToast(error.message || 'Error analyzing video', 'error');
            console.error(error);
        } finally {
            els.fetchBtn.disabled = false;
            els.fetchBtn.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i> Analyze';
        }
    }

    function populateSimpleDropdown(resolutions) {
        els.qualitySelect.innerHTML = '';
        if (!resolutions || resolutions.length === 0) {
            const opt = document.createElement('option');
            opt.text = "Best Available";
            opt.value = "best";
            els.qualitySelect.add(opt);
            return;
        }

        resolutions.forEach((res, index) => {
            const opt = document.createElement('option');
            opt.value = res.value; // The actual height (e.g., 816)
            opt.text = res.label;  // The display label (e.g., "1080p")
            
            // Default to the highest quality (first item)
            if (index === 0) opt.selected = true;
            els.qualitySelect.add(opt);
        });
    }
    
    // In a real implementation, we'd need the raw formats list from the backend
    // Since the current /api/video_info only returns resolutions, we'll simulate the "Advanced" view
    // by just listing resolutions for now, but enabling the logic for when the API is updated.
    function populateAdvancedTable(formats) {
        els.formatsTableBody.innerHTML = '';
        
        // If the backend doesn't send raw formats yet, show a placeholder message
        if (!formats || formats.length === 0) {
            // Fallback using the simple resolutions
             if (state.videoInfo.resolutions) {
                state.videoInfo.resolutions.forEach(res => {
                    const row = els.formatsTableBody.insertRow();
                    row.innerHTML = `
                        <td>mp4</td>
                        <td>${res.label} (${res.value}p)</td>
                        <td>avc1/h.264</td>
                        <td>~</td>
                        <td><button class="btn-sm primary-btn" onclick="triggerAdvancedDownload('${res.value}', 'video')">Download</button></td>
                    `;
                });
                // Add Audio option
                 const row = els.formatsTableBody.insertRow();
                 row.innerHTML = `
                    <td>m4a</td>
                    <td>Audio Only</td>
                    <td>aac</td>
                    <td>~</td>
                    <td><button class="btn-sm primary-btn" onclick="triggerAdvancedDownload(null, 'audio')">Download</button></td>
                `;
             }
             return;
        }
        
        // Real implementation would iterate over `formats`
    }

    async function startSimpleDownload() {
        const url = els.urlInput.value;
        const type = document.querySelector('.format-btn.active').dataset.type;
        
        const payload = {
            url: url,
            type: type
        };

        if (type === 'video') {
            payload.resolution = parseInt(els.qualitySelect.value) || 0; // 0 = best
        } else {
            payload.format = els.audioFormatSelect.value;
        }

        initiateDownload(payload);
    }
    
    // Exposed global for the onclick handlers in table
    window.triggerAdvancedDownload = (res, type) => {
        const payload = {
            url: els.urlInput.value,
            type: type
        };
        if (type === 'video') payload.resolution = parseInt(res);
        else payload.format = 'm4a'; // Default for advanced audio click
        
        initiateDownload(payload);
    };

    async function initiateDownload(payload) {
        try {
            showToast('Starting download...', 'success');
            
            // Match backend 'DownloadRequest' model
            const requestBody = {
                url: payload.url,
                title: state.videoInfo ? state.videoInfo.title : "Unknown Video",
                type: payload.type,
                resolution: payload.resolution,
                format: payload.format
            };

            const response = await fetch('/api/prepare_download', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(requestBody)
            });

            if (!response.ok) {
                const errData = await response.json();
                let msg = errData.detail || 'Download failed to start';
                if (typeof msg === 'object') {
                    msg = JSON.stringify(msg);
                }
                throw new Error(msg);
            }
            
            const data = await response.json();
            const downloadId = data.download_id; 
            
            // Create UI Card
            createDownloadCard(downloadId, state.videoInfo ? state.videoInfo.title : "Downloading...");
            
            // Start Polling
            startPolling(downloadId);

        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    function createDownloadCard(id, title) {
        els.downloadsSection.classList.remove('hidden');
        
        const card = document.createElement('div');
        card.className = 'download-card glass-panel';
        card.id = `card-${id}`;
        card.innerHTML = `
            <div class="download-info">
                <div class="download-header">
                    <span class="download-title" title="${title}">${title}</span>
                    <span class="download-stats" id="stats-${id}">0%</span>
                </div>
                <div class="progress-bar-container">
                    <div class="progress-bar" id="bar-${id}"></div>
                </div>
            </div>
        `;
        
        els.downloadsList.prepend(card);
    }

    function startPolling(id) {
        const interval = setInterval(async () => {
            try {
                const response = await fetch(`/api/download_status/${id}`);
                
                if (!response.ok) return;

                const data = await response.json();
                
                updateDownloadCard(id, data);
                
                if (data.status === 'ready' || data.status === 'error' || data.status === 'expired') {
                    clearInterval(interval);
                    state.activeDownloads.delete(id);
                    if (data.status === 'ready') handleDownloadComplete(id);
                }
                
            } catch (err) {
                console.error("Polling error", err);
            }
        }, 1000);
        
        state.activeDownloads.set(id, interval);
    }

    function updateDownloadCard(id, data) {
        const bar = document.getElementById(`bar-${id}`);
        const stats = document.getElementById(`stats-${id}`);
        if (!bar || !stats) return;
        
        if (data.status === 'error') {
            stats.textContent = 'Error';
            stats.style.color = '#ff4444';
            return;
        }
        
        if (data.status === 'processing' || data.status === 'downloading') {
            bar.style.width = `${data.progress}%`;
            
            let statsText = `${Math.round(data.progress)}%`;
            if (data.download_speed) statsText += ` • ${data.download_speed}`;
            if (data.estimated_time_remaining) statsText += ` • ${formatDuration(data.estimated_time_remaining)} left`;
            
            stats.textContent = statsText;
        } else if (data.status === 'ready') {
            bar.style.width = '100%';
            stats.textContent = 'Complete';
        }
    }

    // ... inside handleDownloadComplete ...
    async function handleDownloadComplete(id) {
        showToast('Download complete!', 'success');
        // Trigger file download using correct endpoint
        window.location.href = `/api/download/${id}`;
        
        // Remove card after delay
        setTimeout(() => {
            const card = document.getElementById(`card-${id}`);
            if (card) card.remove();
            if (els.downloadsList.children.length === 0) {
                els.downloadsSection.classList.add('hidden');
            }
        }, 5000);
    }

    // --- Utilities ---

    function formatDuration(seconds) {
        if (!seconds) return '00:00';
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    }

    function showToast(message, type = 'success') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <span>${message}</span>
            <i class="fa-solid fa-xmark" style="cursor:pointer" onclick="this.parentElement.remove()"></i>
        `;
        
        document.getElementById('toastContainer').appendChild(toast);
        
        // Auto remove
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }

    async function checkAppVersion() {
        try {
            const response = await fetch('/api/version');
            if (!response.ok) throw new Error('Failed to fetch versions');
            
            const data = await response.json();
            document.getElementById('appVersion').textContent = data.app_version;
            document.getElementById('ytdlpVersion').textContent = `yt-dlp ${data.ytdlp_version}`;
        } catch (e) { 
            console.error('Error fetching versions:', e);
            document.getElementById('appVersion').textContent = 'Error';
            document.getElementById('ytdlpVersion').textContent = 'Error';
        }
    }
});