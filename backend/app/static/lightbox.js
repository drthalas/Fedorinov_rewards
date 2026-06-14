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

  function lightboxGroup(link) {
    return link.getAttribute("data-lightbox-group") || "";
  }

  function collectLinks(group) {
    var seen = {};
    return Array.prototype.slice.call(document.querySelectorAll("a.photo-link, a.photo-clickable")).filter(function (link) {
      if (group && lightboxGroup(link) !== group) {
        return false;
      }
      var src = imageSource(link);
      if (!src) {
        return false;
      }
      var key = (group || "__all__") + "|" + src;
      if (seen[key]) {
        return false;
      }
      seen[key] = true;
      return true;
    });
  }

  function indexBySource(items, src) {
    for (var index = 0; index < items.length; index += 1) {
      if (imageSource(items[index]) === src) {
        return index;
      }
    }
    return -1;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var lightbox = document.getElementById("photo-lightbox");
    if (!lightbox) {
      return;
    }

    var image = lightbox.querySelector(".photo-lightbox-image");
    var viewport = lightbox.querySelector(".photo-lightbox-viewport");
    var caption = lightbox.querySelector(".photo-lightbox-caption");
    var previousButton = lightbox.querySelector("[data-lightbox-prev]");
    var nextButton = lightbox.querySelector("[data-lightbox-next]");
    var zoomInButton = lightbox.querySelector("[data-lightbox-zoom-in]");
    var zoomOutButton = lightbox.querySelector("[data-lightbox-zoom-out]");
    var resetButton = lightbox.querySelector("[data-lightbox-reset]");
    var currentGroup = "";
    var links = collectLinks(currentGroup);
    var currentIndex = -1;
    var scale = 1;
    var offsetX = 0;
    var offsetY = 0;
    var dragging = false;
    var dragStartX = 0;
    var dragStartY = 0;
    var dragOriginX = 0;
    var dragOriginY = 0;

    links.forEach(function (link) {
      link.classList.add("photo-clickable");
      link.setAttribute("aria-haspopup", "dialog");
      link.addEventListener("click", function (event) {
        var src = imageSource(link);
        if (!src) {
          return;
        }
        event.preventDefault();
        currentGroup = lightboxGroup(link);
        links = collectLinks(currentGroup);
        var index = indexBySource(links, src);
        open(index >= 0 ? index : 0);
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
      links = collectLinks(currentGroup);
      currentIndex = index;
      var link = links[currentIndex];
      if (!link) {
        return;
      }
      var src = imageSource(link);
      if (!src) {
        return;
      }
      resetTransform();
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
      resetTransform();
    }

    function step(delta) {
      if (!links.length) {
        return;
      }
      var nextIndex = (currentIndex + delta + links.length) % links.length;
      open(nextIndex);
    }

    function clamp(value, min, max) {
      return Math.max(min, Math.min(max, value));
    }

    function applyTransform() {
      scale = clamp(scale, 1, 5);
      if (scale === 1) {
        offsetX = 0;
        offsetY = 0;
      }
      image.style.transform = "translate(" + offsetX + "px, " + offsetY + "px) scale(" + scale + ")";
      image.classList.toggle("is-zoomed", scale > 1);
    }

    function resetTransform() {
      scale = 1;
      offsetX = 0;
      offsetY = 0;
      if (image) {
        applyTransform();
      }
    }

    function zoom(delta) {
      scale = clamp(scale + delta, 1, 5);
      applyTransform();
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
    if (zoomInButton) {
      zoomInButton.addEventListener("click", function () {
        zoom(0.25);
      });
    }
    if (zoomOutButton) {
      zoomOutButton.addEventListener("click", function () {
        zoom(-0.25);
      });
    }
    if (resetButton) {
      resetButton.addEventListener("click", resetTransform);
    }
    if (viewport) {
      viewport.addEventListener("wheel", function (event) {
        if (!lightbox.classList.contains("is-open")) {
          return;
        }
        event.preventDefault();
        zoom(event.deltaY < 0 ? 0.25 : -0.25);
      }, { passive: false });
      viewport.addEventListener("pointerdown", function (event) {
        if (scale <= 1) {
          return;
        }
        dragging = true;
        dragStartX = event.clientX;
        dragStartY = event.clientY;
        dragOriginX = offsetX;
        dragOriginY = offsetY;
        viewport.setPointerCapture(event.pointerId);
      });
      viewport.addEventListener("pointermove", function (event) {
        if (!dragging) {
          return;
        }
        offsetX = dragOriginX + event.clientX - dragStartX;
        offsetY = dragOriginY + event.clientY - dragStartY;
        applyTransform();
      });
      viewport.addEventListener("pointerup", function (event) {
        dragging = false;
        if (viewport.hasPointerCapture(event.pointerId)) {
          viewport.releasePointerCapture(event.pointerId);
        }
      });
      viewport.addEventListener("pointercancel", function () {
        dragging = false;
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
