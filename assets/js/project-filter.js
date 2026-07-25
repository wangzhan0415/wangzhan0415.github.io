(function () {
  function initialize() {
    document.querySelectorAll('[data-project-feed]').forEach(function (feed) {
      var buttons = Array.prototype.slice.call(feed.querySelectorAll('[data-project-filter]'));
      var cards = Array.prototype.slice.call(feed.querySelectorAll('[data-project-card]'));
      var empty = feed.querySelector('[data-project-empty]');
      var statusText = feed.querySelector('[data-project-status-text]');
      var allowed = ['all', 'in-progress', 'completed'];
      if (!buttons.length || !cards.length) return;

      function message(filter, count) {
        if (filter === 'in-progress') return 'Showing ' + count + ' in-progress projects.';
        if (filter === 'completed') return 'Showing ' + count + ' completed projects.';
        return 'Showing all ' + count + ' projects.';
      }

      function applyFilter(filter) {
        if (allowed.indexOf(filter) === -1) filter = 'all';
        var visible = 0;
        cards.forEach(function (card) {
          var show = filter === 'all' || card.dataset.projectStatus === filter;
          card.hidden = !show;
          if (show) visible += 1;
        });
        buttons.forEach(function (button) {
          button.setAttribute('aria-pressed', button.dataset.projectFilter === filter ? 'true' : 'false');
        });
        if (statusText) statusText.textContent = message(filter, visible);
        if (empty) empty.hidden = visible !== 0;
      }

      buttons.forEach(function (button) {
        button.addEventListener('click', function () { applyFilter(button.dataset.projectFilter); });
      });
      applyFilter('all');
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize, { once: true });
  } else {
    initialize();
  }
})();
