(function (root) {
  "use strict";

  function createPhotoPlusFlow() {
    var states = new WeakMap();

    return Object.freeze({
      mode: function (control) {
        return states.get(control) || "clipboard-first";
      },
      shouldOpenFilePicker: function (control) {
        return states.get(control) === "file-next";
      },
      markClipboardSuccess: function (control) {
        states.set(control, "file-next");
      },
      reset: function (control) {
        states.delete(control);
      }
    });
  }

  root.FedorinovPhotoPlusFlow = createPhotoPlusFlow();
})(window);
