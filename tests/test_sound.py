import io
import os
import unittest
import wave
from unittest.mock import patch

from focus_tracker import sound


class TestChime(unittest.TestCase):
    def test_chime_is_a_short_valid_wav(self):
        with wave.open(io.BytesIO(sound.chime_wav())) as wav:
            self.assertEqual(wav.getnchannels(), 1)
            seconds = wav.getnframes() / wav.getframerate()
        self.assertTrue(0.5 < seconds < 1.5, seconds)

    def test_chime_does_not_clip(self):
        with wave.open(io.BytesIO(sound.chime_wav())) as wav:
            frames = wav.readframes(wav.getnframes())
        samples = memoryview(frames).cast("h")
        self.assertLess(max(abs(x) for x in samples), 32767)

    @patch.dict(os.environ, {"FOCUS_TRACKER_SOUND": "off"})
    def test_can_be_muted(self):
        with patch("subprocess.Popen") as popen, patch("sys.stdout") as stdout:
            sound.play_chime()
        popen.assert_not_called()
        stdout.write.assert_not_called()

    @patch.dict(os.environ, {"FOCUS_TRACKER_SOUND": ""})
    @patch("sys.platform", "darwin")
    def test_plays_with_system_player_for_chime_length(self):
        with patch("shutil.which", side_effect=lambda c: "/usr/bin/afplay" if c == "afplay" else None), \
             patch("subprocess.Popen") as popen, patch("time.sleep") as sleep:
            popen.return_value.poll.return_value = None  # still playing
            sound.play_chime()
        args = popen.call_args[0][0]
        self.assertEqual(args[0], "/usr/bin/afplay")
        with wave.open(args[1]) as wav:  # a real, reusable WAV file
            self.assertGreater(wav.getnframes(), 0)
        sleep.assert_called_once_with(sound.CHIME_SECONDS)

    @patch.dict(os.environ, {"FOCUS_TRACKER_SOUND": ""})
    @patch("sys.platform", "linux")
    def test_falls_back_to_bell_if_player_exits_with_error(self):
        with patch("shutil.which", return_value="/usr/bin/aplay"), \
             patch("subprocess.Popen") as popen, patch("time.sleep"), \
             patch("sys.stdout") as stdout:
            popen.return_value.poll.return_value = 1
            sound.play_chime()
        stdout.write.assert_called_with("\a")

    @patch.dict(os.environ, {"FOCUS_TRACKER_SOUND": ""})
    @patch("sys.platform", "linux")
    def test_falls_back_to_bell_without_player(self):
        with patch("shutil.which", return_value=None), patch("sys.stdout") as stdout:
            sound.play_chime()
        stdout.write.assert_called_with("\a")

    @patch.dict(os.environ, {"FOCUS_TRACKER_SOUND": ""})
    @patch("sys.platform", "linux")
    def test_falls_back_to_bell_if_player_fails(self):
        with patch("shutil.which", return_value="/usr/bin/aplay"), \
             patch("subprocess.Popen", side_effect=OSError), patch("sys.stdout") as stdout:
            sound.play_chime()
        stdout.write.assert_called_with("\a")


if __name__ == "__main__":
    unittest.main()
