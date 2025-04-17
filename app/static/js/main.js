document.addEventListener('DOMContentLoaded', function() {
    let fileInput = document.getElementById('file-input');
    let fileTray = document.getElementById('file-tray');
    let fileList = document.getElementById('file-list');
    let trayPlaceholder = document.getElementById('tray-placeholder');
    let uploadSubmitBtn = document.getElementById('upload-submit');
    let originSelect = document.getElementById('origin');
    let destinationSelect = document.getElementById('destination');
    let vehicleTypeSelect = document.getElementById('vehicle-type');
    let applyButton = document.getElementById('apply-filters');
    let analysisContainer = document.getElementById('analysis-container');
    let transporterOriginSelect = document.getElementById('transporter-origin');
    let transporterDestinationSelect = document.getElementById('transporter-destination');
    let applyTransporterFiltersBtn = document.getElementById('apply-transporter-filters');
    
    // Tab switching functionality
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            // Remove active class from all buttons and contents
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));
            
            // Add active class to clicked button and corresponding content
            button.classList.add('active');
            const tabId = button.getAttribute('data-tab');
            document.getElementById(tabId).classList.add('active');
        });
    });
    
    let selectedFiles = [];
    let currentAnalysisResults = null;

    // Utility functions for formatting
    function formatCurrency(amount) {
        if (isNaN(amount) || amount === null || amount === undefined) {
            return '₹0.00';
        }
        return '₹' + Math.abs(amount).toLocaleString('en-IN', {
            maximumFractionDigits: 2,
            minimumFractionDigits: 2
        });
    }
    
    function formatPercentage(percent) {
        if (isNaN(percent) || percent === null || percent === undefined) {
            return '0.00%';
        }
        return Math.abs(percent).toFixed(2) + '%';
    }

    // File tray click to select files
    fileTray.addEventListener('click', function(e) {
        // Prevent click from triggering if we're clicking a remove button
        if (e.target.classList.contains('remove-file') || 
            e.target.parentElement.classList.contains('remove-file')) {
            return;
        }
        fileInput.click();
    });

    // Drag and drop functionality
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        fileTray.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        fileTray.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        fileTray.addEventListener(eventName, unhighlight, false);
    });

    function highlight() {
        fileTray.classList.add('dragover');
    }

    function unhighlight() {
        fileTray.classList.remove('dragover');
    }

    fileTray.addEventListener('drop', handleDrop, false);

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles(files);
    }

    // File input change handling
    fileInput.addEventListener('change', function(e) {
        handleFiles(this.files);
    });

    function handleFiles(files) {
        if (files.length === 0) return;
        
        // Reset previously selected files (only allow one file at a time for analysis)
        selectedFiles = [];
        
        // Add the first CSV file to the selected files array
        const csvFiles = Array.from(files).filter(file => file.type === 'text/csv' || file.name.endsWith('.csv'));
        
        if (csvFiles.length > 0) {
            selectedFiles = [csvFiles[0]];
        } else {
            alert('Please select a CSV file.');
        }
        
        updateFileList();
    }

    function updateFileList() {
        // Clear the file list
        fileList.innerHTML = '';
        
        // Update placeholder visibility
        if (selectedFiles.length > 0) {
            trayPlaceholder.classList.add('hidden');
        } else {
            trayPlaceholder.classList.remove('hidden');
        }
        
        // Add each file to the list
        selectedFiles.forEach((file, index) => {
            const fileElement = document.createElement('div');
            fileElement.className = 'selected-file';
            
            // File name
            const nameSpan = document.createElement('span');
            nameSpan.textContent = file.name;
            fileElement.appendChild(nameSpan);
            
            // Remove button
            const removeBtn = document.createElement('span');
            removeBtn.className = 'remove-file';
            removeBtn.innerHTML = '&times;';
            removeBtn.setAttribute('data-index', index);
            removeBtn.addEventListener('click', function(e) {
                e.stopPropagation(); // Prevent the tray click
                const idx = parseInt(this.getAttribute('data-index'));
                selectedFiles.splice(idx, 1);
                updateFileList();
                
                // Hide analysis container if file is removed
                analysisContainer.style.display = 'none';
            });
            
            fileElement.appendChild(removeBtn);
            fileList.appendChild(fileElement);
        });
    }

    // Set button loading state
    function setButtonLoading(button, isLoading, text = '') {
        if (isLoading) {
            button.disabled = true;
            // Store original text if not provided
            if (!text) {
                button.setAttribute('data-original-text', button.textContent);
            }
            button.innerHTML = '<span class="spinner"></span>' + (text || 'Loading...');
        } else {
            button.disabled = false;
            // Restore original text or use provided text
            button.textContent = text || button.getAttribute('data-original-text');
        }
    }

    // Submit button handling
    uploadSubmitBtn.addEventListener('click', function() {
        if (selectedFiles.length === 0) {
            alert('Please select a CSV file to upload first.');
            return;
        }
        
        // Show loading state
        setButtonLoading(this, true, 'Analyzing...');
        
        // Hide previous analysis results
        analysisContainer.style.display = 'block';
        
        // Reset analysis content areas to show loading spinner
        document.getElementById('total-savings-content').innerHTML = `
            <div class="loading-spinner-container">
                <div class="spinner"></div>
                <p>Analyzing data...</p>
            </div>
        `;
        
        document.getElementById('top-lanes-content').innerHTML = `
            <div class="loading-spinner-container">
                <div class="spinner"></div>
                <p>Analyzing data...</p>
            </div>
        `;
        
        document.getElementById('detailed-insights-content').innerHTML = `
            <div class="loading-spinner-container">
                <div class="spinner"></div>
                <p>Analyzing data...</p>
            </div>
        `;
        
        // Create a FormData object to send the file
        const formData = new FormData();
        formData.append('file', selectedFiles[0]);
        
        // Send the file to the server for analysis
        fetch('/analyze_rates', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Server returned an error response');
            }
            return response.json();
        })
        .then(data => {
            // Reset button state
            setButtonLoading(uploadSubmitBtn, false, 'Submit');
            
            // Store the analysis results
            currentAnalysisResults = data.results;
            
            // Display the analysis results
            displayAnalysisResults(data.results);
            
            // Populate origin dropdown with uploaded data
            populateOriginDropdown(data.origins);
            
            // Scroll to analysis section
            analysisContainer.scrollIntoView({ behavior: 'smooth' });
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred while analyzing the file. Please try again.');
            
            // Reset button state
            setButtonLoading(uploadSubmitBtn, false, 'Submit');
            
            // Hide analysis container on error
            analysisContainer.style.display = 'none';
        });
    });
    
    // Function to display analysis results
    function displayAnalysisResults(results) {
        // Total Savings Analysis
        const totalSavingsContent = document.getElementById('total-savings-content');
        totalSavingsContent.innerHTML = `
            <div class="savings-overview">
                <div class="savings-metric">
                    <div class="metric-label">Your Average Rate</div>
                    <div class="metric-value">${formatCurrency(results.avg_uploaded_shipper)}</div>
                </div>
                <div class="savings-metric">
                    <div class="metric-label">Benchmark Average Rate</div>
                    <div class="metric-value">${formatCurrency(results.avg_benchmark_shipper)}</div>
                </div>
                <div class="savings-metric">
                    <div class="metric-label">Average Rate Difference</div>
                    <div class="metric-value ${results.savings_amount > 0 ? 'negative-value' : 'positive-value'}">
                        ${formatCurrency(Math.abs(results.savings_amount))}
                        ${results.savings_amount > 0 ? 'Higher' : 'Lower'}
                    </div>
                </div>
                <div class="savings-metric">
                    <div class="metric-label">Percentage Difference</div>
                    <div class="metric-value ${results.savings_percent > 0 ? 'negative-value' : 'positive-value'}">
                        ${formatPercentage(Math.abs(results.savings_percent))}
                        ${results.savings_percent > 0 ? 'Higher' : 'Lower'}
                    </div>
                </div>
            </div>
        `;
        
        // Top 5 Lanes Analysis
        const topLanesContent = document.getElementById('top-lanes-content');
        topLanesContent.innerHTML = `
            <table class="top-lanes-table">
                <thead>
                    <tr>
                        <th>Lane</th>
                        <th>Vehicle Type</th>
                        <th>Your Average Rate<br/><span style="font-weight: normal; font-size: 0.8em;">(# of rates)</span></th>
                        <th>Benchmark Average Rate<br/><span style="font-weight: normal; font-size: 0.8em;">(# of rates)</span></th>
                        <th>Difference</th>
                    </tr>
                </thead>
                <tbody>
                    ${results.lane_differences.map(lane => `
                        <tr>
                            <td>${lane.origin} → ${lane.destination}</td>
                            <td>${lane.vehicle_type}</td>
                            <td>
                                ${formatCurrency(lane.uploaded_rate)}
                                <br/>
                                <span style="font-size: 0.8em; color: #666;">(${lane.uploaded_count} rates)</span>
                            </td>
                            <td>
                                ${formatCurrency(lane.benchmark_rate)}
                                <br/>
                                <span style="font-size: 0.8em; color: #666;">(${lane.benchmark_count} rates)</span>
                            </td>
                            <td class="${lane.difference > 0 ? 'negative-value' : 'positive-value'}">
                                ${formatCurrency(Math.abs(lane.difference))}
                                ${lane.difference > 0 ? 'Higher' : 'Lower'}
                                <div class="difference-bar" style="width: ${Math.min(Math.abs(lane.difference_percent || 0), 100)}%"></div>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
            <p style="text-align: center; margin-top: 1rem; font-size: 0.9rem; color: #666;">
                Showing top 5 lanes with highest average rate differences (${results.total_matches} total matching lanes analyzed)
            </p>
        `;
        
        // Display detailed insights
        const detailedInsightsContent = document.getElementById('detailed-insights-content');
        
        if (results.insights.length === 0) {
            detailedInsightsContent.innerHTML = `
                <p style="text-align: center; color: #666;">No insights generated from the analysis.</p>
            `;
        } else {
            let insightsHtml = '<div class="insights-container">';
            
            results.insights.forEach(insight => {
                insightsHtml += `
                    <div class="insight-item ${insight.type}">
                        ${insight.message}
                    </div>
                `;
            });
            
            insightsHtml += '</div>';
            detailedInsightsContent.innerHTML = insightsHtml;
        }
    }

    // Show loading spinner on select elements
    function showLoading(element) {
        element.parentElement.classList.add('loading');
        element.setAttribute('disabled', 'disabled');
    }

    // Hide loading spinner on select elements
    function hideLoading(element) {
        element.parentElement.classList.remove('loading');
        element.removeAttribute('disabled');
    }

    // Remove all existing event listeners for dropdowns
    originSelect.replaceWith(originSelect.cloneNode(true));
    destinationSelect.replaceWith(destinationSelect.cloneNode(true));
    vehicleTypeSelect.replaceWith(vehicleTypeSelect.cloneNode(true));

    // Re-get the elements after replacing
    originSelect = document.getElementById('origin');
    destinationSelect = document.getElementById('destination');
    vehicleTypeSelect = document.getElementById('vehicle-type');

    // Add the only event listeners we need
    originSelect.addEventListener('change', function() {
        const origin = this.value;
        if (!origin) {
            destinationSelect.innerHTML = '<option value="">Select Destination</option>';
            destinationSelect.disabled = true;
            vehicleTypeSelect.innerHTML = '<option value="">Select Vehicle Type</option>';
            vehicleTypeSelect.disabled = true;
            return;
        }
        
        // Show loading state
        showLoading(destinationSelect);
        
        // Fetch destinations from Google Sheets data with encoded origin
        fetch(`/get_destinations/${encodeURIComponent(origin)}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(destinations => {
                destinationSelect.innerHTML = '<option value="">Select Destination</option>';
                destinations.forEach(dest => {
                    const option = document.createElement('option');
                    option.value = dest;
                    option.textContent = dest;
                    destinationSelect.appendChild(option);
                });
                hideLoading(destinationSelect);
                destinationSelect.disabled = false;
                
                // Reset vehicle type dropdown
                vehicleTypeSelect.innerHTML = '<option value="">Select Vehicle Type</option>';
                vehicleTypeSelect.disabled = true;
            })
            .catch(error => {
                console.error('Error fetching destinations:', error);
                hideLoading(destinationSelect);
                alert('Error loading destinations. Please try again.');
            });
    });

    destinationSelect.addEventListener('change', function() {
        const origin = originSelect.value;
        const destination = this.value;
        
        if (!origin || !destination) {
            vehicleTypeSelect.innerHTML = '<option value="">Select Vehicle Type</option>';
            vehicleTypeSelect.disabled = true;
            return;
        }
        
        // Show loading state
        showLoading(vehicleTypeSelect);
        
        // Fetch vehicle types from Google Sheets data with encoded parameters
        fetch(`/get_vehicle_types/${encodeURIComponent(origin)}/${encodeURIComponent(destination)}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(vehicleTypes => {
                vehicleTypeSelect.innerHTML = '<option value="">Select Vehicle Type</option><option value="ALL">Select All</option>';
                vehicleTypes.forEach(type => {
                    const option = document.createElement('option');
                    option.value = type;
                    option.textContent = type;
                    vehicleTypeSelect.appendChild(option);
                });
                hideLoading(vehicleTypeSelect);
                vehicleTypeSelect.disabled = false;
            })
            .catch(error => {
                console.error('Error fetching vehicle types:', error);
                hideLoading(vehicleTypeSelect);
                alert('Error loading vehicle types. Please try again.');
            });
    });

    // Apply filters
    applyButton.addEventListener('click', function() {
        const origin = originSelect.value;
        const destination = destinationSelect.value;
        const vehicleType = vehicleTypeSelect.value;
        const duration = document.getElementById('duration').value;
        
        if (!origin || !destination || !vehicleType) {
            alert('Please select all filter values');
            return;
        }
        
        // Show loading state
        setButtonLoading(this, true, 'Analyzing...');
        
        // Find the matching lanes in the current analysis results
        let filteredLanes = [];
        if (vehicleType === 'ALL') {
            // If "Select All" is chosen, get all lanes for the origin-destination pair
            filteredLanes = currentAnalysisResults.all_lane_differences.filter(lane => 
                lane.origin === origin && 
                lane.destination === destination
            );
        } else {
            // Find specific vehicle type
            const filteredLane = currentAnalysisResults.all_lane_differences.find(lane => 
            lane.origin === origin && 
            lane.destination === destination && 
            lane.vehicle_type === vehicleType
        );
            if (filteredLane) {
                filteredLanes = [filteredLane];
            }
        }
        
        if (filteredLanes.length > 0) {
            // Show the lane level analysis section
            const laneLevelAnalysis = document.getElementById('lane-level-analysis');
            laneLevelAnalysis.style.display = 'block';
            
            // Calculate aggregated metrics for all filtered lanes
            const aggregatedMetrics = filteredLanes.reduce((acc, lane) => {
                acc.totalUploadedRate += lane.uploaded_rate * lane.uploaded_count;
                acc.totalBenchmarkRate += lane.benchmark_rate * lane.benchmark_count;
                acc.totalUploadedCount += lane.uploaded_count;
                acc.totalBenchmarkCount += lane.benchmark_count;
                return acc;
            }, {
                totalUploadedRate: 0,
                totalBenchmarkRate: 0,
                totalUploadedCount: 0,
                totalBenchmarkCount: 0
            });
            
            // Calculate weighted averages
            const avgUploadedRate = aggregatedMetrics.totalUploadedRate / aggregatedMetrics.totalUploadedCount;
            const avgBenchmarkRate = aggregatedMetrics.totalBenchmarkRate / aggregatedMetrics.totalBenchmarkCount;
            const difference = avgUploadedRate - avgBenchmarkRate;
            const percentDiff = (difference / avgUploadedRate * 100);
            
            // Update metrics
            document.getElementById('your-rate').textContent = formatCurrency(avgUploadedRate);
            document.getElementById('your-rate-count').textContent = `(${aggregatedMetrics.totalUploadedCount} rates)`;
            document.getElementById('benchmark-rate').textContent = formatCurrency(avgBenchmarkRate);
            document.getElementById('benchmark-rate-count').textContent = `(${aggregatedMetrics.totalBenchmarkCount} rates)`;
            
            const rateValue = document.getElementById('rate-difference');
            rateValue.textContent = `${formatCurrency(Math.abs(difference))} ${difference > 0 ? 'Higher' : 'Lower'}`;
            rateValue.className = `metric-value ${difference > 0 ? 'higher' : 'lower'}`;
            
            const percentValue = document.getElementById('percentage-difference');
            percentValue.textContent = `${formatPercentage(Math.abs(percentDiff))} ${difference > 0 ? 'Higher' : 'Lower'}`;
            percentValue.className = `metric-value ${difference > 0 ? 'higher' : 'lower'}`;
            
            // Update table
            const tableBody = document.getElementById('lane-details-body');
            tableBody.innerHTML = filteredLanes.map(lane => `
                <tr>
                    <td>${lane.origin} → ${lane.destination}</td>
                    <td>${lane.vehicle_type}</td>
                    <td class="rate-cell">
                        ${formatCurrency(lane.uploaded_rate)}
                        <span class="rate-note">(${lane.uploaded_count} rates)</span>
                                        </td>
                    <td class="rate-cell">
                        ${formatCurrency(lane.benchmark_rate)}
                        <span class="rate-note">(${lane.benchmark_count} rates)</span>
                                        </td>
                    <td class="difference-cell ${lane.difference > 0 ? 'higher' : 'lower'}">
                        ${formatCurrency(Math.abs(lane.difference))} ${lane.difference > 0 ? 'Higher' : 'Lower'}
                                        </td>
                                    </tr>
            `).join('');
            
            // Scroll to the analysis section
            laneLevelAnalysis.scrollIntoView({ behavior: 'smooth' });
        } else {
            alert('No data found for the selected combination');
            document.getElementById('lane-level-analysis').style.display = 'none';
        }
        
        // Reset button state
        setButtonLoading(this, false, 'Apply Filters');
    });

    function populateOriginDropdown(origins) {
        // Populate both origin dropdowns
        [originSelect, transporterOriginSelect].forEach(select => {
            select.innerHTML = '<option value="">Select Origin</option>';
        origins.forEach(origin => {
            const option = document.createElement('option');
            option.value = origin;
            option.textContent = origin;
                select.appendChild(option);
            });
            select.disabled = false;
        });
        
        // Reset other dropdowns
        destinationSelect.innerHTML = '<option value="">Select Destination</option>';
        destinationSelect.disabled = true;
        vehicleTypeSelect.innerHTML = '<option value="">Select Vehicle Type</option>';
        vehicleTypeSelect.disabled = true;
        
        // Reset transporter destination dropdown
        transporterDestinationSelect.innerHTML = '<option value="">Select Destination</option>';
        transporterDestinationSelect.disabled = true;
    }

    // Transporter analysis functionality
    transporterOriginSelect.addEventListener('change', function() {
        const origin = this.value;
        if (!origin) {
            transporterDestinationSelect.innerHTML = '<option value="">Select Destination</option>';
            transporterDestinationSelect.disabled = true;
            return;
        }
        
        // Show loading state
        showLoading(transporterDestinationSelect);
        
        // Fetch destinations from Google Sheets data with encoded origin
        fetch(`/get_destinations/${encodeURIComponent(origin)}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(destinations => {
                transporterDestinationSelect.innerHTML = '<option value="">Select Destination</option>';
                destinations.forEach(dest => {
                    const option = document.createElement('option');
                    option.value = dest;
                    option.textContent = dest;
                    transporterDestinationSelect.appendChild(option);
                });
                hideLoading(transporterDestinationSelect);
                transporterDestinationSelect.disabled = false;
            })
            .catch(error => {
                console.error('Error fetching destinations:', error);
                hideLoading(transporterDestinationSelect);
                alert('Error loading destinations. Please try again.');
            });
    });

    applyTransporterFiltersBtn.addEventListener('click', function() {
        const origin = transporterOriginSelect.value;
        const destination = transporterDestinationSelect.value;
        
        if (!origin || !destination) {
            alert('Please select both origin and destination');
            return;
        }
        
        // Show loading state
        setButtonLoading(this, true, 'Analyzing...');
        
        // Show loading spinners in content areas
        document.getElementById('top-transporters-content').innerHTML = `
            <div class="loading-spinner-container">
                <div class="spinner"></div>
                <p>Analyzing transporter data...</p>
            </div>
        `;
        
        document.getElementById('vehicle-type-content').innerHTML = `
            <div class="loading-spinner-container">
                <div class="spinner"></div>
                <p>Analyzing vehicle type data...</p>
            </div>
        `;
        
        // Fetch transporter analysis data
        fetch(`/get_transporter_analysis/${encodeURIComponent(origin)}/${encodeURIComponent(destination)}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Server returned an error response');
                }
                return response.json();
            })
            .then(data => {
                // Reset button state
                setButtonLoading(applyTransporterFiltersBtn, false, 'Analyze');
                
                // Display top transporters
                const topTransportersContent = document.getElementById('top-transporters-content');
                if (data.top_transporters.length === 0) {
                    topTransportersContent.innerHTML = `
                        <p class="text-center text-muted">No transporter data available for this lane</p>
                    `;
                } else {
                    topTransportersContent.innerHTML = `
                        <table class="top-lanes-table">
                            <thead>
                                <tr>
                                    <th>Transporter</th>
                                    <th>Rating</th>
                                    <th>Category</th>
                                    <th>Total Trips</th>
                                    <th>Average Rate</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${data.top_transporters.map(transporter => `
                                    <tr>
                                        <td>${transporter.name}</td>
                                        <td>${transporter.rating === null ? 'Not Rated' : transporter.rating.toFixed(1)}</td>
                                        <td>
                                            <span class="badge ${transporter.category.toLowerCase()}">${transporter.category}</span>
                                        </td>
                                        <td>${transporter.trips}</td>
                                        <td>${formatCurrency(transporter.avg_rate)}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    `;
                }
                
                // Display vehicle type analysis
                const vehicleTypeContent = document.getElementById('vehicle-type-content');
                if (data.vehicle_type_summary.length === 0) {
                    vehicleTypeContent.innerHTML = `
                        <p class="text-center text-muted">No vehicle type data available for this lane</p>
                    `;
                } else {
                    vehicleTypeContent.innerHTML = `
                        <table class="top-lanes-table">
                            <thead>
                                <tr>
                                    <th>Vehicle Type</th>
                                    <th>Total Transporters</th>
                                    <th>Total Trips</th>
                                    <th>Average Rating</th>
                                    <th>Average Rate</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${data.vehicle_type_summary.map(vt => `
                                    <tr>
                                        <td>${vt.vehicle_type}</td>
                                        <td>${vt.transporter_count}</td>
                                        <td>${vt.trips}</td>
                                        <td>${vt.avg_rating === null ? 'Not Rated' : vt.avg_rating.toFixed(1)}</td>
                                        <td>${formatCurrency(vt.avg_rate)}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    `;
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('An error occurred while analyzing transporter data. Please try again.');
                
                // Reset button state
                setButtonLoading(applyTransporterFiltersBtn, false, 'Analyze');
                
                // Show error message in content areas
                document.getElementById('top-transporters-content').innerHTML = `
                    <p class="text-center text-muted">Error loading transporter analysis</p>
                `;
                document.getElementById('vehicle-type-content').innerHTML = `
                    <p class="text-center text-muted">Error loading vehicle type analysis</p>
                `;
            });
    });

    // Transporter Analysis Functions
    function initTransporterAnalysis() {
        const applyFiltersBtn = document.getElementById('apply-transporter-filters');
        if (applyFiltersBtn) {
            applyFiltersBtn.addEventListener('click', updateTransporterAnalysis);
        }
    }

    function updateTransporterAnalysis() {
        const origin = document.getElementById('origin-select').value;
        const destination = document.getElementById('destination-select').value;
        
        // Fetch and update top rated transporters
        fetch(`/api/top-transporters?origin=${origin}&destination=${destination}`)
            .then(response => response.json())
            .then(data => {
                updateTopTransporters(data);
            })
            .catch(error => console.error('Error fetching top transporters:', error));
        
        // Fetch and update vehicle type analysis
        fetch(`/api/vehicle-analysis?origin=${origin}&destination=${destination}`)
            .then(response => response.json())
            .then(data => {
                updateVehicleAnalysis(data);
            })
            .catch(error => console.error('Error fetching vehicle analysis:', error));
    }

    function updateTopTransporters(data) {
        const container = document.getElementById('top-transporters-content');
        if (!container) return;
        
        // Clear previous content
        container.innerHTML = '';
        
        // Add new content based on data
        // This is a placeholder - update based on your data structure
        const content = data.map(transporter => `
            <div class="transporter-item">
                <strong>${transporter.name}</strong>
                <div>Rating: ${transporter.rating}</div>
                <div>Trips: ${transporter.trips}</div>
            </div>
        `).join('');
        
        container.innerHTML = content;
    }

    function updateVehicleAnalysis(data) {
        const container = document.getElementById('vehicle-analysis-content');
        if (!container) return;
        
        // Clear previous content
        container.innerHTML = '';
        
        // Add new content based on data
        // This is a placeholder - update based on your data structure
        const content = data.map(vehicle => `
            <div class="vehicle-item">
                <strong>${vehicle.type}</strong>
                <div>Count: ${vehicle.count}</div>
                <div>Percentage: ${vehicle.percentage}%</div>
            </div>
        `).join('');
        
        container.innerHTML = content;
    }

    // Initialize transporter analysis when document is ready
    initTransporterAnalysis();
}); 