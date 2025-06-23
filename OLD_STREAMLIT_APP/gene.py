<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Interactive Plasmid Map Visualizer</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        .header {
            text-align: center;
            margin-bottom: 30px;
            color: white;
        }

        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }

        .main-content {
            display: grid;
            grid-template-columns: 1fr 350px;
            gap: 30px;
            align-items: start;
        }

        .map-container {
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            position: relative;
        }

        .info-panel {
            background: white;
            border-radius: 20px;
            padding: 25px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            height: fit-content;
            max-height: 700px;
            overflow-y: auto;
        }

        .info-panel h3 {
            color: #667eea;
            margin-bottom: 15px;
            font-size: 1.3rem;
        }

        .file-upload {
            margin-bottom: 20px;
            text-align: center;
        }

        .upload-area {
            border: 3px dashed #667eea;
            border-radius: 15px;
            padding: 40px 20px;
            background: rgba(102, 126, 234, 0.05);
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .upload-area:hover {
            background: rgba(102, 126, 234, 0.1);
            border-color: #764ba2;
        }

        .upload-area.dragover {
            background: rgba(102, 126, 234, 0.15);
            border-color: #764ba2;
        }

        input[type="file"] {
            display: none;
        }

        .upload-text {
            color: #667eea;
            font-size: 1.1rem;
            font-weight: 500;
        }

        .plasmid-stats {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
        }

        .stat-item {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            font-size: 0.95rem;
        }

        .stat-label {
            font-weight: 600;
            color: #555;
        }

        .stat-value {
            color: #667eea;
            font-weight: 500;
        }

        .features-list {
            max-height: 300px;
            overflow-y: auto;
        }

        .feature-item {
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
            border-left: 4px solid;
        }

        .feature-item:hover {
            background: #f0f0f0;
            transform: translateX(3px);
        }

        .feature-item.selected {
            background: rgba(102, 126, 234, 0.1);
            border-left-color: #667eea;
        }

        .feature-name {
            font-weight: 600;
            color: #333;
            margin-bottom: 4px;
        }

        .feature-details {
            font-size: 0.85rem;
            color: #666;
        }

        .feature-position {
            font-family: 'Courier New', monospace;
            background: rgba(0,0,0,0.05);
            padding: 2px 6px;
            border-radius: 4px;
            margin-left: 8px;
        }

        #plasmidMap {
            display: block;
            margin: 0 auto;
        }

        .tooltip {
            position: absolute;
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 0.85rem;
            pointer-events: none;
            z-index: 1000;
            opacity: 0;
            transition: opacity 0.2s ease;
        }

        .controls {
            display: flex;
            justify-content: center;
            gap: 15px;
            margin-bottom: 20px;
        }

        .control-btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 25px;
            cursor: pointer;
            font-weight: 500;
            transition: all 0.2s ease;
        }

        .control-btn:hover {
            background: #764ba2;
            transform: translateY(-2px);
        }

        .sequence-display {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 15px;
            margin-top: 20px;
            font-family: 'Courier New', monospace;
            font-size: 0.8rem;
            line-height: 1.4;
            max-height: 200px;
            overflow-y: auto;
            word-break: break-all;
        }

        @media (max-width: 1024px) {
            .main-content {
                grid-template-columns: 1fr;
            }
            
            .header h1 {
                font-size: 2rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🧬 Interactive Plasmid Map Visualizer</h1>
            <p>Upload your .dna file to visualize vector maps with features, annotations, and sequence details</p>
        </div>

        <div class="main-content">
            <div class="map-container">
                <div class="file-upload">
                    <div class="upload-area" id="uploadArea">
                        <div class="upload-text">
                            📁 Drop your .dna file here or click to browse
                        </div>
                        <input type="file" id="fileInput" accept=".dna">
                    </div>
                </div>

                <div class="controls">
                    <button class="control-btn" onclick="zoomIn()">🔍 Zoom In</button>
                    <button class="control-btn" onclick="zoomOut()">🔍 Zoom Out</button>
                    <button class="control-btn" onclick="resetView()">↻ Reset View</button>
                </div>

                <svg id="plasmidMap" width="600" height="600"></svg>
            </div>

            <div class="info-panel">
                <h3>📊 Plasmid Information</h3>
                <div class="plasmid-stats" id="plasmidStats">
                    <div class="stat-item">
                        <span class="stat-label">Length:</span>
                        <span class="stat-value" id="sequenceLength">-</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">GC Content:</span>
                        <span class="stat-value" id="gcContent">-</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Features:</span>
                        <span class="stat-value" id="featureCount">-</span>
                    </div>
                </div>

                <h3>🏷️ Features</h3>
                <div class="features-list" id="featuresList">
                    <p style="color: #999; text-align: center; margin: 40px 0;">Upload a plasmid file to see features</p>
                </div>

                <h3>🧬 Sequence Preview</h3>
                <div class="sequence-display" id="sequenceDisplay">
                    Upload a file to view sequence...
                </div>
            </div>
        </div>
    </div>

    <div class="tooltip" id="tooltip"></div>

    <script>
        let currentData = null;
        let currentScale = 1;
        let selectedFeature = null;

        // File upload handling
        const fileInput = document.getElementById('fileInput');
        const uploadArea = document.getElementById('uploadArea');

        uploadArea.addEventListener('click', () => fileInput.click());
        uploadArea.addEventListener('dragover', handleDragOver);
        uploadArea.addEventListener('drop', handleDrop);
        uploadArea.addEventListener('dragleave', handleDragLeave);
        fileInput.addEventListener('change', handleFileSelect);

        function handleDragOver(e) {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        }

        function handleDragLeave(e) {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
        }

        function handleDrop(e) {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                processFile(files[0]);
            }
        }

        function handleFileSelect(e) {
            if (e.target.files.length > 0) {
                processFile(e.target.files[0]);
            }
        }

        function processFile(file) {
            const reader = new FileReader();
            reader.onload = function(e) {
                try {
                    const content = e.target.result;
                    currentData = parseSnapGeneFile(content);
                    updateUI();
                    renderPlasmidMap();
                } catch (error) {
                    alert('Error parsing file: ' + error.message);
                }
            };
            reader.readAsText(file);
        }

        function parseSnapGeneFile(content) {
            // Extract DNA sequence (between SnapGene header and features)
            const sequenceMatch = content.match(/SnapGene[^A-Z]*([ATCG]+)/i);
            const sequence = sequenceMatch ? sequenceMatch[1].toUpperCase() : '';

            // Extract features from XML
            const features = [];
            const featureRegex = /<Feature[^>]*name="([^"]*)"[^>]*>(.*?)<\/Feature>/gs;
            let match;

            while ((match = featureRegex.exec(content)) !== null) {
                const name = match[1];
                const featureContent = match[2];
                
                // Extract range
                const rangeMatch = featureContent.match(/range="(\d+)-(\d+)"/);
                if (rangeMatch) {
                    const start = parseInt(rangeMatch[1]);
                    const end = parseInt(rangeMatch[2]);
                    
                    // Extract color
                    const colorMatch = featureContent.match(/color="([^"]*)"/);
                    const color = colorMatch ? colorMatch[1] : '#cccccc';
                    
                    // Extract type
                    const typeMatch = content.match(new RegExp(`name="${name}"[^>]*type="([^"]*)"`, 'i'));
                    const type = typeMatch ? typeMatch[1] : 'unknown';

                    // Extract directionality
                    const dirMatch = content.match(new RegExp(`name="${name}"[^>]*directionality="([^"]*)"`, 'i'));
                    const direction = dirMatch ? (dirMatch[1] === '1' ? 'forward' : 'reverse') : 'none';

                    features.push({
                        name,
                        start,
                        end,
                        color,
                        type,
                        direction,
                        length: end - start + 1
                    });
                }
            }

            return {
                sequence,
                features,
                length: sequence.length
            };
        }

        function updateUI() {
            if (!currentData) return;

            // Update stats
            document.getElementById('sequenceLength').textContent = `${currentData.length.toLocaleString()} bp`;
            
            const gcCount = currentData.sequence.split('').filter(base => base === 'G' || base === 'C').length;
            const gcContent = currentData.length > 0 ? (gcCount / currentData.length * 100).toFixed(1) : 0;
            document.getElementById('gcContent').textContent = `${gcContent}%`;
            document.getElementById('featureCount').textContent = currentData.features.length;

            // Update features list
            const featuresList = document.getElementById('featuresList');
            featuresList.innerHTML = '';
            
            currentData.features.forEach((feature, index) => {
                const featureDiv = document.createElement('div');
                featureDiv.className = 'feature-item';
                featureDiv.style.borderLeftColor = feature.color;
                featureDiv.onclick = () => selectFeature(index);
                
                featureDiv.innerHTML = `
                    <div class="feature-name">${feature.name}</div>
                    <div class="feature-details">
                        ${feature.type} • ${feature.direction}
                        <span class="feature-position">${feature.start}-${feature.end}</span>
                    </div>
                `;
                
                featuresList.appendChild(featureDiv);
            });

            // Update sequence display
            const sequenceDisplay = document.getElementById('sequenceDisplay');
            const displaySequence = currentData.sequence.substring(0, 500);
            sequenceDisplay.textContent = displaySequence + (currentData.sequence.length > 500 ? '...' : '');
        }

        function selectFeature(index) {
            selectedFeature = index;
            
            // Update UI selection
            document.querySelectorAll('.feature-item').forEach((item, i) => {
                item.classList.toggle('selected', i === index);
            });
            
            // Highlight feature on map
            renderPlasmidMap();
        }

        function renderPlasmidMap() {
            if (!currentData || currentData.length === 0) return;

            const svg = d3.select('#plasmidMap');
            svg.selectAll('*').remove();

            const width = 600;
            const height = 600;
            const centerX = width / 2;
            const centerY = height / 2;
            const outerRadius = 200;
            const innerRadius = 160;

            // Main plasmid circle
            svg.append('circle')
                .attr('cx', centerX)
                .attr('cy', centerY)
                .attr('r', outerRadius)
                .attr('fill', 'none')
                .attr('stroke', '#ddd')
                .attr('stroke-width', 2);

            svg.append('circle')
                .attr('cx', centerX)
                .attr('cy', centerY)
                .attr('r', innerRadius)
                .attr('fill', 'none')
                .attr('stroke', '#eee')
                .attr('stroke-width', 1);

            // Add features
            currentData.features.forEach((feature, index) => {
                const startAngle = (feature.start / currentData.length) * 2 * Math.PI - Math.PI / 2;
                const endAngle = (feature.end / currentData.length) * 2 * Math.PI - Math.PI / 2;
                
                const isSelected = selectedFeature === index;
                const radius = isSelected ? outerRadius + 10 : outerRadius;
                const strokeWidth = isSelected ? 8 : 5;

                // Create arc path
                const arc = d3.arc()
                    .innerRadius(innerRadius)
                    .outerRadius(radius)
                    .startAngle(startAngle)
                    .endAngle(endAngle);

                svg.append('path')
                    .attr('d', arc)
                    .attr('transform', `translate(${centerX}, ${centerY})`)
                    .attr('fill', feature.color)
                    .attr('stroke', isSelected ? '#333' : 'white')
                    .attr('stroke-width', strokeWidth)
                    .attr('opacity', isSelected ? 1 : 0.8)
                    .style('cursor', 'pointer')
                    .on('mouseover', function(event) {
                        showTooltip(event, feature);
                        d3.select(this).attr('opacity', 1);
                    })
                    .on('mouseout', function() {
                        hideTooltip();
                        d3.select(this).attr('opacity', isSelected ? 1 : 0.8);
                    })
                    .on('click', () => selectFeature(index));

                // Add feature labels for major features
                if (feature.length > currentData.length * 0.05) {
                    const midAngle = (startAngle + endAngle) / 2;
                    const labelRadius = outerRadius + 25;
                    const labelX = centerX + Math.cos(midAngle) * labelRadius;
                    const labelY = centerY + Math.sin(midAngle) * labelRadius;

                    svg.append('text')
                        .attr('x', labelX)
                        .attr('y', labelY)
                        .attr('text-anchor', 'middle')
                        .attr('dominant-baseline', 'middle')
                        .attr('font-size', '11px')
                        .attr('font-weight', 'bold')
                        .attr('fill', '#333')
                        .text(feature.name);
                }
            });

            // Add size markers
            const markerPositions = [0, 0.25, 0.5, 0.75];
            markerPositions.forEach(pos => {
                const angle = pos * 2 * Math.PI - Math.PI / 2;
                const x1 = centerX + Math.cos(angle) * (innerRadius - 5);
                const y1 = centerY + Math.sin(angle) * (innerRadius - 5);
                const x2 = centerX + Math.cos(angle) * (innerRadius + 5);
                const y2 = centerY + Math.sin(angle) * (innerRadius + 5);

                svg.append('line')
                    .attr('x1', x1)
                    .attr('y1', y1)
                    .attr('x2', x2)
                    .attr('y2', y2)
                    .attr('stroke', '#666')
                    .attr('stroke-width', 2);

                // Add position labels
                const labelX = centerX + Math.cos(angle) * (innerRadius - 20);
                const labelY = centerY + Math.sin(angle) * (innerRadius - 20);
                const position = Math.round(pos * currentData.length);

                svg.append('text')
                    .attr('x', labelX)
                    .attr('y', labelY)
                    .attr('text-anchor', 'middle')
                    .attr('dominant-baseline', 'middle')
                    .attr('font-size', '10px')
                    .attr('fill', '#666')
                    .text(position);
            });

            // Center label
            svg.append('text')
                .attr('x', centerX)
                .attr('y', centerY - 5)
                .attr('text-anchor', 'middle')
                .attr('font-size', '14px')
                .attr('font-weight', 'bold')
                .attr('fill', '#333')
                .text('Plasmid Map');

            svg.append('text')
                .attr('x', centerX)
                .attr('y', centerY + 15)
                .attr('text-anchor', 'middle')
                .attr('font-size', '12px')
                .attr('fill', '#666')
                .text(`${currentData.length} bp`);
        }

        function showTooltip(event, feature) {
            const tooltip = document.getElementById('tooltip');
            tooltip.innerHTML = `
                <strong>${feature.name}</strong><br>
                Type: ${feature.type}<br>
                Position: ${feature.start}-${feature.end}<br>
                Length: ${feature.length} bp<br>
                Direction: ${feature.direction}
            `;
            tooltip.style.left = (event.pageX + 10) + 'px';
            tooltip.style.top = (event.pageY - 10) + 'px';
            tooltip.style.opacity = '1';
        }

        function hideTooltip() {
            document.getElementById('tooltip').style.opacity = '0';
        }

        function zoomIn() {
            currentScale *= 1.2;
            d3.select('#plasmidMap').transition().attr('transform', `scale(${currentScale})`);
        }

        function zoomOut() {
            currentScale /= 1.2;
            d3.select('#plasmidMap').transition().attr('transform', `scale(${currentScale})`);
        }

        function resetView() {
            currentScale = 1;
            d3.select('#plasmidMap').transition().attr('transform', 'scale(1)');
        }

        // Load sample data on page load if available
        window.addEventListener('load', () => {
            // Try to parse the provided sample data
            const sampleData = `SnapGene±GATCTCGATCCCGCGAAATTAATACGACTCACTATAGGGAGACCACAACGGTTTCCCTCTAGAAATAATTTTGTTTAACTTTAAGAAGGAGATATACATATGCGGGGTTCTCATCATCATCATCATCATGGTATGGCTAGCATGACTGGTGGACAGCAAATGGGTCGGGATGAGAACCTATATTTCCAGGGGGATCCGAGCTCGATGAGTAACAAGTATAGAGTTAGAAAAAACGTATTACATCTTACCGACACGGAAAAAAGAGATTTTGTTCGTACCGTGCTAATACTAAAGGAAAAAGGGATATATGACCGCTATATAGCCTGGCATGGTGCAGCAGGTAAATTTCATACTCCTCCGGGCAGCGATCGAAATGCAGCAGGTATGAGTTCTGCTTTTTTACCGTGGCATCGTGAATACCTTTTACGATTCGAACGTGACCTTCAGTCAATCAATCCAGAAGTAACCCTTCCTTATTGGGAATGGGAAACGGACGCACAGATGCAGGATCCCTCACAATCACAAATTTGGAGTGCAGATTTTATGGGAGGAAACGGAAATCCCATAAAAGATTTTATCGTCGATACCGGGCCATTTGCAGCTGGGCGCTGGACGACGATCGATGAACAAGGAAATCCTTCCGGAGGGCTAAAACGTAATTTTGGAGCAACGAAAGAGGCACCTACACTCCCTACTCGAGATGATGTCCTCAATGCTTTAAAAATAACTCAGTATGATACGCCGCCTTGGGATATGACCAGCCAAAACAGCTTTCGTAATCAGCTTGAAGGATTTATTAACGGGCCACAGCTTCACAATCGCGTACACCGTTGGGTTGGCGGACAGATGGGCGTTGTGCCTACTGCTCCGAATGATCCTGTCTTCTTTTTACACCACGCAAATGTGGATCGTATTTGGGCTGTATGGCAAATTATTCATCGTAATCAAAACTATCAGCCGATGAAAAACGGGCCATTTGGTCAAAACTTTAGAGATCCGATGTACCCTTGGAATACAACCCCTGAAGACGTTATGAACCATCGAAAGCTTGGGTACGTATACGATATAGAATTAAGAAAATCAAAACGTTCCTCATAAGAATTCGAAGCTTGATCCGGCTGCTAACAAAGCCCGAAAGGAAGCTGAGTTGGCTGCTGCCACCGCTGAGCAATAACTAGCATAACCCCTTGGGGCCTCTAAACGGGTCTTGAGGGGTTTTTTGCTGAAAGGAGGAACTATATCCGGATCTGGCGTAATAGCGAAGAGGCCCGCACCGATCGCCCTTCCCAACAGTTGCGCAGCCTGAATGGCGAATGGGACGCGCCCTGTAGCGGCGCATTAAGCGCGGCGGGTGTGGTGGTTACGCGCAGCGTGACCGCTACACTTGCCAGCGCCCTAGCGCCCGCTCCTTTCGCTTTCTTCCCTTCCTTTCTCGCCACGTTCGCCGGCTTTCCCCGTCAAGCTCTAAATCGGGGGCTCCCTTTAGGGTTCCGATTTAGTGCTTTACGGCACCTCGACCCCAAAAAACTTGATTAGGGTGATGGTTCACGTAGTGGGCCATCGCCCTGATAGACGGTTTTTCGCCCTTTGACGTTGGAGTCCACGTTCTTTAATAGTGGACTCTTGTTCCAAACTGGAACAACACTCAACCCTATCTCGGTCTATTCTTTTGATTTATAAGGGATTTTGCCGATTTCGGCCTATTGGTTAAAAAATGAGCTGATTTAACAAAAATTTAACGCGAATTTTAACAAAATATTAACGCTTACAATTTAGGTGGCACTTTTCGGGGAAATGTGCGCGGAACCCCTATTTGTTTATTTTTCTAAATACATTCAAATATGTATCCGCTCATGAGACAATAACCCTGATAAATGCTTCAATAATATTGAAAAAGGAAGAGTATGAGTATTCAACATTTCCGTGTCGCCCTTATTCCCTTTTTTGCGGCATTTTGCCTTCCTGTTTTTGCTCACCCAGAAACGCTGGTGAAAGTAAAAGATGCTGAAGATCAGTTGGGTGCACGAGTGGGTTACATCGAACTGGATCTCAACAGCGGTAAGATCCTTGAGAGTTTTCGCCCCGAAGAACGTTTTCCAATGATGAGCACTTTTAAAGTTCTGCTATGTGGCGCGGTATTATCCCGTATTGACGCCGGGCAAGAGCAACTCGGTCGCCGCATACACTATTCTCAGAATGACTTGGTTGAGTACTCACCAGTCACAGAAAAGCATCTTACGGATGGCATGACAGTAAGAGAATTATGCAGTGCTGCCATAACCATGAGTGATAACACTGCGGCCAACTTACTTCTGACAACGATCGGAGGACCGAAGGAGCTAACCGCTTTTTTGCACAACATGGGGGATCATGTAACTCGCCTTGATCGTTGGGAACCGGAGCTGAATGAAGCCATACCAAACGACGAGCGTGACACCACGATGCCTGTAGCAATGGCAACAACGTTGCGCAAACTATTAACTGGCGAACTACTTACTCTAGCTTCCCGGCAACAATTAATAGACTGGATGGAGGCGGATAAAGTTGCAGGACCACTTCTGCGCTCGGCCCTTCCGGCTGGCTGGTTTATTGCTGATAAATCTGGAGCCGGTGAGCGTGGGTCTCGCGGTATCATTGCAGCACTGGGGCCAGATGGTAAGCCCTCCCGTATCGTAGTTATCTACACGACGGGGAGTCAGGCAACTATGGATGAACGAAATAGACAGATCGCTGAGATAGGTGCCTCACTGATTAAGCATTGGTAACTGTCAGACCAAGTTTACTCATATATACTTTAGATTGATTTAAAACTTCATTTTTAATTTAAAAGGATCTAGGTGAAGATCCTTTTTGATAATCTCATGACCAAAATCCCTTAACGTGAGTTTTCGTTCCACTGAGCGTCAGACCCCGTAGAAAAGATCAAAGGATCTTCTTGAGATCCTTTTTTTCTGCGCGTAATCTGCTGCTTGCAAACAAAAAAACCACCGCTACCAGCGGTGGTTTGTTTGCCGGATCAAGAGCTACCAACTCTTTTTCCGAAGGTAACTGGCTTCAGCAGAGCGCAGATACCAAATACTGTTCTTCTAGTGTAGCCGTAGTTAGGCCACCACTTCAAGAACTCTGTAGCACCGCCTACATACCTCGCTCTGCTAATCCTGTTACCAGTGGCTGCTGCCAGTGGCGATAAGTCGTGTCTTACCGGGTTGGACTCAAGACGATAGTTACCGGATAAGGCGCAGCGGTCGGGCTGAACGGGGGGTTCGTGCACACAGCCCAGCTTGGAGCGAACGACCTACACCGAACTGAGATACCTACAGCGTGAGCTATGAGAAAGCGCCACGCTTCCCGAAGGGAGAAAGGCGGACAGGTATCCGGTAAGCGGCAGGGTCGGAACAGGAGAGCGCACGAGGGAGCTTCCAGGGGGAAACGCCTGGTATCTTTATAGTCCTGTCGGGTTTCGCCACCTCTGACTTGAGCGTCGATTTTTGTGATGCTCGTCAGGGGGGCGGAGCCTATGGAAAAACGCCAGCAACGCGGCCTTTTTACGGTTCCTGGCCTTTTGCTGGCCTTTTGCTCACATGTTCTTTCCTGCGTTATCCCCTGATTCTGTGGATAACCGTATTACCGCCTTTGAGTGAGCTGATACCGCTCGCCGCAGCCGAACGACCGAGCGCAGCGAGTCAGTGAGCGAGGAAGCGGAAGAGCGCCCAATACGCAAACCGCCTCTCCCCGCGCGTTGGCCGATTCATTAATGCAG`;

            try {
                currentData = parseSnapGeneFile(sampleData);
                updateUI();
                renderPlasmidMap();
            } catch (e) {
                console.log('No sample data available');
            }
        });
    </script>
</body>
</html>