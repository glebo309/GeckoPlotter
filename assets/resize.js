document.addEventListener('DOMContentLoaded', () => {
  function setupResize() {
    const handle = document.getElementById('resize-handle');
    const plot = document.querySelector('.resizable-plot-container');
    const table = document.querySelector('.resizable-table-container');

    if (!handle || !plot || !table) {
      console.log('Resize elements missing, retrying...');
      setTimeout(setupResize, 200);
      return;
    }

    handle.onmousedown = null;
    window.onmousemove = null;
    window.onmouseup = null;

    handle.addEventListener('mousedown', (e) => {
          console.log('Resize drag started');

      e.preventDefault();
      let startY = e.clientY;
      let startPlotFlex = parseFloat(getComputedStyle(plot).flexGrow);
      let startTableFlex = parseFloat(getComputedStyle(table).flexGrow);

        function onMouseMove(e) {
        let deltaY = e.clientY - startY;
        let containerHeight = plot.parentElement.offsetHeight;
        let flexChange = (deltaY / containerHeight) * 2;

        let newPlotFlex = Math.max(1, startPlotFlex + flexChange);
        let newTableFlex = Math.max(0, startTableFlex - flexChange);

        plot.style.flex = newPlotFlex.toString();

        if (newTableFlex < 0.05) {
            table.style.display = 'none';  // hide when too small
        } else {
            table.style.display = 'flex';  // show normally
            table.style.flex = newTableFlex.toString();
        }
        }

      function onMouseUp(e) {
        window.removeEventListener('mousemove', onMouseMove);
        window.removeEventListener('mouseup', onMouseUp);
      }

      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('mouseup', onMouseUp);
    });

    console.log('Resize handlers set up.');
  }

  setupResize();
});
