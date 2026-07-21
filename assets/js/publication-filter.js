(function () {
  function ready(callback) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', callback, { once: true });
    } else {
      callback();
    }
  }

  ready(function () {
    var feed = document.querySelector('[data-publication-feed]');
    if (!feed) return;

    var buttons = Array.prototype.slice.call(feed.querySelectorAll('[data-publication-filter]'));
    var cards = Array.prototype.slice.call(feed.querySelectorAll('[data-publication-card]'));
    var status = feed.querySelector('[data-publication-status]');
    var empty = feed.querySelector('[data-publication-empty]');
    var allowed = ['all', 'article', 'conference'];
    if (!buttons.length || !cards.length) return;

    function normalize(type) {
      return allowed.indexOf(type) === -1 ? 'all' : type;
    }

    function message(type, count) {
      if (type === 'article') return 'Showing ' + count + ' articles.';
      if (type === 'conference') return 'Showing ' + count + ' conference papers.';
      return 'Showing all ' + count + ' publications.';
    }

    function setUrl(type, replace) {
      if (!window.history || !window.history.pushState) return;
      var url = new URL(window.location.href);
      if (type === 'all') {
        url.searchParams.delete('type');
      } else {
        url.searchParams.set('type', type);
      }
      window.history[replace ? 'replaceState' : 'pushState']({ publicationType: type }, '', url);
    }

    function applyFilter(type, updateUrl, replaceUrl) {
      type = normalize(type);
      var visible = 0;
      cards.forEach(function (card) {
        var show = type === 'all' || card.dataset.publicationType === type;
        card.hidden = !show;
        if (show) visible += 1;
      });
      buttons.forEach(function (button) {
        button.setAttribute('aria-pressed', button.dataset.publicationFilter === type ? 'true' : 'false');
      });
      if (status) status.textContent = message(type, visible);
      if (empty) empty.hidden = visible !== 0;
      if (updateUrl) setUrl(type, replaceUrl);
    }

    buttons.forEach(function (button) {
      button.addEventListener('click', function () {
        applyFilter(button.dataset.publicationFilter, true, false);
      });
    });

    window.addEventListener('popstate', function () {
      applyFilter(new URLSearchParams(window.location.search).get('type') || 'all', false, false);
    });

    var initial = normalize(new URLSearchParams(window.location.search).get('type') || 'all');
    applyFilter(initial, initial === 'all' ? window.location.search.indexOf('type=') !== -1 : false, true);
  });
})();
