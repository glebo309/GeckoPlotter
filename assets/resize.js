document.addEventListener('DOMContentLoaded', () => {
  function setHeightsByRatio(plot, table, ratio, handlePx) {
    const parent = plot.parentElement;
    const H = parent ? parent.offsetHeight : 0;
    if (!H) return;
    const handle = handlePx || 10;
    const plotH = Math.max(120, Math.round((H - handle) * ratio));
    const tableH = Math.max(100, (H - handle) - plotH);
    plot.style.flex = '0 0 auto';
    table.style.flex = '0 0 auto';
    plot.style.height = plotH + 'px';
    table.style.height = tableH + 'px';
  }

  function applySavedFlex(plot, table) {
    try {
      const ratio = parseFloat(localStorage.getItem('gpSplitRatio') || '');
      if (!isNaN(ratio) && ratio > 0 && ratio < 1) {
        setHeightsByRatio(plot, table, ratio, 10);
      }
    } catch (_) {}
  }

  function persistRatio(ratio) {
    try {
      localStorage.setItem('gpSplitRatio', String(ratio));
    } catch (_) {}
  }

  function setupResize() {
    const handle = document.getElementById('resize-handle');
    const plot = document.querySelector('.resizable-plot-container');
    const table = document.querySelector('.resizable-table-container');

    if (!handle || !plot || !table) {
      // Retry a few times until Dash finishes rendering
      setTimeout(setupResize, 250);
      return;
    }

    // Apply saved flex values so size persists across callbacks
    applySavedFlex(plot, table);

    // Remove previous handlers to avoid duplicates
    handle.onmousedown = null;
    window.removeEventListener('mousemove', window.__gpOnMouseMove || (()=>{}));
    window.removeEventListener('mouseup', window.__gpOnMouseUp || (()=>{}));

    function startDrag(clientY) {
      const startY = clientY;
      const parent = plot.parentElement;
      const H = parent ? parent.offsetHeight : 0;
      // Determine current ratio from current heights (fallback to 0.66)
      const startPlotH = parseFloat(getComputedStyle(plot).height) || Math.round(H * 0.66);
      const startTableH = parseFloat(getComputedStyle(table).height) || Math.max(100, H - startPlotH - 10);
      const startRatio = Math.max(0.1, Math.min(0.9, startPlotH / Math.max(1, (startPlotH + startTableH))));

      handle.classList.add('dragging');
      const prevCursor = document.body.style.cursor;
      document.body.style.cursor = 'ns-resize';
      const onSelectStart = (ev)=>ev.preventDefault();
      document.addEventListener('selectstart', onSelectStart);

      let rafId = null;
      let desiredRatio = startRatio;

      function scheduleApply() {
        if (rafId != null) return;
        rafId = requestAnimationFrame(() => {
          rafId = null;
          setHeightsByRatio(plot, table, desiredRatio, 10);
          window.__gpCurrentRatio = desiredRatio;
        });
      }

      function onMouseMove(ev) {
        const y = ev.touches ? ev.touches[0].clientY : ev.clientY;
        const deltaY = y - startY;
        const containerHeight = plot.parentElement.offsetHeight || 1;
        // Translate delta into ratio change
        let ratio = startRatio + (deltaY / Math.max(150, containerHeight));
        ratio = Math.max(0.2, Math.min(0.9, ratio)); // clamp
        // Quantize to reduce jitter (1% steps)
        ratio = Math.round(ratio * 100) / 100;
        desiredRatio = ratio;
        scheduleApply();
        // Debug
        // console.log('drag', {deltaY, newPlotFlex, newTableFlex});
      }

      function onMouseUp() {
        window.removeEventListener('mousemove', onMouseMove, true);
        window.removeEventListener('mouseup', onMouseUp, true);
        window.removeEventListener('touchmove', onMouseMove, {passive:false});
        window.removeEventListener('touchend', onMouseUp, true);
        handle.classList.remove('dragging');
        document.body.style.cursor = prevCursor || '';
        document.removeEventListener('selectstart', onSelectStart);
        if (rafId != null) {
          cancelAnimationFrame(rafId);
          rafId = null;
        }
        // Persist the result as ratio
        const ratio = typeof window.__gpCurrentRatio === 'number' ? window.__gpCurrentRatio : startRatio;
        persistRatio(ratio);
      }

      window.addEventListener('mousemove', onMouseMove, true);
      window.addEventListener('mouseup', onMouseUp, true);
      window.addEventListener('touchmove', onMouseMove, {passive:false});
      window.addEventListener('touchend', onMouseUp, true);
    }

    handle.addEventListener('mousedown', (e) => {
      e.preventDefault();
      startDrag(e.clientY);
    });

    handle.addEventListener('touchstart', (e) => {
      e.preventDefault();
      if (e.touches && e.touches.length) {
        startDrag(e.touches[0].clientY);
      }
    }, {passive:false});

    // Also re-apply saved flex values after Dash updates the DOM
    const observer = new MutationObserver(() => applySavedFlex(plot, table));
    observer.observe(document.getElementById('main-resizable-layout') || document.body, {
      childList: true,
      subtree: true
    });

    console.log('Resize handlers set up.');
  }

  setupResize();
});
