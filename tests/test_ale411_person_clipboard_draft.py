from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PersonClipboardDraftTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_confirmed_clipboard_redirect_keeps_the_photo_result_marker(self) -> None:
        script = self.read("backend/app/static/clipboard_paste.js")
        upload = script.split("async function uploadClipboardImage", 1)[1].split(
            "function openPersonFilePicker", 1
        )[0]

        self.assertIn("personDraft.captureForPhoto(button)", upload)
        self.assertIn(
            "window.location.href = responseUrl.pathname + responseUrl.search + responseUrl.hash",
            upload,
        )
        self.assertNotIn("window.location.href = returnUrl", upload)

    def test_photo_interaction_ignores_transient_result_query_keys(self) -> None:
        script = self.read("backend/app/static/clipboard_paste.js")
        normalizer = script.split("function normalizedPageSearch", 1)[1].split(
            "function rememberPhotoInteraction", 1
        )[0]

        for key in ("status", "message", "error", "created", "media_cleanup"):
            self.assertIn(f'"{key}"', normalizer)
        self.assertIn("params.delete(key)", normalizer)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_slow_image_preparation_does_not_trigger_picker_fallback(self) -> None:
        script_path = ROOT / "backend/app/static/clipboard_paste.js"
        runner = r'''
const fs = require("fs");
const { webcrypto } = require("crypto");
const source = fs.readFileSync(process.argv[2], "utf8");
const storage = new Map();
let clipboardBlob = new Blob(["fresh-image-a"], { type: "image/png" });

global.window = global;
global.location = {
  href: "http://127.0.0.1/persons/42/edit",
  pathname: "/persons/42/edit",
  search: "",
};
global.sessionStorage = {
  getItem(key) { return storage.has(key) ? storage.get(key) : null; },
  setItem(key, value) { storage.set(key, String(value)); },
  removeItem(key) { storage.delete(key); },
};
Object.defineProperty(global, "crypto", {
  value: {
    subtle: {
      async digest(algorithm, value) {
        await new Promise((resolve) => setTimeout(resolve, 80));
        return webcrypto.subtle.digest(algorithm, value);
      },
    },
  },
});
Object.defineProperty(global, "navigator", {
  value: {
    clipboard: {
      async read() {
        return [{
          types: ["image/png"],
          async getType() { return clipboardBlob; },
        }];
      },
    },
  },
});
window.createImageBitmap = async () => ({ width: 2, height: 2, close() {} });
global.document = {
  addEventListener() {},
  querySelector() { return null; },
  querySelectorAll() { return []; },
  createElement(name) {
    if (name !== "canvas") return {};
    return {
      width: 0,
      height: 0,
      getContext() {
        return { fillStyle: "", fillRect() {}, drawImage() {} };
      },
      toBlob(callback) {
        callback(new Blob(["jpeg-preview"], { type: "image/jpeg" }));
      },
    };
  },
};

eval(source);

(async () => {
  const api = window.FedorinovClipboardImages;
  const first = await api.readWithTimeout(20);
  api.rememberPending(first, ["status=photo_updated"]);
  api.consumePending(first.fingerprint);

  let consumedCode = "";
  try {
    await api.readWithTimeout(20);
  } catch (error) {
    consumedCode = error.code || "";
  }

  clipboardBlob = new Blob(["fresh-image-b"], { type: "image/png" });
  const second = await api.readWithTimeout(20);
  process.stdout.write(JSON.stringify({
    firstReady: Boolean(first.blob),
    consumedCode,
    secondIsFresh: second.fingerprint !== first.fingerprint,
  }));
})().catch((error) => { console.error(error); process.exit(1); });
'''
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "ale411_clipboard_runner.js"
            runner_path.write_text(runner, encoding="utf-8")
            completed = subprocess.run(
                ["node", str(runner_path), str(script_path)],
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertEqual(
            json.loads(completed.stdout),
            {
                "firstReady": True,
                "consumedCode": "clipboard-image-consumed",
                "secondIsFresh": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
