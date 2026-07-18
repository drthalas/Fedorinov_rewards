from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Ale296ClipboardConsumeOnceTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_shared_helper_uses_sha256_and_session_storage_without_clipboard_writes(self) -> None:
        script = self.read("backend/app/static/clipboard_paste.js")
        self.assertIn('window.crypto.subtle.digest("SHA-256"', script)
        self.assertIn('"fedorinov-clipboard-image-pending-v1"', script)
        self.assertIn('"fedorinov-clipboard-image-consumed-v1"', script)
        self.assertIn("window.sessionStorage.setItem", script)
        self.assertNotIn("navigator.clipboard.write", script)
        self.assertNotIn("base64", script.lower())

    def test_pending_is_promoted_only_by_exact_upload_success_marker(self) -> None:
        script_path = ROOT / "backend" / "app" / "static" / "clipboard_paste.js"
        runner = r'''
const fs = require("fs");
const { webcrypto } = require("crypto");
const source = fs.readFileSync(process.argv[2], "utf8");
const values = new Map();
let domReady = null;
global.window = global;
global.crypto = webcrypto;
global.location = { href: "http://127.0.0.1/persons/1/edit", pathname: "/persons/1/edit", search: "" };
global.sessionStorage = {
  getItem(key) { return values.has(key) ? values.get(key) : null; },
  setItem(key, value) { values.set(key, String(value)); },
  removeItem(key) { values.delete(key); },
};
global.document = {
  addEventListener(type, callback) { if (type === "DOMContentLoaded") domReady = callback; },
  querySelectorAll() { return []; },
};
global.URL = URL;
global.URLSearchParams = URLSearchParams;
global.Blob = Blob;
eval(source);

async function fingerprint(text) {
  const blob = new Blob([text], { type: "image/png" });
  const digest = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  return Array.from(new Uint8Array(digest)).map((value) => value.toString(16).padStart(2, "0")).join("");
}

(async () => {
  const api = FedorinovClipboardImages;
  const a = { fingerprint: await fingerprint("image-a") };
  api.rememberPending(a, ["status=photo_updated"]);
  location.href = "http://127.0.0.1/persons/1/edit?status=validation_failed";
  domReady();
  const failedConsumed = api.isConsumed(a);

  api.rememberPending(a, ["status=photo_updated"]);
  location.href = "http://127.0.0.1/persons/1/edit?status=photo_updated";
  domReady();
  const successConsumed = api.isConsumed(a);

  const b = { fingerprint: await fingerprint("image-b") };
  process.stdout.write(JSON.stringify({ failedConsumed, successConsumed, newImageConsumed: api.isConsumed(b) }));
})().catch((error) => { console.error(error); process.exit(1); });
'''
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "ale296_consume_runner.js"
            runner_path.write_text(runner, encoding="utf-8")
            completed = subprocess.run(
                ["node", str(runner_path), str(script_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        self.assertEqual(
            json.loads(completed.stdout),
            {"failedConsumed": False, "successConsumed": True, "newImageConsumed": False},
        )

    def test_inline_photo_upload_consumes_only_redirected_photo_success(self) -> None:
        script = self.read("backend/app/static/clipboard_paste.js")
        upload = script.split("async function uploadClipboardImage", 1)[1].split(
            "function openPersonFilePicker", 1
        )[0]
        self.assertIn('rememberPendingClipboardImage(image, ["status=photo_updated", "media_cleanup=failed"])', upload)
        self.assertIn("response.redirected", upload)
        self.assertIn("consumePendingClipboardImage(image.fingerprint)", upload)
        self.assertGreaterEqual(upload.count("clearPendingClipboardImage(image.fingerprint)"), 3)

    def test_person_reward_mark_and_rank_use_the_shared_consume_once_helper(self) -> None:
        photo_template = self.read("backend/app/templates/photo_management.html")
        clipboard = self.read("backend/app/static/clipboard_paste.js")
        rank = self.read("backend/app/static/guide_image_preview.js")
        for marker in ("data-person-photo-trigger", "data-reward-photo-trigger", "data-mark-photo-trigger"):
            self.assertIn(marker, photo_template)
        self.assertIn('document.querySelectorAll("[data-photo-plus-trigger]").forEach(bindInlinePhotoTrigger)', clipboard)
        self.assertIn("freshImageBlobFromClipboardWithTimeout", clipboard)
        self.assertIn("helper.rememberPending(clipboardImage", rank)
        self.assertIn('"status=rank_updated"', rank)
        self.assertIn("helper.clearPending()", rank)


if __name__ == "__main__":
    unittest.main()
