(function () {
  function initialize() {
    document.querySelectorAll('[data-patent-feed]').forEach(function (feed) {
      var roleButtons = Array.prototype.slice.call(feed.querySelectorAll('[data-patent-filter]'));
      var yearSelect = feed.querySelector('[data-patent-year]');
      var cards = Array.prototype.slice.call(feed.querySelectorAll('[data-patent-card]'));
      var status = feed.querySelector('[data-patent-status]');
      var empty = feed.querySelector('[data-patent-empty]');
      var role = 'all';

      function applyFilters() {
        var year = yearSelect ? yearSelect.value : 'all';
        var visible = 0;
        cards.forEach(function (card) {
          var roleMatches = role === 'all' || card.dataset.ownerRole === role;
          var yearMatches = year === 'all' || card.dataset.grantYear === year;
          card.hidden = !(roleMatches && yearMatches);
          if (roleMatches && yearMatches) visible += 1;
        });
        roleButtons.forEach(function (button) {
          button.setAttribute('aria-pressed', button.dataset.patentFilter === role ? 'true' : 'false');
        });
        if (status) status.textContent = '当前显示 ' + visible + ' 件专利 / Showing ' + visible + ' patents.';
        if (empty) empty.hidden = visible !== 0;
      }

      roleButtons.forEach(function (button) {
        button.addEventListener('click', function () {
          role = button.dataset.patentFilter || 'all';
          applyFilters();
        });
      });
      if (yearSelect) yearSelect.addEventListener('change', applyFilters);
      applyFilters();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize, { once: true });
  } else {
    initialize();
  }
})();
