import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).with_name("hardware-transcoding.py")
SPEC = importlib.util.spec_from_file_location("hardware_transcoding", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(module)


class HardwareTranscodingTests(unittest.TestCase):
    def test_enable_preserves_unrelated_configuration(self):
        current = {"EncoderPreset": "superfast", "EnableHardwareEncoding": False}
        updated = module.desired_encoding_config(
            current, "qsv", "/dev/dri/renderD129"
        )
        self.assertEqual(updated["EncoderPreset"], "superfast")
        self.assertEqual(updated["HardwareAccelerationType"], "qsv")
        self.assertTrue(updated["EnableHardwareEncoding"])
        self.assertEqual(updated["VaapiDevice"], "/dev/dri/renderD129")

    def test_disable_preserves_unrelated_configuration(self):
        current = {
            "EncoderPreset": "superfast",
            "HardwareAccelerationType": "vaapi",
            "EnableHardwareEncoding": True,
        }
        updated = module.desired_encoding_config(
            current, "none", "/dev/dri/renderD128"
        )
        self.assertEqual(updated["EncoderPreset"], "superfast")
        self.assertEqual(updated["HardwareAccelerationType"], "none")
        self.assertFalse(updated["EnableHardwareEncoding"])


if __name__ == "__main__":
    unittest.main()
