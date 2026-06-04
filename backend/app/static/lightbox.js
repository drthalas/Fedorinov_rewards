(function () {
  "use strict";

  function closestCaption(link) {
    var dataCaption = link.getAttribute("data-lightbox-caption");
    if (dataCaption) {
      return dataCaption;
    }
    var img = link.querySelector("img");
    if (img && img.getAttribute("alt")) {
      return img.getAttribute("alt");
    }
    var figure = link.closest("figure, .card, .photo-manage-card");
    if (figure) {
      var caption = figure.querySelector("figcaption, .photo-caption, p, .photo-manage-label");
      if (caption && caption.textContent) {
        return caption.textContent.trim();
      }
    }
    return "Фото";
  }

  function imageSource(link) {
    var explicit = link.getAttribute("data-lightbox-src");
    if (explicit) {
      return explicit;
    }
    var img = link.querySelector("img");
    if (img && img.getAttribute("src")) {
      return img.getAttribute("src");
    }
    return "";
  }

  function collectLinks() {
    return Array.prototype.slice.call(document.querySelectorAll("a.photo-link, a.photo-clickable")).filter(function (link) {
      return Boolean(imageSource(link));
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var lightbox = document.getElementById("photo-lightbox");
    if (!lightbox) {
      return;
    }

    var image = lightbox.querySelector(".photo-lightbox-image");
    var caption = lightbox.querySelector(".photo-lightbox-caption");
    var previousButton = lightbox.querySelector("[data-lightbox-prev]");
    var nextButton = lightbox.querySelector("[data-lightbox-next]");
    var links = collectLinks();
    var currentIndex = -1;

    links.forEach(function (link, index) {
      link.classList.add("photo-clickable");
      link.setAttribute("aria-haspopup", "dialog");
      link.addEventListener("click", function (event) {
        var src = imageSource(link);
        if (!src) {
          return;
        }
        event.preventDefault();
        open(index);
      });
    });

    function updateNavigation() {
      var hasMany = links.length > 1;
      if (previousButton) {
        previousButton.hidden = !hasMany;
      }
      if (nextButton) {
        nextButton.hidden = !hasMany;
      }
    }

    function open(index) {
      links = collectLinks();
      currentIndex = index;
      var link = links[currentIndex];
      if (!link) {
        return;
      }
      var src = imageSource(link);
      if (!src) {
        return;
      }
      image.setAttribute("src", src);
      image.setAttribute("alt", closestCaption(link));
      caption.textContent = closestCaption(link);
      lightbox.classList.add("is-open");
      lightbox.setAttribute("aria-hidden", "false");
      document.body.classList.add("photo-lightbox-open");
      updateNavigation();
      var closeButton = lightbox.querySelector("[data-lightbox-close]");
      if (closeButton) {
        closeButton.focus();
      }
    }

    function close() {
      lightbox.classList.remove("is-open");
      lightbox.setAttribute("aria-hidden", "true");
      document.body.classList.remove("photo-lightbox-open");
      image.setAttribute("src", "");
      currentIndex = -1;
    }

    function step(delta) {
      if (!links.length) {
        return;
      }
      var nextIndex = (currentIndex + delta + links.length) % links.length;
      open(nextIndex);
    }

    lightbox.addEventListener("click", function (event) {
      if (event.target && event.target.hasAttribute("data-lightbox-close")) {
        close();
      }
    });

    if (previousButton) {
      previousButton.addEventListener("click", function () {
        step(-1);
      });
    }
    if (nextButton) {
      nextButton.addEventListener("click", function () {
        step(1);
      });
    }

    document.addEventListener("keydown", function (event) {
      if (!lightbox.classList.contains("is-open")) {
        return;
      }
      if (event.key === "Escape") {
        close();
      } else if (event.key === "ArrowLeft") {
        step(-1);
      } else if (event.key === "ArrowRight") {
        step(1);
      }
    });
  });
})();
